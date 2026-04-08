"""
Domain Analyst: runs pillar-specific deep analysis on extracted signals.

After the generic signal extractor pulls raw signals from VDR documents,
the domain analyst runs one focused analysis per pillar (e.g., SecurityCompliance,
TechnologyArchitecture). Each analysis:

  1. Receives all signals tagged to that pillar + relevant document excerpts
  2. Produces structured *findings* (interpreted analysis, not raw data)
  3. Each finding references its source signals and documents with evidence
  4. Generates pillar-specific questions for the target company

The output is stored at outputs/<company>/domain_findings.json and consumed
by the Deal Intel dashboard page.

Pillars are dynamic — read from the signal catalog, not hardcoded — so when
Quinn updates the catalog with new pillars, the domain analyst adapts.
"""

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from tools.json_utils import extract_json
from tools.scoring_config import compute_confidence_summary

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-20250514"
MAX_TOKENS = 4096
PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "domain_analysis.txt"


def _load_prompt_template() -> str:
    """Load the domain analysis prompt template from disk."""
    return PROMPT_PATH.read_text(encoding="utf-8")


def _signals_for_pillar(
    all_signals: list[dict],
    pillar_id: str,
) -> list[dict]:
    """
    Filter signals belonging to a specific pillar.

    Checks pillar_id first, falls back to lens_id for v1.1 compat.
    """
    matched = []
    for sig in all_signals:
        sig_pillar = sig.get("pillar_id") or sig.get("lens_id") or sig.get("lens") or ""
        if sig_pillar == pillar_id:
            matched.append(sig)
    return matched


def _excerpts_for_pillar(
    enriched_batches: Optional[dict[str, list[dict]]],
    pillar_signals: list[dict],
    doc_filepath_map: Optional[dict[str, str]] = None,
    max_chars: int = 30_000,
) -> str:
    """
    Gather document excerpts relevant to a pillar's signals.

    Supports two modes:
    1. enriched_batches provided: look up text_chunks from memory (legacy)
    2. doc_filepath_map provided: re-read only needed docs from disk (streaming)

    Args:
        enriched_batches: batch_id -> list of docs with text_chunks (or None)
        pillar_signals: signals for this pillar (each has source_doc)
        doc_filepath_map: filename -> filepath for on-demand reading (or None)
        max_chars: max total characters to include

    Returns:
        Formatted string of document excerpts with filenames as headers.
    """
    # Collect unique source filenames from signals
    source_files = set()
    for sig in pillar_signals:
        src = sig.get("source_doc", "")
        if src:
            source_files.add(src)

    if not source_files:
        return "(No source documents identified for this pillar)"

    excerpts: list[str] = []
    total_chars = 0

    if enriched_batches:
        # Mode 1: from enriched batches in memory
        for _batch_id, docs in enriched_batches.items():
            for doc in docs:
                fname = doc.get("filename", "")
                if fname not in source_files:
                    continue
                chunks = doc.get("text_chunks", [])
                if not chunks:
                    continue
                text = "\n".join(chunks)
                if total_chars + len(text) > max_chars:
                    remaining = max_chars - total_chars
                    if remaining > 500:
                        text = text[:remaining] + "\n[...truncated]"
                    else:
                        break
                excerpts.append(f"=== {fname} ===\n{text}")
                total_chars += len(text)
                if total_chars >= max_chars:
                    break

    elif doc_filepath_map:
        # Mode 2: re-read from disk (streaming — memory-safe)
        from tools.document_reader import extract_text

        for fname in source_files:
            filepath = doc_filepath_map.get(fname)
            if not filepath:
                continue
            try:
                chunks = extract_text(filepath)
                if not chunks:
                    continue
                # extract_text returns List[dict] with "text" key per chunk
                text = "\n".join(
                    c["text"] if isinstance(c, dict) else str(c)
                    for c in chunks
                )
                if total_chars + len(text) > max_chars:
                    remaining = max_chars - total_chars
                    if remaining > 500:
                        text = text[:remaining] + "\n[...truncated]"
                    else:
                        break
                excerpts.append(f"=== {fname} ===\n{text}")
                total_chars += len(text)
                if total_chars >= max_chars:
                    break
            except Exception as exc:
                logger.warning("Could not re-read %s for domain analysis: %s", fname, exc)

    if not excerpts:
        return "(Source documents referenced but text not available)"

    return "\n\n".join(excerpts)


