import json
import tempfile
import pytest
from tools.structure_mapper import map_vdr_structure, assign_batch_group


def test_map_vdr_structure_returns_inventory_and_groups(temp_vdr_dir, sample_batch_rules, tmp_path):
    rules_file = tmp_path / "batch_rules.json"
    rules_file.write_text(json.dumps(sample_batch_rules))

    result = map_vdr_structure(temp_vdr_dir, str(rules_file))
    assert "inventory" in result
    assert "batch_groups" in result


def test_inventory_contains_pdf_files(temp_vdr_dir, sample_batch_rules, tmp_path):
    rules_file = tmp_path / "batch_rules.json"
    rules_file.write_text(json.dumps(sample_batch_rules))

    result = map_vdr_structure(temp_vdr_dir, str(rules_file))
    assert len(result["inventory"]) > 0


def test_inventory_item_has_required_fields(temp_vdr_dir, sample_batch_rules, tmp_path):
    rules_file = tmp_path / "batch_rules.json"
    rules_file.write_text(json.dumps(sample_batch_rules))

    result = map_vdr_structure(temp_vdr_dir, str(rules_file))
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


def test_batch_groups_dict_groups_files_by_group(temp_vdr_dir, sample_batch_rules, tmp_path):
    rules_file = tmp_path / "batch_rules.json"
    rules_file.write_text(json.dumps(sample_batch_rules))

    result = map_vdr_structure(temp_vdr_dir, str(rules_file))
    # All inventory items should appear in batch_groups
    all_grouped = [doc for docs in result["batch_groups"].values() for doc in docs]
    assert len(all_grouped) == len(result["inventory"])
