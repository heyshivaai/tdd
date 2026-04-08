"""
DRL Version Store: Track DRL versions and compute field-level diffs.

This module manages DRL version history and field-level change tracking:
- Stores raw parsed state as drl_state_v{N}.json
- Maintains drl_history.json with version log
- Computes field-level diffs (NEWLY_FILLED, IMPROVED, REGRESSED, UNCHANGED, STILL_EMPTY)
- Generates chase language for critical/high-priority empty fields
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


def store_drl_version(
    deal_id: str, parsed_state: dict[str, Any], grades: dict[str, Any]
) -> dict[str, Any]:
    """
    Store a DRL version and maintain history.

    Saves:
    - drl_state_v{N}.json: raw parsed state from parser
    - drl_history.json: version log with scores and deltas

    Args:
        deal_id: Deal identifier (e.g., 'HORIZON').
        parsed_state: Output from drl_parser.parse_drl_excel().
        grades: Output from drl_grader.grade_drl().

    Returns:
        Dictionary with version info:
        {
            "deal_id": str,
            "version": int,
            "stored_at": ISO timestamp,
            "state_path": str,
            "history_path": str
        }
    """
    # Ensure output directory exists
    output_dir = Path("outputs") / deal_id / "questionnaire"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Determine version number
    history_path = output_dir / "drl_history.json"
    version_num = 1

    if history_path.exists():
        with open(history_path, "r") as f:
            history_data = json.load(f)
        version_num = len(history_data.get("versions", [])) + 1

    # Save raw parsed state
    state_path = output_dir / f"drl_state_v{version_num}.json"
    with open(state_path, "w") as f:
        json.dump(parsed_state, f, indent=2, default=str)
    logger.info(f"Saved DRL state v{version_num} to {state_path}")

    # Build version history entry
    version_entry = {
        "version": version_num,
        "uploaded_at": parsed_state.get("uploaded_at", datetime.utcnow().isoformat() + "Z"),
        "filename": parsed_state.get("source_filename", "unknown.xlsx"),
        "overall_completeness": grades.get("overall", {}).get("completeness_pct", 0.0),
        "overall_depth": grades.get("overall", {}).get("depth_score", 0.0),
        "overall_composite": grades.get("overall", {}).get("composite_score", 0.0),
        "grade": grades.get("overall", {}).get("grade", "F"),
        "tab_scores": grades.get("tab_scores", {}),
    }

    # Load or initialize history
    if history_path.exists():
        with open(history_path, "r") as f:
            history_data = json.load(f)
        previous_version = history_data["versions"][-1] if history_data["versions"] else None
    else:
        history_data = {"deal_id": deal_id, "versions": []}
        previous_version = None

    # Compute delta from previous version if it exists
    if previous_version and version_num > 1:
        delta = {
            "completeness_delta": f"{(version_entry['overall_completeness'] - previous_version['overall_completeness']):+.1f}%",
            "depth_delta": f"{(version_entry['overall_depth'] - previous_version['overall_depth']):+.1f}",
            "composite_delta": f"{(version_entry['overall_composite'] - previous_version['overall_composite']):+.1f}",
        }

        # Compute field-level deltas
        newly_filled = 0
        improved = 0
        regressed = 0
        unchanged = 0
        still_empty = 0

        prev_state_path = output_dir / f"drl_state_v{version_num - 1}.json"
        if prev_state_path.exists():
            with open(prev_state_path, "r") as f:
                prev_state = json.load(f)

            # Compare fields tab by tab
            for tab_id, tab_data in parsed_state.get("tabs", {}).items():
                prev_tab = prev_state.get("tabs", {}).get(tab_id, {})
                for field in tab_data.get("fields", []):
                    field_id = field.get("field_id")
                    prev_field = next(
                        (f for f in prev_tab.get("fields", []) if f.get("field_id") == field_id),
                        None,
                    )

                    if not prev_field:
                        continue

                    prev_status = prev_field.get("status", "EMPTY")
                    new_status = field.get("status", "EMPTY")
                    prev_depth = prev_field.get("depth_score", 0)
                    new_depth = field.get("depth_score", 0)

                    if prev_status == "EMPTY" and new_status == "ANSWERED":
                        newly_filled += 1
                    elif new_status == "ANSWERED" and new_depth > prev_depth:
                        improved += 1
                    elif new_status == "ANSWERED" and new_depth < prev_depth:
                        regressed += 1
                    elif new_status == "ANSWERED" and new_depth == prev_depth:
                        unchanged += 1
                    elif new_status == "EMPTY":
                        still_empty += 1

        delta.update({
            "fields_newly_filled": newly_filled,
            "fields_improved": improved,
            "fields_regressed": regressed,
            "fields_unchanged": unchanged,
            "fields_still_empty": still_empty,
        })
        version_entry["delta_from_previous"] = delta

    history_data["versions"].append(version_entry)

    # Save history
    with open(history_path, "w") as f:
        json.dump(history_data, f, indent=2, default=str)
    logger.info(f"Updated DRL history at {history_path}")

    return {
        "deal_id": deal_id,
        "version": version_num,
        "stored_at": datetime.utcnow().isoformat() + "Z",
        "state_path": str(state_path),
        "history_path": str(history_path),
    }


def get_drl_history(deal_id: str) -> dict[str, Any]:
    """
    Retrieve the full DRL version history for a deal.

    Args:
        deal_id: Deal identifier.

    Returns:
        History data from drl_history.json, or empty structure if not found.
    """
    history_path = Path("outputs") / deal_id / "questionnaire" / "drl_history.json"

    if not history_path.exists():
        logger.warning(f"No history found for deal {deal_id}")
        return {"deal_id": deal_id, "versions": []}

    with open(history_path, "r") as f:
        history = json.load(f)
    logger.info(f"Loaded history for {deal_id}: {len(history['versions'])} versions")
    return history


def compute_field_diff(
    deal_id: str, version_from: int, version_to: int
) -> dict[str, Any]:
    """
    Compute field-level diff between two DRL versions.

    Tracks:
    - NEWLY_FILLED: was EMPTY, now ANSWERED
    - IMPROVED: depth_score increased
    - REGRESSED: depth_score decreased
    - UNCHANGED: same status and depth
    - STILL_EMPTY: remains EMPTY

    Generates chase language for critical/high-priority still-empty fields.

    Args:
        deal_id: Deal identifier.
        version_from: Source version number.
        version_to: Target version number.

    Returns:
        Diff structure:
        {
            "from_version": int,
            "to_version": int,
            "generated_at": ISO timestamp,
            "summary": {
                "fields_newly_filled": int,
                "fields_improved": int,
                "fields_unchanged": int,
                "fields_regressed": int,
                "fields_still_empty": int
            },
            "changes": [
                {
                    "field_id": str,
                    "tab": str,
                    "change_type": str,
                    "old_status": str,
                    "new_status": str,
                    ...
                },
                ...
            ],
            "still_empty": [...]
        }

    Raises:
        FileNotFoundError: If state files not found.
    """
    output_dir = Path("outputs") / deal_id / "questionnaire"

    # Load both versions
    state_from_path = output_dir / f"drl_state_v{version_from}.json"
    state_to_path = output_dir / f"drl_state_v{version_to}.json"

    if not state_from_path.exists() or not state_to_path.exists():
        raise FileNotFoundError(
            f"State files not found for versions {version_from}-{version_to}"
        )

    with open(state_from_path, "r") as f:
        state_from = json.load(f)
    with open(state_to_path, "r") as f:
        state_to = json.load(f)

    diff_result = {
        "from_version": version_from,
        "to_version": version_to,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "summary": {
            "fields_newly_filled": 0,
            "fields_improved": 0,
            "fields_unchanged": 0,
            "fields_regressed": 0,
            "fields_still_empty": 0,
        },
        "changes": [],
        "still_empty": [],
    }

    # Map field urgency based on signal mapping
    urgency_map = {
        "CRITICAL": ["CC-03", "CC-04", "CC-05", "TA-01"],
        "HIGH": ["TA-02", "TA-03", "SA-01", "SA-02"],
        "MEDIUM": ["ED-01", "ED-02", "IT-01", "IT-02"],
    }

    # Compare fields tab by tab
    for tab_id, tab_to in state_to.get("tabs", {}).items():
        tab_from = state_from.get("tabs", {}).get(tab_id, {})

        for field_to in tab_to.get("fields", []):
            field_id = field_to.get("field_id")
            field_from = next(
                (f for f in tab_from.get("fields", []) if f.get("field_id") == field_id),
                None,
            )

            if not field_from:
                # New field in v2
                if field_to.get("status") == "ANSWERED":
                    diff_result["summary"]["fields_newly_filled"] += 1
                    change = {
                        "field_id": field_id,
                        "tab": tab_id,
                        "request": field_to.get("request", ""),
                        "change_type": "NEWLY_FILLED",
                        "old_status": "N/A",
                        "new_status": "ANSWERED",
                        "new_depth_score": field_to.get("depth_score", 0),
                        "dataroom_location": field_to.get("dataroom_location"),
                        "maps_to_signals": field_to.get("maps_to_signals", []),
                    }
                    diff_result["changes"].append(change)
                continue

            old_status = field_from.get("status", "EMPTY")
            new_status = field_to.get("status", "EMPTY")
            old_depth = field_from.get("depth_score", 0)
            new_depth = field_to.get("depth_score", 0)

            # NEWLY_FILLED
            if old_status == "EMPTY" and new_status == "ANSWERED":
                diff_result["summary"]["fields_newly_filled"] += 1
                change = {
                    "field_id": field_id,
                    "tab": tab_id,
                    "request": field_to.get("request", ""),
                    "change_type": "NEWLY_FILLED",
                    "old_status": old_status,
                    "new_status": new_status,
                    "new_depth_score": new_depth,
                    "dataroom_location": field_to.get("dataroom_location"),
                    "maps_to_signals": field_to.get("maps_to_signals", []),
                }
                diff_result["changes"].append(change)

            # IMPROVED
            elif new_status == "ANSWERED" and new_depth > old_depth:
                diff_result["summary"]["fields_improved"] += 1
                change = {
                    "field_id": field_id,
                    "tab": tab_id,
                    "request": field_to.get("request", ""),
                    "change_type": "IMPROVED",
                    "old_depth_score": old_depth,
                    "new_depth_score": new_depth,
                    "improvement_note": f"Depth score increased from {old_depth} to {new_depth}",
                }
                diff_result["changes"].append(change)

            # REGRESSED
            elif new_status == "ANSWERED" and new_depth < old_depth:
                diff_result["summary"]["fields_regressed"] += 1
                change = {
                    "field_id": field_id,
                    "tab": tab_id,
                    "request": field_to.get("request", ""),
                    "change_type": "REGRESSED",
                    "old_depth_score": old_depth,
                    "new_depth_score": new_depth,
                    "regression_note": f"Depth score decreased from {old_depth} to {new_depth}",
                }
                diff_result["changes"].append(change)

            # UNCHANGED
            elif new_status == "ANSWERED" and new_depth == old_depth:
                diff_result["summary"]["fields_unchanged"] += 1

            # STILL_EMPTY
            elif new_status == "EMPTY":
                diff_result["summary"]["fields_still_empty"] += 1
                signals = field_to.get("maps_to_signals", [])
                urgency = "MEDIUM"
                for critical_signal in urgency_map.get("CRITICAL", []):
                    if critical_signal in signals:
                        urgency = "CRITICAL"
                        break
                if urgency != "CRITICAL":
                    for high_signal in urgency_map.get("HIGH", []):
                        if high_signal in signals:
                            urgency = "HIGH"
                            break

                # Generate chase language
                request_text = field_to.get("request", "")
                chase_lang = f"Please provide {request_text.lower() if request_text else field_id}. "
                if urgency == "CRITICAL":
                    chase_lang += "This is a critical requirement for our security assessment."
                elif urgency == "HIGH":
                    chase_lang += "This is a high-priority item for our technical review."
                else:
                    chase_lang += "This information is needed to complete our evaluation."

                still_empty_entry = {
                    "field_id": field_id,
                    "tab": tab_id,
                    "request": request_text,
                    "urgency": urgency,
                    "maps_to_signals": signals,
                    "chase_language": chase_lang,
                }
                diff_result["still_empty"].append(still_empty_entry)

    logger.info(
        f"Diff v{version_from} -> v{version_to}: "
        f"{diff_result['summary']['fields_newly_filled']} filled, "
        f"{diff_result['summary']['fields_improved']} improved, "
        f"{diff_result['summary']['fields_still_empty']} still empty"
    )

    return diff_result


def save_field_diff(deal_id: str, diff_result: dict[str, Any]) -> str:
    """
    Save field diff to disk.

    Args:
        deal_id: Deal identifier.
        diff_result: Output from compute_field_diff().

    Returns:
        Path to saved diff file.
    """
    output_dir = Path("outputs") / deal_id / "questionnaire"
    output_dir.mkdir(parents=True, exist_ok=True)

    v_from = diff_result.get("from_version", 1)
    v_to = diff_result.get("to_version", 2)
    diff_path = output_dir / f"drl_diff_v{v_from}_v{v_to}.json"

    with open(diff_path, "w") as f:
        json.dump(diff_result, f, indent=2, default=str)
    logger.info(f"Saved field diff to {diff_path}")

    return str(diff_path)
