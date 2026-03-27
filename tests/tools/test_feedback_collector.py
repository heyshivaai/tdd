import json
import pytest
from pathlib import Path
from tools.feedback_collector import load_feedback_shell, save_feedback, record_signal_rating


def test_load_feedback_shell_reads_json(tmp_path):
    shell = {
        "deal_id": "DEAL-001", "phase": 0, "gate": 1,
        "practitioner_id": "", "timestamp": "",
        "signal_ratings": [], "phase_accuracy_score": None,
        "missed_signals": [],
        "outcome_data": {
            "deal_outcome": "pending",
            "signals_proved_material": [],
            "signals_proved_immaterial": [],
        },
    }
    f = tmp_path / "feedback_gate1.json"
    f.write_text(json.dumps(shell))
    loaded = load_feedback_shell(str(f))
    assert loaded["deal_id"] == "DEAL-001"


def test_save_feedback_writes_json(tmp_path):
    feedback = {
        "deal_id": "DEAL-001", "phase": 0, "gate": 1,
        "practitioner_id": "shiva", "timestamp": "2026-03-27T12:00:00Z",
        "signal_ratings": [
            {"signal_id": "SIG-001", "verdict": "CONFIRMED",
             "practitioner_note": "", "corrected_rating": None}
        ],
        "phase_accuracy_score": 85,
        "missed_signals": [],
        "outcome_data": {
            "deal_outcome": "pending",
            "signals_proved_material": [],
            "signals_proved_immaterial": [],
        },
    }
    out_path = tmp_path / "feedback_gate1_completed.json"
    save_feedback(feedback, str(out_path))
    assert out_path.exists()
    loaded = json.loads(out_path.read_text())
    assert loaded["practitioner_id"] == "shiva"


def test_record_signal_rating_appends_to_list():
    feedback = {
        "deal_id": "DEAL-001", "phase": 0, "gate": 1,
        "practitioner_id": "", "timestamp": "",
        "signal_ratings": [],
        "phase_accuracy_score": None,
        "missed_signals": [],
        "outcome_data": {
            "deal_outcome": "pending",
            "signals_proved_material": [],
            "signals_proved_immaterial": [],
        },
    }
    updated = record_signal_rating(
        feedback=feedback,
        signal_id="SIG-001",
        verdict="CONFIRMED",
        practitioner_note="Validated in discovery call.",
        corrected_rating=None,
    )
    assert len(updated["signal_ratings"]) == 1
    assert updated["signal_ratings"][0]["verdict"] == "CONFIRMED"
    assert updated["signal_ratings"][0]["signal_id"] == "SIG-001"


def test_record_signal_rating_updates_existing():
    feedback = {
        "deal_id": "DEAL-001", "phase": 0, "gate": 1,
        "practitioner_id": "", "timestamp": "",
        "signal_ratings": [
            {"signal_id": "SIG-001", "verdict": "UNCERTAIN",
             "practitioner_note": "", "corrected_rating": None}
        ],
        "phase_accuracy_score": None,
        "missed_signals": [],
        "outcome_data": {"deal_outcome": "pending", "signals_proved_material": [], "signals_proved_immaterial": []},
    }
    updated = record_signal_rating(
        feedback=feedback,
        signal_id="SIG-001",
        verdict="NOISE",
        practitioner_note="False alarm.",
        corrected_rating=None,
    )
    assert len(updated["signal_ratings"]) == 1
    assert updated["signal_ratings"][0]["verdict"] == "NOISE"
