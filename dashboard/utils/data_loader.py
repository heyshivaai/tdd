"""
Data loader for the TDD Deal Dashboard.

Loads scan results from the outputs directory and provides constants
for pillar labels, rating colors, and emoji used by the dashboard.
"""
import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

OUTPUTS_DIR = Path(__file__).parent.parent.parent / "outputs"

# ── Pillar display labels ────────────────────────────────────────────────────
# Maps pillar IDs from the v1.3 signal catalog to human-readable labels.
PILLAR_LABELS: dict[str, str] = {
    "TechnologyArchitecture": "Technology & Architecture",
    "SecurityCompliance": "Security & Compliance",
    "ProductEngineering": "Product & Engineering",
    "DataAnalytics": "Data & Analytics",
    "DevOpsReliability": "DevOps & Reliability",
    "TeamOrganization": "Team & Organization",
    "CommercialTechnology": "Commercial Technology",
    # v1.1 backward-compatible lens IDs
    "Architecture": "Architecture",
    "Codebase": "Codebase",
    "Security": "Security",
    "Product": "Product",
    "DevOps": "DevOps",
    "Team": "Team",
    "Data": "Data",
    "Commercial Tech": "Commercial Tech",
}

RATING_COLORS: dict[str, str] = {
    "RED": "#dc2626",
    "YELLOW": "#d97706",
    "GREEN": "#16a34a",
    "UNKNOWN": "#6b7280",
    "NO_DATA": "#9ca3af",
}

RATING_EMOJI: dict[str, str] = {
    "RED": "🔴",
    "YELLOW": "🟡",
    "GREEN": "🟢",
    "UNKNOWN": "⚪",
    "NO_DATA": "⚪",
}


def load_all_deals() -> list[dict]:
    """
    Load all completed deals from the outputs directory.

    Scans each company subfolder for vdr_intelligence_brief.json or
    domain_findings.json to build the deal list.

    Returns:
        List of deal dicts with keys: company, deal_id, rating,
        signal_count, scanned, sector, deal_type.
    """
    deals = []
    if not OUTPUTS_DIR.exists():
        return deals

    for folder in sorted(OUTPUTS_DIR.iterdir()):
        if not folder.is_dir() or folder.name.startswith("_"):
            continue

        brief = _load_json(folder / "vdr_intelligence_brief.json")
        domain_findings = _load_json(folder / "domain_findings.json")

        if not brief and not domain_findings:
            continue

        # Extract deal metadata from whichever source is available
        meta = {}
        if domain_findings:
            meta = domain_findings.get("_metadata", {})

        # Count signals
        signal_count = 0
        if brief:
            heatmap = brief.get("lens_heatmap", brief.get("pillar_heatmap", {}))
            for lens_data in heatmap.values():
                signal_count += lens_data.get("signal_count", 0)

        # Determine rating
        rating = "UNKNOWN"
        if brief:
            rating = brief.get("overall_signal_rating", "UNKNOWN")

        deals.append({
            "company": folder.name,
            "deal_id": brief.get("deal_id", meta.get("deal_id", "")),
            "rating": rating,
            "signal_count": signal_count,
            "scanned": brief.get("vdr_scan_timestamp", meta.get("completed_at", "")),
            "sector": meta.get("sector", brief.get("sector", "")),
            "deal_type": meta.get("deal_type", brief.get("deal_type", "")),
        })

    return deals


def load_brief(company_name: str) -> Optional[dict]:
    """
    Load VDR intelligence brief for a company.

    Args:
        company_name: Company name (subfolder in outputs/).

    Returns:
        Brief dict or None if not found.
    """
    path = OUTPUTS_DIR / company_name / "vdr_intelligence_brief.json"
    brief = _load_json(path)

    # If brief is empty, check for domain_findings
    if not brief:
        domain_findings_path = OUTPUTS_DIR / company_name / "domain_findings.json"
        if domain_findings_path.exists():
            has_domain_data = domain_findings_path.exists()
            if has_domain_data:
                # Return a minimal brief-like structure so dashboard can render
                return _load_json(domain_findings_path)

    return brief


def extract_all_signals(brief: dict) -> list[dict]:
    """
    Extract all signals from a VDR intelligence brief or domain findings.

    Handles both the brief format (lens_heatmap → domain_slices → signals)
    and the domain_findings format (domains → signals via batch results).

    Args:
        brief: VDR intelligence brief or domain findings dict.

    Returns:
        Flat list of signal dicts.
    """
    signals = []

    # Try domain_slices format (from intelligence brief)
    domain_slices = brief.get("domain_slices", {})
    for slice_name, slice_data in domain_slices.items():
        slice_signals = slice_data.get("signals", [])
        # Signals may be dicts or strings
        for sig in slice_signals:
            if isinstance(sig, dict):
                signals.append(sig)
            elif isinstance(sig, str):
                signals.append({
                    "signal_id": "",
                    "title": sig,
                    "pillar_id": slice_name,
                    "rating": slice_data.get("overall_rating", "UNKNOWN"),
                })

    # If no domain_slices, try batch_results format
    if not signals:
        batch_results = brief.get("batch_results", [])
        if isinstance(batch_results, list):
            for batch in batch_results:
                if isinstance(batch, dict):
                    for sig in batch.get("signals", []):
                        if isinstance(sig, dict):
                            signals.append(sig)
        elif isinstance(batch_results, dict):
            for batch_id, batch in batch_results.items():
                if isinstance(batch, dict):
                    for sig in batch.get("signals", []):
                        if isinstance(sig, dict):
                            signals.append(sig)

    return signals


def _load_json(path: Path) -> Optional[dict]:
    """Load a JSON file, returning None on any error."""
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as exc:
        logger.warning("Failed to load %s: %s", path, exc)
        return None