def _run_single_domain(
    pillar_id: str,
    pillar_label: str,
    signals: list[dict],
    document_excerpts: str,
    company_name: str,
    sector: str,
    deal_type: str,
    client: Any,
    rate_limiter: Any = None,
) -> dict:
    """
    Run domain analysis for a single pillar via Claude API.

    Args:
        pillar_id: e.g. "SecurityCompliance"
        pillar_label: e.g. "Security and Compliance"
        signals: list of extracted signals for this pillar
        document_excerpts: relevant document text
        company_name: target company name
        sector: sector slug
        deal_type: deal type
        client: Anthropic client
        rate_limiter: optional RateLimiter instance

    Returns:
        Domain analysis result dict with findings, grade, questions.
    """
    template = _load_prompt_template()

    signals_block = json.dumps(signals, indent=2, default=str)

    prompt = (
        template
        .replace("{pillar_id}", pillar_id)
        .replace("{pillar_label}", pillar_label)
        .replace("{company_name}", company_name)
        .replace("{sector}", sector)
        .replace("{deal_type}", deal_type)
        .replace("{signal_count}", str(len(signals)))
        .replace("{signals_json}", signals_block)
        .replace("{document_excerpts}", document_excerpts)
    )

    tokens_used = 0
    try:
        if rate_limiter:
            waited = rate_limiter.wait_if_needed(next_estimated_tokens=10_000)
            if waited > 0.5:
                logger.info("  Domain %s: paused %.1fs for rate limit", pillar_id, waited)

        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
            timeout=300.0,
        )
        if not response.content:
            logger.error("Empty response from Claude API for domain %s", pillar_id)
            return {
                "pillar_id": pillar_id,
                "pillar_label": pillar_label,
                "grade": "UNKNOWN",
                "confidence": 0.0,
                "documents_analyzed": 0,
                "findings": [],
                "blind_spots": [],
                "questions_for_target": [],
                "domain_summary": f"Domain analysis failed for {pillar_label}.",
                "_tokens_used": tokens_used,
                "_error": True,
            }
        raw = response.content[0].text

        if hasattr(response, "usage") and response.usage:
            tokens_used = (response.usage.input_tokens or 0) + (response.usage.output_tokens or 0)
            if rate_limiter:
                rate_limiter.record_usage(tokens_used)

        result = _extract_json(raw)
        if result:
            result["_tokens_used"] = tokens_used
            return result

    except Exception as exc:
        logger.error("Domain analysis failed for %s: %s", pillar_id, exc)

    # Fallback: return minimal structure so pipeline continues
    return {
        "pillar_id": pillar_id,
        "pillar_label": pillar_label,
        "grade": "UNKNOWN",
        "confidence": 0.0,
        "documents_analyzed": 0,
        "findings": [],
        "blind_spots": [],
        "questions_for_target": [],
        "domain_summary": f"Domain analysis failed for {pillar_label}.",
        "_tokens_used": tokens_used,
        "_error": True,
    }


