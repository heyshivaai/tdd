# VDR Auto-Triage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Phase 0 VDR scanning system that inventories a VDR folder, extracts signals across 11 lenses, detects document gaps, and produces three outputs (Intelligence Brief JSON, Triage Report MD, Completeness Report MD) — with a Pinecone Signal Intelligence Layer that compounds learning across engagements.

**Architecture:** A four-step pipeline: Structure Mapper → Document Reader → Signal Extractor (per-batch Claude calls) → Cross-Referencer (single Claude call assembling the brief). Phase A (Tasks 1–9) builds the core pipeline without Pinecone. Phase B (Tasks 10–13) wires in the Signal Intelligence Layer and feedback loop. Each phase is independently runnable and testable.

**Tech Stack:** Python 3.11+, anthropic SDK (`claude-sonnet-4-20250514`), PyPDF2, Typer, Pydantic, pinecone-client, python-dotenv

---

## Phase A: Core Pipeline (Tasks 1–9)

---

### Task 1: Project Foundation

**Files:**
- Modify: `requirements.txt`
- Create: `data/signal_lenses.json`
- Create: `data/batch_rules.json`
- Create: `data/expected_docs.json`
- Create: `tests/conftest.py`

- [ ] **Step 1: Install dependencies**

Run:
```bash
pip install anthropic PyPDF2 typer pydantic python-dotenv pinecone-client pytest
pip freeze | grep -E "anthropic|PyPDF2|typer|pydantic|python-dotenv|pinecone" >> requirements.txt
```

- [ ] **Step 2: Write `data/signal_lenses.json`**

```json
{
  "lenses": [
    { "id": "Architecture",       "description": "Scalability, resilience, modularity, cloud posture" },
    { "id": "Codebase",           "description": "Code quality, technical debt, language/framework choices" },
    { "id": "Security",           "description": "Vulnerabilities, compliance (SOC2, HITRUST, GDPR), data governance" },
    { "id": "Product",            "description": "Roadmap realism, feature velocity, PMF signals" },
    { "id": "DevOps",             "description": "CI/CD maturity, observability, incident response, SLAs" },
    { "id": "Team",               "description": "Structure, seniority mix, key-person risk, hiring velocity" },
    { "id": "Data",               "description": "Data models, quality, pipelines, AI/ML readiness" },
    { "id": "CommercialTech",     "description": "Licensing, vendor lock-in, IP ownership" },
    { "id": "AIMLReadiness",      "description": "AI/ML capabilities, data strategy, model governance" },
    { "id": "RegulatoryCompliance","description": "HIPAA, SOC2, ISO27001, sector-specific compliance posture" },
    { "id": "FinancialCost",      "description": "Infrastructure cost, licensing costs, cost efficiency signals" }
  ]
}
```

- [ ] **Step 3: Write `data/batch_rules.json`**

```json
{
  "rules": [
    { "pattern": "pen test",          "batch_group": "security_pen_tests" },
    { "pattern": "penetration",       "batch_group": "security_pen_tests" },
    { "pattern": "soc 2",             "batch_group": "security_compliance" },
    { "pattern": "soc2",              "batch_group": "security_compliance" },
    { "pattern": "hitrust",           "batch_group": "security_compliance" },
    { "pattern": "information security policy", "batch_group": "security_compliance" },
    { "pattern": "isp",               "batch_group": "security_compliance" },
    { "pattern": "cyber",             "batch_group": "security_posture" },
    { "pattern": "conditional access","batch_group": "security_posture" },
    { "pattern": "backup",            "batch_group": "security_posture" },
    { "pattern": "aws",               "batch_group": "infra_cloud_costs" },
    { "pattern": "cspire",            "batch_group": "infra_cloud_costs" },
    { "pattern": "cloud cost",        "batch_group": "infra_cloud_costs" },
    { "pattern": "data flow",         "batch_group": "infra_architecture" },
    { "pattern": "system architecture","batch_group": "infra_architecture" },
    { "pattern": "monitoring",        "batch_group": "infra_architecture" },
    { "pattern": "disaster recovery", "batch_group": "infra_resilience" },
    { "pattern": "business continuity","batch_group": "infra_resilience" },
    { "pattern": "change management", "batch_group": "infra_resilience" },
    { "pattern": "data retention",    "batch_group": "infra_resilience" },
    { "pattern": "product",           "batch_group": "product_overview" },
    { "pattern": "ai architecture",   "batch_group": "product_overview" },
    { "pattern": "sdlc",              "batch_group": "sdlc_process" },
    { "pattern": "deployment",        "batch_group": "sdlc_process" },
    { "pattern": "open source",       "batch_group": "sdlc_process" },
    { "pattern": "vendor",            "batch_group": "commercial_vendors" },
    { "pattern": "proprietary software","batch_group": "commercial_vendors" },
    { "pattern": "tcpa",              "batch_group": "commercial_vendors" },
    { "pattern": "pipeline",          "batch_group": "sales_market" },
    { "pattern": "gtm",               "batch_group": "sales_market" },
    { "pattern": "pricing",           "batch_group": "sales_market" },
    { "pattern": "nps",               "batch_group": "sales_market" },
    { "pattern": "csat",              "batch_group": "sales_market" }
  ],
  "default_batch_group": "general"
}
```

- [ ] **Step 4: Write `data/expected_docs.json`**

```json
{
  "pe-acquisition": {
    "healthcare-saas": [
      { "id": "ED-001", "name": "Penetration test — primary application",        "urgency": "CRITICAL" },
      { "id": "ED-002", "name": "SOC 2 Type 2 report (within 12 months)",         "urgency": "CRITICAL" },
      { "id": "ED-003", "name": "HIPAA risk assessment",                           "urgency": "CRITICAL" },
      { "id": "ED-004", "name": "Disaster recovery plan",                          "urgency": "HIGH" },
      { "id": "ED-005", "name": "Business continuity plan",                        "urgency": "HIGH" },
      { "id": "ED-006", "name": "Information security policy",                     "urgency": "HIGH" },
      { "id": "ED-007", "name": "System architecture diagram",                     "urgency": "HIGH" },
      { "id": "ED-008", "name": "Data flow diagram (including PHI flows)",         "urgency": "HIGH" },
      { "id": "ED-009", "name": "SDLC documentation",                              "urgency": "MEDIUM" },
      { "id": "ED-010", "name": "Vendor / third-party software list",              "urgency": "MEDIUM" },
      { "id": "ED-011", "name": "Cloud infrastructure cost breakdown",             "urgency": "MEDIUM" },
      { "id": "ED-012", "name": "Org chart — technology team",                     "urgency": "MEDIUM" },
      { "id": "ED-013", "name": "Product roadmap (12-month)",                      "urgency": "MEDIUM" }
    ]
  }
}
```

- [ ] **Step 5: Write `tests/conftest.py`**

```python
import json
import os
import pytest
from pathlib import Path


FIXTURES_DIR = Path(__file__).parent / "fixtures"


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

    # Place a dummy PDF in each section
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
```

- [ ] **Step 6: Verify fixtures load without error**

Run:
```bash
cd C:/Users/itssh/tdd && python -m pytest tests/conftest.py --collect-only -q
```
Expected: `no tests ran` (fixtures only, no test functions yet)

- [ ] **Step 7: Commit**

```bash
git add requirements.txt data/signal_lenses.json data/batch_rules.json data/expected_docs.json tests/conftest.py
git commit -m "feat: project foundation — data files and test fixtures"
```

---

### Task 2: Document Reader

**Files:**
- Create: `tools/document_reader.py`
- Create: `tests/tools/test_document_reader.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/tools/test_document_reader.py`:

```python
import pytest
from pathlib import Path
from tools.document_reader import extract_text_from_pdf, chunk_text


def test_extract_text_returns_list_of_chunks(sample_pdf_path):
    result = extract_text_from_pdf(sample_pdf_path)
    assert isinstance(result, list)
    assert len(result) >= 1


def test_extract_text_chunk_has_required_fields(sample_pdf_path):
    result = extract_text_from_pdf(sample_pdf_path)
    chunk = result[0]
    assert "text" in chunk
    assert "source_doc" in chunk
    assert "chunk_index" in chunk
    assert "total_chunks" in chunk


def test_extract_text_source_doc_is_filename(sample_pdf_path):
    result = extract_text_from_pdf(sample_pdf_path)
    assert result[0]["source_doc"] == Path(sample_pdf_path).name


def test_chunk_text_respects_max_chars():
    long_text = "word " * 10000  # ~50,000 chars
    chunks = chunk_text(long_text, source_doc="test.pdf", max_chars=32000)
    for chunk in chunks:
        assert len(chunk["text"]) <= 32000


def test_chunk_text_preserves_all_content():
    text = "Hello world this is a test document."
    chunks = chunk_text(text, source_doc="test.pdf", max_chars=32000)
    combined = " ".join(c["text"] for c in chunks)
    # All words should appear somewhere in combined output
    for word in text.split():
        assert word in combined


def test_chunk_text_chunk_index_is_sequential():
    long_text = "x " * 20000
    chunks = chunk_text(long_text, source_doc="test.pdf", max_chars=5000)
    for i, chunk in enumerate(chunks):
        assert chunk["chunk_index"] == i
        assert chunk["total_chunks"] == len(chunks)


def test_extract_nonexistent_file_returns_empty_list():
    result = extract_text_from_pdf("/nonexistent/path/file.pdf")
    assert result == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
cd C:/Users/itssh/tdd && python -m pytest tests/tools/test_document_reader.py -v
```
Expected: `ImportError` or `ModuleNotFoundError` — `tools.document_reader` does not exist yet.

