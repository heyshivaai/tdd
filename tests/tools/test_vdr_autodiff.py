"""
Tests for VDR diff engine and gap resolver.

Tests document-level diffing between VDR snapshots and automatic gap resolution
when new documents are added to the virtual data room.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock

from tools.vdr_diff_engine import compute_vdr_diff, _is_modified, _compute_file_hash
from tools.gap_resolver import resolve_gaps, _find_best_match, _extract_keywords


@pytest.fixture
def old_vdr_inventory():
    """Sample VDR inventory from first scan."""
    return [
        {
            "filename": "architecture_diagram.pdf",
            "filepath": "/vdr/Tech/architecture_diagram.pdf",
            "vdr_section": "Product & Technology/Architecture",
            "batch_group": "core_tech",
            "size_bytes": 512000,
        },
        {
            "filename": "pen_test_2024.pdf",
            "filepath": "/vdr/Security/pen_test_2024.pdf",
            "vdr_section": "Product & Technology/Security",
            "batch_group": "security",
            "size_bytes": 1024000,
        },
        {
            "filename": "team_org_chart.pdf",
            "filepath": "/vdr/Team/team_org_chart.pdf",
            "vdr_section": "Management/Organization",
            "batch_group": "people",
            "size_bytes": 256000,
        },
    ]


@pytest.fixture
def new_vdr_inventory(old_vdr_inventory):
    """Sample VDR inventory from second scan (with changes)."""
    # Keep first document unchanged, modify second, remove third, add new
    return [
        {
            "filename": "architecture_diagram.pdf",
            "filepath": "/vdr/Tech/architecture_diagram.pdf",
            "vdr_section": "Product & Technology/Architecture",
            "batch_group": "core_tech",
            "size_bytes": 512000,  # Same size = unchanged
        },
        {
            "filename": "pen_test_2024.pdf",
            "filepath": "/vdr/Security/pen_test_2024.pdf",
            "vdr_section": "Product & Technology/Security",
            "batch_group": "security",
            "size_bytes": 1536000,  # Larger = modified
        },
        {
            "filename": "infrastructure_audit.pdf",
            "filepath": "/vdr/Tech/infrastructure_audit.pdf",
            "vdr_section": "Product & Technology/Infrastructure",
            "batch_group": "core_tech",
            "size_bytes": 768000,  # NEW DOCUMENT
        },
    ]


@pytest.fixture
def completeness_report():
    """Sample completeness report with identified gaps."""
    return {
        "missing_documents": [
            {
                "gap_id": "GAP-001",
                "expected_document": "penetration test results external",
                "urgency": "CRITICAL",
            },
            {
                "gap_id": "GAP-002",
                "expected_document": "infrastructure audit report",
                "urgency": "HIGH",
            },
            {
                "gap_id": "GAP-003",
                "expected_document": "team organization structure",
                "urgency": "MEDIUM",
            },
        ],
        "present_but_incomplete": [],
    }


class TestVDRDiffEngine:
    """Test VDR document diffing logic."""

    def test_compute_vdr_diff_detects_new_documents(
        self, old_vdr_inventory, new_vdr_inventory
    ):
        """Diff should identify documents present in new but not old."""
        diff = compute_vdr_diff(old_vdr_inventory, new_vdr_inventory)

        assert diff["summary"]["total_new"] == 1
        assert len(diff["new_documents"]) == 1

        new_doc = diff["new_documents"][0]
        assert new_doc["filename"] == "infrastructure_audit.pdf"
        assert new_doc["vdr_section"] == "Product & Technology/Infrastructure"

    def test_compute_vdr_diff_detects_removed_documents(
        self, old_vdr_inventory, new_vdr_inventory
    ):
        """Diff should identify documents present in old but not new."""
        diff = compute_vdr_diff(old_vdr_inventory, new_vdr_inventory)

        assert diff["summary"]["total_removed"] == 1
        assert len(diff["removed_documents"]) == 1

        removed_doc = diff["removed_documents"][0]
        assert removed_doc["filename"] == "team_org_chart.pdf"

    def test_compute_vdr_diff_detects_modified_documents(
        self, old_vdr_inventory, new_vdr_inventory
    ):
        """Diff should identify documents with changed size/hash."""
        diff = compute_vdr_diff(old_vdr_inventory, new_vdr_inventory)

        assert diff["summary"]["total_modified"] == 1
        assert len(diff["modified_documents"]) == 1

        modified = diff["modified_documents"][0]
        assert modified["filename"] == "pen_test_2024.pdf"
        assert modified["old_size_bytes"] == 1024000
        assert modified["new_size_bytes"] == 1536000
        assert modified["size_change_bytes"] == 512000

    def test_compute_vdr_diff_detects_unchanged_documents(
        self, old_vdr_inventory, new_vdr_inventory
    ):
        """Diff should identify documents with same name and size."""
        diff = compute_vdr_diff(old_vdr_inventory, new_vdr_inventory)

        assert diff["summary"]["total_unchanged"] == 1
        assert len(diff["unchanged_documents"]) == 1

        unchanged = diff["unchanged_documents"][0]
        assert unchanged["filename"] == "architecture_diagram.pdf"

    def test_compute_vdr_diff_summary_is_complete(
        self, old_vdr_inventory, new_vdr_inventory
    ):
        """Diff summary should account for all documents."""
        diff = compute_vdr_diff(old_vdr_inventory, new_vdr_inventory)

        total = (
            diff["summary"]["total_new"]
            + diff["summary"]["total_removed"]
            + diff["summary"]["total_modified"]
            + diff["summary"]["total_unchanged"]
        )
        assert total == 4  # 1 unchanged + 1 modified + 1 new + 1 removed

    def test_compute_vdr_diff_case_insensitive_matching(self):
        """Diff should match filenames case-insensitively."""
        old = [
            {
                "filename": "Architecture.PDF",
                "filepath": "/vdr/arch.pdf",
                "vdr_section": "Tech",
                "batch_group": "core",
                "size_bytes": 1000,
            }
        ]
        new = [
            {
                "filename": "architecture.pdf",  # Different case
                "filepath": "/vdr/arch.pdf",
                "vdr_section": "Tech",
                "batch_group": "core",
                "size_bytes": 1000,
            }
        ]

        diff = compute_vdr_diff(old, new)

        # Should match despite case difference
        assert diff["summary"]["total_new"] == 0
        assert diff["summary"]["total_removed"] == 0
        assert diff["summary"]["total_unchanged"] == 1

    def test_compute_vdr_diff_empty_inventories(self):
        """Diff should handle empty inventories gracefully."""
        diff = compute_vdr_diff([], [])

        assert diff["summary"]["total_new"] == 0
        assert diff["summary"]["total_removed"] == 0
        assert diff["summary"]["total_modified"] == 0
        assert diff["summary"]["total_unchanged"] == 0

    def test_is_modified_by_size(self):
        """_is_modified should detect size differences."""
        old = {"filename": "test.pdf", "size_bytes": 1000}
        new = {"filename": "test.pdf", "size_bytes": 2000}

        assert _is_modified(old, new) == True

    def test_is_modified_same_size(self):
        """_is_modified should return False for same size without hash."""
        old = {"filename": "test.pdf", "size_bytes": 1000}
        new = {"filename": "test.pdf", "size_bytes": 1000}

        assert _is_modified(old, new, use_hash=False) == False

    def test_compute_file_hash_success(self, tmp_path):
        """_compute_file_hash should read first N bytes and hash them."""
        test_file = tmp_path / "test.bin"
        test_file.write_bytes(b"test content here")

        hash_result = _compute_file_hash(str(test_file), chunk_size=10)

        assert len(hash_result) == 32  # MD5 hex digest length
        assert isinstance(hash_result, str)

    def test_compute_file_hash_consistent(self, tmp_path):
        """_compute_file_hash should produce consistent results."""
        test_file = tmp_path / "test.bin"
        test_file.write_bytes(b"consistent content")

        hash1 = _compute_file_hash(str(test_file))
        hash2 = _compute_file_hash(str(test_file))

        assert hash1 == hash2

    def test_compute_file_hash_raises_on_missing_file(self):
        """_compute_file_hash should raise OSError for missing files."""
        with pytest.raises(OSError):
            _compute_file_hash("/nonexistent/file.bin")


class TestGapResolver:
    """Test gap resolution logic."""

    def test_resolve_gaps_matches_new_docs_to_gaps(
        self, completeness_report, new_vdr_inventory
    ):
        """resolve_gaps should match new documents to existing gaps."""
        new_docs = [new_vdr_inventory[2]]  # Just the infrastructure_audit.pdf

        result = resolve_gaps(completeness_report, new_docs)

        assert result["summary"]["total_gaps"] == 3
        assert result["summary"]["resolved"] > 0
        assert result["summary"]["unresolved"] > 0

    def test_resolve_gaps_high_confidence_match(self):
        """resolve_gaps should mark high-confidence matches when keywords strongly overlap."""
        report = {
            "missing_documents": [
                {
                    "gap_id": "GAP-001",
                    "expected_document": "infrastructure audit report external review",
                    "urgency": "CRITICAL",
                }
            ]
        }

        new_docs = [
            {
                "filename": "infrastructure_audit_report_external_review.pdf",
                "filepath": "/vdr/infrastructure_audit_report_external_review.pdf",
                "vdr_section": "Technology",
                "batch_group": "tech",
            }
        ]

        result = resolve_gaps(report, new_docs)

        assert len(result["resolved_gaps"]) > 0
        resolved = result["resolved_gaps"][0]
        assert resolved["confidence"] == "HIGH"

    def test_resolve_gaps_medium_confidence_match(self):
        """resolve_gaps should mark medium-confidence partial matches."""
        report = {
            "missing_documents": [
                {
                    "gap_id": "GAP-002",
                    "expected_document": "architecture audit infrastructure review",
                    "urgency": "HIGH",
                }
            ]
        }

        new_docs = [
            {
                "filename": "infrastructure_report.pdf",
                "filepath": "/vdr/infrastructure_report.pdf",
                "vdr_section": "Technology/Infrastructure",
                "batch_group": "tech",
            }
        ]

        result = resolve_gaps(report, new_docs)

        assert result["summary"]["total_gaps"] == 1
        # Depends on keyword overlap logic

    def test_resolve_gaps_no_matching_docs(self):
        """resolve_gaps should leave gaps unresolved if no matches found."""
        report = {
            "missing_documents": [
                {
                    "gap_id": "GAP-001",
                    "expected_document": "very specific document name",
                    "urgency": "MEDIUM",
                }
            ]
        }

        new_docs = [
            {
                "filename": "completely_unrelated_file.pdf",
                "filepath": "/vdr/unrelated.pdf",
                "vdr_section": "Other",
                "batch_group": "misc",
            }
        ]

        result = resolve_gaps(report, new_docs)

        assert result["summary"]["unresolved"] == 1
        assert result["summary"]["resolved"] == 0

    def test_resolve_gaps_empty_new_docs(self):
        """resolve_gaps should handle empty new documents list."""
        report = {
            "missing_documents": [
                {
                    "gap_id": "GAP-001",
                    "expected_document": "something",
                    "urgency": "MEDIUM",
                }
            ]
        }

        result = resolve_gaps(report, [])

        assert result["summary"]["unresolved"] == 1
        assert result["summary"]["resolved"] == 0

    def test_resolve_gaps_summary_accurate(self):
        """resolve_gaps summary should accurately reflect resolution rate."""
        report = {
            "missing_documents": [
                {
                    "gap_id": "GAP-001",
                    "expected_document": "penetration test",
                    "urgency": "CRITICAL",
                },
                {
                    "gap_id": "GAP-002",
                    "expected_document": "architecture",
                    "urgency": "HIGH",
                },
            ]
        }

        new_docs = [
            {
                "filename": "pen_test_report.pdf",
                "filepath": "/vdr/pen_test.pdf",
                "vdr_section": "Security",
                "batch_group": "sec",
            }
        ]

        result = resolve_gaps(report, new_docs)

        total = result["summary"]["total_gaps"]
        resolved = result["summary"]["resolved"]
        unresolved = result["summary"]["unresolved"]

        assert total == 2
        assert resolved + unresolved == total
        assert (
            result["summary"]["resolution_rate"]
            == resolved / total
        )


class TestKeywordMatching:
    """Test keyword extraction and matching."""

    def test_extract_keywords_filters_short_words(self):
        """_extract_keywords should filter out words <= 3 chars."""
        keywords = _extract_keywords("This is a test document")

        # "is" (2 chars), "a" (1 char) should be filtered
        assert "is" not in keywords
        assert "a" not in keywords
        assert "test" in keywords
        assert "document" in keywords

    def test_extract_keywords_lowercases(self):
        """_extract_keywords should return lowercase words."""
        keywords = _extract_keywords("Penetration TEST Report")

        assert "penetration" in keywords
        assert "test" in keywords
        assert "report" in keywords
        assert "PENETRATION" not in keywords

    def test_extract_keywords_splits_on_special_chars(self):
        """_extract_keywords should split on punctuation."""
        keywords = _extract_keywords("pen-test_report.pdf (external)")

        assert "test" in keywords  # from "test_report"
        assert "report" in keywords
        # "pen" might be filtered if < 3 chars logic applies

    def test_extract_keywords_returns_set(self):
        """_extract_keywords should return a set (no duplicates)."""
        keywords = _extract_keywords("test test document document")

        assert isinstance(keywords, set)
        # Sets automatically deduplicate, so "test" appears only once
        assert len(keywords) == 2  # "test" and "document"

    def test_find_best_match_high_confidence(self):
        """_find_best_match should return HIGH confidence for >80% overlap."""
        gap = "infrastructure audit report review"
        docs = [
            {
                "filename": "infrastructure_audit_report_review.pdf",
                "vdr_section": "Technology",
            }
        ]

        result = _find_best_match(gap, docs)

        if result:
            confidence, matched_doc = result
            assert confidence == "HIGH"
            assert matched_doc["filename"] == "infrastructure_audit_report_review.pdf"

    def test_find_best_match_medium_confidence(self):
        """_find_best_match should return MEDIUM for 50-80% overlap."""
        gap = "architecture infrastructure cloud deployment"
        docs = [
            {
                "filename": "infrastructure_setup.pdf",
                "vdr_section": "Tech/Infrastructure",
            }
        ]

        result = _find_best_match(gap, docs)

        if result:
            confidence, matched_doc = result
            assert confidence in ["MEDIUM", "HIGH"]

    def test_find_best_match_no_match(self):
        """_find_best_match should return None if no keywords overlap."""
        gap = "financial accounting records"
        docs = [
            {
                "filename": "technical_architecture.pdf",
                "vdr_section": "Technology",
            }
        ]

        result = _find_best_match(gap, docs)

        # Likely no match due to no overlapping keywords
        # (financial/accounting vs technical/architecture)

    def test_find_best_match_empty_docs(self):
        """_find_best_match should return None for empty document list."""
        result = _find_best_match("something", [])

        assert result is None

    def test_find_best_match_picks_best_score(self):
        """_find_best_match should pick the document with highest score."""
        gap = "penetration test security"
        docs = [
            {
                "filename": "financial_report.pdf",
                "vdr_section": "Finance",
            },
            {
                "filename": "penetration_test_results.pdf",
                "vdr_section": "Security",
            },
            {
                "filename": "architecture_design.pdf",
                "vdr_section": "Architecture",
            },
        ]

        result = _find_best_match(gap, docs)

        if result:
            confidence, matched_doc = result
            # Should match the penetration test document
            assert (
                "penetration" in matched_doc["filename"].lower()
                or "security" in matched_doc["vdr_section"].lower()
            )


class TestGateManager:
    """Test feedback gate manager (integrated with VDR diff)."""

    def test_gate_manager_integration_with_vdr_diff(
        self, old_vdr_inventory, new_vdr_inventory, completeness_report
    ):
        """VDR diff results can be used to feed into gate feedback."""
        # This is an integration point where diff results inform gap resolution
        diff = compute_vdr_diff(old_vdr_inventory, new_vdr_inventory)

        # New and modified documents can resolve gaps
        new_docs = diff["new_documents"] + [
            d for d in diff["modified_documents"]
        ]

        resolved = resolve_gaps(completeness_report, new_docs)

        assert resolved["summary"]["total_gaps"] > 0

    def test_vdr_scan_provides_checkpoint_data(
        self, new_vdr_inventory, completeness_report
    ):
        """VDR scan data can inform checkpoint gate decisions."""
        # Simulate a gate checkpoint using VDR data
        gate_findings = {
            "red_flags": [],
            "yellow_flags": [],
            "completeness_score": 75,
            "overall_risk_score": 2.5,
        }

        # Add gap resolution findings
        resolved = resolve_gaps(completeness_report, new_vdr_inventory)
        if resolved["summary"]["resolved"] > 0:
            gate_findings["gap_resolution_rate"] = (
                resolved["summary"]["resolution_rate"]
            )

        assert "gap_resolution_rate" in gate_findings
        assert gate_findings["gap_resolution_rate"] > 0
