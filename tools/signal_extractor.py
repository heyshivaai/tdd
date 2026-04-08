"""
Signal extractor: sends a batch of related VDR documents to Claude and parses
the structured signal output.

Why: Grouping related documents in a single Claude call gives cross-document
context within a batch (e.g., comparing pen test #1 vs pen test #2). One API
call per batch keeps cost manageable while preserving intra-batch intelligence.

v1.3 update: Now loads the Crosslake Signal Catalog (v1.3) with pillar taxonomy
and injects relevant pillar definitions and catalog signals into each extraction
prompt. This enables Claude to map observations to canonical signal IDs (TA-01,
SC-01, etc.) for cross-deal comparability using the 7-pillar framework with 29
signals.
"""
import json
import logging
from pathlib import Path
from typing import List, Optional

from tools.json_utils import extract_json

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "vdr_signal_extraction.txt"
DATA_DIR = Path(__file__).parent.parent / "data"
MODEL = "claude-sonnet-4-20250514"
MAX_TOKENS = 8192
# Chunks per API call. Higher = fewer calls but larger payloads.
# At Tier 2 (450K input TPM) we can comfortably send 20 chunks per call
# (~40K-60K tokens), keeping total calls manageable.
MAX_CHUNKS_PER_CALL = 20

# ── Token-aware sub-batch limits ───────────────────────────────────────────
# Claude's absolute input limit is 200K tokens. We reserve headroom for the
# system prompt (~2K tokens), pillar definitions (~3K), catalog (~3K), and
# output tokens (4K), giving us ~150K tokens of document content per call.
# Character-to-token ratio is ~4 chars per token (conservative estimate).
CHARS_PER_TOKEN_ESTIMATE = 4
MAX_INPUT_TOKENS_PER_CALL = 150_000  # document content budget
MAX_CHARS_PER_CALL = MAX_INPUT_TOKENS_PER_CALL * CHARS_PER_TOKEN_ESTIMATE  # 600K chars

# Number of concurrent sub-batch API calls.  Tier 2 allows 1,000 req/min;
# 3 concurrent calls stay well within that while cutting wall-clock time ~3x.
MAX_CONCURRENT_CALLS = 3

# ── v1.3 Catalog & Pillar Definitions ───────────────────────────────────────
# Loaded once at module level for reuse across batches.

_PILLARS_V13: List[dict] = []
_CATALOG_V13: List[dict] = []

# Mapping from batch_group to the v1.3 pillar IDs most likely relevant.
# This keeps the catalog context injected into each prompt focused and small.
BATCH_TO_PILLARS = {
    "security_pen_tests": ["SecurityCompliance"],
    "security_compliance": ["SecurityCompliance"],
    "security_posture": ["SecurityCompliance", "InfrastructureDeployment"],
    "infra_cloud_costs": ["InfrastructureDeployment", "RDSpendAssessment"],
    "infra_architecture": ["TechnologyArchitecture", "InfrastructureDeployment"],
    "infra_resilience": ["InfrastructureDeployment"],
    "product_overview": ["TechnologyArchitecture", "SDLCProductManagement", "DataAIReadiness"],
    "human_resources": ["OrganizationTalent"],
    "sdlc_process": ["SDLCProductManagement", "TechnologyArchitecture"],
    "commercial_vendors": ["SecurityCompliance", "RDSpendAssessment"],
    "sales_market": ["SDLCProductManagement", "RDSpendAssessment"],
    # v1.4 calibration-enhanced routing: widen pillar exposure per batch
    # so new signals (org structure, spend economics, tooling, etc.) get extracted
    "financial_data": ["RDSpendAssessment", "InfrastructureDeployment"],
    "corporate_overview": ["SDLCProductManagement", "OrganizationTalent", "RDSpendAssessment"],
    "general": [  # Uncategorised docs get scanned across all pillars
        "TechnologyArchitecture", "SecurityCompliance", "OrganizationTalent",
        "DataAIReadiness", "RDSpendAssessment", "InfrastructureDeployment",
        "SDLCProductManagement",
    ],
}

