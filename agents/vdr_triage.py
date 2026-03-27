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
    All four output files are written to outputs/<company_name>/.
    """
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
    logger.info(
        "Completeness score: %d/100 — %d gaps found",
        completeness["completeness_score"],
        len(completeness["missing_documents"]),
    )

    logger.info("Step 3: Signal extraction per batch")
    all_batch_results = []
    for batch_id, docs in batch_groups.items():
        enriched_docs = []
        for doc in docs:
            chunks = extract_text_from_pdf(doc["filepath"])
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
            continue

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
        logger.info("  Batch %s: %d signals extracted", batch_id, len(batch_result.get("signals", [])))

    logger.info("Step 4: Cross-referencing into VDR Intelligence Brief")
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
