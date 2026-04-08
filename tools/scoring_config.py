"""
Shared scoring constants for the TDD platform.

Centralizes grade thresholds, depth heuristics, and weighting coefficients
so they're defined once and documented in one place.

VDR and DRL thresholds intentionally differ:
  - VDR grading is more lenient (85+ = A) because document completeness
    depends heavily on what the target company has available.
  - DRL grading is stricter (90+ = A) because practitioners control the
    questionnaire response process and should achieve higher completeness.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Grade Thresholds
# ---------------------------------------------------------------------------

# VDR document completeness grading
VDR_GRADE_THRESHOLDS: list[tuple[int, str]] = [
    (85, "A"),
    (70, "B"),
    (55, "C"),
    (40, "D"),
    (0, "F"),
]

# DRL questionnaire response grading (stricter)
DRL_GRADE_THRESHOLDS: list[tuple[int, str, str]] = [
    (90, "A", "Exceptional — ready for deep diligence"),
    (75, "B", "Good — minor gaps, chase list is short"),
    (60, "C", "Adequate — meaningful gaps, targeted follow-up needed"),
    (40, "D", "Incomplete — significant gaps, broad follow-up required"),
    (0,  "F", "Insufficient — not yet usable for diligence"),
]

# Grade display colors (shared across dashboard)
GRADE_COLORS: dict[str, str] = {
    "A": "#15803d",
    "B": "#16a34a",
    "C": "#d97706",
    "D": "#c2410c",
    "F": "#dc2626",
}

GRADE_EMOJI: dict[str, str] = {
    "A": "🟢",
    "B": "🔵",
    "C": "🟡",
    "D": "🟠",
    "F": "🔴",
}

# ---------------------------------------------------------------------------
# Depth Scoring Heuristics (DRL response quality)
# ---------------------------------------------------------------------------

# Character-length thresholds for text response depth scoring
DEPTH_CHAR_THRESHOLDS = {
    "bare_minimum": 20,   # < 20 chars → 0.3 (just a word or two)
    "acceptable": 80,     # 20-80 chars → 0.6 (one sentence)
    # > 80 chars → 1.0 (detailed response)
}

DEPTH_SCORES = {
    "empty": 0.0,
    "bare_minimum": 0.3,
    "acceptable": 0.6,
    "detailed": 1.0,
    "numeric_value": 0.8,  # Concrete data point (number or date)
}

# ---------------------------------------------------------------------------
# DRL Grading Weights
# ---------------------------------------------------------------------------

# Completeness vs depth weighting in composite score
DRL_COMPLETENESS_WEIGHT = 0.5
DRL_DEPTH_WEIGHT = 0.5

# Technology tab depth sub-weights
TECH_DEPTH_WEIGHTS = {
    "dataroom_location": 0.4,
    "comments": 0.3,
    "status": 0.2,
    "date_responded": 0.1,
}

# Census tab completeness sub-weights
CENSUS_HAS_DATA_WEIGHT = 0.3
CENSUS_REQUIRED_COL_WEIGHT = 0.7

# ---------------------------------------------------------------------------
# VDR Grading Weights
# ---------------------------------------------------------------------------

# VDR grade dimensions
VDR_COVERAGE_WEIGHT = 0.35
VDR_DEPTH_WEIGHT = 0.25
VDR_FRESHNESS_WEIGHT = 0.20
VDR_DIVERSITY_WEIGHT = 0.20

# ---------------------------------------------------------------------------
# Version Diff Thresholds
# ---------------------------------------------------------------------------

# Minimum depth change to count as "improved" vs "unchanged"
VERSION_DIFF_DEPTH_THRESHOLD = 0.05

# Gap resolver minimum confidence for a match
GAP_RESOLVE_MIN_CONFIDENCE = 0.3

# Gap resolver scoring weights
GAP_KEYWORD_WEIGHT = 0.6
GAP_BATCH_GROUP_WEIGHT = 0.3
GAP_SECTION_WEIGHT = 0.1


# ---------------------------------------------------------------------------
# Signal Confidence Scoring
# ---------------------------------------------------------------------------


def compute_confidence_summary(signals: list[dict]) -> dict:
    """
    Summarize confidence distribution across a list of signals.

    Used for domain summary and dashboard display. Extracts the LOW and
    unknown-confidence signals so practitioners can see exactly which
    findings need manual verification.

    Args:
        signals: List of signal dicts (each should have a 'confidence' key).

    Returns:
        Dict with total_signals, confidence_counts, low_confidence_count,
        low_confidence_pct, and low_confidence_signals list.
    """
    counts: dict[str, int] = {"HIGH": 0, "MEDIUM": 0, "LOW": 0, "unknown": 0}
    for signal in signals:
        c = signal.get("confidence", "unknown").upper()
        if c in counts:
            counts[c] += 1
        else:
            counts["unknown"] += 1

    total = len(signals)
    low_confidence_signals = [
        s for s in signals
        if s.get("confidence", "").upper() in ("LOW", "") or "confidence" not in s
    ]

    return {
        "total_signals": total,
        "confidence_counts": counts,
        "low_confidence_count": counts["LOW"] + counts["unknown"],
        "low_confidence_pct": round(
            (counts["LOW"] + counts["unknown"]) / total * 100, 1
        ) if total > 0 else 0,
        "low_confidence_signals": low_confidence_signals,
    }