# Backward compatibility alias for external consumers
BATCH_TO_LENSES = BATCH_TO_PILLARS

# ── Pillar ID normalisation ────────────────────────────────────────────────
# Claude frequently returns abbreviated, legacy, or invented pillar IDs.
# Three-strategy normalisation:
#   1. catalog_signal_id prefix (e.g. "TA-01" → TechnologyArchitecture)
#   2. Explicit name mapping (known abbreviations and synonyms)
#   3. Keyword matching as last resort

_CANONICAL_PILLARS = {
    "TechnologyArchitecture",
    "SecurityCompliance",
    "InfrastructureDeployment",
    "DataAIReadiness",
    "SDLCProductManagement",
    "RDSpendAssessment",
    "OrganizationTalent",
}

# catalog_signal_id prefix → canonical pillar
_PREFIX_TO_PILLAR: dict[str, str] = {
    "TA": "TechnologyArchitecture",
    "SC": "SecurityCompliance",
    "ID": "InfrastructureDeployment",
    "DA": "DataAIReadiness",
    "SP": "SDLCProductManagement",
    "RD": "RDSpendAssessment",
    "RS": "RDSpendAssessment",
    "OT": "OrganizationTalent",
}

# Explicit name mapping — covers abbreviations, legacy IDs, and LLM inventions
_PILLAR_NORMALIZE: dict[str, str] = {
    # TechnologyArchitecture
    "TA": "TechnologyArchitecture",
    "TECH_ARCH": "TechnologyArchitecture",
    "TECARCH": "TechnologyArchitecture",
    "Scalability": "TechnologyArchitecture",
    "CloudCompute": "TechnologyArchitecture",
    "PM": "TechnologyArchitecture",
    # SecurityCompliance
    "SC": "SecurityCompliance",
    "SECUR": "SecurityCompliance",
    "ComplianceGovernance": "SecurityCompliance",
    "ComplianceRisk": "SecurityCompliance",
    "COMPLREG": "SecurityCompliance",
    "DataGovernance": "SecurityCompliance",
    "DATAGOVERNANCE": "SecurityCompliance",
    "Completeness": "SecurityCompliance",
    "Compliance": "SecurityCompliance",
    "Cybersecurity": "SecurityCompliance",
    "Audit & Compliance": "SecurityCompliance",
    "CP": "SecurityCompliance",
    "VV": "SecurityCompliance",
    "P06": "SecurityCompliance",
    "P08": "SecurityCompliance",
    "CC": "SecurityCompliance",
    "CCR": "SecurityCompliance",
    "CustomerCommercialization": "SecurityCompliance",
    "CS": "SecurityCompliance",
    # InfrastructureDeployment
    "ID": "InfrastructureDeployment",
    "OP": "InfrastructureDeployment",
    "OPR": "InfrastructureDeployment",
    "ProcessMaturity": "InfrastructureDeployment",
    "OperationalEfficiency": "InfrastructureDeployment",
    "P09": "InfrastructureDeployment",
    # DataAIReadiness
    "DA": "DataAIReadiness",
    "DAR": "DataAIReadiness",
    "DATA_AI": "DataAIReadiness",
    "DATAAIREADY": "DataAIReadiness",
    # SDLCProductManagement
    "SP": "SDLCProductManagement",
    "SDLCPRODMGMT": "SDLCProductManagement",
    # RDSpendAssessment
    "RD": "RDSpendAssessment",
    "RS": "RDSpendAssessment",
    "RDS": "RDSpendAssessment",
    "R&DSpend": "RDSpendAssessment",
    "SpendAssessment": "RDSpendAssessment",
    # OrganizationTalent
    "OT": "OrganizationTalent",
    "TO": "OrganizationTalent",
}