def run_domain_analyses(
    all_signals: list[dict],
    enriched_batches: Optional[dict[str, list[dict]]],
    pillar_definitions: list[dict],
    company_name: str,
    sector: str,
    deal_type: str,
    client: Any,
    rate_limiter: Any = None,
    max_concurrent: int = 3,
    doc_filepath_map: Optional[dict[str, str]] = None,
) -> dict:
    """
    Run domain analysis across all pillars in parallel.

    This is the main entry point called by vdr_triage.py after signal
    extraction and before the cross-referencer.

    Args:
        all_signals: flat list of all extracted signals from all batches
        enriched_batches: batch_id -> list of docs with text_chunks (or None in streaming mode)
        pillar_definitions: list of pillar dicts with 'id' and 'label' keys
        company_name: target company
        sector: sector slug
        deal_type: deal type
        client: Anthropic client
        rate_limiter: optional RateLimiter
        max_concurrent: max parallel API calls (default 3)
        doc_filepath_map: filename -> filepath for on-demand reading (streaming mode)

    Returns:
        dict keyed by pillar_id, each value is the domain analysis result.
        Also includes _metadata with timing and token usage.
    """
    start_time = datetime.now(timezone.utc)

    # Build pillar list — dynamic from catalog, not hardcoded
    if not pillar_definitions:
        # Fallback: derive pillars from signal data itself
        seen = {}
        for sig in all_signals:
            pid = sig.get("pillar_id") or sig.get("lens_id") or ""
            plabel = sig.get("pillar_label") or sig.get("lens_label") or pid
            if pid and pid not in seen:
                seen[pid] = plabel
        pillar_definitions = [{"id": k, "label": v} for k, v in seen.items()]

    results: dict[str, dict] = {}
    total_tokens = 0
    pillars_with_signals = 0

    def _analyze_pillar(pillar: dict) -> tuple[str, dict]:
        """Run analysis for one pillar. Returns (pillar_id, result)."""
        pid = pillar.get("id", pillar.get("pillar_id", ""))
        plabel = pillar.get("label", pillar.get("pillar_name", pid))

        signals = _signals_for_pillar(all_signals, pid)
        if not signals:
            return pid, {
                "pillar_id": pid,
                "pillar_label": plabel,
                "grade": "NO_DATA",
                "confidence": 0.0,
                "documents_analyzed": 0,
                "findings": [],
                "blind_spots": [f"No signals extracted for {plabel} — VDR may lack coverage"],
                "questions_for_target": [
                    f"Provide documentation covering {plabel} capabilities and practices."
                ],
                "domain_summary": f"No signals found for {plabel}. The VDR may not contain relevant documents for this domain.",
                "_tokens_used": 0,
            }

        excerpts = _excerpts_for_pillar(
            enriched_batches, signals, doc_filepath_map=doc_filepath_map,
        )

        result = _run_single_domain(
            pillar_id=pid,
            pillar_label=plabel,
            signals=signals,
            document_excerpts=excerpts,
            company_name=company_name,
            sector=sector,
            deal_type=deal_type,
            client=client,
            rate_limiter=rate_limiter,
        )
        return pid, result

    # Run in parallel
    with ThreadPoolExecutor(max_workers=max_concurrent) as executor:
        futures = {
            executor.submit(_analyze_pillar, pillar): pillar
            for pillar in pillar_definitions
        }
        for future in as_completed(futures):
            pillar = futures[future]
            pid = pillar.get("id", pillar.get("pillar_id", ""))
            try:
                pillar_id, result = future.result()
                # Add confidence summary for this domain's signals
                domain_signals = _signals_for_pillar(all_signals, pillar_id)
                if domain_signals:
                    result["confidence_summary"] = compute_confidence_summary(domain_signals)
                results[pillar_id] = result
                tokens = result.get("_tokens_used", 0)
                total_tokens += tokens
                sig_count = len(domain_signals)
                finding_count = len(result.get("findings", []))
                if sig_count > 0:
                    pillars_with_signals += 1
                logger.info(
                    "  Domain %s: %s — %d signals → %d findings (%d tokens)",
                    pillar_id, result.get("grade", "?"), sig_count, finding_count, tokens,
                )
            except Exception as exc:
                logger.error("Domain analysis thread failed for %s: %s", pid, exc)
                results[pid] = {
                    "pillar_id": pid,
                    "pillar_label": pillar.get("label", pid),
                    "grade": "UNKNOWN",
                    "findings": [],
                    "blind_spots": [],
                    "questions_for_target": [],
                    "domain_summary": f"Analysis failed: {exc}",
                    "_error": True,
                }

    end_time = datetime.now(timezone.utc)

    # Aggregate chase list from all domains
    all_questions: list[dict] = []
    for pid, result in results.items():
        for q in result.get("questions_for_target", []):
            if isinstance(q, str):
                all_questions.append({
                    "pillar_id": pid,
                    "pillar_label": result.get("pillar_label", pid),
                    "question": q,
                    "priority": "medium",
                })
            elif isinstance(q, dict):
                q["pillar_id"] = pid
                q["pillar_label"] = result.get("pillar_label", pid)
                all_questions.append(q)

    # Aggregate confidence summary across all domains
    overall_confidence = compute_confidence_summary(all_signals)

    return {
        "domains": results,
        "chase_list": all_questions,
        "confidence_summary": overall_confidence,
        "_metadata": {
            "company_name": company_name,
            "sector": sector,
            "deal_type": deal_type,
            "total_pillars": len(pillar_definitions),
            "pillars_with_signals": pillars_with_signals,
            "total_findings": sum(len(r.get("findings", [])) for r in results.values()),
            "total_questions": len(all_questions),
            "total_tokens": total_tokens,
            "started_at": start_time.isoformat(),
            "completed_at": end_time.isoformat(),
            "duration_seconds": (end_time - start_time).total_seconds(),
        },
    }


def save_domain_findings(
    domain_results: dict,
    output_dir: Path,
    company_name: str,
) -> Path:
    """
    Save domain analysis results to disk.

    Args:
        domain_results: output from run_domain_analyses()
        output_dir: base outputs directory
        company_name: company name (subfolder key)

    Returns:
        Path to the written JSON file.
    """
    company_dir = output_dir / company_name
    company_dir.mkdir(parents=True, exist_ok=True)
    out_path = company_dir / "domain_findings.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(domain_results, f, indent=2, default=str)
    logger.info("Domain findings saved to %s", out_path)
    return out_path


def _extract_json(raw: str) -> Optional[dict]:
    """
    Delegate to shared extract_json function.

    Kept as a local wrapper for backward compatibility with existing code.
    """
    return extract_json(raw)
