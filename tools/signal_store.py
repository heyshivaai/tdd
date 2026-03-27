"""
Signal store: reads and writes signals to the Pinecone `tdd-signals` integrated index.

Why: Every signal extracted across all deals and all phases is stored here.
Before each Claude call, the caller queries this store to inject prior patterns
that match the current sector and lens. Practitioner feedback updates verdicts
so the system calibrates over time.

Index: tdd-signals (multilingual-e5-large integrated, field_map: signal_text -> embedding)
Namespace: deals
"""
import logging
import os
from typing import List

from dotenv import load_dotenv
from pinecone import Pinecone

load_dotenv()
logger = logging.getLogger(__name__)

INDEX_NAME = "tdd-signals"
NAMESPACE = "deals"


def _get_index():
    """Return a Pinecone index handle. Called fresh per operation."""
    pc = Pinecone(api_key=os.environ["PINECONE_API_KEY"])
    return pc.Index(INDEX_NAME)


def store_signals(signals: List[dict], deal_id: str, sector: str, phase: int = 0) -> int:
    """
    Embed and upsert all signals from a batch into Pinecone.

    The text field (`signal_text`) is embedded by the integrated model.
    Returns count of records upserted.
    """
    index = _get_index()
    records = []
    for sig in signals:
        signal_text = (
            f"{sig.get('signal_id', '')} | {sig.get('title', '')} | "
            f"{sig.get('observation', '')} | {sig.get('evidence_quote', '')}"
        )
        record = {
            "_id": f"{deal_id}_{sig['signal_id']}",
            "signal_text": signal_text,
            "lens": sig.get("lens", ""),
            "rating": sig.get("rating", ""),
            "confidence": sig.get("confidence", ""),
            "title": sig.get("title", ""),
            "deal_id": deal_id,
            "sector": sector,
            "phase": phase,
            "source_doc": sig.get("source_doc", ""),
            "deal_implication": sig.get("deal_implication", ""),
            "practitioner_verdict": "",
            "outcome_material": "",
        }
        records.append(record)

    if records:
        index.upsert_records(namespace=NAMESPACE, records=records)
        logger.info("Stored %d signals for deal %s", len(records), deal_id)

    return len(records)


def store_gap(gap: dict, deal_id: str, sector: str) -> None:
    """
    Store a completeness gap as a searchable record in Pinecone.

    Why: Gap patterns across deals (e.g., "missing HIPAA risk assessment in healthcare-saas")
    are valuable signals themselves — the system learns which gaps are common vs. unusual.
    """
    index = _get_index()
    record = {
        "_id": f"{deal_id}_{gap['gap_id']}",
        "signal_text": f"Missing: {gap['expected_document']} | {gap.get('reason_expected', '')}",
        "lens": "Completeness",
        "rating": gap.get("urgency", "MEDIUM"),
        "confidence": "HIGH",
        "title": f"Missing: {gap['expected_document']}",
        "deal_id": deal_id,
        "sector": sector,
        "phase": 0,
        "source_doc": "completeness_check",
        "deal_implication": gap.get("reason_expected", ""),
        "practitioner_verdict": "",
        "outcome_material": "",
    }
    index.upsert_records(namespace=NAMESPACE, records=[record])


def query_similar_patterns(
    query_text: str,
    sector: str,
    lens: str | None,
    top_k: int = 3,
) -> List[dict]:
    """
    Semantic search for prior signals matching the query, filtered by sector and lens.

    Returns a list of pattern dicts: {title, lens, rating, deal_id, signal_text}.
    Returns empty list on any error so callers degrade gracefully.
    """
    index = _get_index()
    query_filter: dict = {"sector": {"$eq": sector}}
    if lens:
        query_filter["lens"] = {"$eq": lens}

    try:
        result = index.search(
            namespace=NAMESPACE,
            query={"inputs": {"text": query_text}, "top_k": top_k},
            fields=["signal_text", "lens", "rating", "title", "deal_id"],
            filter=query_filter,
        )
        return [
            {
                "title": hit.fields.get("title", ""),
                "lens": hit.fields.get("lens", ""),
                "rating": hit.fields.get("rating", ""),
                "deal_id": hit.fields.get("deal_id", ""),
                "signal_text": hit.fields.get("signal_text", ""),
            }
            for hit in result.result.hits
        ]
    except Exception as exc:
        logger.error("Pinecone query failed: %s", exc)
        return []


def update_signal_verdict(
    deal_id: str,
    signal_id: str,
    verdict: str,
    corrected_rating: str | None,
) -> None:
    """
    Update a signal's practitioner verdict (and optionally its rating) in Pinecone.

    Called after a Human Gate feedback session to calibrate future scans.
    """
    index = _get_index()
    record_id = f"{deal_id}_{signal_id}"
    fields = {"practitioner_verdict": verdict}
    if corrected_rating:
        fields["rating"] = corrected_rating
    try:
        index.update(id=record_id, namespace=NAMESPACE, set_metadata=fields)
    except Exception as exc:
        logger.error("Failed to update signal verdict for %s: %s", record_id, exc)