# Keyword → pillar for last-resort fuzzy matching
_KEYWORD_PILLAR: list[tuple[list[str], str]] = [
    (["security", "compliance", "soc2", "hipaa", "hitrust", "penetration",
      "vulnerability", "breach", "gdpr", "iso27001", "audit", "cyber",
      "phi", "pii", "incident", "mttd", "detection delay", "data breach"],
     "SecurityCompliance"),
    (["architecture", "scalability", "cloud", "aws", "azure", "microservice",
      "monolith", "api", "platform", "stack", "framework", "migration",
      "multi-cloud", "gcp", "tech debt", "tooling", "winforms", "legacy"],
     "TechnologyArchitecture"),
    (["infrastructure", "deploy", "ci/cd", "devops", "observability", "sla",
      "disaster", "recovery", "uptime", "incident", "monitoring"],
     "InfrastructureDeployment"),
    (["data", "analytics", "ml", "ai", "pipeline", "warehouse", "lake",
      "model", "training", "feature"],
     "DataAIReadiness"),
    (["sdlc", "agile", "sprint", "roadmap", "product", "velocity",
      "backlog", "qa", "testing", "release"],
     "SDLCProductManagement"),
    (["r&d", "spend", "capex", "opex", "license", "vendor", "cost",
      "budget", "investment", "ip", "patent", "revenue", "carr", "arr",
      "customer concentration", "hosting cost"],
     "RDSpendAssessment"),
    (["team", "hiring", "retention", "org", "talent", "key-person",
      "leadership", "headcount", "culture", "succession", "restructure",
      "consolidate", "cto", "direct report", "span of control", "offshore"],
     "OrganizationTalent"),
]


def _normalize_pillar_ids(signals: list[dict]) -> list[dict]:
    """Normalise pillar_id on each signal to a canonical v1.3 pillar name.

    Uses three strategies in priority order:
      1. catalog_signal_id prefix (e.g. TA-01 → TechnologyArchitecture)
      2. Explicit name mapping table
      3. Keyword matching on signal title and observation text

    Modifies signals in-place and returns the same list.
    """
    for sig in signals:
        pid = sig.get("pillar_id", "")

        # Already canonical?
        if pid in _CANONICAL_PILLARS:
            continue

        # Strategy 1: catalog_signal_id prefix
        cat_id = sig.get("catalog_signal_id", "") or ""
        if cat_id and "-" in cat_id:
            prefix = cat_id.split("-")[0].upper()
            if prefix in _PREFIX_TO_PILLAR:
                sig["pillar_id"] = _PREFIX_TO_PILLAR[prefix]
                continue

        # Strategy 2: explicit name mapping
        canonical = _PILLAR_NORMALIZE.get(pid)
        if canonical:
            sig["pillar_id"] = canonical
            continue

        # Strategy 3: keyword matching on signal content
        text = (
            (sig.get("title", "") + " " + sig.get("observation", ""))
            .lower()
        )
        best_score = 0
        best_pillar = "TechnologyArchitecture"  # default fallback
        for keywords, pillar in _KEYWORD_PILLAR:
            score = sum(1 for kw in keywords if kw in text)
            if score > best_score:
                best_score = score
                best_pillar = pillar
        sig["pillar_id"] = best_pillar

    return signals


def _load_v13_data() -> None:
    """
    Load pillar definitions and signal catalog from JSON files.

    Prefers v1.4 (calibration-enhanced) files, falls back to v1.3.
    Called lazily on first use. Populates module-level _PILLARS_V13 and
    _CATALOG_V13 lists. Falls back to empty lists if files are missing
    (backward compatibility with v1.1 deployments).
    """
    global _PILLARS_V13, _CATALOG_V13
    if _PILLARS_V13:
        return  # Already loaded

    # Single source of truth — no version suffix, tracked by git
    pillars_path = DATA_DIR / "signal_pillars.json"
    catalog_path = DATA_DIR / "signal_catalog.json"

    if pillars_path.exists():
        data = json.loads(pillars_path.read_text(encoding="utf-8"))
        _PILLARS_V13 = data.get("pillars", [])
        ver = data.get("version", "?")
        logger.info("Loaded signal pillars v%s: %d pillars", ver, len(_PILLARS_V13))
    else:
        logger.warning("signal_pillars.json not found at %s", pillars_path)

    if catalog_path.exists():
        data = json.loads(catalog_path.read_text(encoding="utf-8"))
        _CATALOG_V13 = data.get("signals", [])
        ver = data.get("version", "?")
        logger.info("Loaded signal catalog v%s: %d signals", ver, len(_CATALOG_V13))
    else:
        logger.warning("signal_catalog.json not found at %s", catalog_path)


