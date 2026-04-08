import json
import pytest
from pathlib import Path


@pytest.fixture
def sample_pdf_path(tmp_path):
    """Creates a minimal valid PDF in a temp dir for testing."""
    pdf_content = (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n"
        b"4 0 obj\n<< /Length 44 >>\nstream\n"
        b"BT /F1 12 Tf 100 700 Td (Critical finding: open port 22) Tj ET\n"
        b"endstream\nendobj\n"
        b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
        b"xref\n0 6\n0000000000 65535 f\n"
        b"0000000009 00000 n\n0000000058 00000 n\n0000000115 00000 n\n"
        b"0000000266 00000 n\n0000000360 00000 n\n"
        b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n441\n%%EOF"
    )
    pdf_file = tmp_path / "test_pen_test.pdf"
    pdf_file.write_bytes(pdf_content)
    return str(pdf_file)


@pytest.fixture
def temp_vdr_dir(tmp_path):
    """Creates a minimal VDR folder structure for testing."""
    sections = [
        "Product & Technology/Security/Pen Tests",
        "Product & Technology/Security/Compliance",
        "Product & Technology/Infrastructure",
        "Sales & Marketing",
    ]
    for section in sections:
        (tmp_path / section).mkdir(parents=True, exist_ok=True)

    for section in sections:
        pdf = tmp_path / section / "sample_doc.pdf"
        pdf.write_bytes(b"%PDF-1.4\n%%EOF")

    return str(tmp_path)


@pytest.fixture
def sample_batch_rules():
    rules_path = Path(__file__).parent.parent / "data" / "batch_rules.json"
    with open(rules_path) as f:
        return json.load(f)


@pytest.fixture
def sample_expected_docs():
    docs_path = Path(__file__).parent.parent / "data" / "expected_docs.json"
    with open(docs_path) as f:
        return json.load(f)


@pytest.fixture
def sample_batch_result():
    return {
        "batch_id": "security_pen_tests",
        "documents": ["pen_test_external.pdf"],
        "signals": [
            {
                "signal_id": "SIG-001",
                "lens": "Security",
                "rating": "RED",
                "confidence": "HIGH",
                "title": "Critical open findings across pen tests",
                "observation": "External pen test shows 3 critical findings unresolved for 6+ months.",
                "evidence_quote": "Critical finding: open port 22",
                "source_doc": "pen_test_external.pdf",
                "deal_implication": "Unresolved critical vulnerabilities indicate weak remediation culture.",
                "similar_prior_signal_id": None,
            }
        ],
        "batch_summary": "Security pen test batch shows significant open findings.",
    }
