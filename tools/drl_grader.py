"""
DRL Grader: Score DRL responses on completeness and depth.

This module grades parsed DRL state on two equally-weighted dimensions:
- Completeness (50%): percentage of fields filled per tab's rules
- Depth (50%): average quality/richness of filled field responses

Composite score is (0.5 × completeness_pct) + (0.5 × depth_normalized_to_100).
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def grade_drl(parsed_state: dict[str, Any]) -> dict[str, Any]:
    """
    Grade DRL responses on completeness and depth, per-tab and overall.

    Takes parsed_state output from drl_parser.parse_drl_excel() and computes:
    - Completeness (50%): % of fields filled per tab's fill rules
    - Depth (50%): average depth_score of filled fields, normalized to 0-100
    - Composite: (0.5 × completeness) + (0.5 × depth_normalized)

    Grade thresholds:
    - A: 85-100 (sufficient to proceed to deep diligence)
    - B: 70-84 (minor gaps, targeted follow-up)
    - C: 55-69 (significant gaps, structured chase needed)
    - D: 40-54 (inadequate, send formal gap notice)
    - F: 0-39 (unusable, escalate to deal lead)

    Args:
        parsed_state: Output dict from drl_parser.parse_drl_excel().

    Returns:
        Dictionary with per-tab scores and overall grade:
        {
            "deal_id": str,
            "version": int,
            "graded_at": ISO timestamp,
            "tab_scores": {
                "technology": {
                    "completeness_pct": float,
                    "depth_score": float,
                    "composite_score": float,
                    "grade": str
                },
                ...
            },
            "overall": {
                "completeness_pct": float,
                "depth_score": float,
                "composite_score": float,
                "grade": str
            }
        }
    """
    from datetime import datetime

    grades_result = {
        "deal_id": parsed_state.get("deal_id", "UNKNOWN"),
        "version": parsed_state.get("version", 1),
        "graded_at": datetime.utcnow().isoformat() + "Z",
        "tab_scores": {},
        "overall": {},
    }

    all_depths = []
    all_completeness = []

    # Grade each tab
    for tab_id, tab_data in parsed_state.get("tabs", {}).items():
        total_fields = tab_data.get("total_fields", 0)
        filled_fields = tab_data.get("filled_fields", 0)
        fields = tab_data.get("fields", [])

        # Completeness: % of fields filled
        completeness_pct = (filled_fields / total_fields * 100) if total_fields > 0 else 0.0

        # Depth: average depth_score of filled fields, normalized to 0-100
        depth_scores = [
            f.get("depth_score", 0) for f in fields if f.get("status") == "ANSWERED"
        ]
        depth_avg = (sum(depth_scores) / len(depth_scores)) if depth_scores else 0.0
        depth_normalized = (depth_avg / 10 * 100) if depth_avg > 0 else 0.0

        # Composite score
        composite_score = (0.5 * completeness_pct) + (0.5 * depth_normalized)

        # Assign grade
        if composite_score >= 85:
            grade = "A"
        elif composite_score >= 70:
            grade = "B"
        elif composite_score >= 55:
            grade = "C"
        elif composite_score >= 40:
            grade = "D"
        else:
            grade = "F"

        grades_result["tab_scores"][tab_id] = {
            "completeness_pct": round(completeness_pct, 1),
            "depth_score": round(depth_avg, 1),
            "composite_score": round(composite_score, 1),
            "grade": grade,
        }

        all_completeness.append(completeness_pct)
        all_depths.append(depth_avg)

        logger.info(
            f"Tab {tab_id}: completeness={completeness_pct:.1f}%, "
            f"depth={depth_avg:.1f}/10, composite={composite_score:.1f}, grade={grade}"
        )

    # Overall grade (average of tab scores)
    overall_completeness = (
        (sum(all_completeness) / len(all_completeness))
        if all_completeness
        else 0.0
    )
    overall_depth = (
        (sum(all_depths) / len(all_depths)) if all_depths else 0.0
    )
    overall_depth_normalized = (overall_depth / 10 * 100) if overall_depth > 0 else 0.0
    overall_composite = (0.5 * overall_completeness) + (0.5 * overall_depth_normalized)

    if overall_composite >= 85:
        overall_grade = "A"
    elif overall_composite >= 70:
        overall_grade = "B"
    elif overall_composite >= 55:
        overall_grade = "C"
    elif overall_composite >= 40:
        overall_grade = "D"
    else:
        overall_grade = "F"

    grades_result["overall"] = {
        "completeness_pct": round(overall_completeness, 1),
        "depth_score": round(overall_depth, 1),
        "composite_score": round(overall_composite, 1),
        "grade": overall_grade,
    }

    logger.info(
        f"Overall grade: {overall_grade} "
        f"(completeness={overall_completeness:.1f}%, depth={overall_depth:.1f}/10)"
    )

    return grades_result


def _get_action_for_grade(grade: str) -> str:
    """
    Get recommended practitioner action for a grade.

    Args:
        grade: Grade letter (A-F).

    Returns:
        Recommended action string.
    """
    actions = {
        "A": "Sufficient to proceed to deep diligence",
        "B": "Minor gaps — targeted follow-up",
        "C": "Significant gaps — structured chase needed",
        "D": "Inadequate — send formal gap notice",
        "F": "Unusable — escalate to deal lead",
    }
    return actions.get(grade, "Unknown")
