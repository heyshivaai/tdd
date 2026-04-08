"""
VDR Triage Agent: orchestrates the four-step Phase 0 pipeline.

Pipeline: Structure Mapper → Completeness Checker → Document Reader →
          Signal Extractor (per batch) → Cross-Referencer → Report Writer

Outputs written to outputs/<company_name>/:
  - vdr_intelligence_brief.json
  - vdr_triage_report.md
  - vdr_completeness_report.md
  - feedback_gate1.json (empty shell)

Usage:
    python -m agents.vdr_triage --vdr-path "VDR/..." --company HORIZON \
        --deal-id DEAL-001 --sector healthcare-saas --deal-type pe-acquisition
"""
import json
import logging
import os
from pathlib import Path
from typing import Tuple

import anthropic
import typer
from dotenv import load_dotenv

from tools.completeness_checker import check_completeness
from tools.cross_referencer import cross_reference_signals
from tools.document_reader import extract_text, extract_text_from_pdf
from tools.report_writer import (
    write_completeness_report,
    write_feedback_shell,
    write_intelligence_brief,
    write_triage_report,
)
from tools.scan_registry import update_scan, start_batch_timer, finish_batch_timer
from tools.signal_extractor import extract_signals_from_batch
from tools.signal_store import query_similar_patterns, store_gap, store_signals
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
    selected_batches: list[str] | None = None,
) -> Tuple[dict, dict]:
    """
    Execute the full Phase 0 VDR triage pipeline.

    Args:
        selected_batches: If provided, only process these batch groups.
            None means process all batches (full scan).

    Returns (intelligence_brief, completeness_report) as dicts.
    All four output files are written to outputs/<company_name>/.
    """
    logger.info("Step 1: Mapping VDR structure — %s", vdr_path)
    update_scan(company_name, phase="mapping_vdr", progress={"step": "Step 1/4: Mapping VDR structure"})
    vdr_map = map_vdr_structure(vdr_path, str(BATCH_RULES_PATH))
    inventory = vdr_map["inventory"]
    batch_groups = vdr_map["batch_groups"]
    logger.info("Inventory: %d files across %d batch groups", len(inventory), len(batch_groups))
    # Filter to selected batches if selective scan
    if selected_batches:
        skipped = set(batch_groups.keys()) - set(selected_batches)
        batch_groups = {k: v for k, v in batch_groups.items() if k in selected_batches}
        logger.info("Selective scan: %d batches selected, %d skipped (%s)",
                    len(batch_groups), len(skipped), ", ".join(sorted(skipped)))

    update_scan(company_name, progress={
        "doc_count": len(inventory),
        "batches_total": len(batch_groups),
        "step": f"Step 1/4 complete: {len(inventory)} files, {len(batch_groups)} batches"
              + (f" (selective: {len(batch_groups)} of {len(vdr_map['batch_groups'])})" if selected_batches else ""),
    })

    logger.info("Step 2: Checking completeness")
    update_scan(company_name, phase="completeness_check", progress={"step": "Step 2/4: Checking completeness"})
    with open(EXPECTED_DOCS_PATH) as f:
        expected_docs = json.load(f)
    completeness = check_completeness(
        inventory=inventory,
        expected_docs=expected_docs,
        sector=sector,
        deal_type=deal_type,
        deal_id=deal_id,
    )
    logger.info(
        "Completeness score: %d/100 — %d gaps found",
        completeness["completeness_score"],
        len(completeness["missing_documents"]),
    )

    update_scan(company_name, progress={
        "completeness_score": completeness["completeness_score"],
        "gaps_found": len(completeness["missing_documents"]),
        "step": f"Step 2/4 complete: score {completeness['completeness_score']}/100, {len(completeness['missing_documents'])} gaps",
    })

    logger.info("Step 3: Signal extraction per batch")
    update_scan(company_name, phase="signal_extraction", progress={
        "step": "Step 3/4: Signal extraction",
        "batches_total": len(batch_groups),
    })
    all_batch_results = []
    batch_index = 0
    for batch_id, docs in batch_groups.items():
        start_batch_timer(company_name)
        enriched_docs = []
        for doc in docs:
            # Use generic extract_text which handles PDF, DOCX, XLSX, etc.
            file_type = doc.get("file_type", ".pdf")
            if file_type == ".pdf":
                chunks = extract_text_from_pdf(doc["filepath"])
            else:
                chunks = extract_text(doc["filepath"])
            enriched_docs.append({**doc, "text_chunks": chunks})

        total_chunks = sum(len(d["text_chunks"]) for d in enriched_docs)
        logger.info(
            "  Batch %s: %d docs, %d chunks total",
            batch_id,
            len(docs),
            total_chunks,
        )

        if total_chunks == 0:
            logger.info("  Batch %s: no readable text — skipping signal extraction", batch_id)
            all_batch_results.append(
                {"batch_id": batch_id, "documents": [d["filename"] for d in docs], "signals": [], "batch_summary": ""}
            )
            batch_index += 1
            finish_batch_timer(company_name)
            update_scan(company_name, progress={
                "batches_done": batch_index,
                "step": f"Step 3/4: Batch {batch_index}/{len(batch_groups)} — {batch_id} (skipped, no text)",
                "current_batch": batch_id,
            })
            continue

        # Phase B: Query Signal Intelligence Layer for prior patterns
        prior_patterns = query_similar_patterns(
            query_text=f"{sector} {batch_id} signals",
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
        logger.info("  Batch %s: %d signals extracted, %d prior patterns used",
                    batch_id, signal_count, len(prior_patterns))
        batch_index += 1
        finish_batch_timer(company_name)
        total_signals_so_far = sum(len(b.get("signals", [])) for b in all_batch_results)
        update_scan(company_name, progress={
            "batches_done": batch_index,
            "signals_found": total_signals_so_far,
            "step": f"Step 3/4: Batch {batch_index}/{len(batch_groups)} — {batch_id} ({signal_count} signals)",
            "current_batch": batch_id,
        })

        # Store signals in Signal Intelligence Layer
        if batch_result.get("signals"):
            store_signals(batch_result["signals"], deal_id=deal_id, sector=sector, phase=0)

    logger.info("Step 4: Cross-referencing into VDR Intelligence Brief")
    update_scan(company_name, phase="cross_referencing", progress={
        "step": "Step 4/4: Cross-referencing signals into intelligence brief",
    })
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

    # ── Merge raw batch signals into the brief ──────────────────────────────
    # The cross-referencer produces a synthesized summary (domain_slices, compound
    # risks, rating). We also need the raw extracted signals and batch_results so
    # the dashboard can show signal inventory, pillar counts, and per-batch detail.
    all_signals = [sig for batch in all_batch_results for sig in batch.get("signals", [])]
    brief["batch_results"] = all_batch_results
    brief["signals"] = all_signals
    brief["signal_count"] = len(all_signals)
    brief["document_inventory"] = inventory

    # Store completeness gaps in Signal Intelligence Layer
    for gap in completeness.get("missing_documents", []):
        store_gap(gap, deal_id=deal_id, sector=sector)

    logger.info("Writing outputs to %s/%s/", OUTPUT_DIR, company_name)
    write_intelligence_brief(brief, OUTPUT_DIR)
    write_triage_report(brief, OUTPUT_DIR)
    write_completeness_report(completeness, OUTPUT_DIR)
    write_feedback_shell(brief, OUTPUT_DIR, gate=1)

    total_signals = sum(len(b.get("signals", [])) for b in all_batch_results)
    logger.info(
        "Triage complete. Rating: %s | Signals: %d | Gaps: %d",
        brief.get("overall_signal_rating"),
        total_signals,
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
