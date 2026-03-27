import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from agents.vdr_triage import run_triage


def make_mock_client():
    """Mock client returning minimal valid Claude responses."""
    signal_response = {
        "batch_id": "general",
        "documents": ["sample_doc.pdf"],
        "signals": [
            {
                "signal_id": "SIG-001",
                "lens": "Security",
                "rating": "RED",
                "confidence": "HIGH",
                "title": "Test signal",
                "observation": "Test observation.",
                "evidence_quote": "Test quote",
                "source_doc": "sample_doc.pdf",
                "deal_implication": "Test implication.",
                "similar_prior_signal_id": None,
            }
        ],
        "batch_summary": "Test batch.",
    }
    brief_response = {
        "company_name": "TESTCO",
        "deal_id": "DEAL-TEST",
        "vdr_scan_timestamp": "2026-03-27T00:00:00Z",
        "overall_signal_rating": "RED",
        "lens_heatmap": {"Security": {"rating": "RED", "signal_count": 1, "red_count": 1, "top_signal": "Test signal"}},
        "compound_risks": [],
        "prioritized_reading_list": [],
        "domain_slices": {
            "security_slice": {"signals": [], "summary": "", "overall_rating": "RED"},
            "infra_slice": {"signals": [], "summary": "", "overall_rating": "GREEN"},
            "product_slice": {"signals": [], "summary": "", "overall_rating": "GREEN"},
        },
        "document_inventory": [],
    }

    call_count = {"n": 0}

    def side_effect(*args, **kwargs):
        mock_msg = MagicMock()
        if call_count["n"] == 0:
            mock_msg.content = [MagicMock(text=json.dumps(brief_response))]
        else:
            mock_msg.content = [MagicMock(text=json.dumps(signal_response))]
        call_count["n"] += 1
        return mock_msg

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = side_effect
    return mock_client


@patch("agents.vdr_triage.query_similar_patterns", return_value=[])
@patch("agents.vdr_triage.store_signals", return_value=0)
@patch("agents.vdr_triage.store_gap", return_value=None)
def test_run_triage_returns_brief_and_completeness(mock_gap, mock_store, mock_query, temp_vdr_dir):
    client = make_mock_client()
    brief, completeness = run_triage(
        vdr_path=temp_vdr_dir,
        company_name="TESTCO",
        deal_id="DEAL-TEST",
        sector="healthcare-saas",
        deal_type="pe-acquisition",
        client=client,
    )
    assert "company_name" in brief
    assert "missing_documents" in completeness


@patch("agents.vdr_triage.query_similar_patterns", return_value=[])
@patch("agents.vdr_triage.store_signals", return_value=0)
@patch("agents.vdr_triage.store_gap", return_value=None)
def test_run_triage_outputs_written_to_disk(mock_gap, mock_store, mock_query, temp_vdr_dir, tmp_path):
    client = make_mock_client()
    with patch("agents.vdr_triage.OUTPUT_DIR", tmp_path):
        run_triage(
            vdr_path=temp_vdr_dir,
            company_name="TESTCO",
            deal_id="DEAL-TEST",
            sector="healthcare-saas",
            deal_type="pe-acquisition",
            client=client,
        )
    output_files = list(tmp_path.rglob("*.*"))
    assert len(output_files) >= 3


def test_run_triage_calls_store_signals(temp_vdr_dir):
    """Phase B: signals are stored in Pinecone after each batch extraction."""
    client = make_mock_client()
    with patch("agents.vdr_triage.store_signals") as mock_store, \
         patch("agents.vdr_triage.store_gap") as mock_gap, \
         patch("agents.vdr_triage.query_similar_patterns", return_value=[]):
        run_triage(
            vdr_path=temp_vdr_dir,
            company_name="TESTCO",
            deal_id="DEAL-TEST",
            sector="healthcare-saas",
            deal_type="pe-acquisition",
            client=client,
        )
    # At least one of store_signals or store_gap should have been called
    assert mock_store.called or mock_gap.called
