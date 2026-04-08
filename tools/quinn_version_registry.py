"""
Quinn Version Registry — Track template and catalog versions per deal.

Maintains a JSON registry at outputs/_quinn_registry.json that records which
template version and catalog version each deal was last processed against.
This allows Quinn to identify deals affected by template or catalog changes
and determine whether reprocessing is required.

Usage:
    from tools.quinn_version_registry import register_version, find_affected_deals

    register_version("deal-123", template_version=2, catalog_version="1.4")
    affected = find_affected_deals(catalog_version="1.3")
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

REGISTRY_PATH = Path(__file__).parent.parent / "outputs" / "_quinn_registry.json"


# ── Registry Structure ────────────────────────────────────────────────────────

def _load_registry() -> dict:
    """Load the version registry from disk. Creates empty registry if missing."""
    if not REGISTRY_PATH.exists():
        return {
            "version": "1.0",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "deals": {}
        }

    try:
        data = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        return data
    except json.JSONDecodeError as e:
        logger.error(f"Corrupt registry at {REGISTRY_PATH}: {e}. Starting fresh.")
        return {
            "version": "1.0",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "deals": {}
        }


def _save_registry(registry: dict) -> None:
    """Save the version registry to disk."""
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    registry["updated_at"] = datetime.now(timezone.utc).isoformat()
    REGISTRY_PATH.write_text(json.dumps(registry, indent=2, ensure_ascii=False), encoding="utf-8")


# ── Core Registry Operations ──────────────────────────────────────────────────

def register_version(
    deal_id: str,
    template_version: int | str,
    catalog_version: str,
    scan_id: str = "",
) -> None:
    """
    Register or update the template and catalog versions for a deal.

    Called after a scan or DRL upload to record what versions were used.
    Multiple scans of the same deal track the version history.

    Args:
        deal_id: Unique identifier for the deal (e.g., "acme-corp-2024")
        template_version: DRL template version (e.g., 1, 2, or "1.0")
        catalog_version: Signal catalog version (e.g., "1.3", "1.4")
        scan_id: Optional identifier for this specific scan/submission (e.g., "scan-001", "drl-v2")
    """
    registry = _load_registry()

    if deal_id not in registry["deals"]:
        registry["deals"][deal_id] = {
            "first_registered": datetime.now(timezone.utc).isoformat(),
            "template_version": None,
            "catalog_version": None,
            "scans": []
        }

    deal = registry["deals"][deal_id]
    deal["template_version"] = str(template_version)
    deal["catalog_version"] = str(catalog_version)
    deal["last_updated"] = datetime.now(timezone.utc).isoformat()

    # Track scan history
    deal["scans"].append({
        "scan_id": scan_id or f"scan-{len(deal['scans']) + 1}",
        "template_version": str(template_version),
        "catalog_version": str(catalog_version),
        "timestamp": datetime.now(timezone.utc).isoformat()
    })

    _save_registry(registry)
    logger.info(f"Registered {deal_id}: template={template_version}, catalog={catalog_version}")


def get_version_registry(deal_id: str = "") -> dict:
    """
    Retrieve version registry for one deal or all deals.

    Args:
        deal_id: If provided, returns info for that deal only. If empty, returns all deals.

    Returns:
        For a single deal (deal_id provided):
            {
                "deal_id": str,
                "first_registered": ISO-8601,
                "template_version": str,
                "catalog_version": str,
                "migration_status": "compatible" | "requires_reprocessing" | "blocked" | "unknown",
                "scans": [
                    {
                        "scan_id": str,
                        "template_version": str,
                        "catalog_version": str,
                        "timestamp": ISO-8601
                    },
                    ...
                ]
            }

        For all deals (deal_id empty):
            {
                "version": "1.0",
                "created_at": ISO-8601,
                "updated_at": ISO-8601,
                "deals": {
                    "<deal_id>": {...},
                    ...
                }
            }
    """
    registry = _load_registry()

    if deal_id:
        if deal_id not in registry["deals"]:
            return {
                "deal_id": deal_id,
                "first_registered": None,
                "template_version": None,
                "catalog_version": None,
                "migration_status": "unknown",
                "scans": []
            }

        deal = registry["deals"][deal_id]
        return {
            "deal_id": deal_id,
            "first_registered": deal.get("first_registered"),
            "template_version": deal.get("template_version"),
            "catalog_version": deal.get("catalog_version"),
            "migration_status": deal.get("migration_status", "unknown"),
            "scans": deal.get("scans", [])
        }

    return registry


def find_affected_deals(
    template_version: str | int = "",
    catalog_version: str = "",
) -> list[str]:
    """
    Find all deals that were processed with a specific template or catalog version.

    Used to identify which deals might be affected by a schema change.

    Args:
        template_version: Find deals using this template version (optional)
        catalog_version: Find deals using this catalog version (optional)

    Returns:
        List of deal IDs matching the criteria.
    """
    registry = _load_registry()
    affected = []

    for deal_id, deal in registry.get("deals", {}).items():
        matches_template = (
            not template_version or
            str(deal.get("template_version")) == str(template_version)
        )
        matches_catalog = (
            not catalog_version or
            str(deal.get("catalog_version")) == catalog_version
        )

        if matches_template and matches_catalog:
            affected.append(deal_id)

    logger.info(
        f"Found {len(affected)} deals matching: "
        f"template={template_version or 'any'}, catalog={catalog_version or 'any'}"
    )
    return sorted(affected)


# ── Migration Status Tracking ─────────────────────────────────────────────────

def mark_migration_status(
    deal_id: str,
    status: str,
    notes: str = "",
) -> None:
    """
    Mark a deal's migration status relative to a schema change.

    Called by Quinn after analyzing whether a deal is affected by breaking changes.

    Args:
        deal_id: Deal identifier
        status: One of:
            - "compatible": Existing data is unaffected; no reprocessing needed
            - "requires_reprocessing": Reprocessing is needed but no data loss
            - "blocked": Cannot reprocess safely; manual intervention required
            - "unknown": Status not yet determined
        notes: Human-readable explanation (e.g., reason for "blocked" status)
    """
    valid_statuses = {"compatible", "requires_reprocessing", "blocked", "unknown"}
    if status not in valid_statuses:
        raise ValueError(f"Invalid status '{status}'. Must be one of: {valid_statuses}")

    registry = _load_registry()

    if deal_id not in registry["deals"]:
        logger.warning(f"Cannot mark migration status for unknown deal {deal_id}")
        return

    deal = registry["deals"][deal_id]
    deal["migration_status"] = status
    deal["migration_notes"] = notes
    deal["migration_checked_at"] = datetime.now(timezone.utc).isoformat()

    _save_registry(registry)
    logger.info(f"Marked {deal_id} migration status: {status}")


def get_migration_summary() -> dict:
    """
    Get a summary of migration statuses across all deals.

    Useful for dashboards and batch migration planning.

    Returns:
        {
            "total_deals": int,
            "by_status": {
                "compatible": int,
                "requires_reprocessing": int,
                "blocked": int,
                "unknown": int
            },
            "deals_by_status": {
                "compatible": [deal_id, ...],
                "requires_reprocessing": [deal_id, ...],
                "blocked": [deal_id, ...],
                "unknown": [deal_id, ...]
            }
        }
    """
    registry = _load_registry()
    summary = {
        "total_deals": 0,
        "by_status": {
            "compatible": 0,
            "requires_reprocessing": 0,
            "blocked": 0,
            "unknown": 0
        },
        "deals_by_status": {
            "compatible": [],
            "requires_reprocessing": [],
            "blocked": [],
            "unknown": []
        }
    }

    for deal_id, deal in registry.get("deals", {}).items():
        summary["total_deals"] += 1
        status = deal.get("migration_status", "unknown")

        if status in summary["by_status"]:
            summary["by_status"][status] += 1
            summary["deals_by_status"][status].append(deal_id)

    return summary


# ── Scan History ──────────────────────────────────────────────────────────────

def get_deal_scan_history(deal_id: str) -> list[dict]:
    """
    Get the complete scan history for a deal.

    Returns a chronological list of all scans/submissions with their versions.

    Args:
        deal_id: Deal identifier

    Returns:
        [
            {
                "scan_id": str,
                "template_version": str,
                "catalog_version": str,
                "timestamp": ISO-8601
            },
            ...
        ]
    """
    registry = _load_registry()

    if deal_id not in registry["deals"]:
        return []

    return registry["deals"][deal_id].get("scans", [])


def list_all_deals() -> list[str]:
    """Get a list of all registered deal IDs."""
    registry = _load_registry()
    return sorted(registry.get("deals", {}).keys())


# ── Registry Inspection ───────────────────────────────────────────────────────

def validate_registry() -> tuple[bool, list[str]]:
    """
    Validate registry integrity.

    Checks that all deal IDs are unique, versions are reasonable format, etc.

    Returns:
        (is_valid: bool, errors: list[str])
    """
    registry = _load_registry()
    errors = []

    if "deals" not in registry:
        errors.append("Registry missing 'deals' key")
        return False, errors

    seen_ids = set()
    for deal_id, deal in registry["deals"].items():
        if deal_id in seen_ids:
            errors.append(f"Duplicate deal_id: {deal_id}")
        seen_ids.add(deal_id)

        if not isinstance(deal, dict):
            errors.append(f"Deal {deal_id}: not a dict")
            continue

        # Validate version fields exist and are reasonable
        for scan in deal.get("scans", []):
            if not isinstance(scan.get("template_version"), (str, int)):
                errors.append(f"Deal {deal_id} scan: invalid template_version")
            if not isinstance(scan.get("catalog_version"), str):
                errors.append(f"Deal {deal_id} scan: invalid catalog_version")

    if errors:
        logger.warning(f"Registry validation found {len(errors)} error(s)")

    return len(errors) == 0, errors


def export_registry(output_path: str = "") -> str:
    """
    Export the current registry to a JSON file (for backup or analysis).

    Args:
        output_path: Where to export (default: outputs/_quinn_registry_export.json)

    Returns:
        Path where registry was exported.
    """
    if not output_path:
        output_path = Path(__file__).parent.parent / "outputs" / "_quinn_registry_export.json"

    output_path = Path(output_path)
    registry = _load_registry()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(registry, indent=2, ensure_ascii=False), encoding="utf-8")

    logger.info(f"Registry exported to {output_path}")
    return str(output_path)
