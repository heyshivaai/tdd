import json
import pytest
from pathlib import Path
from tools.report_writer import (
    write_intelligence_brief,
    write_triage_report,
    write_completeness_report,
    write_feedback_shell,
)

SAMPLE_BRIEF = {
    "company_name": "HORIZON",
    "deal_id": "DEAL-001",
    "vdr_scan_timestamp": "2026-03-27T12:00:00Z",
    "overall_signal_rating": "RED",
    "lens_heatmap": {
        "Security": {"rating": "RED", "signal_count": 2, "red_count": 1, "top_signal": "Critical pen test findings"}
    },
    "compound_risks": [
        {"risk_id": "CR-01", "title": "Dual security gap", "contributing_signals": ["SIG-001"],
         "severity": "CRITICAL", "narrative": "Pen test + missing SOC2."}
    ],
    "prioritized_reading_list": [
        {"rank": 1, "document": "pen_test.pdf", "vdr_section": "Security",
         "reason": "RED signal", "estimated_read_time_mins": 30, "top_signal_preview": "Critical findings"}
    ],
    "domain_slices": {
        "security_slice": {"signals": [], "summary": "High-risk.", "overall_rating": "RED"},
        "infra_slice": {"signals": [], "summary": "OK.", "overall_rating": "YELLOW"},
        "product_slice": {"signals": [], "summary": "Good.", "overall_rating": "GREEN"},
    },
    "document_inventory": [
        {"filename": "pen_test.pdf", "vdr_section": "Security",
         "batch_group": "security_pen_tests", "signal_count": 1, "top_rating": "RED"}
    ],
}

SAMPLE_COMPLETENESS = {
    "deal_id": "DEAL-001",
    "deal_type": "pe-acquisition",
    "sector": "healthcare-saas",
    "missing_documents": [
        {"gap_id": "GAP-001", "urgency": "CRITICAL", "expected_document": "Pen test",
         "reason_expected": "Standard requirement", "request_language": "Please provide..."}
    ],
    "present_but_incomplete": [],
    "completeness_score": 70,
    "chase_list_summary": "One critical gap found.",
}


def test_write_intelligence_brief_creates_json_file(tmp_path):
    path = write_intelligence_brief(SAMPLE_BRIEF, tmp_path)
    assert path.exists()
    assert path.suffix == ".json"
    loaded = json.loads(path.read_text())
    assert loaded["company_name"] == "HORIZON"


def test_write_triage_report_creates_md_file(tmp_path):
    path = write_triage_report(SAMPLE_BRIEF, tmp_path)
    assert path.exists()
    assert path.suffix == ".md"
    content = path.read_text()
    assert "HORIZON" in content
    assert "RED" in content


def test_write_triage_report_contains_reading_list(tmp_path):
    path = write_triage_report(SAMPLE_BRIEF, tmp_path)
    content = path.read_text()
    assert "pen_test.pdf" in content


def test_write_triage_report_contains_compound_risks(tmp_path):
    path = write_triage_report(SAMPLE_BRIEF, tmp_path)
    content = path.read_text()
    assert "Dual security gap" in content


def test_write_completeness_report_creates_md_file(tmp_path):
    path = write_completeness_report(SAMPLE_COMPLETENESS, tmp_path)
    assert path.exists()
    assert path.suffix == ".md"
    content = path.read_text()
    assert "GAP-001" in content
    assert "CRITICAL" in content


def test_write_feedback_shell_creates_json(tmp_path):
    path = write_feedback_shell(SAMPLE_BRIEF, tmp_path, gate=1)
    assert path.exists()
    assert path.suffix == ".json"
    shell = json.loads(path.read_text())
    assert "deal_id" in shell
    assert "signal_ratings" in shell
    assert isinstance(shell["signal_ratings"], list)
