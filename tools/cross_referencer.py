"""
Cross-referencer: takes all per-batch signal results and calls Claude once to
synthesise compound risks, prioritized reading list, and domain slices into the
VDR Intelligence Brief.

Why: Individual batch extractions have no cross-batch context. This single
aggregation call sees all signals at once and can identify patterns that span
multiple documents and lenses — the most valuable compound intelligence.
"""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "vdr_cross_reference.txt"
MODEL = "claude-sonnet-4-20250514"
MAX_TOKENS = 8192


def cross_reference_signals(
    all_batch_results: List[dict],
    inventory: List[dict],
    gap_report: dict,
    company_name: str,
    sector: str,
    deal_type: str,
    deal_id: str,
    client,
) -> dict:
    """
    Synthesise all batch signals into a VDR Intelligence Brief via one Claude call.

    Returns the brief dict matching the 4.2 data contract.
    On failure, returns a minimal valid brief so the pipeline can continue.
    """
    all_signals = [sig for batch in all_batch_results for sig in batch.get("signals", [])]
    timestamp = datetime.now(timezone.utc).isoformat()

    prompt = _build_prompt(
        all_signals=all_signals,
        inventory=inventory,
        gap_report=gap_report,
        company_name=company_name,
        sector=sector,
        deal_type=deal_type,
        deal_id=deal_id,
        timestamp=timestamp,
    )

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text
        result = _extract_json(raw)
        if result:
            result.setdefault("vdr_scan_timestamp", timestamp)
            return result
    except Exception as exc:
        logger.error("Cross-reference Claude call failed: %s", exc)

    return _empty_brief(company_name, deal_id, timestamp)


def _build_prompt(
    all_signals: List[dict],
    inventory: List[dict],
    gap_report: dict,
    company_name: str,
    sector: str,
    deal_type: str,
    deal_id: str,
    timestamp: str,
) -> str:
    """Fill the cross-reference prompt template using string replace."""
    template = PROMPT_PATH.read_text(encoding="utf-8")
    inventory_summary = json.dumps(
        [{"filename": d["filename"], "section": d["vdr_section"]} for d in inventory],
        indent=2,
    )
    gaps_summary = json.dumps(gap_report.get("missing_documents", [])[:10], indent=2)

    return (
        template
        .replace("{company_name}", company_name)
        .replace("{sector}", sector)
        .replace("{deal_type}", deal_type)
        .replace("{deal_id}", deal_id)
        .replace("{timestamp}", timestamp)
        .replace("{all_signals_json}", json.dumps(all_signals, indent=2))
        .replace("{inventory_summary}", inventory_summary)
        .replace("{gaps_summary}", gaps_summary)
    )


def _extract_json(raw: str) -> dict | None:
    """Extract and parse the first JSON object from Claude's response."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start == -1 or end == 0:
        return None
    try:
        return json.loads(raw[start:end])
    except json.JSONDecodeError:
        return None


def _empty_brief(company_name: str, deal_id: str, timestamp: str) -> dict:
    """Return a minimal valid brief when the Claude call fails."""
    return {
        "company_name": company_name,
        "deal_id": deal_id,
        "vdr_scan_timestamp": timestamp,
        "overall_signal_rating": "UNKNOWN",
        "lens_heatmap": {},
        "compound_risks": [],
        "prioritized_reading_list": [],
        "domain_slices": {
            "security_slice": {"signals": [], "summary": "", "overall_rating": "UNKNOWN"},
            "infra_slice": {"signals": [], "summary": "", "overall_rating": "UNKNOWN"},
            "product_slice": {"signals": [], "summary": "", "overall_rating": "UNKNOWN"},
        },
        "document_inventory": [],
    }
