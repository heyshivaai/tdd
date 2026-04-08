"""
Gap Resolver: match new VDR documents against known completeness gaps.

Why: When a VDR is rescanned and new documents are added, we want to
automatically detect which gaps from the prior completeness report might
now be resolved. This reduces manual review and accelerates the chase list.

Uses keyword matching between gap descriptions and new document names,
with confidence scoring based on match quality.
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def resolve_gaps(
    completeness_report: dict,
    new_documents: list[dict],
    signal_catalog: Optional[dict] = None,
) -> dict:
    """
    Match new VDR documents against existing gaps from completeness_checker output.

    For each gap in the completeness report, attempts to match it against
    the newly added documents. Confidence is based on keyword overlap between
    the gap description and the document filename/path.

    Args:
        completeness_report: Output dict from completeness_checker.check_completeness.
                            Expected keys: missing_documents, present_but_incomplete
        new_documents: List of new document dicts from vdr_diff_engine.
                      Expected keys: filename, filepath, vdr_section, batch_group
        signal_catalog: Optional signal catalog dict (for future enhancement).

    Returns:
        {
            "resolved_gaps": [
                {
                    "gap_id": str,
                    "gap_description": str,
                    "expected_document": str,
                    "resolved_by": str,  # filename of the resolving document
                    "confidence": "HIGH" | "MEDIUM" | "LOW",
                    "resolved_at_vdr_section": str,
                    "resolved_in_batch_group": str,
                    "signals_affected": [str]  # placeholder for future integration
                }
            ],
            "unresolved_gaps": [
                {
                    "gap_id": str,
                    "gap_description": str,
                    "expected_document": str,
                    "urgency": str
                }
            ],
            "summary": {
                "total_gaps": int,
                "resolved": int,
                "unresolved": int,
                "resolution_rate": float  # 0.0 to 1.0
            }
        }
    """
    missing_gaps = completeness_report.get("missing_documents", [])
    resolved_gaps = []
    unresolved_gaps = []

    for gap in missing_gaps:
        gap_id = gap.get("gap_id", "")
        gap_desc = gap.get("expected_document", "")
        urgency = gap.get("urgency", "MEDIUM")

        best_match = _find_best_match(gap_desc, new_documents)

        if best_match:
            confidence, matched_doc = best_match
            resolved_gaps.append({
                "gap_id": gap_id,
                "gap_description": gap_desc,
                "expected_document": gap_desc,
                "resolved_by": matched_doc["filename"],
                "confidence": confidence,
                "resolved_at_vdr_section": matched_doc.get("vdr_section", ""),
                "resolved_in_batch_group": matched_doc.get("batch_group", ""),
                "signals_affected": [],
            })
        else:
            unresolved_gaps.append({
                "gap_id": gap_id,
                "gap_description": gap_desc,
                "expected_document": gap_desc,
                "urgency": urgency,
            })

    total_gaps = len(missing_gaps)
    resolved_count = len(resolved_gaps)
    unresolved_count = len(unresolved_gaps)
    resolution_rate = (
        resolved_count / total_gaps if total_gaps > 0 else 0.0
    )

    return {
        "resolved_gaps": resolved_gaps,
        "unresolved_gaps": unresolved_gaps,
        "summary": {
            "total_gaps": total_gaps,
            "resolved": resolved_count,
            "unresolved": unresolved_count,
            "resolution_rate": round(resolution_rate, 3),
        },
    }


def _find_best_match(
    gap_description: str,
    new_documents: list[dict],
) -> Optional[tuple[str, dict]]:
    """
    Find the best-matching document for a gap description.

    Scoring logic:
    - HIGH: Exact or near-exact name match (gap keywords in filename, >80% similarity)
    - MEDIUM: Keyword overlap >50%
    - LOW: Partial keyword match >30%

    Returns:
        (confidence_level, matched_doc) tuple, or None if no match found.
    """
    if not new_documents:
        return None

    # Extract keywords from gap description (words >3 chars, lowercased)
    gap_keywords = _extract_keywords(gap_description)
    if not gap_keywords:
        return None

    best_score = 0.0
    best_confidence = "LOW"
    best_doc = None

    for doc in new_documents:
        # Extract keywords from document filename and path
        doc_text = f"{doc.get('filename', '')} {doc.get('vdr_section', '')}".lower()
        doc_keywords = _extract_keywords(doc_text)

        # Compute overlap score
        if doc_keywords:
            overlap = len(gap_keywords & doc_keywords) / len(gap_keywords)
        else:
            overlap = 0.0

        # Determine confidence level
        if overlap > 0.8:
            confidence = "HIGH"
            score = overlap * 1.0
        elif overlap > 0.5:
            confidence = "MEDIUM"
            score = overlap * 0.8
        elif overlap > 0.3:
            confidence = "LOW"
            score = overlap * 0.5
        else:
            continue

        if score > best_score:
            best_score = score
            best_confidence = confidence
            best_doc = doc

    if best_doc:
        return (best_confidence, best_doc)

    return None


def _extract_keywords(text: str) -> set[str]:
    """
    Extract meaningful keywords from text for matching.

    Splits on whitespace and special characters, filters out short words.

    Args:
        text: Text to extract keywords from.

    Returns:
        Set of keywords (lowercased, >3 chars).
    """
    # Split on whitespace and common separators
    import re
    words = re.split(r'[\s\-_.,()[\]{}]+', text.lower())
    # Filter: remove empty strings and words <=3 chars
    keywords = {w for w in words if w and len(w) > 3}
    return keywords
