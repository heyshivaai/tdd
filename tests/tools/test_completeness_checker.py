import pytest
from tools.completeness_checker import check_completeness, generate_request_language


def test_check_completeness_returns_correct_shape(sample_expected_docs):
    inventory = [
        {"filename": "soc2_report_2024.pdf", "vdr_section": "Security",
         "batch_group": "security_compliance", "size_bytes": 5000},
    ]
    result = check_completeness(
        inventory=inventory,
        expected_docs=sample_expected_docs,
        sector="healthcare-saas",
        deal_type="pe-acquisition",
        deal_id="DEAL-001",
    )
    assert "deal_id" in result
    assert "missing_documents" in result
    assert "present_but_incomplete" in result
    assert "completeness_score" in result
    assert "chase_list_summary" in result


def test_missing_pen_test_detected(sample_expected_docs):
    inventory = [
        {"filename": "soc2_report_2024.pdf", "vdr_section": "Security",
         "batch_group": "security_compliance", "size_bytes": 5000},
    ]
    result = check_completeness(
        inventory=inventory,
        expected_docs=sample_expected_docs,
        sector="healthcare-saas",
        deal_type="pe-acquisition",
        deal_id="DEAL-001",
    )
    gap_names = [g["expected_document"] for g in result["missing_documents"]]
    assert any("pen" in name.lower() or "penetration" in name.lower() for name in gap_names)


def test_completeness_score_is_between_0_and_100(sample_expected_docs):
    inventory = []
    result = check_completeness(
        inventory=inventory,
        expected_docs=sample_expected_docs,
        sector="healthcare-saas",
        deal_type="pe-acquisition",
        deal_id="DEAL-001",
    )
    assert 0 <= result["completeness_score"] <= 100


def test_full_inventory_gives_high_score(sample_expected_docs):
    expected = sample_expected_docs["pe-acquisition"]["healthcare-saas"]
    inventory = [
        {"filename": doc["name"].lower().replace(" ", "_").replace("—", "").replace("(", "").replace(")", "") + ".pdf",
         "vdr_section": "Security", "batch_group": "general", "size_bytes": 1000}
        for doc in expected
    ]
    result = check_completeness(
        inventory=inventory,
        expected_docs=sample_expected_docs,
        sector="healthcare-saas",
        deal_type="pe-acquisition",
        deal_id="DEAL-001",
    )
    assert result["completeness_score"] >= 50


def test_generate_request_language_critical():
    lang = generate_request_language("Penetration test — primary application", "CRITICAL")
    assert len(lang) > 20


def test_generate_request_language_high():
    lang = generate_request_language("Disaster recovery plan", "HIGH")
    assert len(lang) > 20


def test_gap_has_required_fields(sample_expected_docs):
    inventory = []
    result = check_completeness(
        inventory=inventory,
        expected_docs=sample_expected_docs,
        sector="healthcare-saas",
        deal_type="pe-acquisition",
        deal_id="DEAL-001",
    )
    if result["missing_documents"]:
        gap = result["missing_documents"][0]
        assert "gap_id" in gap
        assert "urgency" in gap
        assert "expected_document" in gap
        assert "reason_expected" in gap
        assert "request_language" in gap