def _format_pillar_definitions() -> str:
    """
    Format v1.3 pillar definitions as a compact string for prompt injection.

    Returns:
        Multi-line string listing each pillar with ID and label.
    """
    _load_v13_data()
    if not _PILLARS_V13:
        # Fallback to v1.3 pillar list if data not available
        return (
            "TechnologyArchitecture, SecurityCompliance, OrganizationTalent, "
            "DataAIReadiness, RDSpendAssessment, InfrastructureDeployment, "
            "SDLCProductManagement"
        )
    lines = []
    for pillar in _PILLARS_V13:
        lines.append(f"- {pillar['id']} ({pillar['label']}): {pillar['signal_count']} signals")
    return "\n".join(lines)


def _format_catalog_signals_for_batch(batch_id: str) -> str:
    """
    Format catalog signals relevant to this batch group for prompt injection.

    Only includes signals from pillars mapped to this batch group to keep
    the prompt focused and within token limits.

    Args:
        batch_id: Batch group identifier (e.g., "security_pen_tests")

    Returns:
        Multi-line string listing relevant catalog signals with IDs and names.
    """
    _load_v13_data()
    if not _CATALOG_V13:
        return "(No catalog signals loaded — extraction will proceed without catalog matching)"

    # Determine which pillars are relevant for this batch
    base_batch = batch_id.split("_sub")[0]  # Strip sub-batch suffix
    relevant_pillars = BATCH_TO_PILLARS.get(base_batch, [])

    if not relevant_pillars:
        # For unknown batches, include all signals (truncated)
        relevant = _CATALOG_V13[:30]
    else:
        relevant = [s for s in _CATALOG_V13 if s.get("pillar_id") in relevant_pillars]

    if not relevant:
        return "(No catalog signals mapped to this batch group)"

    lines = []
    for s in relevant:
        lines.append(
            f"- {s['signal_id']} [{s['pillar_id']}] {s['name']}: "
            f"{s.get('technical_definition', '')[:120]}"
        )
    return "\n".join(lines)


