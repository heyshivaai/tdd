"""
Quinn Agent — Schema Guardian for the TDD Platform.

Quinn watches for changes to the DRL template and signal catalog, computes
structural fingerprints, identifies affected deals, and generates migration packets.

Runs on demand or when templates/catalogs change. The orchestration entry point.

Usage from CLI:
    python -m agents.quinn --drl-path data/drl_template.xlsx --deal-id acme-corp-2024

Usage in code:
    from agents.quinn import run_quinn_check

    result = run_quinn_check(
        drl_template_path="data/drl_template.xlsx",
        catalog_path="data/signal_catalog.json",
        deal_id="acme-corp-2024"
    )
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from tools.quinn_schema_engine import (
    fingerprint_drl_template,
    fingerprint_signal_catalog,
    compare_fingerprints,
    save_fingerprints,
    load_fingerprints,
)
from tools.quinn_version_registry import (
    register_version,
    get_version_registry,
    find_affected_deals,
    mark_migration_status,
    get_migration_summary,
)

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"


# ── Main Quinn Orchestrator ───────────────────────────────────────────────────

def run_quinn_check(
    drl_template_path: str = "",
    catalog_path: str = "",
    deal_id: str = "",
) -> dict:
    """
    Run a complete Quinn schema check.

    Quinn's workflow:
    1. Fingerprint current DRL template (if path provided)
    2. Fingerprint current signal catalog
    3. Compare against stored fingerprints from last run
    4. If changes detected, generate migration packet and identify affected deals
    5. Update version registry for the deal (if deal_id provided)
    6. Return summary with recommendations

    Args:
        drl_template_path: Path to DRL template Excel file. If empty, skips DRL check.
        catalog_path: Path to signal catalog JSON. If empty, uses data/signal_catalog.json.
        deal_id: If provided, registers this deal with the current versions and marks migration status.

    Returns:
        {
            "status": "success" | "error",
            "timestamp": ISO-8601,
            "deal_id": str (if provided),
            "changes_detected": bool,
            "drl_migration_packet": {...} (if DRL changes detected),
            "catalog_migration_packet": {...} (if catalog changes detected),
            "affected_deals": {
                "drl_template": [deal_id, ...],
                "signal_catalog": [deal_id, ...]
            },
            "version_registry": {...} (if deal_id provided),
            "migration_summary": {...},
            "recommendations": [str, ...],
            "errors": [str, ...]
        }
    """
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

    result = {
        "status": "success",
        "timestamp": _iso_now(),
        "deal_id": deal_id or None,
        "changes_detected": False,
        "drl_migration_packet": None,
        "catalog_migration_packet": None,
        "affected_deals": {
            "drl_template": [],
            "signal_catalog": []
        },
        "version_registry": None,
        "migration_summary": None,
        "recommendations": [],
        "errors": []
    }

    try:
        # Load previous fingerprints for comparison
        previous_fps = load_fingerprints()
        current_fps = {}

        # ── Step 1: Check DRL Template ─────────────────────────────────────────
        if drl_template_path:
            drl_path = Path(drl_template_path)
            if not drl_path.exists():
                result["errors"].append(f"DRL template not found: {drl_path}")
            else:
                try:
                    logger.info(f"Fingerprinting DRL template: {drl_path}")
                    current_drl_fp = fingerprint_drl_template(str(drl_path))
                    current_fps["drl_template"] = current_drl_fp

                    if "drl_template" in previous_fps:
                        drl_migration = compare_fingerprints(
                            previous_fps["drl_template"],
                            current_drl_fp
                        )

                        if drl_migration["changes_detected"]:
                            result["changes_detected"] = True
                            result["drl_migration_packet"] = drl_migration
                            logger.warning(
                                f"DRL template change detected: "
                                f"{drl_migration['breaking_changes_count']} breaking, "
                                f"{drl_migration['compatible_changes_count']} compatible"
                            )

                            # Identify affected deals
                            old_version = drl_migration["from_version"]
                            affected = find_affected_deals(template_version=old_version)
                            result["affected_deals"]["drl_template"] = affected
                            drl_migration["affected_deals"] = affected

                            if drl_migration["reprocessing_required"]:
                                result["recommendations"].append(
                                    f"DRL template breaking changes detected ({old_version} → {drl_migration['to_version']}). "
                                    f"Affected {len(affected)} deals. Requires reprocessing of DRL responses."
                                )
                        else:
                            logger.info("DRL template: no changes detected")
                    else:
                        logger.info("First DRL template fingerprint recorded")

                except Exception as e:
                    result["errors"].append(f"DRL fingerprinting failed: {e}")
                    logger.exception("DRL fingerprinting error")

        # ── Step 2: Check Signal Catalog ───────────────────────────────────────
        if not catalog_path:
            catalog_path = str(DATA_DIR / "signal_catalog.json")

        catalog_file = Path(catalog_path)
        if not catalog_file.exists():
            result["errors"].append(f"Signal catalog not found: {catalog_file}")
        else:
            try:
                logger.info(f"Fingerprinting signal catalog: {catalog_file}")
                current_catalog_fp = fingerprint_signal_catalog(str(catalog_file))
                current_fps["signal_catalog"] = current_catalog_fp

                if "signal_catalog" in previous_fps:
                    catalog_migration = compare_fingerprints(
                        previous_fps["signal_catalog"],
                        current_catalog_fp
                    )

                    if catalog_migration["changes_detected"]:
                        result["changes_detected"] = True
                        result["catalog_migration_packet"] = catalog_migration
                        logger.warning(
                            f"Catalog change detected: "
                            f"{catalog_migration['breaking_changes_count']} breaking, "
                            f"{catalog_migration['compatible_changes_count']} compatible"
                        )

                        # Identify affected deals
                        old_version = catalog_migration["from_version"]
                        affected = find_affected_deals(catalog_version=old_version)
                        result["affected_deals"]["signal_catalog"] = affected
                        catalog_migration["affected_deals"] = affected

                        if catalog_migration["reprocessing_required"]:
                            result["recommendations"].append(
                                f"Catalog breaking changes detected ({old_version} → {catalog_migration['to_version']}). "
                                f"Affected {len(affected)} deals. Recommend re-running signal extraction."
                            )
                    else:
                        logger.info("Catalog: no changes detected")
                else:
                    logger.info("First catalog fingerprint recorded")

            except Exception as e:
                result["errors"].append(f"Catalog fingerprinting failed: {e}")
                logger.exception("Catalog fingerprinting error")

        # ── Step 3: Save Updated Fingerprints ──────────────────────────────────
        if current_fps:
            try:
                save_fingerprints(current_fps)
            except Exception as e:
                result["errors"].append(f"Failed to save fingerprints: {e}")

        # ── Step 4: Register Deal Version (if deal_id provided) ────────────────
        if deal_id:
            try:
                drl_version = (
                    current_fps.get("drl_template", {}).get("version")
                    or previous_fps.get("drl_template", {}).get("version")
                    or "unknown"
                )
                catalog_version = (
                    current_fps.get("signal_catalog", {}).get("version")
                    or previous_fps.get("signal_catalog", {}).get("version")
                    or "unknown"
                )

                register_version(
                    deal_id=deal_id,
                    template_version=drl_version,
                    catalog_version=catalog_version,
                    scan_id=f"quinn-scan-{_iso_now()}"
                )

                # Determine migration status
                drl_breaking = (
                    result["drl_migration_packet"]["breaking_changes_count"] > 0
                    if result["drl_migration_packet"]
                    else False
                )
                catalog_breaking = (
                    result["catalog_migration_packet"]["breaking_changes_count"] > 0
                    if result["catalog_migration_packet"]
                    else False
                )

                if drl_breaking or catalog_breaking:
                    migration_status = "requires_reprocessing"
                    migration_notes = "Breaking changes in schema"
                else:
                    migration_status = "compatible"
                    migration_notes = ""

                mark_migration_status(deal_id, migration_status, migration_notes)
                result["version_registry"] = get_version_registry(deal_id)

            except Exception as e:
                result["errors"].append(f"Failed to register deal version: {e}")
                logger.exception("Deal registration error")

        # ── Step 5: Get Migration Summary ──────────────────────────────────────
        try:
            result["migration_summary"] = get_migration_summary()
        except Exception as e:
            result["errors"].append(f"Failed to compute migration summary: {e}")

        # ── Step 6: Add Recommendations ────────────────────────────────────────
        if not result["changes_detected"]:
            result["recommendations"].append("No schema changes detected. All deals remain compatible.")
        elif not result["errors"]:
            if result["migration_summary"]:
                blocked_count = result["migration_summary"]["by_status"].get("blocked", 0)
                reprocess_count = result["migration_summary"]["by_status"].get("requires_reprocessing", 0)

                if blocked_count > 0:
                    result["recommendations"].append(
                        f"WARNING: {blocked_count} deals are blocked and require manual intervention."
                    )

                if reprocess_count > 0:
                    result["recommendations"].append(
                        f"Action: Re-run scans or DRL processing for {reprocess_count} affected deals."
                    )

    except Exception as e:
        result["status"] = "error"
        result["errors"].append(f"Unexpected error in Quinn: {e}")
        logger.exception("Unexpected Quinn error")

    return result


# ── CLI Entry Point ───────────────────────────────────────────────────────────

def main(
    drl_path: str = "",
    catalog_path: str = "",
    deal_id: str = "",
    output_file: str = "",
) -> None:
    """
    CLI entry point for Quinn.

    Example:
        python -m agents.quinn --drl-path data/drl_template.xlsx --deal-id acme-2024

    Args:
        drl_path: Path to DRL template
        catalog_path: Path to signal catalog (optional, defaults to data/signal_catalog.json)
        deal_id: Deal identifier (optional)
        output_file: Output file for results (optional, defaults to outputs/_quinn_check_<timestamp>.json)
    """
    result = run_quinn_check(
        drl_template_path=drl_path,
        catalog_path=catalog_path,
        deal_id=deal_id
    )

    # Determine output file
    if not output_file:
        output_file = OUTPUTS_DIR / f"_quinn_check_{_iso_now()}.json"
    else:
        output_file = Path(output_file)

    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    # Print summary to console
    print(f"\n{'=' * 70}")
    print(f"Quinn Schema Guardian — Schema Check Results")
    print(f"{'=' * 70}")
    print(f"Status: {result['status'].upper()}")
    print(f"Changes Detected: {result['changes_detected']}")
    print(f"Timestamp: {result['timestamp']}")

    if result["deal_id"]:
        print(f"Deal ID: {result['deal_id']}")
        if result["version_registry"]:
            print(f"  Template Version: {result['version_registry'].get('template_version')}")
            print(f"  Catalog Version: {result['version_registry'].get('catalog_version')}")
            print(f"  Migration Status: {result['version_registry'].get('migration_status')}")

    if result["drl_migration_packet"]:
        packet = result["drl_migration_packet"]
        print(f"\nDRL Template Migration:")
        print(f"  Breaking Changes: {packet['breaking_changes_count']}")
        print(f"  Compatible Changes: {packet['compatible_changes_count']}")
        print(f"  Affected Deals: {len(packet['affected_deals'])}")

    if result["catalog_migration_packet"]:
        packet = result["catalog_migration_packet"]
        print(f"\nCatalog Migration:")
        print(f"  Breaking Changes: {packet['breaking_changes_count']}")
        print(f"  Compatible Changes: {packet['compatible_changes_count']}")
        print(f"  Affected Deals: {len(packet['affected_deals'])}")

    if result["migration_summary"]:
        summary = result["migration_summary"]
        print(f"\nMigration Summary:")
        print(f"  Total Deals: {summary['total_deals']}")
        print(f"  Compatible: {summary['by_status'].get('compatible', 0)}")
        print(f"  Requires Reprocessing: {summary['by_status'].get('requires_reprocessing', 0)}")
        print(f"  Blocked: {summary['by_status'].get('blocked', 0)}")

    if result["recommendations"]:
        print(f"\nRecommendations:")
        for rec in result["recommendations"]:
            print(f"  - {rec}")

    if result["errors"]:
        print(f"\nErrors:")
        for err in result["errors"]:
            print(f"  - {err}")

    print(f"\nFull results: {output_file}")
    print(f"{'=' * 70}\n")


# ── Utility Functions ─────────────────────────────────────────────────────────

def _iso_now() -> str:
    """Return current ISO-8601 timestamp."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


# ── CLI Integration ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        prog="python -m agents.quinn",
        description="Quinn — Schema Guardian for TDD Platform"
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Check command
    check_parser = subparsers.add_parser("check", help="Run a complete Quinn schema check")
    check_parser.add_argument(
        "--drl-path",
        default="",
        help="Path to DRL template Excel file"
    )
    check_parser.add_argument(
        "--catalog-path",
        default="",
        help="Path to signal catalog JSON (optional)"
    )
    check_parser.add_argument(
        "--deal-id",
        default="",
        help="Deal identifier to register with current versions"
    )
    check_parser.add_argument(
        "--output",
        default="",
        help="Output file for results (optional)"
    )

    args = parser.parse_args()

    if args.command == "check":
        main(args.drl_path, args.catalog_path, args.deal_id, args.output)
    elif args.command:
        parser.print_help()
    else:
        parser.print_help()
        sys.exit(1)
