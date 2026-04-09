"""
Practitioner Review Generator: produces a structured review manifest and
inline confidence flags for the Deal Intel surface.

Two gates, both retroactive (no pipeline blocking):
  Gate 1 — Post-VDR Scan: signal-level review (accuracy of extraction)
  Gate 2 — Post-Agent Deep Dive: finding-level review (quality of interpretation)

For each gate the generator produces:
  1. practitioner_review_gate{N}.json — standalone review manifest for the UI
  2. Inline review_required flags merged into the intelligence brief / domain findings

The manifest prioritizes items by review urgency:
  CRITICAL — RED signals, LOW-confidence items, agent-flagged blind spots
  HIGH     — MEDIUM-confidence signals, contradictory findings across agents
  MEDIUM   — YELLOW signals, agents with LOW overall confidence
  LOW      — GREEN signals with HIGH confidence (spot-check only)

Why: Practitioners should not have to read everything. This ranks what to
look at first so a 30-minute review catches 90%+ of the risk surface.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).parent.parent / "outputs"


# ---------------------------------------------------------------------------
# Review urgency classification
# ---------------------------------------------------------------------------

def _classify_signal_urgency(signal: dict) -> str:
    """
    Assign review urgency to a single signal based on rating + confidence.

    Rules:
      RED + any confidence       → CRITICAL
      any rating + LOW/unknown   → CRITICAL
      YELLOW + MEDIUM confidence → HIGH
      YELLOW + HIGH confidence   → MEDIUM
      GREEN + MEDIUM confidence  → MEDIUM
      GREEN + HIGH confidence    → LOW
    """
    rating = signal.get("rating", "").upper()
    confidence = signal.get("confidence", "unknown").upper()

    if rating == "RED":
        return "CRITICAL"
    if confidence in ("LOW", "UNKNOWN", ""):
        return "CRITICAL"
    if rating == "YELLOW" and confidence == "MEDIUM":
        return "HIGH"
    if rating == "YELLOW" and confidence == "HIGH":
        return "MEDIUM"
    if confidence == "MEDIUM":
        return "MEDIUM"
    return "LOW"


def _classify_finding_urgency(finding: dict, agent_confidence: str) -> str:
    """
    Assign review urgency to an agent finding based on severity,
    finding confidence, and the agent's overall confidence level.

    An agent with LOW overall confidence makes ALL its findings at least HIGH urgency.
    """
    severity = finding.get("rating", finding.get("severity", "")).upper()
    confidence = finding.get("confidence", "unknown").upper()

    # Agent-level override: if the agent itself is low-confidence, escalate
    if agent_confidence in ("LOW", "MISSING", ""):
        if severity in ("CRITICAL", "CONCERNING"):
            return "CRITICAL"
        return "HIGH"

    if severity == "CRITICAL":
        return "CRITICAL"
    if confidence in ("LOW", "UNKNOWN", ""):
        return "CRITICAL"
    if severity in ("CONCERNING",) and confidence == "MEDIUM":
        return "HIGH"
    if severity in ("CONCERNING",) and confidence == "HIGH":
        return "MEDIUM"
    if confidence == "MEDIUM":
        return "MEDIUM"
    return "LOW"


# ---------------------------------------------------------------------------
# Gate 1: Signal-level review manifest
# ---------------------------------------------------------------------------

def generate_gate1_manifest(
    intelligence_brief: dict,
    deal_id: str,
    company_name: str,
) -> dict:
    """
    Generate Gate 1 (post-VDR scan) practitioner review manifest.

    Reads signals from the intelligence brief, classifies each by review
    urgency, and produces a prioritized manifest with full traceability.

    Args:
        intelligence_brief: The vdr_intelligence_brief.json dict.
        deal_id: Deal identifier.
        company_name: Company name.

    Returns:
        Review manifest dict with items sorted by urgency.
    """
    signals = intelligence_brief.get("signals", [])
    compound_risks = intelligence_brief.get("compound_risks", [])

    review_items = []

    # Signal-level items
    for sig in signals:
        urgency = _classify_signal_urgency(sig)
        review_items.append({
            "item_id": sig.get("signal_id", ""),
            "item_type": "signal",
            "pillar": sig.get("pillar_id", sig.get("pillar_label", "")),
            "title": sig.get("title", ""),
            "rating": sig.get("rating", ""),
            "confidence": sig.get("confidence", ""),
            "extraction_note": sig.get("extraction_note", ""),
            "evidence_quote": sig.get("evidence_quote", ""),
            "source_doc": sig.get("source_doc", ""),
            "deal_implication": sig.get("deal_implication", ""),
            "review_urgency": urgency,
            "review_reason": _signal_review_reason(sig, urgency),
            # Practitioner fills these:
            "verdict": "",           # CONFIRMED | NOISE | UNCERTAIN
            "corrected_rating": "",  # RED | YELLOW | GREEN (if changed)
            "practitioner_note": "",
            "additional_evidence_source": "",
            "follow_up_owner": "",
        })

    # Compound risk items
    for cr in compound_risks:
        severity = cr.get("severity", "").upper()
        urgency = "CRITICAL" if severity == "CRITICAL" else "HIGH" if severity == "HIGH" else "MEDIUM"
        review_items.append({
            "item_id": cr.get("risk_id", ""),
            "item_type": "compound_risk",
            "pillar": "cross-domain",
            "title": cr.get("title", ""),
            "rating": severity,
            "confidence": "MEDIUM",  # Compound risks are always synthesized
            "extraction_note": "",
            "evidence_quote": cr.get("narrative", ""),
            "source_doc": ", ".join(cr.get("contributing_signals", [])),
            "deal_implication": cr.get("narrative", ""),
            "review_urgency": urgency,
            "review_reason": f"Synthesized compound risk ({severity}) — verify contributing signal interactions",
            "verdict": "",
            "corrected_rating": "",
            "practitioner_note": "",
            "additional_evidence_source": "",
            "follow_up_owner": "",
        })

    # Sort by urgency priority
    urgency_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    review_items.sort(key=lambda x: urgency_order.get(x["review_urgency"], 99))

    # Summary stats
    urgency_counts = {}
    for item in review_items:
        u = item["review_urgency"]
        urgency_counts[u] = urgency_counts.get(u, 0) + 1

    manifest = {
        "deal_id": deal_id,
        "company_name": company_name,
        "gate": 1,
        "gate_label": "Post-VDR Scan",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total_items": len(review_items),
            "urgency_distribution": urgency_counts,
            "signals_reviewed": 0,
            "signals_total": len(signals),
            "completion_pct": 0.0,
        },
        "review_items": review_items,
    }
    return manifest


def _signal_review_reason(signal: dict, urgency: str) -> str:
    """Generate a human-readable reason why this signal needs review."""
    rating = signal.get("rating", "").upper()
    confidence = signal.get("confidence", "unknown").upper()
    note = signal.get("extraction_note", "")

    reasons = []
    if rating == "RED":
        reasons.append("RED-rated signal — verify deal-breaker assessment")
    if confidence in ("LOW", "UNKNOWN", ""):
        reasons.append("LOW confidence — weak evidence, needs manual verification")
    elif confidence == "MEDIUM":
        reasons.append(f"MEDIUM confidence — inferred from context")
    if note:
        reasons.append(f"AI note: {note}")
    if not reasons:
        reasons.append("Spot-check for accuracy")
    return "; ".join(reasons)


# ---------------------------------------------------------------------------
# Gate 2: Finding-level review manifest (post-agent deep dives)
# ---------------------------------------------------------------------------

def generate_gate2_manifest(
    agent_reports: dict[str, dict],
    domain_findings: dict | None,
    deal_id: str,
    company_name: str,
) -> dict:
    """
    Generate Gate 2 (post-agent deep dive) practitioner review manifest.

    Reads findings from all agent reports + domain analysis, classifies
    each by review urgency considering agent-level confidence.

    Args:
        agent_reports: Dict of agent_name -> agent report JSON.
        domain_findings: Optional domain_findings.json dict.
        deal_id: Deal identifier.
        company_name: Company name.

    Returns:
        Review manifest dict with findings, blind spots, and chase questions.
    """
    finding_items = []
    blind_spots = []
    chase_questions = []

    # Process each agent report
    for agent_name, report in agent_reports.items():
        # Navigate to the report's inner structure
        report_key = next(
            (k for k in report.keys() if k.endswith("_intelligence_report") or k.endswith("_report")),
            list(report.keys())[0] if report else None,
        )
        if not report_key:
            continue

        inner = report[report_key]
        metadata = inner.get("metadata", {})
        agent_confidence = metadata.get("overall_confidence", "MISSING").upper()

        # Extract findings from domain_findings within the agent report
        for domain in inner.get("domain_findings", []):
            domain_name = domain.get("domain", "")
            for finding in domain.get("findings", []):
                urgency = _classify_finding_urgency(finding, agent_confidence)
                finding_items.append({
                    "item_id": finding.get("finding_id", ""),
                    "item_type": "agent_finding",
                    "agent": agent_name,
                    "agent_confidence": agent_confidence,
                    "domain": domain_name,
                    "title": finding.get("observation", "")[:120],
                    "severity": finding.get("rating", finding.get("severity", "")),
                    "confidence": finding.get("confidence", ""),
                    "confidence_reason": finding.get("confidence_reason", ""),
                    "evidence": finding.get("evidence", finding.get("evidence_quote", "")),
                    "source_signals": finding.get("source_signals", []),
                    "deal_implication": finding.get("deal_implication", ""),
                    "review_urgency": urgency,
                    "review_reason": _finding_review_reason(
                        finding, agent_name, agent_confidence, urgency,
                    ),
                    # Practitioner fills these:
                    "verdict": "",          # CONFIRMED | NOISE | UNCERTAIN
                    "adjusted_severity": "",
                    "practitioner_note": "",
                    "priority": "",         # P1 | P2 | P3 | P4
                    "remediation_effort": "",  # S | M | L | XL
                    "additional_evidence_source": "",
                    "follow_up_owner": "",
                })

            # Contradictory signals become review items
            for contradiction in domain.get("contradictory_signals", []):
                blind_spots.append({
                    "item_id": f"CONTRA-{agent_name}-{domain_name[:10]}",
                    "item_type": "contradiction",
                    "agent": agent_name,
                    "domain": domain_name,
                    "description": contradiction if isinstance(contradiction, str) else str(contradiction),
                    "review_urgency": "HIGH",
                    "practitioner_note": "",
                    "has_resolution_data": "",  # YES | NO
                    "follow_up_owner": "",
                })

        # Also extract from tasks > task_N > findings (riley, casey, taylor)
        tasks_dict = inner.get("tasks", {})
        if isinstance(tasks_dict, dict) and not finding_items:
            for task_key, task_data in tasks_dict.items():
                if not isinstance(task_data, dict):
                    continue
                task_findings = task_data.get("findings", [])
                if not isinstance(task_findings, list):
                    continue
                task_domain = task_key.replace("task_", "").replace("_", " ").title()
                for finding in task_findings:
                    if not isinstance(finding, dict):
                        continue
                    urgency = _classify_finding_urgency(finding, agent_confidence)
                    finding_items.append({
                        "item_id": finding.get("finding_id", ""),
                        "item_type": "agent_finding",
                        "agent": agent_name,
                        "agent_confidence": agent_confidence,
                        "domain": task_domain,
                        "title": finding.get("observation", finding.get("title", ""))[:120],
                        "severity": finding.get("rating", finding.get("severity", "")),
                        "confidence": finding.get("confidence", ""),
                        "confidence_reason": finding.get("confidence_reason", ""),
                        "evidence": finding.get("evidence", finding.get("evidence_quote", "")),
                        "source_signals": finding.get("source_signals", []),
                        "deal_implication": finding.get("deal_implication", finding.get("business_impact", "")),
                        "review_urgency": urgency,
                        "review_reason": _finding_review_reason(
                            finding, agent_name, agent_confidence, urgency,
                        ),
                        "verdict": "",
                        "adjusted_severity": "",
                        "practitioner_note": "",
                        "priority": "",
                        "remediation_effort": "",
                        "additional_evidence_source": "",
                        "follow_up_owner": "",
                    })

        # Agent-level blind spots
        if agent_confidence in ("LOW", "MISSING"):
            blind_spots.append({
                "item_id": f"AGENT-{agent_name}-LOW",
                "item_type": "agent_blind_spot",
                "agent": agent_name,
                "domain": "Agent-wide",
                "description": (
                    f"Agent '{agent_name}' has {agent_confidence} confidence. "
                    f"Reason: {metadata.get('confidence_notes', 'No data sources available')}"
                ),
                "review_urgency": "CRITICAL",
                "practitioner_note": "",
                "has_resolution_data": "",
                "follow_up_owner": "",
            })

    # Process domain findings (from domain_analyst.py output) if available
    if domain_findings:
        for pillar_id, domain_result in domain_findings.get("domains", {}).items():
            for bs in domain_result.get("blind_spots", []):
                blind_spots.append({
                    "item_id": f"BS-{pillar_id}",
                    "item_type": "domain_blind_spot",
                    "agent": "domain_analyst",
                    "domain": domain_result.get("pillar_label", pillar_id),
                    "description": bs if isinstance(bs, str) else str(bs),
                    "review_urgency": "HIGH",
                    "practitioner_note": "",
                    "has_resolution_data": "",
                    "follow_up_owner": "",
                })

            for q in domain_result.get("questions_for_target", []):
                q_text = q if isinstance(q, str) else q.get("question", str(q))
                q_priority = "medium" if isinstance(q, str) else q.get("priority", "medium")
                chase_questions.append({
                    "item_id": f"CQ-{pillar_id}-{len(chase_questions)+1}",
                    "pillar": pillar_id,
                    "pillar_label": domain_result.get("pillar_label", pillar_id),
                    "question": q_text,
                    "priority": q_priority,
                    # Practitioner fills:
                    "status": "",      # SENT | ANSWERED | NOT_APPLICABLE
                    "answer": "",
                    "follow_up_owner": "",
                })

    # Sort findings by urgency
    urgency_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    finding_items.sort(key=lambda x: urgency_order.get(x["review_urgency"], 99))
    blind_spots.sort(key=lambda x: urgency_order.get(x["review_urgency"], 99))

    # Summary stats
    urgency_counts = {}
    for item in finding_items:
        u = item["review_urgency"]
        urgency_counts[u] = urgency_counts.get(u, 0) + 1

    agent_confidence_map = {}
    for agent_name, report in agent_reports.items():
        report_key = next(
            (k for k in report.keys() if k.endswith("_intelligence_report") or k.endswith("_report")),
            list(report.keys())[0] if report else None,
        )
        if report_key:
            meta = report[report_key].get("metadata", {})
            agent_confidence_map[agent_name] = meta.get("overall_confidence", "MISSING")

    manifest = {
        "deal_id": deal_id,
        "company_name": company_name,
        "gate": 2,
        "gate_label": "Post-Agent Deep Dive",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total_findings": len(finding_items),
            "total_blind_spots": len(blind_spots),
            "total_chase_questions": len(chase_questions),
            "urgency_distribution": urgency_counts,
            "agent_confidence_map": agent_confidence_map,
            "findings_reviewed": 0,
            "completion_pct": 0.0,
        },
        "finding_items": finding_items,
        "blind_spots": blind_spots,
        "chase_questions": chase_questions,
    }
    return manifest


def _finding_review_reason(
    finding: dict, agent_name: str, agent_confidence: str, urgency: str,
) -> str:
    """Generate a human-readable reason why this finding needs review."""
    reasons = []
    if agent_confidence in ("LOW", "MISSING"):
        reasons.append(f"Agent '{agent_name}' has {agent_confidence} confidence — treat as hypothesis")
    severity = finding.get("rating", finding.get("severity", "")).upper()
    if severity == "CRITICAL":
        reasons.append("CRITICAL severity — verify impact assessment")
    confidence = finding.get("confidence", "").upper()
    if confidence in ("LOW", "MEDIUM"):
        reasons.append(f"{confidence} confidence finding")
    reason = finding.get("confidence_reason", "")
    if reason:
        reasons.append(f"AI reasoning: {reason[:80]}")
    if not reasons:
        reasons.append("Spot-check for accuracy")
    return "; ".join(reasons)


# ---------------------------------------------------------------------------
# Save manifests to disk
# ---------------------------------------------------------------------------

def save_review_manifest(manifest: dict, output_dir: Path | None = None) -> Path:
    """
    Write a review manifest to the deal's output folder.

    Args:
        manifest: Gate 1 or Gate 2 manifest dict.
        output_dir: Base outputs dir (defaults to project outputs/).

    Returns:
        Path to the written JSON file.
    """
    base = output_dir or OUTPUT_DIR
    company = manifest.get("company_name", "unknown")
    gate = manifest.get("gate", 0)
    deal_dir = base / company
    deal_dir.mkdir(parents=True, exist_ok=True)

    out_path = deal_dir / f"practitioner_review_gate{gate}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, default=str)
    logger.info("Review manifest (Gate %d) saved to %s", gate, out_path)
    return out_path
