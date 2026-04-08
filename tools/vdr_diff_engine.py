"""
VDR Diff Engine: compute document-level diffs between VDR snapshots.

Why: When a VDR is rescanned, we need to know what's new, removed, modified,
and unchanged so we can extract signals incrementally (only from new/modified
docs) and identify which gaps might be resolved.

Uses filename as the primary key for matching. Modified detection compares
file size and optionally MD5 hash of the first 64KB for speed.
"""
import hashlib
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def compute_vdr_diff(
    old_inventory: list[dict],
    new_inventory: list[dict],
) -> dict:
    """
    Compare two VDR inventories (from structure_mapper.map_vdr_structure).

    Matches documents by filename. Modified detection uses file size and
    optional MD5 hash of first 64KB.

    Args:
        old_inventory: List of document dicts from prior VDR scan.
                       Expected keys: filename, filepath, vdr_section, batch_group, size_bytes
        new_inventory: List of document dicts from current VDR scan.

    Returns:
        {
            "new_documents": [...],       # in new but not old (by filename)
            "removed_documents": [...],   # in old but not new
            "modified_documents": [...],  # same name, different size/hash
            "unchanged_documents": [...], # same name, same size
            "summary": {
                "total_new": int,
                "total_removed": int,
                "total_modified": int,
                "total_unchanged": int
            }
        }
    """
    # Build lookup maps by filename (lowercased for case-insensitive matching)
    old_by_name = {doc["filename"].lower(): doc for doc in old_inventory}
    new_by_name = {doc["filename"].lower(): doc for doc in new_inventory}

    new_docs = []
    removed_docs = []
    modified_docs = []
    unchanged_docs = []

    # Check for new and modified documents
    for new_name, new_doc in new_by_name.items():
        if new_name not in old_by_name:
            new_docs.append(new_doc)
        else:
            old_doc = old_by_name[new_name]
            if _is_modified(old_doc, new_doc):
                modified_docs.append({
                    "filename": new_doc["filename"],
                    "filepath": new_doc["filepath"],
                    "vdr_section": new_doc["vdr_section"],
                    "batch_group": new_doc["batch_group"],
                    "old_size_bytes": old_doc["size_bytes"],
                    "new_size_bytes": new_doc["size_bytes"],
                    "size_change_bytes": new_doc["size_bytes"] - old_doc["size_bytes"],
                })
            else:
                unchanged_docs.append(new_doc)

    # Check for removed documents
    for old_name, old_doc in old_by_name.items():
        if old_name not in new_by_name:
            removed_docs.append(old_doc)

    return {
        "new_documents": new_docs,
        "removed_documents": removed_docs,
        "modified_documents": modified_docs,
        "unchanged_documents": unchanged_docs,
        "summary": {
            "total_new": len(new_docs),
            "total_removed": len(removed_docs),
            "total_modified": len(modified_docs),
            "total_unchanged": len(unchanged_docs),
        },
    }


def _is_modified(
    old_doc: dict,
    new_doc: dict,
    use_hash: bool = False,
) -> bool:
    """
    Determine if a document has been modified.

    Compares file size first. If use_hash is True, also compares MD5 hash
    of first 64KB of file content (if filepath is available).

    Args:
        old_doc: Document dict from old inventory.
        new_doc: Document dict from new inventory.
        use_hash: If True, compute and compare file hash. Default False (size-only).

    Returns:
        True if the documents differ, False if they're the same.
    """
    # Size check is always done
    old_size = old_doc.get("size_bytes", 0)
    new_size = new_doc.get("size_bytes", 0)

    if old_size != new_size:
        return True

    # If sizes are equal and use_hash is False, consider them unchanged
    if not use_hash:
        return False

    # Hash-based comparison (optional, slower)
    old_filepath = old_doc.get("filepath")
    new_filepath = new_doc.get("filepath")

    if old_filepath and new_filepath:
        try:
            old_hash = _compute_file_hash(old_filepath, chunk_size=65536)
            new_hash = _compute_file_hash(new_filepath, chunk_size=65536)
            return old_hash != new_hash
        except OSError as e:
            logger.warning("Could not hash files for comparison: %s", e)
            return False

    return False


def _compute_file_hash(filepath: str, chunk_size: int = 65536) -> str:
    """
    Compute MD5 hash of first chunk_size bytes of a file.

    Args:
        filepath: Path to the file.
        chunk_size: Number of bytes to hash (default 64KB).

    Returns:
        Hex digest of MD5 hash.

    Raises:
        OSError: If file cannot be read.
    """
    md5_hash = hashlib.md5()
    try:
        with open(filepath, "rb") as f:
            chunk = f.read(chunk_size)
            if chunk:
                md5_hash.update(chunk)
    except OSError:
        raise

    return md5_hash.hexdigest()
