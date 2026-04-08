"""
Signal Catalog Manager — CLI for managing signal_catalog.json and signal_pillars.json.

Single source of truth lives in data/signal_catalog.json and data/signal_pillars.json.
This tool handles additions, validation, and changelog generation so nobody edits JSON by hand.

Usage:
    python -m tools.catalog_manager add-signal
    python -m tools.catalog_manager list
    python -m tools.catalog_manager validate
    python -m tools.catalog_manager bump --reason "Horizon calibration round 2"
"""
from __future__ import annotations

import json
import datetime
from pathlib import Path
from typing import Optional

import typer

app = typer.Typer(help="Manage the signal catalog and pillars.")

DATA_DIR = Path(__file__).parent.parent / "data"
CATALOG_PATH = DATA_DIR / "signal_catalog.json"
PILLARS_PATH = DATA_DIR / "signal_pillars.json"
CHANGELOG_PATH = DATA_DIR / "CHANGELOG.md"

VALID_PILLARS = {
    "TechnologyArchitecture": {"prefix": "TA", "label": "Technology & Architecture"},
    "SecurityCompliance": {"prefix": "SC", "label": "Security and Compliance"},
    "OrganizationTalent": {"prefix": "OT", "label": "Organization & Talent"},
    "DataAIReadiness": {"prefix": "DA", "label": "Data & AI Readiness"},
    "RDSpendAssessment": {"prefix": "RS", "label": "R&D Spend Assessment"},
    "InfrastructureDeployment": {"prefix": "ID", "label": "Infrastructure and Deployment"},
    "SDLCProductManagement": {"prefix": "SP", "label": "SDLC and Product Management Process"},
}

VALID_WEIGHTS = ["High", "Medium"]
VALID_TEMPORAL = ["Current Health", "Dual", "Future Readiness"]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_catalog() -> dict:
    """Load the signal catalog from disk."""
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def _save_catalog(catalog: dict) -> None:
    """Write the catalog back to disk."""
    CATALOG_PATH.write_text(json.dumps(catalog, indent=2, ensure_ascii=False), encoding="utf-8")


def _load_pillars() -> dict:
    """Load the signal pillars from disk."""
    return json.loads(PILLARS_PATH.read_text(encoding="utf-8"))


def _save_pillars(pillars: dict) -> None:
    """Write the pillars back to disk."""
    PILLARS_PATH.write_text(json.dumps(pillars, indent=2, ensure_ascii=False), encoding="utf-8")


def _next_signal_id(catalog: dict, pillar_id: str) -> str:
    """Generate the next sequential signal ID for a pillar (e.g., TA-09)."""
    prefix = VALID_PILLARS[pillar_id]["prefix"]
    existing = [
        s["signal_id"] for s in catalog["signals"]
        if s["signal_id"].startswith(prefix + "-")
    ]
    if not existing:
        return f"{prefix}-01"
    max_num = max(int(sid.split("-")[1]) for sid in existing)
    return f"{prefix}-{max_num + 1:02d}"


def _pillar_number(pillar_id: str) -> int:
    """Get the pillar number from the ordered VALID_PILLARS dict."""
    return list(VALID_PILLARS.keys()).index(pillar_id) + 1


def _append_changelog(version: str, entries: list[dict], reason: str) -> None:
    """Append a new version block to CHANGELOG.md."""
    date = datetime.date.today().isoformat()

    lines = [
        f"\n## v{version} — {date}\n",
        f"\n**Source:** {reason}\n",
    ]

    if entries:
        lines.append(f"\n**Added {len(entries)} signal(s)** ({int(version.split('.')[0])}.{int(version.split('.')[1]) - 1} → {version}):\n")
        lines.append("\n| Signal ID | Pillar | Name | Why Added |")
        lines.append("\n|-----------|--------|------|-----------|")
        for e in entries:
            lines.append(f"\n| {e['signal_id']} | {e['pillar_id']} | {e['name']} | {e['reason']} |")
        lines.append("\n")

    # Read existing changelog and insert new block after the header
    if CHANGELOG_PATH.exists():
        content = CHANGELOG_PATH.read_text(encoding="utf-8")
        # Find the first ## heading and insert before it
        marker = "\n## v"
        idx = content.find(marker)
        if idx != -1:
            new_content = content[:idx] + "".join(lines) + content[idx:]
        else:
            new_content = content + "".join(lines)
    else:
        header = "# Signal Catalog Changelog\n\nAll changes to `signal_catalog.json` and `signal_pillars.json` are documented here.\n"
        new_content = header + "".join(lines)

    CHANGELOG_PATH.write_text(new_content, encoding="utf-8")


def _bump_version(catalog: dict) -> str:
    """Increment the minor version (e.g., 1.4 → 1.5)."""
    parts = catalog["version"].split(".")
    major, minor = int(parts[0]), int(parts[1])
    return f"{major}.{minor + 1}"


