import json
import pytest
from unittest.mock import MagicMock
from tools.cross_referencer import cross_reference_signals


BRIEF_RESPONSE = {
    "company_name": "HORIZON",
    "deal_id": "DEAL-001",
    "vdr_scan_timestamp": "2026-03-27T12:00:00Z",
    "overall_signal_rating": "RED",
    "lens_heatmap": {
        "Security": {"rating": "RED", "signal_count": 2, "red_count": 1, "top_signal": "Critical pen test findings"}
    },
    "compound_risks": [
        {
            "risk_id": "CR-01",
            "title": "Unresolved pen test + absent SOC2",
            "contributing_signals": ["SIG-001", "SIG-002"],
            "severity": "CRITICAL",
            "narrative": "Two independent security gaps compound each other.",
        }
    ],
    "prioritized_reading_list": [
        {"rank": 1, "document": "pen_test.pdf", "vdr_section": "Security",
         "reason": "RED signal found", "estimated_read_time_mins": 30,
         "top_signal_preview": "Critical findings"}
    ],
    "domain_slices": {
        "security_slice": {"signals": [], "summary": "High-risk security posture.", "overall_rating": "RED"},
        "infra_slice": {"signals": [], "summary": "Infra posture acceptable.", "overall_rating": "YELLOW"},
        "product_slice": {"signals": [], "summary": "Product signals positive.", "overall_rating": "GREEN"},
    },
    "document_inventory": [
        {"filename": "pen_test.pdf", "vdr_section": "Security", "batch_group": "security_pen_tests",
         "signal_count": 1, "top_rating": "RED"}
    ],
}


def make_mock_client(response_json: dict):
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text=json.dumps(response_json))]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_message
    return mock_client


def test_cross_reference_returns_brief_shape(sample_batch_result):
    client = make_mock_client(BRIEF_RESPONSE)
    inventory = [{"filename": "pen_test.pdf", "vdr_section": "Security",
                  "batch_group": "security_pen_tests", "size_bytes": 1000}]
    gap_report = {"missing_documents": [], "present_but_incomplete": [],
                  "completeness_score": 80, "chase_list_summary": "OK"}

    result = cross_reference_signals(
        all_batch_results=[sample_batch_result],
        inventory=inventory,
        gap_report=gap_report,
        company_name="HORIZON",
        sector="healthcare-saas",
        deal_type="pe-acquisition",
        deal_id="DEAL-001",
        client=client,
    )
    for key in ["company_name", "deal_id", "overall_signal_rating",
                "lens_heatmap", "compound_risks", "prioritized_reading_list",
                "domain_slices", "document_inventory"]:
        assert key in result, f"Missing key: {key}"


def test_cross_reference_has_vdr_scan_timestamp(sample_batch_result):
    client = make_mock_client(BRIEF_RESPONSE)
    inventory = []
    gap_report = {"missing_documents": [], "present_but_incomplete": [],
                  "completeness_score": 100, "chase_list_summary": "OK"}

    result = cross_reference_signals(
        all_batch_results=[sample_batch_result],
        inventory=inventory,
        gap_report=gap_report,
        company_name="HORIZON",
        sector="healthcare-saas",
        deal_type="pe-acquisition",
        deal_id="DEAL-001",
        client=client,
    )
    assert "vdr_scan_timestamp" in result


def test_cross_reference_handles_api_failure(sample_batch_result):
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = Exception("API error")

    inventory = []
    gap_report = {"missing_documents": [], "present_but_incomplete": [],
                  "completeness_score": 100, "chase_list_summary": "OK"}

    result = cross_reference_signals(
        all_batch_results=[sample_batch_result],
        inventory=inventory,
        gap_report=gap_report,
        company_name="HORIZON",
        sector="healthcare-saas",
        deal_type="pe-acquisition",
        deal_id="DEAL-001",
        client=mock_client,
    )
    assert "company_name" in result
    assert result["overall_signal_rating"] in ("RED", "YELLOW", "GREEN", "UNKNOWN")
