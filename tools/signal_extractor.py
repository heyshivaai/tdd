"""
Signal extractor: sends a batch of related VDR documents to Claude and parses
the structured signal output.

Why: Grouping related documents in a single Claude call gives cross-document
context within a batch (e.g., comparing pen test #1 vs pen test #2). One API
call per batch keeps cost manageable while preserving intra-batch intelligence.
"""
import json
import logging
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "vdr_signal_extraction.txt"
MODEL = "claude-sonnet-4-20250514"
MAX_TOKENS = 4096


def extract_signals_from_batch(
    batch_id: str,
    documents: List[dict],
    company_name: str,
    sector: str,
    deal_type: str,
    prior_patterns: List[dict],
    client,
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

    Returns:
        Per-batch signal extraction result dict with signals, batch_summary, etc.
    """
    document_list = [doc["filename"] for doc in documents]
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

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text
        result = _extract_json(raw)
    except Exception as exc:
        logger.error("Claude API call failed for batch %s: %s", batch_id, exc)
        return {"batch_id": batch_id, "documents": document_list, "signals": [], "batch_summary": ""}

    if not result:
        return {"batch_id": batch_id, "documents": document_list, "signals": [], "batch_summary": ""}

    return result


def _assemble_document_text(documents: List[dict]) -> str:
    """
    Concatenate all text chunks from all documents in a batch, labelled by source.

    Args:
        documents: List of document dicts with 'filename' and 'text_chunks' keys

    Returns:
        Concatenated, source-labelled document text
    """
    parts = []
    for doc in documents:
        chunks = doc.get("text_chunks", [])
        if not chunks:
            continue
        doc_text = "\n".join(c["text"] for c in chunks)
        parts.append(f"=== DOCUMENT: {doc['filename']} ===\n{doc_text}")
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
                f"(lens: {p.get('lens', '')})"
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
    )


def _extract_json(raw: str) -> dict | None:
    """
    Extract and parse the first JSON object from Claude's response.

    Tries full parse first, then searches for the first { and last } if that fails.

    Args:
        raw: Raw response text from Claude

    Returns:
        Parsed JSON dict, or None if no valid JSON found
    """
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start == -1 or end == 0:
        logger.error("No JSON object found in response")
        return None
    try:
        return json.loads(raw[start:end])
    except json.JSONDecodeError as exc:
        logger.error("JSON parse failed: %s", exc)
        return None