def extract_signals_from_batch(
    batch_id: str,
    documents: List[dict],
    company_name: str,
    sector: str,
    deal_type: str,
    prior_patterns: List[dict],
    client,
    rate_limiter: Optional["RateLimiter"] = None,
) -> dict:
    """
    Extract signals from a batch of documents using one Claude API call.

    Args:
        batch_id: Unique identifier for this batch (e.g., "security_pen_tests")
        documents: List of document inventory dicts, each with a 'text_chunks' key
        company_name: Name of the company being analyzed
        sector: Sector/vertical (e.g., "healthcare-saas")
        deal_type: Type of deal (e.g., "pe-acquisition")
        prior_patterns: List of similar signal dicts from Pinecone (empty list if
                        Signal Intelligence Layer not wired in Phase A)
        client: Anthropic client instance
        rate_limiter: Optional RateLimiter instance for smart pausing.
                      If None, no rate limiting is applied (caller is responsible).

    Returns:
        Per-batch signal extraction result dict with signals, batch_summary,
        and _tokens_used (int) for the caller's rate limiter.
    """
    document_list = [doc["filename"] for doc in documents]
    total_chunks = sum(len(d.get("text_chunks", [])) for d in documents)

    # Split into sub-batches if this batch exceeds the per-call chunk limit.
    # Each sub-batch is sent as a separate Claude call and results are merged.
    if total_chunks > MAX_CHUNKS_PER_CALL:
        return _extract_signals_split(
            batch_id=batch_id,
            documents=documents,
            company_name=company_name,
            sector=sector,
            deal_type=deal_type,
            prior_patterns=prior_patterns,
            client=client,
            rate_limiter=rate_limiter,
        )

    document_text = _assemble_document_text(documents)

    prompt = _build_prompt(
        batch_id=batch_id,
        document_list=document_list,
        company_name=company_name,
        sector=sector,
        deal_type=deal_type,
        document_text=document_text,
        prior_patterns=prior_patterns,
    )

    tokens_used = 0
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
            timeout=300.0,
        )
        if not response.content:
            logger.error("Empty response from Claude API for batch %s", batch_id)
            return {"batch_id": batch_id, "documents": document_list, "signals": [], "batch_summary": "", "_tokens_used": 0}
        raw = response.content[0].text
        # Track token usage from the API response
        if hasattr(response, "usage") and response.usage:
            tokens_used = (response.usage.input_tokens or 0) + (response.usage.output_tokens or 0)
            if rate_limiter:
                rate_limiter.record_usage(tokens_used)
        result = _extract_json(raw)
    except Exception as exc:
        logger.error("Claude API call failed for batch %s: %s", batch_id, exc)
        return {"batch_id": batch_id, "documents": document_list, "signals": [], "batch_summary": "", "_tokens_used": 0}

    if not result:
        return {"batch_id": batch_id, "documents": document_list, "signals": [], "batch_summary": "", "_tokens_used": tokens_used}

    result["_tokens_used"] = tokens_used
    return result


