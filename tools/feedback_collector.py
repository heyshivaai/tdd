"""
Feedback collector: CLI tool for practitioners to rate signals at each Human Gate.

Reads the feedback shell written by report_writer, collects ratings interactively,
writes the completed feedback to disk, and upserts verdicts to Pinecone.

Why: Explicit practitioner feedback at each gate is the primary calibration signal
for the Signal Intelligence Layer. Every verdict (CONFIRMED/NOISE/UNCERTAIN) makes
future scans in the same sector and lens more accurate.

Usage:
    python -m tools.feedback_collector --deal DEAL-001 --phase 0 --gate 1
"""
import json
import logging
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
    """
    Load a feedback shell JSON file into a dict.

    Args:
        path: Filesystem path to the feedback_gate{N}.json file.

    Returns:
        Parsed JSON dict with deal_id, phase, gate, signal_ratings, etc.
    """
    with open(path) as f:
        return json.load(f)


def save_feedback(feedback: dict, path: str) -> None:
    """
    Write the completed feedback dict to a JSON file.

    Args:
        feedback: Completed feedback dict with practitioner_id, signal_ratings, etc.
        path: Destination filesystem path (typically feedback_gate{N}_completed.json).
    """
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

    Replaces any existing rating for signal_id (idempotent).
    Does not write to disk — returns the updated feedback dict.

    Args:
        feedback: The mutable feedback dict to update.
        signal_id: Unique signal identifier (e.g., "SIG-001").
        verdict: One of CONFIRMED, NOISE, or UNCERTAIN.
        practitioner_note: Free-text note explaining the verdict.
        corrected_rating: If verdict is CONFIRMED, optionally correct the signal's initial rating (RED/YELLOW/GREEN).

    Returns:
        Updated feedback dict with the new/updated signal rating appended.
    """
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
    phase: int = typer.Option(0, help="Phase number (0 = VDR triage)"),
    gate: int = typer.Option(1, help="Gate number (1, 2, 3, etc.)"),
    practitioner: str = typer.Option("", help="Practitioner ID/name"),
) -> None:
    """
    Interactively collect practitioner signal ratings at a Human Gate.

    Reads feedback_gate{gate}.json, walks through signals in the brief,
    collects CONFIRMED/NOISE/UNCERTAIN verdict + optional note + optional corrected rating,
    then writes completed feedback to disk and upserts verdicts to Pinecone.

    Example:
        python -m tools.feedback_collector --deal DEAL-001 --phase 0 --gate 1 --practitioner "Shiva"
    """
    # Find the VDR Intelligence Brief for this deal
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
    typer.echo(f"{len(signals)} signals to review. C=CONFIRMED, N=NOISE, U=UNCERTAIN\n")

    for sig in signals:
        typer.echo(f"[{sig.get('rating')}] {sig['signal_id']}: {sig.get('title', '')}")
        typer.echo(f"  {sig.get('observation', '')}")
        raw = typer.prompt("  Verdict (C/N/U)", default="C").upper()
        verdict = {"C": "CONFIRMED", "N": "NOISE", "U": "UNCERTAIN"}.get(raw, "UNCERTAIN")
        note = typer.prompt("  Note (optional)", default="")
        corrected = None
        if verdict == "CONFIRMED":
            correction_raw = typer.prompt("  Corrected rating (or Enter to keep)", default="").upper()
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
