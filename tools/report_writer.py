"""
Report writer: renders the three VDR triage outputs (JSON brief, triage MD report,
completeness MD report) and a blank feedback shell from the brief dict.

Why: Separating rendering from computation means the orchestrator only deals with
data; formatting decisions live here and can be iterated without touching logic.
"""
import json
from pathlib import Path
from typing import List

RATING_EMOJI = {
    "RED": "RED",
    "YELLOW": "YELLOW",
    "GREEN": "GREEN",
    "UNKNOWN": "UNKNOWN",
    "CRITICAL": "CRITICAL",
    "HIGH": "HIGH",
    "MEDIUM": "MEDIUM",
}


def write_intelligence_brief(brief: dict, output_dir: Path) -> Path:
    """Write the VDR Intelligence Brief JSON to output_dir/<deal_id>/vdr_intelligence_brief.json.

    Uses deal_id as the folder name (consistent with deal system), falling back
    to company_name for backward compatibility.
    """
    folder = brief.get("deal_id") or brief.get("company_name", "UNKNOWN")
    dest = _ensure_company_dir(output_dir, folder) / "vdr_intelligence_brief.json"
    dest.write_text(json.dumps(brief, indent=2, ensure_ascii=False), encoding="utf-8")
    return dest


def write_triage_report(brief: dict, output_dir: Path) -> Path:
    """Render the practitioner-facing triage report (heatmap + reading list + compound risks)."""
    folder = brief.get("deal_id") or brief.get("company_name", "UNKNOWN")
    dest = _ensure_company_dir(output_dir, folder) / "vdr_triage_report.md"
    dest.write_text(_render_triage_md(brief), encoding="utf-8")
    return dest


def write_completeness_report(completeness: dict, output_dir: Path) -> Path:
    """Render the completeness gap report as Markdown."""
    deal_id = completeness.get("deal_id", "UNKNOWN")
    dest = _ensure_company_dir(output_dir, deal_id) / "vdr_completeness_report.md"
    dest.write_text(_render_completeness_md(completeness), encoding="utf-8")
    return dest


def write_feedback_shell(brief: dict, output_dir: Path, gate: int) -> Path:
    """Write an empty practitioner feedback JSON shell for the given gate."""
    folder = brief.get("deal_id") or brief.get("company_name", "UNKNOWN")
    deal_id = brief.get("deal_id", "UNKNOWN")
    dest = _ensure_company_dir(output_dir, folder) / f"feedback_gate{gate}.json"
    shell = {
        "deal_id": deal_id,
        "phase": 0,
        "gate": gate,
        "practitioner_id": "",
        "timestamp": "",
        "signal_ratings": [],
        "phase_accuracy_score": None,
        "missed_signals": [],
        "outcome_data": {
            "deal_outcome": "pending",
            "signals_proved_material": [],
            "signals_proved_immaterial": [],
        },
    }
    dest.write_text(json.dumps(shell, indent=2), encoding="utf-8")
    return dest


# --- Private rendering helpers ---

def _sanitize_folder_name(name: str) -> str:
    """Sanitize a folder name to prevent path traversal and invalid characters.

    Why: deal_id and company_name come from user input (or LLM output).
    A value like '../../etc' or 'foo/bar' could escape the outputs directory.
    """
    # Remove path separators and parent-directory references
    sanitized = name.replace("/", "_").replace("\\", "_").replace("..", "_")
    # Strip leading/trailing whitespace and dots
    sanitized = sanitized.strip().strip(".")
    return sanitized or "UNKNOWN"


def _ensure_company_dir(output_dir: Path, company: str) -> Path:
    """Create and return output_dir/<company>/ directory.

    Sanitizes the folder name to prevent path traversal attacks.
    """
    safe_name = _sanitize_folder_name(company)
    d = output_dir / safe_name
    # Final check: resolved path must be under output_dir
    if not str(d.resolve()).startswith(str(output_dir.resolve())):
        raise ValueError(f"Invalid folder name would escape output directory: {company!r}")
    d.mkdir(parents=True, exist_ok=True)
    return d


def _rating_badge(rating: str) -> str:
    """Return a plain-text rating label (no emoji, for safe Markdown rendering)."""
    return f"**{rating}**"


def _render_triage_md(brief: dict) -> str:
    """Render the triage report Markdown from a brief dict."""
    lines: List[str] = []
    company = brief.get("company_name", "UNKNOWN")
    deal_id = brief.get("deal_id", "")
    ts = brief.get("vdr_scan_timestamp", "")
    overall = brief.get("overall_signal_rating", "UNKNOWN")

    lines += [
        f"# VDR Triage Report — {company}",
        f"**Deal ID:** {deal_id}  |  **Scanned:** {ts}  |  **Overall:** {_rating_badge(overall)}",
        "",
        "---",
        "",
        "## Signal Heatmap",
        "",
        "| Lens | Rating | Signals | RED | Top Signal |",
        "|---|---|---|---|---|",
    ]

    for lens, data in brief.get("lens_heatmap", {}).items():
        lines.append(
            f"| {lens} | {_rating_badge(data['rating'])} | "
            f"{data['signal_count']} | {data['red_count']} | {data['top_signal']} |"
        )

    lines += ["", "---", "", "## Compound Risks", ""]
    for risk in brief.get("compound_risks", []):
        sev = risk.get("severity", "")
        lines += [
            f"### {risk['risk_id']}: {risk['title']} — {_rating_badge(sev)}",
            "",
            risk.get("narrative", ""),
            "",
            f"*Contributing signals: {', '.join(risk.get('contributing_signals', []))}*",
            "",
        ]

    lines += ["---", "", "## Prioritized Reading List", ""]
    for item in brief.get("prioritized_reading_list", []):
        lines.append(
            f"{item['rank']}. **{item['document']}** ({item['vdr_section']}) — "
            f"~{item.get('estimated_read_time_mins', '?')} min  \n"
            f"   *{item.get('reason', '')}*  \n"
            f"   Preview: {item.get('top_signal_preview', '')}"
        )
        lines.append("")

    lines += ["---", "", "## Domain Slices", ""]
    for slice_name, slice_data in brief.get("domain_slices", {}).items():
        rating = slice_data.get("overall_rating", "UNKNOWN")
        lines += [
            f"### {slice_name.replace('_', ' ').title()} — {_rating_badge(rating)}",
            "",
            slice_data.get("summary", ""),
            "",
        ]

    return "\n".join(lines)


def _render_completeness_md(report: dict) -> str:
    """Render the completeness gap report Markdown from a completeness dict."""
    lines: List[str] = []
    lines += [
        f"# VDR Completeness Report — {report.get('deal_id', '')}",
        f"**Deal Type:** {report.get('deal_type', '')}  |  "
        f"**Sector:** {report.get('sector', '')}  |  "
        f"**Completeness Score:** {report.get('completeness_score', 0)}/100",
        "",
        f"> {report.get('chase_list_summary', '')}",
        "",
        "---",
        "",
        "## Missing Documents",
        "",
        "| Gap ID | Urgency | Expected Document | Request Language |",
        "|---|---|---|---|",
    ]

    for gap in report.get("missing_documents", []):
        lines.append(
            f"| {gap['gap_id']} | {_rating_badge(gap['urgency'])} | "
            f"{gap['expected_document']} | {gap['request_language']} |"
        )

    if report.get("present_but_incomplete"):
        lines += ["", "---", "", "## Present but Incomplete", ""]
        for item in report["present_but_incomplete"]:
            lines += [
                f"**{item['document']}**: {item['issue']}",
                f"> Request: {item['request_language']}",
                "",
            ]

    return "\n".join(lines)
