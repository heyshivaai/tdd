import json
import pytest
from unittest.mock import MagicMock
from tools.signal_extractor import extract_signals_from_batch, _build_prompt


def make_mock_client(response_json: dict):
    """Build a mock anthropic client that returns the given JSON."""
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text=json.dumps(response_json))]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_message
    return mock_client


VALID_BATCH_RESPONSE = {
    "batch_id": "security_pen_tests",
    "documents": ["pen_test.pdf"],
    "signals": [
        {
            "signal_id": "SIG-001",
            "lens": "Security",
            "rating": "RED",
            "confidence": "HIGH",
            "title": "Critical open findings in pen test",
            "observation": "3 critical findings unresolved for 6 months.",
            "evidence_quote": "Critical: open port 22 accessible from internet",
            "source_doc": "pen_test.pdf",
            "deal_implication": "Weak remediation culture poses acquisition risk.",
            "similar_prior_signal_id": None,
        }
    ],
    "batch_summary": "Significant unresolved security vulnerabilities found.",
}


def test_extract_signals_returns_dict_with_signals():
    client = make_mock_client(VALID_BATCH_RESPONSE)
    result = extract_signals_from_batch(
        batch_id="security_pen_tests",
        documents=[{
            "filename": "pen_test.pdf",
            "filepath": "/tmp/pen_test.pdf",
            "vdr_section": "Security",
            "batch_group": "security_pen_tests",
            "size_bytes": 1000,
            "text_chunks": [{"text": "Critical: open port 22", "source_doc": "pen_test.pdf", "chunk_index": 0, "total_chunks": 1}],
        }],
        company_name="HORIZON",
        sector="healthcare-saas",
        deal_type="pe-acquisition",
        prior_patterns=[],
        client=client,
    )
    assert "signals" in result
    assert len(result["signals"]) >= 1


def test_extract_signals_signal_has_required_fields():
    client = make_mock_client(VALID_BATCH_RESPONSE)
    result = extract_signals_from_batch(
        batch_id="security_pen_tests",
        documents=[{
            "filename": "pen_test.pdf",
            "filepath": "/tmp/pen_test.pdf",
            "vdr_section": "Security",
            "batch_group": "security_pen_tests",
            "size_bytes": 1000,
            "text_chunks": [{"text": "test", "source_doc": "pen_test.pdf", "chunk_index": 0, "total_chunks": 1}],
        }],
        company_name="HORIZON",
        sector="healthcare-saas",
        deal_type="pe-acquisition",
        prior_patterns=[],
        client=client,
    )
    signal = result["signals"][0]
    for field in ["signal_id", "lens", "rating", "confidence", "title",
                  "observation", "evidence_quote", "source_doc", "deal_implication"]:
        assert field in signal, f"Missing field: {field}"


def test_build_prompt_includes_company_name():
    prompt = _build_prompt(
        batch_id="security_pen_tests",
        document_list=["pen_test.pdf"],
        company_name="HORIZON",
        sector="healthcare-saas",
        deal_type="pe-acquisition",
        document_text="Some text here.",
        prior_patterns=[],
    )
    assert "HORIZON" in prompt


def test_build_prompt_includes_prior_patterns_when_provided():
    patterns = [{"title": "Prior critical pen test", "lens": "Security", "rating": "RED"}]
    prompt = _build_prompt(
        batch_id="security_pen_tests",
        document_list=["pen_test.pdf"],
        company_name="HORIZON",
        sector="healthcare-saas",
        deal_type="pe-acquisition",
        document_text="Some text here.",
        prior_patterns=patterns,
    )
    assert "Prior critical pen test" in prompt


def test_extract_signals_handles_json_parse_error():
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text="NOT VALID JSON {{{")]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_message

    result = extract_signals_from_batch(
        batch_id="security_pen_tests",
        documents=[{
            "filename": "pen_test.pdf",
            "filepath": "/tmp/pen_test.pdf",
            "vdr_section": "Security",
            "batch_group": "security_pen_tests",
            "size_bytes": 1000,
            "text_chunks": [{"text": "test", "source_doc": "pen_test.pdf", "chunk_index": 0, "total_chunks": 1}],
        }],
        company_name="HORIZON",
        sector="healthcare-saas",
        deal_type="pe-acquisition",
        prior_patterns=[],
        client=mock_client,
    )
    assert "signals" in result
    assert result["signals"] == []