def _extract_signals_split(
    batch_id: str,
    documents: List[dict],
    company_name: str,
    sector: str,
    deal_type: str,
    prior_patterns: List[dict],
    client,
    rate_limiter: Optional["RateLimiter"] = None,
) -> dict:
    """
    Handle batches that exceed MAX_CHUNKS_PER_CALL by splitting docs into sub-batches.

    Sub-batches are sent concurrently (up to MAX_CONCURRENT_CALLS at a time) using
    a thread pool. All extracted signals are merged into a single result.

    Why concurrent: Each API call takes ~25-30s wall-clock (network + Claude
    inference). Sequential processing of 25 sub-batches = ~12 min; with 3
    concurrent calls it drops to ~4 min. Tier 2 allows 1,000 req/min so
    concurrency is well within limits.

    Args:
        Same as extract_signals_from_batch, plus rate_limiter.

    Returns:
        Merged batch result dict with all signals from all sub-batches,
        and _tokens_used (int) total across all sub-batches.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    # Bin documents into sub-batches using token-aware sizing.
    # Primary constraint: MAX_CHARS_PER_CALL (estimated tokens × 4 chars/token).
    # Secondary constraint: MAX_CHUNKS_PER_CALL (legacy, keeps calls reasonable).
    # This prevents the 400 "prompt is too long" error from the API.
    def _doc_chars(doc: dict) -> int:
        """Estimate total character count for a document's text chunks."""
        return sum(len(c.get("text", "")) for c in doc.get("text_chunks", []))

    sub_batches: list[list[dict]] = []
    current_sub: list[dict] = []
    current_chars = 0
    current_chunks = 0
    for doc in documents:
        doc_chars = _doc_chars(doc)
        doc_chunks = len(doc.get("text_chunks", []))

        # If a single document exceeds the limit, it gets its own sub-batch
        # (will be truncated at prompt assembly time if still too large)
        if doc_chars > MAX_CHARS_PER_CALL:
            if current_sub:
                sub_batches.append(current_sub)
                current_sub = []
                current_chars = 0
                current_chunks = 0
            sub_batches.append([doc])
            logger.warning(
                "  Oversized document %s (%d chars, ~%dK tokens) — isolated in own sub-batch",
                doc.get("filename", "?"), doc_chars, doc_chars // CHARS_PER_TOKEN_ESTIMATE // 1000,
            )
            continue

        # Would adding this doc exceed either limit?
        if current_sub and (
            current_chars + doc_chars > MAX_CHARS_PER_CALL
            or current_chunks + doc_chunks > MAX_CHUNKS_PER_CALL
        ):
            sub_batches.append(current_sub)
            current_sub = []
            current_chars = 0
            current_chunks = 0

        current_sub.append(doc)
        current_chars += doc_chars
        current_chunks += doc_chunks
    if current_sub:
        sub_batches.append(current_sub)

    total_chunk_count = sum(len(d.get("text_chunks", [])) for d in documents)
    total_chars = sum(_doc_chars(d) for d in documents)
    logger.info(
        "  Batch %s: %d chunks, ~%dK tokens -- splitting into %d sub-batches (%d concurrent)",
        batch_id, total_chunk_count, total_chars // CHARS_PER_TOKEN_ESTIMATE // 1000,
        len(sub_batches), MAX_CONCURRENT_CALLS,
    )

    all_signals: list[dict] = []
    summaries: list[str] = []
    total_tokens = 0

    def _call_sub_batch(idx: int, sub_docs: list[dict]) -> dict:
        """Execute a single sub-batch API call. Thread-safe."""
        sub_id = f"{batch_id}_sub{idx + 1}"
        document_list = [doc["filename"] for doc in sub_docs]
        document_text = _assemble_document_text(sub_docs)
        prompt = _build_prompt(
            batch_id=sub_id,
            document_list=document_list,
            company_name=company_name,
            sector=sector,
            deal_type=deal_type,
            document_text=document_text,
            prior_patterns=prior_patterns,
        )
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                messages=[{"role": "user", "content": prompt}],
                timeout=300.0,
            )
            tokens_used = 0
            if hasattr(response, "usage") and response.usage:
                tokens_used = (response.usage.input_tokens or 0) + (response.usage.output_tokens or 0)
                if rate_limiter:
                    rate_limiter.record_usage(tokens_used)

            if not response.content:
                logger.error("Empty response from Claude API for sub-batch %s", sub_id)
                return {"signals": [], "summary": "", "tokens": 0}
            result = _extract_json(response.content[0].text)
            signals = result.get("signals", []) if result else []
            summary = result.get("batch_summary", "") if result else ""
            logger.info("  Sub-batch %s: %d signals, %d tokens", sub_id, len(signals), tokens_used)
            return {"signals": signals, "summary": summary, "tokens": tokens_used}
        except Exception as exc:
            logger.error("Claude API call failed for sub-batch %s: %s", sub_id, exc)
            return {"signals": [], "summary": "", "tokens": 0}

    # Fire sub-batches concurrently with a thread pool.
    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_CALLS) as executor:
        futures = {
            executor.submit(_call_sub_batch, idx, sub_docs): idx
            for idx, sub_docs in enumerate(sub_batches)
        }
        for future in as_completed(futures):
            res = future.result()
            all_signals.extend(res["signals"])
            if res["summary"]:
                summaries.append(res["summary"])
            total_tokens += res["tokens"]

    # Normalise any abbreviated/legacy pillar IDs to canonical v1.3 names
    _normalize_pillar_ids(all_signals)

    return {
        "batch_id": batch_id,
        "documents": [doc["filename"] for doc in documents],
        "signals": all_signals,
        "batch_summary": " | ".join(summaries),
        "_tokens_used": total_tokens,
    }


