"""
Gate Manager: manage practitioner feedback gates between pipeline phases.

Why: TDD phases (Pre-LOI, Full Diligence, Value Creation) have natural
checkpoints where practitioners need to review findings and decide whether
to proceed. Gates track this feedback with an audit trail.

Gates are stored as JSON files in outputs/<deal_id>/feedback_gate{N}.json
to maintain a deal-specific history even if the main reports are regenerated.
"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def create_gate(
    deal_id: str,
    gate_number: int,
    findings_summary: dict,
    output_base: str = "outputs",
) -> dict:
    """
    Create a feedback gate checkpoint for a deal.

    Creates a gate record with status='pending' and saves it to
    outputs/<deal_id>/feedback_gate{N}.json

    Args:
        deal_id: Unique deal identifier (e.g., "HORIZON").
        gate_number: Gate sequence number (1, 2, 3, ...).
        findings_summary: Dict with keys: domain_scores, red_flags, yellow_flags,
                         completeness_score, overall_risk_score
        output_base: Base directory for outputs (default "outputs").

    Returns:
        Gate record dict with keys: gate_id, deal_id, gate_number, status,
                                    created_at, reviewed_at, reviewer,
                                    findings_count, items
    """
    now = datetime.utcnow().isoformat() + "Z"

    # Count items needing review
    findings_count = (
        len(findings_summary.get("red_flags", [])) +
        len(findings_summary.get("yellow_flags", []))
    )

    # Build gate items from findings
    items = []
    for flag in findings_summary.get("red_flags", []):
        items.append({
            "type": "red_flag",
            "title": flag.get("title", ""),
            "description": flag.get("description", ""),
            "status": "pending_review"
        })
    for flag in findings_summary.get("yellow_flags", []):
        items.append({
            "type": "yellow_flag",
            "title": flag.get("title", ""),
            "description": flag.get("description", ""),
            "status": "pending_review"
        })

    gate_record = {
        "gate_id": f"{deal_id}_gate_{gate_number}",
        "deal_id": deal_id,
        "gate_number": gate_number,
        "status": "pending",
        "created_at": now,
        "reviewed_at": None,
        "reviewer": None,
        "findings_count": findings_count,
        "completeness_score": findings_summary.get("completeness_score"),
        "overall_risk_score": findings_summary.get("overall_risk_score"),
        "items": items,
        "approval_notes": None,
        "rejection_items": None,
    }

    # Save to disk
    _save_gate(deal_id, gate_number, gate_record, output_base)
    logger.info("Created gate %d for deal %s", gate_number, deal_id)

    return gate_record


def approve_gate(
    deal_id: str,
    gate_number: int,
    reviewer: str,
    notes: str = "",
    output_base: str = "outputs",
) -> dict:
    """
    Mark a gate as approved.

    Args:
        deal_id: Deal identifier.
        gate_number: Gate sequence number.
        reviewer: Name or identifier of the reviewer.
        notes: Optional approval notes.
        output_base: Base directory for outputs.

    Returns:
        Updated gate record.

    Raises:
        FileNotFoundError: If gate doesn't exist.
    """
    gate = _load_gate(deal_id, gate_number, output_base)
    if not gate:
        raise FileNotFoundError(
            f"Gate {gate_number} not found for deal {deal_id}"
        )

    now = datetime.utcnow().isoformat() + "Z"
    gate["status"] = "approved"
    gate["reviewed_at"] = now
    gate["reviewer"] = reviewer
    gate["approval_notes"] = notes

    _save_gate(deal_id, gate_number, gate, output_base)
    logger.info(
        "Approved gate %d for deal %s by %s",
        gate_number,
        deal_id,
        reviewer
    )

    return gate


def reject_gate(
    deal_id: str,
    gate_number: int,
    reviewer: str,
    rejection_items: list[str],
    notes: str = "",
    output_base: str = "outputs",
) -> dict:
    """
    Reject a gate with specific items to address.

    Args:
        deal_id: Deal identifier.
        gate_number: Gate sequence number.
        reviewer: Name or identifier of the reviewer.
        rejection_items: List of items (from gate.items) that need remediation.
        notes: Optional rejection notes with remediation guidance.
        output_base: Base directory for outputs.

    Returns:
        Updated gate record.

    Raises:
        FileNotFoundError: If gate doesn't exist.
    """
    gate = _load_gate(deal_id, gate_number, output_base)
    if not gate:
        raise FileNotFoundError(
            f"Gate {gate_number} not found for deal {deal_id}"
        )

    now = datetime.utcnow().isoformat() + "Z"
    gate["status"] = "rejected"
    gate["reviewed_at"] = now
    gate["reviewer"] = reviewer
    gate["rejection_items"] = rejection_items
    gate["approval_notes"] = notes

    # Mark rejected items in the items list
    for item in gate.get("items", []):
        if item.get("title") in rejection_items or item.get("description") in rejection_items:
            item["status"] = "rejected_requires_action"

    _save_gate(deal_id, gate_number, gate, output_base)
    logger.info(
        "Rejected gate %d for deal %s by %s (items to address: %d)",
        gate_number,
        deal_id,
        reviewer,
        len(rejection_items)
    )

    return gate


def get_gate_status(
    deal_id: str,
    gate_number: int = 0,
    output_base: str = "outputs",
) -> dict:
    """
    Get gate status for a deal.

    Args:
        deal_id: Deal identifier.
        gate_number: Specific gate number (1, 2, 3, ...).
                    If 0, returns status of all gates for the deal.
        output_base: Base directory for outputs.

    Returns:
        If gate_number > 0: Single gate record
        If gate_number == 0: Dict with keys "gates" (list of all gates) and "summary"
    """
    if gate_number > 0:
        gate = _load_gate(deal_id, gate_number, output_base)
        if not gate:
            return {"error": f"Gate {gate_number} not found for deal {deal_id}"}
        return gate

    # Return all gates for this deal
    deal_output_dir = Path(output_base) / deal_id
    if not deal_output_dir.exists():
        return {"gates": [], "summary": {"total_gates": 0, "pending": 0, "approved": 0, "rejected": 0}}

    gates = []
    for gate_file in sorted(deal_output_dir.glob("feedback_gate*.json")):
        try:
            with open(gate_file) as f:
                gate = json.load(f)
                gates.append(gate)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Could not load gate from %s: %s", gate_file, e)

    # Compute summary
    summary = {
        "total_gates": len(gates),
        "pending": sum(1 for g in gates if g.get("status") == "pending"),
        "approved": sum(1 for g in gates if g.get("status") == "approved"),
        "rejected": sum(1 for g in gates if g.get("status") == "rejected"),
    }

    return {"gates": gates, "summary": summary}


def _save_gate(
    deal_id: str,
    gate_number: int,
    gate_record: dict,
    output_base: str,
) -> None:
    """
    Save a gate record to disk.

    Args:
        deal_id: Deal identifier.
        gate_number: Gate sequence number.
        gate_record: Gate dict to save.
        output_base: Base directory for outputs.
    """
    deal_output_dir = Path(output_base) / deal_id
    deal_output_dir.mkdir(parents=True, exist_ok=True)

    gate_file = deal_output_dir / f"feedback_gate{gate_number}.json"
    try:
        with open(gate_file, "w") as f:
            json.dump(gate_record, f, indent=2)
        logger.debug("Saved gate to %s", gate_file)
    except OSError as e:
        logger.error("Failed to save gate to %s: %s", gate_file, e)
        raise


def _load_gate(
    deal_id: str,
    gate_number: int,
    output_base: str,
) -> Optional[dict]:
    """
    Load a gate record from disk.

    Args:
        deal_id: Deal identifier.
        gate_number: Gate sequence number.
        output_base: Base directory for outputs.

    Returns:
        Gate dict, or None if not found or error occurs.
    """
    gate_file = Path(output_base) / deal_id / f"feedback_gate{gate_number}.json"
    if not gate_file.exists():
        return None

    try:
        with open(gate_file) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Could not load gate from %s: %s", gate_file, e)
        return None
