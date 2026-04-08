import pytest
from unittest.mock import MagicMock, patch
from tools.signal_store import store_signals, query_similar_patterns, update_signal_verdict, store_gap


SAMPLE_SIGNALS = [
    {
        "signal_id": "SIG-001",
        "lens": "Security",
        "rating": "RED",
        "confidence": "HIGH",
        "title": "Critical pen test findings",
        "observation": "3 critical vulnerabilities unresolved.",
        "evidence_quote": "Critical: open port 22",
        "source_doc": "pen_test.pdf",
        "deal_implication": "Weak remediation culture.",
        "similar_prior_signal_id": None,
    }
]


def test_store_signals_returns_count():
    mock_index = MagicMock()
    mock_index.upsert_records.return_value = None
    with patch("tools.signal_store._get_index", return_value=mock_index):
        count = store_signals(SAMPLE_SIGNALS, deal_id="DEAL-001", sector="healthcare-saas")
    assert count == 1


def test_store_signals_builds_record_with_signal_text_field():
    mock_index = MagicMock()
    captured = {}

    def capture_upsert(namespace, records):
        captured["records"] = records

    mock_index.upsert_records.side_effect = capture_upsert
    with patch("tools.signal_store._get_index", return_value=mock_index):
        store_signals(SAMPLE_SIGNALS, deal_id="DEAL-001", sector="healthcare-saas")

    record = captured["records"][0]
    assert "signal_text" in record
    assert record.get("lens") == "Security"
    assert record.get("rating") == "RED"
    assert record.get("deal_id") == "DEAL-001"


def test_store_signals_record_id_includes_deal_and_signal():
    mock_index = MagicMock()
    captured = {}

    def capture_upsert(namespace, records):
        captured["records"] = records

    mock_index.upsert_records.side_effect = capture_upsert
    with patch("tools.signal_store._get_index", return_value=mock_index):
        store_signals(SAMPLE_SIGNALS, deal_id="DEAL-001", sector="healthcare-saas")

    record = captured["records"][0]
    assert "DEAL-001" in record["_id"]
    assert "SIG-001" in record["_id"]


def test_query_similar_patterns_returns_list():
    mock_result = MagicMock()
    mock_hit = MagicMock()
    mock_hit.fields = {
        "signal_text": "Critical pen test findings",
        "lens": "Security",
        "rating": "RED",
        "title": "Critical pen test",
        "deal_id": "DEAL-007",
    }
    mock_result.result.hits = [mock_hit]
    mock_index = MagicMock()
    mock_index.search.return_value = mock_result

    with patch("tools.signal_store._get_index", return_value=mock_index):
        results = query_similar_patterns(
            query_text="pen test vulnerabilities",
            sector="healthcare-saas",
            lens="Security",
            top_k=3,
        )
    assert isinstance(results, list)
    assert len(results) == 1
    assert results[0]["lens"] == "Security"


def test_query_similar_patterns_returns_empty_list_on_error():
    mock_index = MagicMock()
    mock_index.search.side_effect = Exception("Pinecone error")

    with patch("tools.signal_store._get_index", return_value=mock_index):
        results = query_similar_patterns(
            query_text="anything",
            sector="healthcare-saas",
            lens=None,
            top_k=3,
        )
    assert results == []


def test_update_signal_verdict_calls_update():
    mock_index = MagicMock()
    with patch("tools.signal_store._get_index", return_value=mock_index):
        update_signal_verdict(
            deal_id="DEAL-001",
            signal_id="SIG-001",
            verdict="CONFIRMED",
            corrected_rating=None,
        )
    mock_index.update.assert_called_once()


def test_store_gap_upserts_record():
    mock_index = MagicMock()
    captured = {}

    def capture_upsert(namespace, records):
        captured["records"] = records

    mock_index.upsert_records.side_effect = capture_upsert
    gap = {
        "gap_id": "GAP-001",
        "urgency": "CRITICAL",
        "expected_document": "Pen test",
        "reason_expected": "Standard requirement",
        "request_language": "Please provide...",
    }
    with patch("tools.signal_store._get_index", return_value=mock_index):
        store_gap(gap, deal_id="DEAL-001", sector="healthcare-saas")

    assert "records" in captured
    assert len(captured["records"]) == 1
    assert "signal_text" in captured["records"][0]