- [ ] **Step 3: Implement `tools/document_reader.py`**

```python
"""
Document reader: extracts text from PDF files and chunks them for Claude API calls.

Why: PDFs can be large. We chunk to stay within Claude's context window (max_chars=32000
per chunk). Chunks preserve source metadata so signals can be traced back to their document.
"""
import logging
from pathlib import Path
from typing import List

import PyPDF2

logger = logging.getLogger(__name__)

MAX_CHARS = 32000


def extract_text_from_pdf(filepath: str) -> List[dict]:
    """
    Extract text from a PDF and return as a list of chunks.

    Each chunk is a dict with keys: text, source_doc, chunk_index, total_chunks.
    Returns an empty list if the file cannot be read (logs the error).
    """
    path = Path(filepath)
    if not path.exists():
        logger.warning("PDF not found: %s", filepath)
        return []

    try:
        with open(filepath, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            full_text = "\n".join(
                page.extract_text() or "" for page in reader.pages
            ).strip()
    except Exception as exc:
        logger.error("Failed to read PDF %s: %s", filepath, exc)
        return []

    if not full_text:
        logger.warning("No text extracted from %s", filepath)
        return []

    return chunk_text(full_text, source_doc=path.name)


def chunk_text(text: str, source_doc: str, max_chars: int = MAX_CHARS) -> List[dict]:
    """
    Split text into chunks no larger than max_chars, preserving word boundaries.

    Returns a list of dicts: {text, source_doc, chunk_index, total_chunks}.
    """
    words = text.split()
    chunks: List[str] = []
    current_chunk_words: List[str] = []
    current_length = 0

    for word in words:
        word_len = len(word) + 1  # +1 for space
        if current_length + word_len > max_chars and current_chunk_words:
            chunks.append(" ".join(current_chunk_words))
            current_chunk_words = [word]
            current_length = word_len
        else:
            current_chunk_words.append(word)
            current_length += word_len

    if current_chunk_words:
        chunks.append(" ".join(current_chunk_words))

    total = len(chunks)
    return [
        {
            "text": chunk,
            "source_doc": source_doc,
            "chunk_index": i,
            "total_chunks": total,
        }
        for i, chunk in enumerate(chunks)
    ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
cd C:/Users/itssh/tdd && python -m pytest tests/tools/test_document_reader.py -v
```
Expected: All 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/document_reader.py tests/tools/test_document_reader.py
git commit -m "feat: document reader — PDF extraction and chunking"
```

---

### Task 3: Structure Mapper

**Files:**
- Create: `tools/structure_mapper.py`
- Create: `tests/tools/test_structure_mapper.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/tools/test_structure_mapper.py`:

```python
import os
import pytest
from tools.structure_mapper import map_vdr_structure, assign_batch_group


def test_map_vdr_structure_returns_inventory_and_groups(temp_vdr_dir, sample_batch_rules):
    import json, tempfile
    rules_path = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    json.dump(sample_batch_rules, rules_path)
    rules_path.close()

    result = map_vdr_structure(temp_vdr_dir, rules_path.name)
    assert "inventory" in result
    assert "batch_groups" in result


def test_inventory_contains_pdf_files(temp_vdr_dir, sample_batch_rules):
    import json, tempfile
    rules_path = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    json.dump(sample_batch_rules, rules_path)
    rules_path.close()

    result = map_vdr_structure(temp_vdr_dir, rules_path.name)
    assert len(result["inventory"]) > 0


def test_inventory_item_has_required_fields(temp_vdr_dir, sample_batch_rules):
    import json, tempfile
    rules_path = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    json.dump(sample_batch_rules, rules_path)
    rules_path.close()

    result = map_vdr_structure(temp_vdr_dir, rules_path.name)
    item = result["inventory"][0]
    assert "filename" in item
    assert "filepath" in item
    assert "vdr_section" in item
    assert "batch_group" in item
    assert "size_bytes" in item


def test_assign_batch_group_matches_pen_test():
    rules = [{"pattern": "pen test", "batch_group": "security_pen_tests"}]
    assert assign_batch_group("internal pen test report 2024.pdf", rules, "general") == "security_pen_tests"


def test_assign_batch_group_falls_back_to_default():
    rules = [{"pattern": "pen test", "batch_group": "security_pen_tests"}]
    assert assign_batch_group("annual report.pdf", rules, "general") == "general"