# ── Commands ──────────────────────────────────────────────────────────────────

@app.command()
def add_signal(
    pillar: str = typer.Option(..., help="Pillar ID (e.g., TechnologyArchitecture)"),
    name: str = typer.Option(..., help="Signal name"),
    definition: str = typer.Option(..., help="Technical definition"),
    sources: str = typer.Option(..., help="Primary data sources"),
    guidance: str = typer.Option(..., help="Interpretation guidance"),
    reason: str = typer.Option(..., help="Why this signal is being added (for changelog)"),
    weight: str = typer.Option("High", help="Conviction weight: High or Medium"),
    temporal: str = typer.Option("Current Health", help="Temporal orientation: Current Health, Dual, or Future Readiness"),
    modifiers: str = typer.Option("", help="Contextual modifiers (comma-separated)"),
    auto_bump: bool = typer.Option(True, help="Auto-bump catalog version"),
) -> None:
    """Add a new signal to the catalog, update pillars, and append changelog."""

    # Validate inputs
    if pillar not in VALID_PILLARS:
        typer.echo(f"Invalid pillar: {pillar}")
        typer.echo(f"Valid pillars: {', '.join(VALID_PILLARS.keys())}")
        raise typer.Exit(1)

    if weight not in VALID_WEIGHTS:
        typer.echo(f"Invalid weight: {weight}. Must be one of: {VALID_WEIGHTS}")
        raise typer.Exit(1)

    if temporal not in VALID_TEMPORAL:
        typer.echo(f"Invalid temporal: {temporal}. Must be one of: {VALID_TEMPORAL}")
        raise typer.Exit(1)

    catalog = _load_catalog()
    pillars = _load_pillars()

    # Check for duplicate names
    existing_names = [s["name"].lower() for s in catalog["signals"]]
    if name.lower() in existing_names:
        typer.echo(f"Signal with name '{name}' already exists.")
        raise typer.Exit(1)

    # Generate signal ID
    signal_id = _next_signal_id(catalog, pillar)
    pillar_info = VALID_PILLARS[pillar]

    # Build signal object
    signal = {
        "signal_id": signal_id,
        "pillar_number": _pillar_number(pillar),
        "pillar_name": pillar_info["label"],
        "name": name,
        "conviction_weight": weight,
        "temporal_orientation": temporal,
        "technical_definition": definition,
        "primary_data_sources": sources,
        "contextual_modifiers": modifiers,
        "interpretation_guidance": guidance,
        "pillar_id": pillar,
    }

    # Add to catalog
    catalog["signals"].append(signal)
    catalog["total_signals"] = len(catalog["signals"])

    if auto_bump:
        new_version = _bump_version(catalog)
        catalog["version"] = new_version
        catalog["generated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        pillars["version"] = new_version
    else:
        new_version = catalog["version"]

    # Update pillars
    for p in pillars["pillars"]:
        if p["id"] == pillar:
            if signal_id not in p["signal_ids"]:
                p["signal_ids"].append(signal_id)
                p["signal_count"] = len(p["signal_ids"])
            break
    pillars["total_signals"] = sum(p["signal_count"] for p in pillars["pillars"])

    # Save
    _save_catalog(catalog)
    _save_pillars(pillars)

    # Changelog
    _append_changelog(
        new_version,
        [{"signal_id": signal_id, "pillar_id": pillar, "name": name, "reason": reason}],
        reason,
    )

    typer.echo(f"✓ Added {signal_id}: {name} → {pillar}")
    typer.echo(f"  Catalog: v{new_version}, {catalog['total_signals']} signals")
    typer.echo(f"  Changelog updated")


@app.command()
def add_batch(
    signals_file: Path = typer.Argument(..., help="JSON file with array of signal objects"),
    reason: str = typer.Option(..., help="Why these signals are being added (for changelog)"),
    auto_bump: bool = typer.Option(True, help="Auto-bump catalog version"),
) -> None:
    """Add multiple signals from a JSON file. Each object needs: pillar, name, definition, sources, guidance, reason."""

    if not signals_file.exists():
        typer.echo(f"File not found: {signals_file}")
        raise typer.Exit(1)

    new_signals = json.loads(signals_file.read_text(encoding="utf-8"))
    if not isinstance(new_signals, list):
        typer.echo("Expected a JSON array of signal objects.")
        raise typer.Exit(1)

    catalog = _load_catalog()
    pillars = _load_pillars()
    changelog_entries = []

    for sig_input in new_signals:
        pillar = sig_input["pillar"]
        if pillar not in VALID_PILLARS:
            typer.echo(f"Skipping invalid pillar: {pillar}")
            continue

        name = sig_input["name"]
        existing_names = [s["name"].lower() for s in catalog["signals"]]
        if name.lower() in existing_names:
            typer.echo(f"Skipping duplicate: {name}")
            continue

        signal_id = _next_signal_id(catalog, pillar)
        pillar_info = VALID_PILLARS[pillar]

        signal = {
            "signal_id": signal_id,
            "pillar_number": _pillar_number(pillar),
            "pillar_name": pillar_info["label"],
            "name": name,
            "conviction_weight": sig_input.get("weight", "High"),
            "temporal_orientation": sig_input.get("temporal", "Current Health"),
            "technical_definition": sig_input["definition"],
            "primary_data_sources": sig_input["sources"],
            "contextual_modifiers": sig_input.get("modifiers", ""),
            "interpretation_guidance": sig_input["guidance"],
            "pillar_id": pillar,
        }

        catalog["signals"].append(signal)

        for p in pillars["pillars"]:
            if p["id"] == pillar:
                p["signal_ids"].append(signal_id)
                p["signal_count"] = len(p["signal_ids"])
                break

        changelog_entries.append({
            "signal_id": signal_id,
            "pillar_id": pillar,
            "name": name,
            "reason": sig_input.get("reason", reason),
        })
        typer.echo(f"  + {signal_id}: {name} → {pillar}")

    catalog["total_signals"] = len(catalog["signals"])
    pillars["total_signals"] = sum(p["signal_count"] for p in pillars["pillars"])

    if auto_bump and changelog_entries:
        new_version = _bump_version(catalog)
        catalog["version"] = new_version
        catalog["generated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        pillars["version"] = new_version
    else:
        new_version = catalog["version"]

    _save_catalog(catalog)
    _save_pillars(pillars)

    if changelog_entries:
        _append_changelog(new_version, changelog_entries, reason)

    typer.echo(f"\n✓ Added {len(changelog_entries)} signals → v{new_version} ({catalog['total_signals']} total)")


@app.command(name="list")
def list_signals(
    pillar: Optional[str] = typer.Option(None, help="Filter by pillar ID"),
) -> None:
    """List all signals in the catalog."""
    catalog = _load_catalog()

    signals = catalog["signals"]
    if pillar:
        signals = [s for s in signals if s["pillar_id"] == pillar]

    typer.echo(f"Signal Catalog v{catalog['version']} — {len(signals)} signals")
    typer.echo(f"{'ID':<8} {'Pillar':<28} {'Weight':<8} {'Name'}")
    typer.echo("─" * 80)
    for s in signals:
        typer.echo(f"{s['signal_id']:<8} {s['pillar_id']:<28} {s['conviction_weight']:<8} {s['name']}")


@app.command()
def validate() -> None:
    """Validate catalog and pillars integrity."""
    catalog = _load_catalog()
    pillars = _load_pillars()
    errors = []

    # Unique signal IDs
    ids = [s["signal_id"] for s in catalog["signals"]]
    dupes = set(x for x in ids if ids.count(x) > 1)
    if dupes:
        errors.append(f"Duplicate signal IDs: {dupes}")

    # Valid pillar IDs
    for s in catalog["signals"]:
        if s["pillar_id"] not in VALID_PILLARS:
            errors.append(f"{s['signal_id']}: invalid pillar_id '{s['pillar_id']}'")

    # Pillar signal counts match
    for p in pillars["pillars"]:
        expected = sum(1 for s in catalog["signals"] if s["pillar_id"] == p["id"])
        if expected != p["signal_count"]:
            errors.append(f"{p['id']}: pillar says {p['signal_count']} signals, catalog has {expected}")
        for sid in p["signal_ids"]:
            if sid not in ids:
                errors.append(f"{p['id']}: references {sid} but it's not in the catalog")

    # Total counts
    if catalog["total_signals"] != len(catalog["signals"]):
        errors.append(f"Catalog total_signals={catalog['total_signals']} but has {len(catalog['signals'])} signals")

    # Version consistency
    if catalog["version"] != pillars["version"]:
        errors.append(f"Version mismatch: catalog={catalog['version']}, pillars={pillars['version']}")

    if errors:
        typer.echo(f"✗ {len(errors)} error(s):")
        for e in errors:
            typer.echo(f"  - {e}")
        raise typer.Exit(1)
    else:
        typer.echo(f"✓ Catalog v{catalog['version']}: {len(ids)} signals, {len(pillars['pillars'])} pillars — all valid")


@app.command()
def bump(
    reason: str = typer.Option(..., help="Reason for version bump"),
) -> None:
    """Bump the catalog version without adding signals (e.g., after prompt changes)."""
    catalog = _load_catalog()
    pillars = _load_pillars()

    new_version = _bump_version(catalog)
    catalog["version"] = new_version
    catalog["generated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    pillars["version"] = new_version

    _save_catalog(catalog)
    _save_pillars(pillars)
    _append_changelog(new_version, [], reason)

    typer.echo(f"✓ Bumped to v{new_version}: {reason}")


if __name__ == "__main__":
    app()
