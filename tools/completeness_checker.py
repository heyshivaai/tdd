"""
Completeness checker: compares the VDR document inventory against a list of
expected documents for a given deal type and sector, then generates a gap report
with request language a practitioner can send verbatim.

Why: Identifying missing documents at triage time lets practitioners issue a
targeted request list immediately — saving days of back-and-forth mid-diligence.
"""
from typing import List


REQUEST_TEMPLATES = {
    "CRITICAL": (
        "Please provide {document} as a matter of urgency. "
        "This document is required to complete our security and risk assessment."
    ),
    "HIGH": (
        "Please provide {document} at your earliest convenience. "
        "This is needed to complete our technical review."
    ),
    "MEDIUM": (
        "When available, please share {document} to support our technical due diligence."
    ),
}


def check_completeness(
    inventory: List[dict],
    expected_docs: dict,
    sector: str,
    deal_type: str,
    deal_id: str,
) -> dict:
    """
    Compare document inventory against expected docs for the given deal type + sector.

    Returns the completeness report dict matching the 4.3 data contract:
    {deal_id, deal_type, sector, missing_documents, present_but_incomplete,
     completeness_score, chase_list_summary}

    Args:
        inventory: List of document dicts from VDR with keys: filename, vdr_section, batch_group, size_bytes
        expected_docs: Nested dict structure from expected_docs.json: {deal_type: {sector: [...]}}
        sector: Target sector (e.g., "healthcare-saas")
        deal_type: Target deal type (e.g., "pe-acquisition")
        deal_id: Unique identifier for this deal

    Returns:
        Dict with keys: deal_id, deal_type, sector, missing_documents, present_but_incomplete,
                       completeness_score, chase_list_summary
    """
    expected_list = expected_docs.get(deal_type, {}).get(sector, [])
    inventory_text = " ".join(doc["filename"].lower() for doc in inventory)

    missing: List[dict] = []
    present_count = 0

    for i, expected in enumerate(expected_list):
        doc_name = expected["name"]
        # Extract keywords from the expected document name for matching
        keywords = [w for w in doc_name.lower().split() if len(w) > 3]
        matched = any(kw in inventory_text for kw in keywords)

        if matched:
            present_count += 1
        else:
            missing.append(
                {
                    "gap_id": f"GAP-{i + 1:03d}",
                    "urgency": expected["urgency"],
                    "expected_document": doc_name,
                    "reason_expected": (
                        f"Standard {deal_type} ({sector}) diligence requires {doc_name}."
                    ),
                    "request_language": generate_request_language(doc_name, expected["urgency"]),
                }
            )

    total = len(expected_list)
    score = int((present_count / total) * 100) if total > 0 else 100
    critical_count = sum(1 for g in missing if g["urgency"] == "CRITICAL")

    summary = (
        f"VDR completeness score: {score}/100. "
        f"{len(missing)} expected document(s) not found, {critical_count} CRITICAL. "
        f"Recommend issuing a document request before proceeding with full diligence."
    )

    return {
        "deal_id": deal_id,
        "deal_type": deal_type,
        "sector": sector,
        "missing_documents": missing,
        "present_but_incomplete": [],
        "completeness_score": score,
        "chase_list_summary": summary,
    }


def generate_request_language(document_name: str, urgency: str) -> str:
    """
    Generate a practitioner-ready request string for a missing document.

    Uses urgency-keyed templates so CRITICAL gaps read with appropriate weight.

    Args:
        document_name: Name of the expected document (e.g., "Penetration test — primary application")
        urgency: One of "CRITICAL", "HIGH", or "MEDIUM"

    Returns:
        A templated request string ready to send to data room custodian
    """
    template = REQUEST_TEMPLATES.get(urgency, REQUEST_TEMPLATES["MEDIUM"])
    return template.format(document=document_name)