def _assemble_document_text(documents: List[dict]) -> str:
    """
    Concatenate all text chunks from all documents in a batch, labelled by source.

    Applies a hard character ceiling (MAX_CHARS_PER_CALL) to prevent prompts
    from exceeding Claude's 200K input token limit. If a single sub-batch
    somehow still exceeds the budget, text is truncated with a marker.

    Supports both legacy chunk shape ({text, source_doc, chunk_index, total_chunks})
    and new structure-aware shape ({text, section_hint, extraction_method, quality, ...}).
    When the new shape is detected, chunk position context is included so Claude
    knows where in the document each chunk came from.

    Args:
        documents: List of document dicts with 'filename' and 'text_chunks' keys

    Returns:
        Concatenated, source-labelled document text
    """
    parts = []
    running_chars = 0
    for doc in documents:
        chunks = doc.get("text_chunks", [])
        if not chunks:
            continue

        # Build chunk text with position context when available
        chunk_parts = []
        for c in chunks:
            if "section_hint" in c:
                # New structure-aware chunk — include position context
                ctx = (
                    f"[Chunk {c['chunk_index'] + 1}/{c['total_chunks']}"
                    f" | {c.get('section_hint', '')}"
                    f" | quality: {c.get('quality', 'unknown')}]"
                )
                chunk_parts.append(f"{ctx}\n{c['text']}")
            else:
                chunk_parts.append(c["text"])

        doc_text = "\n".join(chunk_parts)
        header = f"=== DOCUMENT: {doc['filename']} ==="
        segment = f"{header}\n{doc_text}"

        if running_chars + len(segment) > MAX_CHARS_PER_CALL:
            remaining = MAX_CHARS_PER_CALL - running_chars
            if remaining > 500:
                # Include a truncated portion of this document
                segment = segment[:remaining] + "\n[... TRUNCATED — token limit reached ...]"
                parts.append(segment)
                logger.warning(
                    "  Truncated document text at %dK chars to stay within API limits",
                    MAX_CHARS_PER_CALL // 1000,
                )
            else:
                logger.warning(
                    "  Skipped document %s — no room left in sub-batch",
                    doc.get("filename", "?"),
                )
            break

        parts.append(segment)
        running_chars += len(segment)
    return "\n\n".join(parts)


def _build_prompt(
    batch_id: str,
    document_list: List[str],
    company_name: str,
    sector: str,
    deal_type: str,
    document_text: str,
    prior_patterns: List[dict],
) -> str:
    """
    Fill the signal extraction prompt template using string replace (not .format()).

    Injects v1.3 pillar definitions and batch-relevant catalog signals into the
    prompt so Claude can map observations to canonical signal IDs.

    Args:
        batch_id: Batch identifier
        document_list: List of document filenames
        company_name: Company name
        sector: Sector/vertical
        deal_type: Deal type
        document_text: Full concatenated document text
        prior_patterns: Similar prior signals for context

    Returns:
        Filled prompt ready for Claude API
    """
    template = PROMPT_PATH.read_text(encoding="utf-8")

    prior_block = ""
    if prior_patterns:
        lines = ["PRIOR PATTERNS FROM SIMILAR DEALS (use to calibrate confidence):"]
        for p in prior_patterns[:3]:
            lines.append(
                f"- [{p.get('rating', 'UNKNOWN')}] {p.get('title', '')} "
                f"(pillar: {p.get('pillar_id', p.get('pillar', p.get('lens_id', p.get('lens', ''))))})"
            )
        prior_block = "\n".join(lines)

    return (
        template
        .replace("{company_name}", company_name)
        .replace("{sector}", sector)
        .replace("{deal_type}", deal_type)
        .replace("{batch_id}", batch_id)
        .replace("{document_list}", ", ".join(document_list))
        .replace("{document_list_json}", json.dumps(document_list))
        .replace("{prior_patterns_block}", prior_block)
        .replace("{document_text}", document_text)
        .replace("{lens_definitions}", _format_pillar_definitions())
        .replace("{catalog_signals_for_batch}", _format_catalog_signals_for_batch(batch_id))
    )


def _extract_json(raw: str) -> dict | None:
    """
    Delegate to shared extract_json function.

    Kept as a local wrapper for backward compatibility with existing code.
    """
    return extract_json(raw)
