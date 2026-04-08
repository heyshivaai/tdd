"""
Report export: generates DOCX reports from scan results.

Reads domain_findings.json, vdr_intelligence_brief.json, and scan_history.json
to produce a comprehensive Technology Due Diligence report.
"""
import io
import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

OUTPUTS_DIR = Path(__file__).parent.parent / "outputs"


def generate_report(company_name: str) -> Optional[io.BytesIO]:
    """
    Generate a DOCX Technology Due Diligence report for a company.

    Reads from outputs/<company_name>/ and assembles a formatted DOCX
    with executive summary, domain findings, signal details, and chase list.

    Args:
        company_name: Company name (subfolder in outputs/).

    Returns:
        BytesIO buffer containing the DOCX file, or None if generation failed.
    """
    company_dir = OUTPUTS_DIR / company_name
    if not company_dir.exists():
        logger.error("No output directory found for %s", company_name)
        return None

    try:
        from docx import Document
        from docx.shared import Inches, Pt, RGBColor
        from docx.enum.text import WD_ALIGN_PARAGRAPH
    except ImportError:
        logger.error("python-docx not installed — cannot generate DOCX report")
        return None

    # Load data
    brief_path = company_dir / "vdr_intelligence_brief.json"
    domain_path = company_dir / "domain_findings.json"

    brief = {}
    domain_data = {}

    if brief_path.exists():
        try:
            with open(brief_path, "r", encoding="utf-8") as f:
                brief = json.load(f)
        except Exception as exc:
            logger.warning("Failed to load brief: %s", exc)

    if domain_path.exists():
        try:
            with open(domain_path, "r", encoding="utf-8") as f:
                domain_data = json.load(f)
        except Exception as exc:
            logger.warning("Failed to load domain findings: %s", exc)

    if not brief and not domain_data:
        logger.error("No scan data found for %s", company_name)
        return None

    # Build document
    doc = Document()

    # Title
    title = doc.add_heading(f"Technology Due Diligence Report", level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER

    doc.add_paragraph(f"Company: {company_name}")
    doc.add_paragraph(
        f"Rating: {brief.get('overall_signal_rating', domain_data.get('_metadata', {}).get('rating', 'N/A'))}"
    )

    # Executive Summary
    doc.add_heading("Executive Summary", level=1)
    if brief.get("executive_summary"):
        doc.add_paragraph(brief["executive_summary"])
    else:
        doc.add_paragraph(
            f"This report covers the technology due diligence analysis of {company_name}. "
            f"The analysis was conducted across {len(domain_data.get('domains', {}))} domains."
        )

    # Domain Findings
    domains = domain_data.get("domains", {})
    if domains:
        doc.add_heading("Domain Analysis", level=1)

        for pid, dinfo in domains.items():
            plabel = dinfo.get("pillar_label", pid)
            grade = dinfo.get("grade", "UNKNOWN")
            summary = dinfo.get("domain_summary", "")

            doc.add_heading(f"{plabel} — {grade}", level=2)
            if summary:
                doc.add_paragraph(summary)

            findings = dinfo.get("findings", [])
            if findings:
                doc.add_heading("Findings", level=3)
                for finding in findings:
                    sev = finding.get("severity", "MEDIUM")
                    title_text = finding.get("title", "Untitled")
                    desc = finding.get("description", "")
                    p = doc.add_paragraph()
                    run = p.add_run(f"[{sev}] {title_text}")
                    run.bold = True
                    if desc:
                        doc.add_paragraph(desc)

            blind_spots = dinfo.get("blind_spots", [])
            if blind_spots:
                doc.add_heading("Blind Spots", level=3)
                for bs in blind_spots:
                    doc.add_paragraph(f"• {bs}")

    # Chase List
    chase_list = domain_data.get("chase_list", [])
    if chase_list:
        doc.add_heading("Questions for Target Company", level=1)
        for i, q in enumerate(chase_list, 1):
            question = q.get("question", str(q)) if isinstance(q, dict) else str(q)
            pillar = q.get("pillar_label", "") if isinstance(q, dict) else ""
            prefix = f"[{pillar}] " if pillar else ""
            doc.add_paragraph(f"{i}. {prefix}{question}")

    # Signal Summary
    if brief:
        heatmap = brief.get("lens_heatmap", brief.get("pillar_heatmap", {}))
        if heatmap:
            doc.add_heading("Signal Heatmap", level=1)
            table = doc.add_table(rows=1, cols=4)
            table.style = "Light Grid Accent 1"
            hdr = table.rows[0].cells
            hdr[0].text = "Domain"
            hdr[1].text = "Rating"
            hdr[2].text = "Signals"
            hdr[3].text = "Red Flags"
            for lens_name, lens_data in heatmap.items():
                row = table.add_row().cells
                row[0].text = lens_name
                row[1].text = lens_data.get("rating", "?")
                row[2].text = str(lens_data.get("signal_count", 0))
                row[3].text = str(lens_data.get("red_count", 0))

    # Save to buffer
    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    logger.info("Generated DOCX report for %s (%d bytes)", company_name, buf.getbuffer().nbytes)
    return buf
