"""
Practitioner Recommender: recommend Crosslake specialist involvement based on findings.

Why: TDD findings span multiple domains (security, engineering, org talent, etc.).
Not all practitioners need to review every deal. This module recommends which
Crosslake specialists should be involved based on the signals and findings,
prioritized by severity and signal volume.

Maps v1.1 signal lenses to Crosslake specialist roles, and scores recommendations
based on RED flags (CRITICAL), signal count (HIGH/MEDIUM), and pillar coverage.
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Mapping: signal lens/domain ID -> specialist role
SPECIALIST_MAPPING = {
    # Security
    "CybersecurityCompliance": "Security & Compliance Lead",
    "ThirdPartyVendorRisk": "Security & Compliance Lead",

    # Engineering
    "TechnologyArchitecture": "Engineering & Architecture Lead",
    "EngineeringDelivery": "Engineering & Architecture Lead",

    # Infrastructure
    "InfrastructureTechnology": "Infrastructure & DevOps Lead",
    "OperationalEfficiency": "Infrastructure & DevOps Lead",

    # Organization & Talent
    "OrganizationTalent": "Org & Talent Specialist",

    # Data & AI
    "DataAIReadiness": "Data & AI Specialist",

    # Product & Strategy
    "ProductCustomerExperience": "Product & Strategy Lead",
    "StrategyRoadmap": "Product & Strategy Lead",

    # Value Creation
    "ValueCreationPotential": "Value Creation Lead",
}


def recommend_specialists(
    findings: dict,
    signal_catalog: Optional[dict] = None,
) -> list[dict]:
    """
    Based on signal findings, recommend which Crosslake specialists to involve.

    Evaluates findings across domains and returns a prioritized list of
    specialists to engage, with reasoning tied to specific signals and flags.

    Args:
        findings: Findings dict with keys: domain_scores, red_flags, yellow_flags,
                 signals (list of signal dicts with keys: lens, title, rating)
        signal_catalog: Optional signal catalog for future enhancement.

    Returns:
        List of specialist recommendation dicts, ordered by priority (CRITICAL first),
        then by domain. Each dict contains:
        {
            "specialist_role": str,
            "reason": str,
            "priority": "CRITICAL" | "HIGH" | "MEDIUM",
            "relevant_signals": [str],  # signal IDs/titles
            "relevant_pillars": [str]   # domain names
        }
    """
    specialists = {}  # role -> recommendation dict

    # Extract signals grouped by lens/domain
    signals_by_lens = _group_signals_by_lens(findings.get("signals", []))

    # Check for RED flags and assign CRITICAL priorities
    red_flags_by_lens = _extract_flags_by_lens(findings.get("red_flags", []))
    for lens, flags in red_flags_by_lens.items():
        specialist = SPECIALIST_MAPPING.get(lens, "General Lead")
        if specialist not in specialists:
            specialists[specialist] = _create_recommendation(
                specialist,
                lens,
                "CRITICAL",
                flags,
                signals_by_lens.get(lens, [])
            )

    # Check for HIGH signal volume (>3) in any domain
    for lens, signals in signals_by_lens.items():
        specialist = SPECIALIST_MAPPING.get(lens, "General Lead")
        if len(signals) > 3 and specialist not in specialists:
            specialists[specialist] = _create_recommendation(
                specialist,
                lens,
                "HIGH",
                [],
                signals
            )
        elif len(signals) > 3 and specialist in specialists:
            # Upgrade if not already CRITICAL
            if specialists[specialist]["priority"] != "CRITICAL":
                specialists[specialist]["priority"] = "HIGH"

    # Check for YELLOW flags and assign MEDIUM priorities
    yellow_flags_by_lens = _extract_flags_by_lens(findings.get("yellow_flags", []))
    for lens, flags in yellow_flags_by_lens.items():
        specialist = SPECIALIST_MAPPING.get(lens, "General Lead")
        if specialist not in specialists:
            specialists[specialist] = _create_recommendation(
                specialist,
                lens,
                "MEDIUM",
                flags,
                signals_by_lens.get(lens, [])
            )

    # Sort by priority (CRITICAL, HIGH, MEDIUM) and then by specialist name
    priority_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2}
    sorted_specialists = sorted(
        specialists.values(),
        key=lambda x: (priority_order.get(x["priority"], 3), x["specialist_role"])
    )

    logger.info(
        "Generated %d specialist recommendations",
        len(sorted_specialists)
    )

    return sorted_specialists


def _group_signals_by_lens(signals: list[dict]) -> dict[str, list[dict]]:
    """
    Group signals by their lens/domain.

    Args:
        signals: List of signal dicts (each with "lens" key).

    Returns:
        Dict mapping lens -> list of signal dicts.
    """
    by_lens = {}
    for signal in signals:
        lens = signal.get("lens", "Unknown")
        if lens not in by_lens:
            by_lens[lens] = []
        by_lens[lens].append(signal)
    return by_lens


def _extract_flags_by_lens(flags: list[dict]) -> dict[str, list[dict]]:
    """
    Group flags by their lens/domain.

    Args:
        flags: List of flag dicts (each with "lens" or "domain" key).

    Returns:
        Dict mapping lens -> list of flag dicts.
    """
    by_lens = {}
    for flag in flags:
        # Try both 'lens' and 'domain' keys for flexibility
        lens = flag.get("lens") or flag.get("domain", "Unknown")
        if lens not in by_lens:
            by_lens[lens] = []
        by_lens[lens].append(flag)
    return by_lens


def _create_recommendation(
    specialist_role: str,
    lens: str,
    priority: str,
    flags: list[dict],
    signals: list[dict],
) -> dict:
    """
    Create a specialist recommendation dict.

    Args:
        specialist_role: Name of the specialist role.
        lens: Signal lens/domain ID.
        priority: "CRITICAL", "HIGH", or "MEDIUM".
        flags: List of relevant flags.
        signals: List of relevant signals.

    Returns:
        Recommendation dict.
    """
    # Build reason from flags and signal count
    reasons = []
    if flags:
        reasons.append(
            f"{len(flags)} RED flag(s) in {lens}"
        )
    if len(signals) > 0:
        reasons.append(
            f"{len(signals)} signal(s) detected"
        )

    reason = "; ".join(reasons) if reasons else f"Signals detected in {lens}"

    # Extract signal titles/IDs
    signal_titles = [
        s.get("title") or s.get("signal_id", "Unknown")
        for s in signals[:3]  # Top 3
    ]
    if len(signals) > 3:
        signal_titles.append(f"... +{len(signals) - 3} more")

    # Extract flag titles
    flag_titles = [f.get("title", "") for f in flags[:2]]

    return {
        "specialist_role": specialist_role,
        "reason": reason,
        "priority": priority,
        "relevant_signals": signal_titles + flag_titles,
        "relevant_pillars": [lens],
    }
