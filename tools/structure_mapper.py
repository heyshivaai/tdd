"""
Structure mapper: walks a VDR folder and builds an inventory of all PDF files,
assigning each file to a batch group based on filename pattern matching.

Why: Before extracting signals, we need to know what exists and which files
belong together (e.g., all pen tests in one batch). Batch grouping gives Claude
cross-document context within a related set.
"""
import json
from pathlib import Path
from typing import List, Dict, Any


def map_vdr_structure(vdr_path: str, batch_rules_path: str) -> Dict[str, Any]:
    """
    Walk a VDR directory tree and build a document inventory with batch assignments.

    Args:
        vdr_path: Root directory path of the VDR to scan.
        batch_rules_path: Path to JSON file containing batch assignment rules.

    Returns:
        Dict with keys:
            - "inventory": List of document dicts (filename, filepath, vdr_section,
                         batch_group, size_bytes)
            - "batch_groups": dict mapping batch_group -> list of document dicts
    """
    with open(batch_rules_path) as f:
        config = json.load(f)

    rules: List[Dict[str, str]] = config.get("rules", [])
    default_group: str = config.get("default_batch_group", "general")

    root = Path(vdr_path)
    inventory: List[Dict[str, Any]] = []

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

    batch_groups: Dict[str, List[Dict[str, Any]]] = {}
    for doc in inventory:
        group = doc["batch_group"]
        batch_groups.setdefault(group, []).append(doc)

    return {"inventory": inventory, "batch_groups": batch_groups}


def assign_batch_group(filename_lower: str, rules: List[Dict[str, str]], default: str) -> str:
    """
    Match a filename (lowercased) against pattern rules; return first match's batch_group.

    Args:
        filename_lower: Filename string (should be lowercased by caller).
        rules: List of dicts with "pattern" and "batch_group" keys.
        default: Default batch group if no rule matches.

    Returns:
        The batch_group string for this file, or default if no match.

    Why: Case-insensitive pattern matching lets us write rules once and apply
    them to any filename. Returns the first matching rule to prioritize more
    specific patterns if listed first.
    """
    for rule in rules:
        if rule["pattern"] in filename_lower:
            return rule["batch_group"]
    return default