def test_batch_groups_dict_groups_files_by_group(temp_vdr_dir, sample_batch_rules):
    import json, tempfile
    rules_path = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    json.dump(sample_batch_rules, rules_path)
    rules_path.close()

    result = map_vdr_structure(temp_vdr_dir, rules_path.name)
    # All inventory items should appear in batch_groups
    all_grouped = [doc for docs in result["batch_groups"].values() for doc in docs]
    assert len(all_grouped) == len(result["inventory"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
cd C:/Users/itssh/tdd && python -m pytest tests/tools/test_structure_mapper.py -v
```
Expected: `ImportError` — `tools.structure_mapper` does not exist.

- [ ] **Step 3: Implement `tools/structure_mapper.py`**

```python
"""
Structure mapper: walks a VDR folder and builds an inventory of all PDF files,
assigning each file to a batch group based on filename pattern matching.

Why: Before extracting signals, we need to know what exists and which files
belong together (e.g., all pen tests in one batch). Batch grouping gives Claude
cross-document context within a related set.
"""
import json
import os
from pathlib import Path
from typing import List, dict


def map_vdr_structure(vdr_path: str, batch_rules_path: str) -> dict:
    """
    Walk a VDR directory tree and build a document inventory with batch assignments.

    Returns:
        {
            "inventory": List of document dicts (filename, filepath, vdr_section,
                         batch_group, size_bytes),
            "batch_groups": dict mapping batch_group → list of document dicts
        }
    """
    with open(batch_rules_path) as f:
        config = json.load(f)

    rules: List[dict] = config.get("rules", [])
    default_group: str = config.get("default_batch_group", "general")

    root = Path(vdr_path)
    inventory: List[dict] = []

    for filepath in sorted(root.rglob("*.pdf")):
        relative = filepath.relative_to(root)
        vdr_section = str(relative.parent) if relative.parent != Path(".") else "root"
        batch_group = assign_batch_group(filepath.name.lower(), rules, default_group)

        inventory.append(
            {
                "filename": filepath.name,
                "filepath": str(filepath),
                "vdr_section": vdr_section,
                "batch_group": batch_group,
                "size_bytes": filepath.stat().st_size,
            }
        )

    batch_groups: dict[str, List[dict]] = {}
    for doc in inventory:
        group = doc["batch_group"]
        batch_groups.setdefault(group, []).append(doc)

    return {"inventory": inventory, "batch_groups": batch_groups}


def assign_batch_group(filename_lower: str, rules: List[dict], default: str) -> str:
    """
    Match a filename (lowercased) against pattern rules; return first match's batch_group.

    Falls back to default if no rule matches.
    """
    for rule in rules:
        if rule["pattern"] in filename_lower:
            return rule["batch_group"]
    return default
```

- [ ] **Step 4: Fix the type annotation bug before running tests**

Replace `from typing import List, dict` with `from typing import List` in `tools/structure_mapper.py` (built-in `dict` doesn't need importing):

```python
from typing import List
```

- [ ] **Step 5: Run tests to verify they pass**

Run:
```bash
cd C:/Users/itssh/tdd && python -m pytest tests/tools/test_structure_mapper.py -v
```
Expected: All 6 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add tools/structure_mapper.py tests/tools/test_structure_mapper.py
git commit -m "feat: structure mapper — VDR folder walk and batch group assignment"
```

---

### Task 4: Completeness Checker

**Files:**
- Create: `tools/completeness_checker.py`
- Create: `tests/tools/test_completeness_checker.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/tools/test_completeness_checker.py`:

```python
import pytest
from tools.completeness_checker import check_completeness, generate_request_language


def test_check_completeness_returns_correct_shape(sample_expected_docs):
    inventory = [
        {"filename": "soc2_report_2024.pdf", "vdr_section": "Security", "batch_group": "security_compliance", "size_bytes": 5000},
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
    # Inventory has no pen test file
    inventory = [
        {"filename": "soc2_report_2024.pdf", "vdr_section": "Security", "batch_group": "security_compliance", "size_bytes": 5000},
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
    # Build a fake inventory that hits every expected keyword
    inventory = [
        {"filename": doc["name"].lower().replace(" ", "_") + ".pdf",
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
    assert result["completeness_score"] >= 60


def test_generate_request_language_critical():
    lang = generate_request_language("Penetration test — primary application", "CRITICAL")
    assert "penetration" in lang.lower() or "pen test" in lang.lower() or "Penetration" in lang
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
cd C:/Users/itssh/tdd && python -m pytest tests/tools/test_completeness_checker.py -v
```
Expected: `ImportError` — `tools.completeness_checker` does not exist.

- [ ] **Step 3: Implement `tools/completeness_checker.py`**

```python
"""
Completeness checker: compares the VDR document inventory against a list of
expected documents for a given deal type and sector, then generates a gap report
with request language a practitioner can send verbatim.

Why: Identifying missing documents at triage time lets practitioners issue a
targeted request list immediately — saving days of back-and-forth mid-diligence.
"""
from typing import List


REQUEST_TEMPLATES = {
    "CRITICAL": (
        "Please provide {document} as a matter of urgency. "
        "This document is required to complete our security and risk assessment."
    ),
    "HIGH": (
        "Please provide {document} at your earliest convenience. "
        "This is needed to complete our technical review."
    ),
    "MEDIUM": (
        "When available, please share {document} to support our technical due diligence."
    ),
}


def check_completeness(
    inventory: List[dict],
    expected_docs: dict,
    sector: str,
    deal_type: str,
    deal_id: str,
) -> dict:
    """
    Compare document inventory against expected docs for the given deal type + sector.

    Returns the completeness report dict matching the 4.3 data contract.
    """
    expected_list = expected_docs.get(deal_type, {}).get(sector, [])
    inventory_text = " ".join(doc["filename"].lower() for doc in inventory)

    missing: List[dict] = []
    present_count = 0

    for i, expected in enumerate(expected_list):
        doc_name = expected["name"]
        # Heuristic: check if any keyword from the expected doc name appears in inventory filenames
        keywords = [w for w in doc_name.lower().split() if len(w) > 3]
        matched = any(kw in inventory_text for kw in keywords)

        if matched:
            present_count += 1
        else:
            missing.append(
                {
                    "gap_id": f"GAP-{i + 1:03d}",
                    "urgency": expected["urgency"],
                    "expected_document": doc_name,
                    "reason_expected": (
                        f"Standard {deal_type} ({sector}) diligence requires {doc_name}."
                    ),
                    "request_language": generate_request_language(doc_name, expected["urgency"]),
                }
            )

    total = len(expected_list)
    score = int((present_count / total) * 100) if total > 0 else 100
    critical_count = sum(1 for g in missing if g["urgency"] == "CRITICAL")

    summary = (
        f"VDR completeness score: {score}/100. "
        f"{len(missing)} expected document(s) not found, {critical_count} CRITICAL. "
        f"Recommend issuing a document request before proceeding with full diligence."
    )

    return {
        "deal_id": deal_id,
        "deal_type": deal_type,
        "sector": sector,
        "missing_documents": missing,
        "present_but_incomplete": [],  # Phase B: stale-date detection added with signal_store
        "completeness_score": score,
        "chase_list_summary": summary,
    }


def generate_request_language(document_name: str, urgency: str) -> str:
    """
    Generate a practitioner-ready request string for a missing document.

    Uses urgency-keyed templates so CRITICAL gaps read with appropriate weight.
    """
    template = REQUEST_TEMPLATES.get(urgency, REQUEST_TEMPLATES["MEDIUM"])
    return template.format(document=document_name)
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
cd C:/Users/itssh/tdd && python -m pytest tests/tools/test_completeness_checker.py -v
```
Expected: All 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/completeness_checker.py tests/tools/test_completeness_checker.py
git commit -m "feat: completeness checker — gap detection and request language generation"
```

---

### Task 5: Prompts

**Files:**
- Create: `prompts/vdr_signal_extraction.txt`
- Create: `prompts/vdr_cross_reference.txt`
- Create: `prompts/vdr_completeness.txt`

No tests needed for prompt text files — they are tested via integration in Tasks 6 and 7.

- [ ] **Step 1: Write `prompts/vdr_signal_extraction.txt`**

```
You are a technology due diligence analyst at a private equity advisory firm. You are scanning documents from a VDR (Virtual Data Room) to surface deal-relevant signals for a PE acquisition.

COMPANY: {company_name}
SECTOR: {sector}
DEAL TYPE: {deal_type}
BATCH: {batch_id}
DOCUMENTS IN THIS BATCH: {document_list}

{prior_patterns_block}

SIGNAL LENSES (classify each signal under one of these):
Architecture, Codebase, Security, Product, DevOps, Team, Data, CommercialTech, AIMLReadiness, RegulatoryCompliance, FinancialCost

DOCUMENT TEXT:
{document_text}

---

TASK: Extract all deal-relevant signals from the documents above. A signal is an observation that could affect deal value, risk pricing, or remediation cost.

For EACH signal, return a JSON object with this exact shape:
{
  "signal_id": "SIG-NNN",
  "lens": "<one of the 11 lenses>",
  "rating": "RED | YELLOW | GREEN",
  "confidence": "HIGH | MEDIUM | LOW",
  "title": "<10 words max — the finding, not the topic>",
  "observation": "<2-3 sentences — what you found and why it matters>",
  "evidence_quote": "<verbatim quote from source document, max 100 words>",
  "source_doc": "<filename only>",
  "deal_implication": "<1 sentence — so what for the buyer?>",
  "similar_prior_signal_id": "<prior signal ID if matched, else null>"
}

RATING GUIDE:
- RED: Deal-breaker or significant remediation cost (>$500K or 6+ months to fix)
- YELLOW: Meaningful concern, manageable with plan
- GREEN: Positive signal or well-managed area

CONFIDENCE GUIDE:
- HIGH: Clear evidence in quoted text
- MEDIUM: Inferred from context — evidence is suggestive but not explicit
- LOW: Weak signal — noted but uncertain

Return your response as a JSON object:
{
  "batch_id": "{batch_id}",
  "documents": {document_list_json},
  "signals": [ ...signal objects... ],
  "batch_summary": "<2-3 sentences summarising the key findings from this batch>"
}

RULES:
- Every RED and YELLOW signal MUST include a verbatim evidence_quote traceable to the source document
- Do not invent signals not supported by the text
- Do not return generic observations like "security practices should be reviewed" — be specific
- If the documents in this batch contain conflicting information, surface both signals and note the contradiction
- Number signals sequentially from SIG-001 within this batch
```

- [ ] **Step 2: Write `prompts/vdr_cross_reference.txt`**

```
You are a senior technology due diligence analyst synthesising findings from a VDR scan for a PE acquisition.

COMPANY: {company_name}
SECTOR: {sector}
DEAL TYPE: {deal_type}
DEAL ID: {deal_id}

ALL SIGNALS FROM VDR SCAN:
{all_signals_json}

DOCUMENT INVENTORY SUMMARY:
{inventory_summary}

COMPLETENESS GAPS:
{gaps_summary}

---

TASK: Synthesise all signals into a VDR Intelligence Brief. You have four jobs:

1. COMPOUND RISKS: Identify 3-5 risks that span multiple documents or lenses. A compound risk is more serious than any single signal because it appears across independent sources.

2. CONTRADICTIONS: Flag any cases where one document claims X while another implies not-X (e.g., "SOC2 certified" but "critical pen test findings open for 8 months").

3. PRIORITIZED READING LIST: Rank the top 10 documents a practitioner should read first, based on signal density, severity, and gap urgency.

4. DOMAIN SLICES: Produce three independently readable summaries for downstream agents:
   - security_slice: all Security + RegulatoryCompliance signals
   - infra_slice: all Architecture + DevOps + FinancialCost signals
   - product_slice: all Product + AIMLReadiness signals

LENS HEATMAP: For each of the 11 lenses, provide: rating (RED/YELLOW/GREEN), signal_count, red_count, top_signal title.

Return your response as a JSON object matching this exact shape:
{
  "company_name": "{company_name}",
  "deal_id": "{deal_id}",
  "vdr_scan_timestamp": "{timestamp}",
  "overall_signal_rating": "RED | YELLOW | GREEN",
  "lens_heatmap": {
    "<lens_name>": { "rating": "...", "signal_count": N, "red_count": N, "top_signal": "..." }
  },
  "compound_risks": [
    {
      "risk_id": "CR-NN",
      "title": "...",
      "contributing_signals": ["SIG-NNN", ...],
      "severity": "CRITICAL | HIGH | MEDIUM",
      "narrative": "2-3 sentence explanation of why this combination matters"
    }
  ],
  "prioritized_reading_list": [
    {
      "rank": N,
      "document": "filename",
      "vdr_section": "...",
      "reason": "...",
      "estimated_read_time_mins": N,
      "top_signal_preview": "..."
    }
  ],
  "domain_slices": {
    "security_slice": { "signals": [...], "summary": "...", "overall_rating": "..." },
    "infra_slice": { "signals": [...], "summary": "...", "overall_rating": "..." },
    "product_slice": { "signals": [...], "summary": "...", "overall_rating": "..." }
  },
  "document_inventory": [
    {
      "filename": "...",
      "vdr_section": "...",
      "batch_group": "...",
      "signal_count": N,
      "top_rating": "RED | YELLOW | GREEN | NONE"
    }
  ]
}

RULES:
- overall_signal_rating: RED if any compound risk is CRITICAL; YELLOW if any RED signal; GREEN otherwise
- Reading list must contain at least 5 documents; aim for 10
- Every compound risk must reference ≥2 contributing signal IDs from different batch groups
- Domain slices must be independently readable — include enough context so a reader of only the slice understands the picture
```

- [ ] **Step 3: Write `prompts/vdr_completeness.txt`**

```
You are a technology due diligence analyst reviewing the completeness of a VDR for a PE acquisition.

COMPANY: {company_name}
SECTOR: {sector}
DEAL TYPE: {deal_type}
DEAL ID: {deal_id}

DOCUMENT INVENTORY (files present in VDR):
{inventory_json}

EXPECTED DOCUMENTS FOR THIS DEAL TYPE AND SECTOR:
{expected_docs_json}

DOCUMENTS FLAGGED AS PRESENT BUT POTENTIALLY STALE OR INCOMPLETE:
{stale_flags_json}

---

TASK: Identify gaps between what is present and what should be present for a thorough PE technology due diligence in the {sector} sector.

For each missing document:
1. Assess urgency: CRITICAL (blocks diligence), HIGH (needed within 48h), MEDIUM (needed before close)
2. State why this document is expected for this sector/deal type
3. Generate verbatim request language a practitioner could send to the target company

For each present-but-incomplete document:
1. Describe what makes it incomplete (stale date, missing sections, wrong scope)
2. Generate a follow-up request

Return a JSON object:
{
  "deal_id": "{deal_id}",
  "deal_type": "{deal_type}",
  "sector": "{sector}",
  "missing_documents": [
    {
      "gap_id": "GAP-NNN",
      "urgency": "CRITICAL | HIGH | MEDIUM",
      "expected_document": "...",
      "reason_expected": "...",
      "request_language": "..."
    }
  ],
  "present_but_incomplete": [
    {
      "document": "filename",
      "issue": "...",
      "request_language": "..."
    }
  ],
  "completeness_score": N,
  "chase_list_summary": "3-sentence brief: what to ask for, why, and urgency"
}

SCORING: completeness_score = (present_and_adequate / total_expected) * 100
```

- [ ] **Step 4: Verify prompt files exist**

Run:
```bash
ls C:/Users/itssh/tdd/prompts/
```
Expected: `vdr_signal_extraction.txt  vdr_cross_reference.txt  vdr_completeness.txt`

- [ ] **Step 5: Commit**

```bash
git add prompts/vdr_signal_extraction.txt prompts/vdr_cross_reference.txt prompts/vdr_completeness.txt
git commit -m "feat: VDR extraction, cross-reference and completeness prompts"
```

---

### Task 6: Signal Extractor

**Files:**
- Create: `tools/signal_extractor.py`
- Create: `tests/tools/test_signal_extractor.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/tools/test_signal_extractor.py`:

```python
import json
import pytest
from unittest.mock import MagicMock, patch
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
        documents=[{"filename": "pen_test.pdf", "filepath": "/tmp/pen_test.pdf",
                    "vdr_section": "Security", "batch_group": "security_pen_tests",
                    "size_bytes": 1000, "text_chunks": [{"text": "Critical: open port 22", "source_doc": "pen_test.pdf", "chunk_index": 0, "total_chunks": 1}]}],
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
        documents=[{"filename": "pen_test.pdf", "filepath": "/tmp/pen_test.pdf",
                    "vdr_section": "Security", "batch_group": "security_pen_tests",
                    "size_bytes": 1000, "text_chunks": [{"text": "test", "source_doc": "pen_test.pdf", "chunk_index": 0, "total_chunks": 1}]}],
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
        documents=[{"filename": "pen_test.pdf", "filepath": "/tmp/pen_test.pdf",
                    "vdr_section": "Security", "batch_group": "security_pen_tests",
                    "size_bytes": 1000, "text_chunks": [{"text": "test", "source_doc": "pen_test.pdf", "chunk_index": 0, "total_chunks": 1}]}],
        company_name="HORIZON",
        sector="healthcare-saas",
        deal_type="pe-acquisition",
        prior_patterns=[],
        client=mock_client,
    )
    # Should return an empty-signals result, not raise
    assert "signals" in result
    assert result["signals"] == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
cd C:/Users/itssh/tdd && python -m pytest tests/tools/test_signal_extractor.py -v
```
Expected: `ImportError` — `tools.signal_extractor` does not exist.

- [ ] **Step 3: Implement `tools/signal_extractor.py`**

```python
"""
Signal extractor: sends a batch of related VDR documents to Claude and parses
the structured signal output.

Why: Grouping related documents in a single Claude call gives cross-document
context within a batch (e.g., comparing pen test #1 vs pen test #2). One API
call per batch keeps cost manageable while preserving intra-batch intelligence.
"""
import json
import logging
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "vdr_signal_extraction.txt"
MODEL = "claude-sonnet-4-20250514"
MAX_TOKENS = 4096


def extract_signals_from_batch(
    batch_id: str,
    documents: List[dict],
    company_name: str,
    sector: str,
    deal_type: str,
    prior_patterns: List[dict],
    client,
) -> dict:
    """
    Extract signals from a batch of documents using one Claude API call.

    documents: list of inventory dicts, each with a 'text_chunks' key added by the caller.
    prior_patterns: list of similar signal dicts from Pinecone (empty list if Signal
                    Intelligence Layer is not yet wired in Phase A).
    Returns: per-batch signal extraction result dict (4.1 data contract).
    """
    document_list = [doc["filename"] for doc in documents]
    document_text = _assemble_document_text(documents)

    prompt = _build_prompt(
        batch_id=batch_id,
        document_list=document_list,
        company_name=company_name,
        sector=sector,
        deal_type=deal_type,
        document_text=document_text,
        prior_patterns=prior_patterns,
    )

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text
        result = _extract_json(raw)
    except Exception as exc:
        logger.error("Claude API call failed for batch %s: %s", batch_id, exc)
        return {"batch_id": batch_id, "documents": document_list, "signals": [], "batch_summary": ""}

    if not result:
        return {"batch_id": batch_id, "documents": document_list, "signals": [], "batch_summary": ""}

    return result


def _assemble_document_text(documents: List[dict]) -> str:
    """Concatenate all text chunks from all documents in a batch, labelled by source."""
    parts = []
    for doc in documents:
        chunks = doc.get("text_chunks", [])
        if not chunks:
            continue
        doc_text = "\n".join(c["text"] for c in chunks)
        parts.append(f"=== DOCUMENT: {doc['filename']} ===\n{doc_text}")
    return "\n\n".join(parts)


def _build_prompt(
    batch_id: str,
    document_list: List[str],
    company_name: str,
    sector: str,
    deal_type: str,
    document_text: str,
    prior_patterns: List[dict],
) -> str:
    """Fill the signal extraction prompt template."""
    template = PROMPT_PATH.read_text(encoding="utf-8")

    prior_block = ""
    if prior_patterns:
        lines = [
            "PRIOR PATTERNS FROM SIMILAR DEALS (use to calibrate confidence):"
        ]
        for p in prior_patterns[:3]:
            lines.append(
                f"- [{p.get('rating', 'UNKNOWN')}] {p.get('title', '')} "
                f"(lens: {p.get('lens', '')})"
            )
        prior_block = "\n".join(lines)

    return (
        template
        .replace("{company_name}", company_name)
        .replace("{sector}", sector)
        .replace("{deal_type}", deal_type)
        .replace("{batch_id}", batch_id)
        .replace("{document_list}", ", ".join(document_list))
        .replace("{document_list_json}", json.dumps(document_list))
        .replace("{prior_patterns_block}", prior_block)
        .replace("{document_text}", document_text)
    )


def _extract_json(raw: str) -> dict | None:
    """Extract and parse the first JSON object from Claude's response."""
    try:
        # Try direct parse first
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Fall back to finding the first { ... } block
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start == -1 or end == 0:
        logger.error("No JSON object found in response")
        return None
    try:
        return json.loads(raw[start:end])
    except json.JSONDecodeError as exc:
        logger.error("JSON parse failed: %s", exc)
        return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
cd C:/Users/itssh/tdd && python -m pytest tests/tools/test_signal_extractor.py -v
```
Expected: All 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/signal_extractor.py tests/tools/test_signal_extractor.py
git commit -m "feat: signal extractor — per-batch Claude API call with prior pattern injection"
```

---

### Task 7: Cross-Referencer

**Files:**
- Create: `tools/cross_referencer.py`
- Create: `tests/tools/test_cross_referencer.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/tools/test_cross_referencer.py`:

```python
import json
import pytest
from datetime import datetime
from unittest.mock import MagicMock
from tools.cross_referencer import cross_reference_signals


BRIEF_RESPONSE = {
    "company_name": "HORIZON",
    "deal_id": "DEAL-001",
    "vdr_scan_timestamp": "2026-03-27T12:00:00Z",
    "overall_signal_rating": "RED",
    "lens_heatmap": {
        "Security": {"rating": "RED", "signal_count": 2, "red_count": 1, "top_signal": "Critical open pen test findings"}
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
         "top_signal_preview": "Critical open findings"}
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
    # Should return a minimal valid brief, not raise
    assert "company_name" in result
    assert result["overall_signal_rating"] in ("RED", "YELLOW", "GREEN", "UNKNOWN")
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
cd C:/Users/itssh/tdd && python -m pytest tests/tools/test_cross_referencer.py -v
```
Expected: `ImportError`.

- [ ] **Step 3: Implement `tools/cross_referencer.py`**

```python
"""
Cross-referencer: takes all per-batch signal results and calls Claude once to
synthesise compound risks, prioritized reading list, and domain slices into the
VDR Intelligence Brief.

Why: Individual batch extractions have no cross-batch context. This single
aggregation call sees all signals at once and can identify patterns that span
multiple documents and lenses — the most valuable compound intelligence.
"""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "vdr_cross_reference.txt"
MODEL = "claude-sonnet-4-20250514"
MAX_TOKENS = 8192


def cross_reference_signals(
    all_batch_results: List[dict],
    inventory: List[dict],
    gap_report: dict,
    company_name: str,
    sector: str,
    deal_type: str,
    deal_id: str,
    client,
) -> dict:
    """
    Synthesise all batch signals into a VDR Intelligence Brief via one Claude call.

    Returns the brief dict matching the 4.2 data contract.
    On failure, returns a minimal valid brief so the pipeline can continue.
    """
    all_signals = [sig for batch in all_batch_results for sig in batch.get("signals", [])]
    timestamp = datetime.now(timezone.utc).isoformat()

    prompt = _build_prompt(
        all_signals=all_signals,
        inventory=inventory,
        gap_report=gap_report,
        company_name=company_name,
        sector=sector,
        deal_type=deal_type,
        deal_id=deal_id,
        timestamp=timestamp,
    )

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text
        result = _extract_json(raw)
        if result:
            result.setdefault("vdr_scan_timestamp", timestamp)
            return result
    except Exception as exc:
        logger.error("Cross-reference Claude call failed: %s", exc)

    return _empty_brief(company_name, deal_id, timestamp)


def _build_prompt(
    all_signals: List[dict],
    inventory: List[dict],
    gap_report: dict,
    company_name: str,
    sector: str,
    deal_type: str,
    deal_id: str,
    timestamp: str,
) -> str:
    template = PROMPT_PATH.read_text(encoding="utf-8")
    inventory_summary = json.dumps(
        [{"filename": d["filename"], "section": d["vdr_section"]} for d in inventory],
        indent=2,
    )
    gaps_summary = json.dumps(gap_report.get("missing_documents", [])[:10], indent=2)

    return (
        template
        .replace("{company_name}", company_name)
        .replace("{sector}", sector)
        .replace("{deal_type}", deal_type)
        .replace("{deal_id}", deal_id)
        .replace("{timestamp}", timestamp)
        .replace("{all_signals_json}", json.dumps(all_signals, indent=2))
        .replace("{inventory_summary}", inventory_summary)
        .replace("{gaps_summary}", gaps_summary)
    )


def _extract_json(raw: str) -> dict | None:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start == -1 or end == 0:
        return None
    try:
        return json.loads(raw[start:end])
    except json.JSONDecodeError:
        return None


def _empty_brief(company_name: str, deal_id: str, timestamp: str) -> dict:
    return {
        "company_name": company_name,
        "deal_id": deal_id,
        "vdr_scan_timestamp": timestamp,
        "overall_signal_rating": "UNKNOWN",
        "lens_heatmap": {},
        "compound_risks": [],
        "prioritized_reading_list": [],
        "domain_slices": {
            "security_slice": {"signals": [], "summary": "", "overall_rating": "UNKNOWN"},
            "infra_slice": {"signals": [], "summary": "", "overall_rating": "UNKNOWN"},
            "product_slice": {"signals": [], "summary": "", "overall_rating": "UNKNOWN"},
        },
        "document_inventory": [],
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
cd C:/Users/itssh/tdd && python -m pytest tests/tools/test_cross_referencer.py -v
```
Expected: All 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/cross_referencer.py tests/tools/test_cross_referencer.py
git commit -m "feat: cross-referencer — compound risk synthesis and VDR Intelligence Brief"
```

---

### Task 8: Report Writer

**Files:**
- Create: `tools/report_writer.py`
- Create: `tests/tools/test_report_writer.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/tools/test_report_writer.py`:

```python
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
    assert len(shell["signal_ratings"]) == 0  # empty shell — practitioner fills in
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
cd C:/Users/itssh/tdd && python -m pytest tests/tools/test_report_writer.py -v
```
Expected: `ImportError`.

- [ ] **Step 3: Implement `tools/report_writer.py`**

```python
"""
Report writer: renders the three VDR triage outputs (JSON brief, triage MD report,
completeness MD report) and a blank feedback shell from the brief dict.

Why: Separating rendering from computation means the orchestrator only deals with
data; formatting decisions live here and can be iterated without touching logic.
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List

RATING_EMOJI = {"RED": "🔴", "YELLOW": "🟡", "GREEN": "🟢", "UNKNOWN": "⚪", "CRITICAL": "🔴", "HIGH": "🟡", "MEDIUM": "🟠"}


def write_intelligence_brief(brief: dict, output_dir: Path) -> Path:
    """Write the VDR Intelligence Brief JSON to output_dir/<company>/vdr_intelligence_brief.json."""
    company = brief.get("company_name", "UNKNOWN")
    dest = _ensure_company_dir(output_dir, company) / "vdr_intelligence_brief.json"
    dest.write_text(json.dumps(brief, indent=2, ensure_ascii=False), encoding="utf-8")
    return dest


def write_triage_report(brief: dict, output_dir: Path) -> Path:
    """Render the practitioner-facing triage report (heatmap + reading list + compound risks)."""
    company = brief.get("company_name", "UNKNOWN")
    dest = _ensure_company_dir(output_dir, company) / "vdr_triage_report.md"
    dest.write_text(_render_triage_md(brief), encoding="utf-8")
    return dest


def write_completeness_report(completeness: dict, output_dir: Path) -> Path:
    """Render the completeness gap report as Markdown."""
    deal_id = completeness.get("deal_id", "UNKNOWN")
    # Use deal_id as directory if company name not in completeness dict
    dest = output_dir / deal_id / "vdr_completeness_report.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(_render_completeness_md(completeness), encoding="utf-8")
    return dest


def write_feedback_shell(brief: dict, output_dir: Path, gate: int) -> Path:
    """Write an empty practitioner feedback JSON shell for the given gate."""
    company = brief.get("company_name", "UNKNOWN")
    deal_id = brief.get("deal_id", "UNKNOWN")
    dest = _ensure_company_dir(output_dir, company) / f"feedback_gate{gate}.json"
    shell = {
        "deal_id": deal_id,
        "phase": 0,
        "gate": gate,
        "practitioner_id": "",
        "timestamp": "",
        "signal_ratings": [],
        "phase_accuracy_score": None,
        "missed_signals": [],
        "outcome_data": {
            "deal_outcome": "pending",
            "signals_proved_material": [],
            "signals_proved_immaterial": [],
        },
    }
    dest.write_text(json.dumps(shell, indent=2), encoding="utf-8")
    return dest


# --- Private rendering helpers ---

def _ensure_company_dir(output_dir: Path, company: str) -> Path:
    d = output_dir / company
    d.mkdir(parents=True, exist_ok=True)
    return d


def _rating_badge(rating: str) -> str:
    return f"{RATING_EMOJI.get(rating, '⚪')} **{rating}**"


def _render_triage_md(brief: dict) -> str:
    lines: List[str] = []
    company = brief.get("company_name", "UNKNOWN")
    deal_id = brief.get("deal_id", "")
    ts = brief.get("vdr_scan_timestamp", "")
    overall = brief.get("overall_signal_rating", "UNKNOWN")

    lines += [
        f"# VDR Triage Report — {company}",
        f"**Deal ID:** {deal_id}  |  **Scanned:** {ts}  |  **Overall:** {_rating_badge(overall)}",
        "",
        "---",
        "",
        "## Signal Heatmap",
        "",
        "| Lens | Rating | Signals | RED | Top Signal |",
        "|---|---|---|---|---|",
    ]

    for lens, data in brief.get("lens_heatmap", {}).items():
        lines.append(
            f"| {lens} | {_rating_badge(data['rating'])} | "
            f"{data['signal_count']} | {data['red_count']} | {data['top_signal']} |"
        )

    lines += ["", "---", "", "## Compound Risks", ""]
    for risk in brief.get("compound_risks", []):
        sev = risk.get("severity", "")
        lines += [
            f"### {risk['risk_id']}: {risk['title']} — {_rating_badge(sev)}",
            "",
            risk.get("narrative", ""),
            "",
            f"*Contributing signals: {', '.join(risk.get('contributing_signals', []))}*",
            "",
        ]

    lines += ["---", "", "## Prioritized Reading List", ""]
    for item in brief.get("prioritized_reading_list", []):
        lines.append(
            f"{item['rank']}. **{item['document']}** ({item['vdr_section']}) — "
            f"~{item.get('estimated_read_time_mins', '?')} min  \n"
            f"   *{item.get('reason', '')}*  \n"
            f"   Preview: {item.get('top_signal_preview', '')}"
        )
        lines.append("")

    lines += ["---", "", "## Domain Slices", ""]
    for slice_name, slice_data in brief.get("domain_slices", {}).items():
        rating = slice_data.get("overall_rating", "UNKNOWN")
        lines += [
            f"### {slice_name.replace('_', ' ').title()} — {_rating_badge(rating)}",
            "",
            slice_data.get("summary", ""),
            "",
        ]

    return "\n".join(lines)


def _render_completeness_md(report: dict) -> str:
    lines: List[str] = []
    lines += [
        f"# VDR Completeness Report — {report.get('deal_id', '')}",
        f"**Deal Type:** {report.get('deal_type', '')}  |  "
        f"**Sector:** {report.get('sector', '')}  |  "
        f"**Completeness Score:** {report.get('completeness_score', 0)}/100",
        "",
        f"> {report.get('chase_list_summary', '')}",
        "",
        "---",
        "",
        "## Missing Documents",
        "",
        "| Gap ID | Urgency | Expected Document | Request Language |",
        "|---|---|---|---|",
    ]

    for gap in report.get("missing_documents", []):
        urgency_badge = _rating_badge(gap["urgency"])
        lines.append(
            f"| {gap['gap_id']} | {urgency_badge} | "
            f"{gap['expected_document']} | {gap['request_language']} |"
        )

    if report.get("present_but_incomplete"):
        lines += ["", "---", "", "## Present but Incomplete", ""]
        for item in report["present_but_incomplete"]:
            lines += [
                f"**{item['document']}**: {item['issue']}",
                f"> Request: {item['request_language']}",
                "",
            ]

    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
cd C:/Users/itssh/tdd && python -m pytest tests/tools/test_report_writer.py -v
```
Expected: All 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/report_writer.py tests/tools/test_report_writer.py
git commit -m "feat: report writer — JSON brief, triage MD, completeness MD, feedback shell"
```

---

### Task 9: VDR Triage Orchestrator (Phase A)

**Files:**
- Create: `agents/vdr_triage.py`
- Create: `tests/agents/test_vdr_triage.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/agents/test_vdr_triage.py`:

```python
import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from agents.vdr_triage import run_triage


def make_mock_client():
    """Mock client that returns minimal valid Claude responses."""
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
        # First N calls are signal extraction; last is cross-reference
        if call_count["n"] == 0:
            mock_msg.content = [MagicMock(text=json.dumps(brief_response))]
        else:
            mock_msg.content = [MagicMock(text=json.dumps(signal_response))]
        call_count["n"] += 1
        return mock_msg

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = side_effect
    return mock_client


def test_run_triage_returns_brief_and_completeness(temp_vdr_dir):
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


def test_run_triage_outputs_written_to_disk(temp_vdr_dir, tmp_path):
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
    output_files = list(tmp_path.rglob("*"))
    # At least brief JSON, triage report, completeness report, feedback shell
    assert len(output_files) >= 4
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
cd C:/Users/itssh/tdd && python -m pytest tests/agents/test_vdr_triage.py -v
```
Expected: `ImportError`.

- [ ] **Step 3: Implement `agents/vdr_triage.py`**

```python
"""
VDR Triage Agent: orchestrates the four-step Phase 0 pipeline.

Pipeline: Structure Mapper → Document Reader → Signal Extractor (per batch) → Cross-Referencer
Outputs: vdr_intelligence_brief.json, vdr_triage_report.md, vdr_completeness_report.md,
         feedback_gate1.json (empty shell)

Usage:
    python -m agents.vdr_triage --vdr-path "VDR/..." --company HORIZON \\
        --deal-id DEAL-001 --sector healthcare-saas --deal-type pe-acquisition
"""
import logging
import os
from pathlib import Path
from typing import Tuple

import anthropic
import typer
from dotenv import load_dotenv

from tools.completeness_checker import check_completeness
from tools.cross_referencer import cross_reference_signals
from tools.document_reader import extract_text_from_pdf
from tools.report_writer import (
    write_completeness_report,
    write_feedback_shell,
    write_intelligence_brief,
    write_triage_report,
)
from tools.signal_extractor import extract_signals_from_batch
from tools.structure_mapper import map_vdr_structure

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"
OUTPUT_DIR = Path(__file__).parent.parent / "outputs"
BATCH_RULES_PATH = DATA_DIR / "batch_rules.json"
EXPECTED_DOCS_PATH = DATA_DIR / "expected_docs.json"

app = typer.Typer()


def run_triage(
    vdr_path: str,
    company_name: str,
    deal_id: str,
    sector: str,
    deal_type: str,
    client,
) -> Tuple[dict, dict]:
    """
    Execute the full Phase 0 VDR triage pipeline.

    Returns (intelligence_brief, completeness_report) as dicts.
    All three output files + feedback shell are written to outputs/<company_name>/.
    """
    import json

    logger.info("Step 1: Mapping VDR structure — %s", vdr_path)
    vdr_map = map_vdr_structure(vdr_path, str(BATCH_RULES_PATH))
    inventory = vdr_map["inventory"]
    batch_groups = vdr_map["batch_groups"]
    logger.info("Inventory: %d files across %d batch groups", len(inventory), len(batch_groups))

    logger.info("Step 2: Checking completeness")
    with open(EXPECTED_DOCS_PATH) as f:
        expected_docs = json.load(f)
    completeness = check_completeness(
        inventory=inventory,
        expected_docs=expected_docs,
        sector=sector,
        deal_type=deal_type,
        deal_id=deal_id,
    )
    logger.info("Completeness score: %d/100 — %d gaps found",
                completeness["completeness_score"], len(completeness["missing_documents"]))

    logger.info("Step 3: Extracting text and running signal extraction per batch")
    all_batch_results = []
    for batch_id, docs in batch_groups.items():
        enriched_docs = []
        for doc in docs:
            chunks = extract_text_from_pdf(doc["filepath"])
            enriched_docs.append({**doc, "text_chunks": chunks})

        logger.info("  Batch %s: %d docs, %d chunks",
                    batch_id, len(docs),
                    sum(len(d["text_chunks"]) for d in enriched_docs))

        batch_result = extract_signals_from_batch(
            batch_id=batch_id,
            documents=enriched_docs,
            company_name=company_name,
            sector=sector,
            deal_type=deal_type,
            prior_patterns=[],  # Phase B: Pinecone query injected here
            client=client,
        )
        all_batch_results.append(batch_result)
        signal_count = len(batch_result.get("signals", []))
        logger.info("  Batch %s: %d signals extracted", batch_id, signal_count)

    logger.info("Step 4: Cross-referencing signals into VDR Intelligence Brief")
    brief = cross_reference_signals(
        all_batch_results=all_batch_results,
        inventory=inventory,
        gap_report=completeness,
        company_name=company_name,
        sector=sector,
        deal_type=deal_type,
        deal_id=deal_id,
        client=client,
    )

    logger.info("Writing outputs")
    write_intelligence_brief(brief, OUTPUT_DIR)
    write_triage_report(brief, OUTPUT_DIR)
    write_completeness_report(completeness, OUTPUT_DIR)
    write_feedback_shell(brief, OUTPUT_DIR, gate=1)

    logger.info(
        "Triage complete. Overall rating: %s | Signals: %d | Gaps: %d",
        brief.get("overall_signal_rating"),
        sum(len(b.get("signals", [])) for b in all_batch_results),
        len(completeness["missing_documents"]),
    )
    return brief, completeness


@app.command()
def main(
    vdr_path: str = typer.Option(..., help="Path to VDR root folder"),
    company: str = typer.Option(..., help="Company name (used for output folder)"),
    deal_id: str = typer.Option(..., help="Deal identifier (e.g. DEAL-001)"),
    sector: str = typer.Option(..., help="Sector slug (e.g. healthcare-saas)"),
    deal_type: str = typer.Option(..., help="Deal type (e.g. pe-acquisition)"),
) -> None:
    """Run VDR Auto-Triage for a PE deal."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        typer.echo("ERROR: ANTHROPIC_API_KEY not set in environment", err=True)
        raise typer.Exit(1)

    client = anthropic.Anthropic(api_key=api_key)
    run_triage(
        vdr_path=vdr_path,
        company_name=company,
        deal_id=deal_id,
        sector=sector,
        deal_type=deal_type,
        client=client,
    )


if __name__ == "__main__":
    app()
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
cd C:/Users/itssh/tdd && python -m pytest tests/agents/test_vdr_triage.py -v
```
Expected: Both tests PASS.

- [ ] **Step 5: Run full Phase A test suite**

Run:
```bash
cd C:/Users/itssh/tdd && python -m pytest tests/ -v --tb=short
```
Expected: All tests PASS with no errors.

- [ ] **Step 6: Commit**

```bash
git add agents/vdr_triage.py tests/agents/test_vdr_triage.py
git commit -m "feat: VDR triage orchestrator — Phase A pipeline complete"
```

---

## Phase B: Signal Intelligence Layer (Tasks 10–13)

---

### Task 10: Signal Store (Pinecone)

**Files:**
- Create: `tools/signal_store.py`
- Create: `tests/tools/test_signal_store.py`

- [ ] **Step 1: Check Pinecone index exists**

Run:
```bash
python -c "
from pinecone import Pinecone
import os
from dotenv import load_dotenv
load_dotenv()
pc = Pinecone(api_key=os.environ['PINECONE_API_KEY'])
indexes = pc.list_indexes()
print([i.name for i in indexes])
"
```
Expected output includes `tdd-signals`. If not, create it:
```bash
python -c "
from pinecone import Pinecone
import os
from dotenv import load_dotenv
load_dotenv()
pc = Pinecone(api_key=os.environ['PINECONE_API_KEY'])
pc.create_index_for_model(
    name='tdd-signals',
    cloud='aws',
    region='us-east-1',
    embed={
        'model': 'multilingual-e5-large',
        'field_map': {'text': 'signal_text'}
    }
)
print('Index created')
"
```

- [ ] **Step 2: Write the failing tests**

Create `tests/tools/test_signal_store.py`:

```python
import pytest
from unittest.mock import MagicMock, patch
from tools.signal_store import store_signals, query_similar_patterns, update_signal_verdict


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


def test_store_signals_builds_record_with_text_field():
    mock_index = MagicMock()
    captured = {}

    def capture_upsert(namespace, records):
        captured["records"] = records

    mock_index.upsert_records.side_effect = capture_upsert
    with patch("tools.signal_store._get_index", return_value=mock_index):
        store_signals(SAMPLE_SIGNALS, deal_id="DEAL-001", sector="healthcare-saas")

    record = captured["records"][0]
    assert "signal_text" in record
    assert "SIG-001" in record["signal_text"] or "Critical pen test" in record["signal_text"]
    assert record.get("lens") == "Security"
    assert record.get("rating") == "RED"


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
```

- [ ] **Step 3: Run tests to verify they fail**

Run:
```bash
cd C:/Users/itssh/tdd && python -m pytest tests/tools/test_signal_store.py -v
```
Expected: `ImportError`.

- [ ] **Step 4: Implement `tools/signal_store.py`**

```python
"""
Signal store: reads and writes signals to the Pinecone `tdd-signals` integrated index.

Why: Every signal extracted across all deals and all phases is stored here.
Before each Claude call, the caller queries this store to inject prior patterns
that match the current sector and lens. Practitioner feedback updates verdicts
so the system calibrates over time.

Index: tdd-signals (multilingual-e5-large integrated, field_map: signal_text → embedding)
Namespace: deals
"""
import logging
import os
from typing import List

from dotenv import load_dotenv
from pinecone import Pinecone

load_dotenv()
logger = logging.getLogger(__name__)

INDEX_NAME = "tdd-signals"
NAMESPACE = "deals"


def _get_index():
    """Return a Pinecone index handle. Initialised fresh each call (connection is lightweight)."""
    pc = Pinecone(api_key=os.environ["PINECONE_API_KEY"])
    return pc.Index(INDEX_NAME)


def store_signals(signals: List[dict], deal_id: str, sector: str, phase: int = 0) -> int:
    """
    Embed and upsert all signals from a batch into Pinecone.

    The text field (`signal_text`) is what gets embedded by the integrated model.
    Returns count of records upserted.
    """
    index = _get_index()
    records = []
    for sig in signals:
        signal_text = (
            f"{sig.get('signal_id', '')} | {sig.get('title', '')} | "
            f"{sig.get('observation', '')} | {sig.get('evidence_quote', '')}"
        )
        record = {
            "_id": f"{deal_id}_{sig['signal_id']}",
            "signal_text": signal_text,
            "lens": sig.get("lens", ""),
            "rating": sig.get("rating", ""),
            "confidence": sig.get("confidence", ""),
            "title": sig.get("title", ""),
            "deal_id": deal_id,
            "sector": sector,
            "phase": phase,
            "source_doc": sig.get("source_doc", ""),
            "deal_implication": sig.get("deal_implication", ""),
            "practitioner_verdict": "",
            "outcome_material": "",
        }
        records.append(record)

    if records:
        index.upsert_records(namespace=NAMESPACE, records=records)
        logger.info("Stored %d signals for deal %s", len(records), deal_id)

    return len(records)


def store_gap(gap: dict, deal_id: str, sector: str) -> None:
    """Store a completeness gap as a searchable record."""
    index = _get_index()
    record = {
        "_id": f"{deal_id}_{gap['gap_id']}",
        "signal_text": f"Missing: {gap['expected_document']} | {gap.get('reason_expected', '')}",
        "lens": "Completeness",
        "rating": gap.get("urgency", "MEDIUM"),
        "confidence": "HIGH",
        "title": f"Missing: {gap['expected_document']}",
        "deal_id": deal_id,
        "sector": sector,
        "phase": 0,
        "source_doc": "completeness_check",
        "deal_implication": gap.get("reason_expected", ""),
        "practitioner_verdict": "",
        "outcome_material": "",
    }
    index.upsert_records(namespace=NAMESPACE, records=[record])


def query_similar_patterns(
    query_text: str,
    sector: str,
    lens: str | None,
    top_k: int = 3,
) -> List[dict]:
    """
    Semantic search for prior signals matching the query text, filtered by sector and lens.

    Returns a list of pattern dicts with keys: title, lens, rating, deal_id, signal_text.
    Returns empty list on any error so callers degrade gracefully.
    """
    index = _get_index()
    query_filter = {"sector": {"$eq": sector}}
    if lens:
        query_filter["lens"] = {"$eq": lens}

    try:
        result = index.search(
            namespace=NAMESPACE,
            query={"inputs": {"text": query_text}, "top_k": top_k},
            fields=["signal_text", "lens", "rating", "title", "deal_id"],
            filter=query_filter,
        )
        return [
            {
                "title": hit.fields.get("title", ""),
                "lens": hit.fields.get("lens", ""),
                "rating": hit.fields.get("rating", ""),
                "deal_id": hit.fields.get("deal_id", ""),
                "signal_text": hit.fields.get("signal_text", ""),
            }
            for hit in result.result.hits
        ]
    except Exception as exc:
        logger.error("Pinecone query failed: %s", exc)
        return []


def update_signal_verdict(
    deal_id: str,
    signal_id: str,
    verdict: str,
    corrected_rating: str | None,
) -> None:
    """
    Update a signal's practitioner verdict (and optionally its rating) in Pinecone.

    Called after a Human Gate feedback session.
    """
    index = _get_index()
    record_id = f"{deal_id}_{signal_id}"
    fields = {"practitioner_verdict": verdict}
    if corrected_rating:
        fields["rating"] = corrected_rating
    try:
        index.update(id=record_id, namespace=NAMESPACE, set_metadata=fields)
    except Exception as exc:
        logger.error("Failed to update signal verdict for %s: %s", record_id, exc)
```

- [ ] **Step 5: Run tests to verify they pass**

Run:
```bash
cd C:/Users/itssh/tdd && python -m pytest tests/tools/test_signal_store.py -v
```
Expected: All 4 tests PASS (all mock-based, no live Pinecone calls).

- [ ] **Step 6: Commit**

```bash
git add tools/signal_store.py tests/tools/test_signal_store.py
git commit -m "feat: signal store — Pinecone read/write for cross-engagement learning"
```

---

### Task 11: Feedback Collector

**Files:**
- Create: `tools/feedback_collector.py`
- Create: `tests/tools/test_feedback_collector.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/tools/test_feedback_collector.py`:

```python
import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from tools.feedback_collector import load_feedback_shell, save_feedback, record_signal_rating


def test_load_feedback_shell_reads_json(tmp_path):
    shell = {
        "deal_id": "DEAL-001", "phase": 0, "gate": 1,
        "practitioner_id": "", "timestamp": "",
        "signal_ratings": [], "phase_accuracy_score": None,
        "missed_signals": [],
        "outcome_data": {"deal_outcome": "pending", "signals_proved_material": [], "signals_proved_immaterial": []},
    }
    f = tmp_path / "feedback_gate1.json"
    f.write_text(json.dumps(shell))
    loaded = load_feedback_shell(str(f))
    assert loaded["deal_id"] == "DEAL-001"


def test_save_feedback_writes_json(tmp_path):
    feedback = {
        "deal_id": "DEAL-001", "phase": 0, "gate": 1,
        "practitioner_id": "shiva", "timestamp": "2026-03-27T12:00:00Z",
        "signal_ratings": [{"signal_id": "SIG-001", "verdict": "CONFIRMED",
                             "practitioner_note": "", "corrected_rating": None}],
        "phase_accuracy_score": 85,
        "missed_signals": [],
        "outcome_data": {"deal_outcome": "pending", "signals_proved_material": [], "signals_proved_immaterial": []},
    }
    out_path = tmp_path / "feedback_gate1_completed.json"
    save_feedback(feedback, str(out_path))
    assert out_path.exists()
    loaded = json.loads(out_path.read_text())
    assert loaded["practitioner_id"] == "shiva"


def test_record_signal_rating_returns_updated_feedback():
    feedback = {
        "deal_id": "DEAL-001", "phase": 0, "gate": 1,
        "practitioner_id": "", "timestamp": "",
        "signal_ratings": [],
        "phase_accuracy_score": None,
        "missed_signals": [],
        "outcome_data": {"deal_outcome": "pending", "signals_proved_material": [], "signals_proved_immaterial": []},
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
cd C:/Users/itssh/tdd && python -m pytest tests/tools/test_feedback_collector.py -v
```
Expected: `ImportError`.

- [ ] **Step 3: Implement `tools/feedback_collector.py`**

```python
"""
Feedback collector: CLI tool for practitioners to rate signals at each Human Gate.
Reads the feedback shell written by report_writer, collects ratings interactively,
then writes the completed feedback back to disk and upserts verdicts to Pinecone.

Usage:
    python -m tools.feedback_collector --deal DEAL-001 --phase 0 --gate 1
"""
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import List

import typer
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).parent.parent / "outputs"

app = typer.Typer()


def load_feedback_shell(path: str) -> dict:
    """Load a feedback shell JSON file into a dict."""
    with open(path) as f:
        return json.load(f)


def save_feedback(feedback: dict, path: str) -> None:
    """Write the completed feedback dict to a JSON file."""
    with open(path, "w") as f:
        json.dump(feedback, f, indent=2)


def record_signal_rating(
    feedback: dict,
    signal_id: str,
    verdict: str,
    practitioner_note: str,
    corrected_rating: str | None,
) -> dict:
    """
    Add or update a signal rating in the feedback dict.

    Returns the updated feedback dict (does not write to disk).
    """
    # Remove existing rating for this signal_id if present
    feedback["signal_ratings"] = [
        r for r in feedback["signal_ratings"] if r["signal_id"] != signal_id
    ]
    feedback["signal_ratings"].append(
        {
            "signal_id": signal_id,
            "verdict": verdict,
            "practitioner_note": practitioner_note,
            "corrected_rating": corrected_rating,
        }
    )
    return feedback


@app.command()
def main(
    deal: str = typer.Option(..., help="Deal ID (e.g. DEAL-001)"),
    phase: int = typer.Option(0, help="Phase number"),
    gate: int = typer.Option(1, help="Gate number"),
    practitioner: str = typer.Option("", help="Practitioner ID"),
) -> None:
    """
    Interactively collect practitioner signal ratings at a Human Gate.

    Reads feedback_gate{gate}.json, walks through each signal in the brief,
    collects CONFIRMED/NOISE/UNCERTAIN verdict + optional note, then writes
    completed feedback and upserts verdicts to Pinecone.
    """
    # Find the brief to get signals
    brief_path = None
    for p in OUTPUT_DIR.rglob("vdr_intelligence_brief.json"):
        try:
            with open(p) as f:
                brief = json.load(f)
            if brief.get("deal_id") == deal:
                brief_path = p
                break
        except Exception:
            continue

    if not brief_path:
        typer.echo(f"No VDR Intelligence Brief found for deal {deal}", err=True)
        raise typer.Exit(1)

    shell_path = brief_path.parent / f"feedback_gate{gate}.json"
    if not shell_path.exists():
        typer.echo(f"Feedback shell not found: {shell_path}", err=True)
        raise typer.Exit(1)

    feedback = load_feedback_shell(str(shell_path))
    feedback["practitioner_id"] = practitioner or "practitioner"
    feedback["timestamp"] = datetime.now(timezone.utc).isoformat()

    # Collect all signals from domain slices
    signals: List[dict] = []
    for slice_data in brief.get("domain_slices", {}).values():
        signals.extend(slice_data.get("signals", []))

    if not signals:
        typer.echo("No signals found in brief to rate. Exiting.")
        raise typer.Exit(0)

    typer.echo(f"\n=== Gate {gate} Feedback — {deal} (Phase {phase}) ===")
    typer.echo(f"{len(signals)} signals to review. Enter verdict: C=CONFIRMED, N=NOISE, U=UNCERTAIN\n")

    for sig in signals:
        typer.echo(f"[{sig.get('rating')}] {sig['signal_id']}: {sig.get('title', '')}")
        typer.echo(f"  {sig.get('observation', '')}")
        raw = typer.prompt("  Verdict (C/N/U)", default="C").upper()
        verdict = {"C": "CONFIRMED", "N": "NOISE", "U": "UNCERTAIN"}.get(raw, "UNCERTAIN")
        note = typer.prompt("  Note (optional)", default="")
        corrected = None
        if verdict == "CONFIRMED":
            typer.echo(f"  Rating was {sig.get('rating')}. Press Enter to keep, or type RED/YELLOW/GREEN to correct.")
            correction_raw = typer.prompt("  Corrected rating", default="").upper()
            if correction_raw in ("RED", "YELLOW", "GREEN"):
                corrected = correction_raw

        feedback = record_signal_rating(feedback, sig["signal_id"], verdict, note, corrected)
        typer.echo("")

    accuracy = typer.prompt("Overall accuracy score (0-100)", default="80")
    feedback["phase_accuracy_score"] = int(accuracy)

    completed_path = brief_path.parent / f"feedback_gate{gate}_completed.json"
    save_feedback(feedback, str(completed_path))
    typer.echo(f"\nFeedback saved to {completed_path}")

    # Write verdicts to Pinecone
    try:
        from tools.signal_store import update_signal_verdict
        for rating in feedback["signal_ratings"]:
            update_signal_verdict(
                deal_id=deal,
                signal_id=rating["signal_id"],
                verdict=rating["verdict"],
                corrected_rating=rating.get("corrected_rating"),
            )
        typer.echo(f"Verdicts written to Pinecone for {len(feedback['signal_ratings'])} signals.")
    except Exception as exc:
        typer.echo(f"Warning: Pinecone update failed: {exc}", err=True)


if __name__ == "__main__":
    app()
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
cd C:/Users/itssh/tdd && python -m pytest tests/tools/test_feedback_collector.py -v
```
Expected: All 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/feedback_collector.py tests/tools/test_feedback_collector.py
git commit -m "feat: feedback collector — CLI practitioner signal rating and Pinecone verdict update"
```

---

### Task 12: Wire Pinecone into Triage Orchestrator (Phase B)

**Files:**
- Modify: `agents/vdr_triage.py`
- Modify: `tests/agents/test_vdr_triage.py`

- [ ] **Step 1: Write new failing test for Pinecone integration**

Add to `tests/agents/test_vdr_triage.py`:

```python
def test_run_triage_stores_signals_in_pinecone(temp_vdr_dir):
    """Phase B: signals and gaps are stored in Pinecone after triage."""
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
    # store_signals called at least once (one per non-empty batch)
    assert mock_store.called or mock_gap.called
```

- [ ] **Step 2: Run to verify failure**

Run:
```bash
cd C:/Users/itssh/tdd && python -m pytest tests/agents/test_vdr_triage.py::test_run_triage_stores_signals_in_pinecone -v
```
Expected: FAIL — `store_signals` not yet imported in `agents/vdr_triage.py`.

- [ ] **Step 3: Add Pinecone calls to `agents/vdr_triage.py`**

In `agents/vdr_triage.py`, add these imports at the top (after existing imports):

```python
from tools.signal_store import query_similar_patterns, store_gap, store_signals
```

In `run_triage`, replace the `prior_patterns=[]` comment line in the signal extraction loop:

```python
        # Query Signal Intelligence Layer for prior patterns (Phase B)
        prior_patterns = []
        if docs:
            query_text = f"{sector} {batch_id} signals"
            prior_patterns = query_similar_patterns(
                query_text=query_text,
                sector=sector,
                lens=None,
                top_k=3,
            )

        batch_result = extract_signals_from_batch(
            batch_id=batch_id,
            documents=enriched_docs,
            company_name=company_name,
            sector=sector,
            deal_type=deal_type,
            prior_patterns=prior_patterns,
            client=client,
        )
        all_batch_results.append(batch_result)
        signal_count = len(batch_result.get("signals", []))
        logger.info("  Batch %s: %d signals extracted", batch_id, signal_count)

        # Store signals in Signal Intelligence Layer
        if batch_result.get("signals"):
            store_signals(batch_result["signals"], deal_id=deal_id, sector=sector, phase=0)
```

After the `cross_reference_signals` call (before writing outputs), add:

```python
    # Store completeness gaps in Signal Intelligence Layer
    for gap in completeness.get("missing_documents", []):
        store_gap(gap, deal_id=deal_id, sector=sector)
```

- [ ] **Step 4: Run full test suite**

Run:
```bash
cd C:/Users/itssh/tdd && python -m pytest tests/ -v --tb=short
```
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add agents/vdr_triage.py tests/agents/test_vdr_triage.py
git commit -m "feat: wire Pinecone into triage — prior pattern injection and signal/gap storage"
```

---

### Task 13: HORIZON Integration Run

**Files:**
- No new files — this is a live integration test against the real VDR.

- [ ] **Step 1: Verify .env has required keys**

Run:
```bash
python -c "
import os
from dotenv import load_dotenv
load_dotenv()
for key in ['ANTHROPIC_API_KEY', 'PINECONE_API_KEY']:
    val = os.environ.get(key, '')
    status = 'OK' if val else 'MISSING'
    print(f'{key}: {status}')
"
```
Expected: Both `OK`.

- [ ] **Step 2: Run the triage on HORIZON VDR**

Run:
```bash
cd C:/Users/itssh/tdd && python -m agents.vdr_triage \
  --vdr-path "VDR/HST Pathways-Diligence-HORIZON - VDR (1)" \
  --company HORIZON \
  --deal-id DEAL-001 \
  --sector healthcare-saas \
  --deal-type pe-acquisition
```
Expected: Logs show progress through all batches. No unhandled exceptions.

- [ ] **Step 3: Verify outputs written to disk**

Run:
```bash
ls outputs/HORIZON/
```
Expected: `vdr_intelligence_brief.json  vdr_triage_report.md  vdr_completeness_report.md  feedback_gate1.json`

- [ ] **Step 4: Spot-check signal quality**

Run:
```bash
python -c "
import json
with open('outputs/HORIZON/vdr_intelligence_brief.json') as f:
    brief = json.load(f)
print('Overall rating:', brief['overall_signal_rating'])
print('Lens heatmap:')
for lens, data in brief.get('lens_heatmap', {}).items():
    print(f'  {lens}: {data[\"rating\"]} ({data[\"signal_count\"]} signals)')
print('Compound risks:', len(brief.get('compound_risks', [])))
print('Reading list items:', len(brief.get('prioritized_reading_list', [])))
"
```
Expected: ≥8 lenses with signals, ≥3 compound risks, ≥5 reading list items.

- [ ] **Step 5: Spot-check completeness report**

Run:
```bash
python -c "
import json
with open('outputs/HORIZON/vdr_completeness_report.md') as f:
    print(f.read()[:2000])
"
```
Expected: ≥3 gaps listed with CRITICAL/HIGH/MEDIUM urgency and request language.

- [ ] **Step 6: Verify signal count in Pinecone**

Run:
```bash
python -c "
from pinecone import Pinecone
import os
from dotenv import load_dotenv
load_dotenv()
pc = Pinecone(api_key=os.environ['PINECONE_API_KEY'])
index = pc.Index('tdd-signals')
stats = index.describe_index_stats()
print('Total vectors:', stats.total_vector_count)
"
```
Expected: Total vectors > 0 (signals were stored).

- [ ] **Step 7: Commit final state**

```bash
git add outputs/HORIZON/vdr_intelligence_brief.json outputs/HORIZON/vdr_triage_report.md outputs/HORIZON/vdr_completeness_report.md
git commit -m "feat: HORIZON VDR triage — pilot run complete, outputs committed"
```

---

## Self-Review Against Spec

**Spec coverage check:**

| Spec Requirement | Covered by Task |
|---|---|
| 4-step pipeline (structure mapper → reader → extractor → cross-ref) | Tasks 3, 2, 6, 7 |
| 3 outputs (brief JSON, triage MD, completeness MD) | Task 8 |
| Feedback shell written at Gate 1 | Task 8 |
| 11 signal lenses | Task 1 |
| Document batching by type | Tasks 1, 3 |
| Prior pattern injection from Pinecone | Tasks 10, 12 |
| Signal store (upsert + query + update) | Task 10 |
| Gap storage in Pinecone | Tasks 10, 12 |
| Practitioner feedback collector CLI | Task 11 |
| Typer CLI entry point | Task 9 |
| HORIZON pilot run | Task 13 |
| All 16 success criteria | Tasks 9 + 13 validation steps |
| `.env` secrets only | Tasks 9, 10, 11 |
| Type hints + docstrings | All implementation tasks |

**No gaps found.**
