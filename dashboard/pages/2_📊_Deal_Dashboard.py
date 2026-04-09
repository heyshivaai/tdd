"""
Deal Dashboard — decision-support layout.

Information architecture (top → bottom):
  Section A: Deal Status — hero, workflow status bar, contextual next-action CTA
  Section B: At a Glance — KPI row + Risk Summary (RED/CRITICAL items aggregated)
  Section C: Domain Intelligence — unified per-pillar cards (signals + findings + questions)
  Section D: Chase List — prioritised questions for the target company
  Section E: Practitioner Review — download workbooks, upload feedback, recalibration

Data sources:
  - domain_findings.json  (7 pillars, findings, chase list)
  - signal checkpoints    (raw signals per batch)
  - vdr_intelligence_brief.json (overall rating, signal index — optional fallback)
  - _scan_registry.json   (scan status, partial scan awareness)

Pillars are dynamic — read from domain_findings.json, not hardcoded.
"""

import json
import sys
from collections import Counter
from io import BytesIO
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dashboard.utils.data_loader import (
    OUTPUTS_DIR,
    PILLAR_LABELS,
    RATING_COLORS,
    RATING_EMOJI,
    extract_all_signals,
    load_all_deals,
    load_brief,
)

st.set_page_config(page_title="Deal Dashboard · VDR Triage", page_icon="📊", layout="wide")

# ── Styles ────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* Hero */
.di-hero {
    background: linear-gradient(135deg, #0f172a 0%, #1e293b 60%, #334155 100%);
    border-radius: 14px; padding: 32px 36px 28px; margin-bottom: 0; color: #f8fafc;
}
.di-hero h1 { font-size: 1.6rem; font-weight: 800; margin: 0 0 4px; color: #f8fafc; }
.di-hero .sub { font-size: 0.85rem; color: #94a3b8; margin: 0; }

/* Workflow status bar */
.workflow-bar {
    border-radius: 0 0 14px 14px; padding: 14px 24px; margin-bottom: 22px;
    display: flex; align-items: center; gap: 16px; font-size: 0.88rem;
}
.workflow-bar.phase-scan    { background: #eff6ff; border: 1px solid #bfdbfe; border-top: none; color: #1e40af; }
.workflow-bar.phase-agents  { background: #fef3c7; border: 1px solid #fcd34d; border-top: none; color: #92400e; }
.workflow-bar.phase-review  { background: #ecfdf5; border: 1px solid #86efac; border-top: none; color: #065f46; }
.workflow-bar .step { display: flex; align-items: center; gap: 6px; }
.workflow-bar .step.done { opacity: 0.5; }
.workflow-bar .step.active { font-weight: 700; }
.workflow-bar .arrow { color: #94a3b8; font-size: 0.8rem; }

/* Section labels */
.section-label {
    font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.1em;
    color: #94a3b8; font-weight: 700; margin: 28px 0 6px; padding-left: 2px;
}
.section-title {
    font-size: 1.1rem; font-weight: 700; color: #0f172a;
    margin: 0 0 14px; padding-bottom: 8px; border-bottom: 2px solid #e2e8f0;
}

/* KPI cards */
.kpi-card {
    background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px;
    padding: 14px 16px; text-align: center;
}
.kpi-card .label { font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.06em;
    color: #64748b; font-weight: 600; margin-bottom: 3px; }
.kpi-card .value { font-size: 1.45rem; font-weight: 800; color: #0f172a; }
.kpi-card .delta { font-size: 0.72rem; color: #64748b; margin-top: 2px; }

/* Risk summary panel */
.risk-panel {
    background: linear-gradient(135deg, #fef2f2 0%, #fff7ed 100%);
    border: 1px solid #fca5a5; border-radius: 12px;
    padding: 18px 22px; margin: 12px 0 8px;
}
.risk-panel-title {
    font-size: 0.82rem; font-weight: 700; color: #991b1b;
    text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 10px;
}
.risk-item {
    background: #ffffff; border: 1px solid #fecaca; border-radius: 8px;
    padding: 10px 14px; margin-bottom: 6px; border-left: 4px solid #dc2626;
    font-size: 0.88rem;
}
.risk-item.yellow { border-left-color: #d97706; border-color: #fed7aa; }
.risk-item .risk-source { font-size: 0.72rem; color: #94a3b8; margin-top: 2px; }

/* Domain card */
.domain-card {
    background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 12px;
    padding: 18px 20px; margin-bottom: 12px; transition: border-color .15s;
}
.domain-card:hover { border-color: #94a3b8; }
.domain-card .grade { font-size: 1.3rem; font-weight: 800; }
.domain-card .name { font-size: 0.95rem; font-weight: 700; color: #0f172a; }
.domain-card .stat { font-size: 0.78rem; color: #64748b; }

/* Severity badges */
.sev-badge {
    display:inline-block; border-radius:12px; padding:2px 10px;
    font-size:0.75rem; font-weight:700; letter-spacing:.03em;
}
.sev-CRITICAL { background:#fef2f2; color:#dc2626; border:1px solid #fca5a5; }
.sev-HIGH     { background:#fff7ed; color:#ea580c; border:1px solid #fdba74; }
.sev-MEDIUM   { background:#fffbeb; color:#d97706; border:1px solid #fcd34d; }
.sev-LOW      { background:#f0fdf4; color:#16a34a; border:1px solid #86efac; }

/* Signal card */
.signal-card {
    background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px;
    padding: 12px 16px; margin-bottom: 8px; border-left: 4px solid #94a3b8;
}
.signal-card.rating-RED    { border-left-color: #dc2626; }
.signal-card.rating-YELLOW { border-left-color: #d97706; }
.signal-card.rating-GREEN  { border-left-color: #16a34a; }

/* Evidence box */
.evidence-box {
    background: #f1f5f9; border-left: 3px solid #3b82f6; border-radius: 6px;
    padding: 10px 14px; margin: 6px 0; font-size: 0.85rem;
}
.evidence-box .doc-name { font-weight: 700; color: #1e40af; font-size: 0.8rem; }
.evidence-box blockquote {
    margin: 6px 0 0; padding: 4px 8px; background: #ffffff;
    border-left: 2px solid #93c5fd; font-style: italic; color: #334155;
    font-size: 0.82rem;
}

/* Chase item */
.chase-item {
    background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px;
    padding: 10px 14px; margin-bottom: 8px;
}

/* Confidence bar */
.conf-bar { display:flex; height:22px; border-radius:6px; overflow:hidden; margin:6px 0; }
.conf-bar .seg-HIGH   { background:#16a34a; }
.conf-bar .seg-MEDIUM { background:#d97706; }
.conf-bar .seg-LOW    { background:#dc2626; }

/* Practitioner panel */
.practitioner-panel {
    background: linear-gradient(135deg, #f0f9ff 0%, #eff6ff 100%);
    border: 1px solid #bfdbfe; border-radius: 14px;
    padding: 24px 28px; margin-top: 8px;
}

/* Review status badges */
.review-badge {
    border-radius: 8px; padding: 8px 12px; font-size: 0.8rem; margin-top: 6px;
}
.review-badge.done { background: #f0fdf4; border: 1px solid #86efac; color: #065f46; }
.review-badge.pending { background: #fffbeb; border: 1px solid #fcd34d; color: #92400e; }

/* Scan monitor override */
.scan-monitor { margin-bottom: 8px; }
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# SCAN MONITOR — shows running / failed scans (collapsible, top of page)
# ══════════════════════════════════════════════════════════════════════════════
from tools.scan_registry import get_all_scans, cleanup_stale_scans

cleanup_stale_scans()
_all_scans = get_all_scans()
if _all_scans:
    _running = {k: v for k, v in _all_scans.items() if v.get("status") == "running"}
    _failed = {k: v for k, v in _all_scans.items() if v.get("status") == "failed"}

    if _running or _failed:
        with st.expander(
            f"Scan Monitor — {len(_running)} running, {len(_failed)} failed, "
            f"{len(_all_scans) - len(_running) - len(_failed)} completed",
            expanded=bool(_running),
        ):
            for company, scan in sorted(
                _all_scans.items(), key=lambda x: x[1].get("updated_at", ""), reverse=True
            ):
                status = scan.get("status", "unknown")
                phase = scan.get("phase", "")
                prog = scan.get("progress", {})
                batches_done = prog.get("batches_done", 0)
                batches_total = prog.get("batches_total", 0)
                batches_resumed = prog.get("batches_resumed", 0)
                signals = prog.get("signals_found", 0)
                doc_count = prog.get("doc_count", 0)

                if status == "running":
                    icon, color = "🔄", "#2563eb"
                    detail = (
                        f"Phase: **{phase}** | "
                        f"Batches: **{batches_done}/{batches_total}** | "
                        f"Signals: **{signals}** | Docs: **{doc_count}**"
                    )
                    if batches_resumed:
                        detail += f" | Resumed: **{batches_resumed}**"
                elif status == "completed":
                    icon, color = "✅", "#16a34a"
                    rating = scan.get("rating", "")
                    detail = f"Rating: **{rating}** | Signals: **{signals}** | Docs: **{doc_count}**"
                elif status == "failed":
                    icon, color = "❌", "#dc2626"
                    error = scan.get("error", "Unknown error")
                    detail = f"Error: {error[:120]}"
                else:
                    icon, color = "⏸️", "#6b7280"
                    detail = f"Status: {status}"

                started = scan.get("started_at", "")[:16].replace("T", " ")
                version = scan.get("version", "?")

                _info_col, _btn_col = st.columns([5, 1])
                with _info_col:
                    st.markdown(
                        f"{icon} **{company}** (v{version}) — "
                        f'<span style="color:{color};font-weight:600">{status.upper()}</span>'
                        f'<br><span style="font-size:0.85em;color:#64748b">'
                        f'Started: {started} UTC | {detail}</span>',
                        unsafe_allow_html=True,
                    )
                with _btn_col:
                    if status == "running":
                        if st.button("View Scan", key=f"view_{company}", use_container_width=True):
                            st.session_state["selected_deal"] = company
                            st.switch_page("pages/1_🔍_New_Scan.py")
                    elif status == "failed":
                        if st.button("Retry", key=f"retry_{company}", use_container_width=True):
                            st.session_state["selected_deal"] = company
                            st.switch_page("pages/1_🔍_New_Scan.py")

                if status == "running" and batches_total:
                    st.progress(batches_done / batches_total)
                st.markdown("---")


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _grade_color(grade: str) -> str:
    """Return hex color for a grade."""
    return {"RED": "#dc2626", "YELLOW": "#d97706", "GREEN": "#16a34a"}.get(grade, "#6b7280")


def _grade_emoji(grade: str) -> str:
    """Return emoji for a grade."""
    return {"RED": "🔴", "YELLOW": "🟡", "GREEN": "🟢", "NO_DATA": "⚪"}.get(grade, "⚪")


def _sev_emoji(severity: str) -> str:
    """Return emoji for a severity level."""
    return {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🟢"}.get(severity, "⚪")


def _sev_order(severity: str) -> int:
    """Return sort order for severity (0 = most critical)."""
    return {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}.get(severity, 99)


def _normalize_finding(raw: dict) -> dict:
    """Normalise a finding dict from any agent output format.

    Handles both legacy (evidence as string) and new (evidence as structured
    array) formats. Passes through all extra fields the dashboard can render.
    """
    evidence = raw.get("evidence", raw.get("evidence_quote", ""))
    # If evidence is a string, wrap it in a single-item structured list
    if isinstance(evidence, str) and evidence:
        evidence = [{"type": "inference", "detail": evidence}]
    elif not isinstance(evidence, list):
        evidence = []

    return {
        "finding_id": raw.get("finding_id", ""),
        "title": raw.get("title", raw.get("finding", raw.get("observation", ""))),
        "severity": raw.get("severity", raw.get("rating", raw.get("risk_level", "MEDIUM"))),
        "description": raw.get("description", raw.get("detail", raw.get("observation", ""))),
        "evidence": evidence,
        "source_signals": raw.get("source_signals", []),
        "business_impact": raw.get("deal_implication", raw.get("business_impact", raw.get("impact", ""))),
        "category": raw.get("category", ""),
        "remediation": raw.get("remediation", {}),
        "question_for_target": raw.get("question_for_target", ""),
        "contradictions": raw.get("contradictions", []),
        "confidence": raw.get("confidence", ""),
        "confidence_reason": raw.get("confidence_reason", ""),
        "benchmark_comparison": raw.get("benchmark_comparison", ""),
    }


def _load_domain_findings(company_name: str) -> dict | None:
    """Load agent findings — from domain_findings.json or individual agent outputs.

    Checks domain_findings.json first (legacy format). If not found, reads
    individual agent JSONs from outputs/<company>/agents/ and synthesises
    them into a unified view for the dashboard.
    """
    path = OUTPUTS_DIR / company_name / "domain_findings.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass

    # Fall back to individual agent outputs
    agents_dir = OUTPUTS_DIR / company_name / "agents"
    if not agents_dir.exists():
        return None

    agent_files = sorted(agents_dir.glob("*.json"))
    if not agent_files:
        return None

    agents_data = {}
    for af in agent_files:
        try:
            agents_data[af.stem] = json.loads(af.read_text(encoding="utf-8"))
        except Exception:
            continue

    if not agents_data:
        return None

    REPORT_KEYS = {
        "alex": "alex",
        "morgan": "morgan_intelligence_report",
        "jordan": "jordan_repository_report",
        "riley": "riley_security_report",
        "casey": "casey_code_quality_report",
        "taylor": "taylor_infrastructure_report",
        "drew": "drew_benchmarking_report",
        "sam": "sam_final_report",
    }

    AGENT_DOMAINS = {
        "alex": "Company Profile & Risk Hypothesis",
        "morgan": "Public Signal Intelligence",
        "jordan": "Code & Repository Health",
        "riley": "Security Posture",
        "casey": "Code Quality",
        "taylor": "Infrastructure & Cost",
        "drew": "Benchmarking & Compound Risks",
        "sam": "Final Synthesis",
    }

    domains = {}
    chase_list = []

    for agent_name, raw_data in agents_data.items():
        report_key = REPORT_KEYS.get(agent_name, agent_name)
        report = raw_data.get(report_key, raw_data)
        domain_label = AGENT_DOMAINS.get(agent_name, agent_name.title())

        overall_rating = (
            report.get("overall_domain_rating")
            or report.get("overall_rating")
            or report.get("domain_rating")
            or "UNKNOWN"
        )

        rating_map = {
            "CRITICAL": "RED", "CONCERNING": "YELLOW", "STRONG": "GREEN",
            "ADEQUATE": "GREEN", "RED": "RED", "YELLOW": "YELLOW", "GREEN": "GREEN",
        }
        grade = rating_map.get(overall_rating.upper(), overall_rating.upper())

        summary = (
            report.get("overall_domain_summary")
            or report.get("executive_summary")
            or report.get("summary")
            or ""
        )
        if isinstance(summary, dict):
            summary = summary.get("summary", str(summary))
        elif not isinstance(summary, str):
            summary = str(summary)

        findings = []
        for fkey in ["domain_findings", "findings", "key_findings", "critical_findings"]:
            val = report.get(fkey, [])
            if isinstance(val, list):
                for item in val:
                    if isinstance(item, dict):
                        sub_findings = item.get("findings", [])
                        if sub_findings and isinstance(sub_findings, list):
                            for sf in sub_findings:
                                if isinstance(sf, dict):
                                    findings.append(_normalize_finding(sf))
                        else:
                            findings.append(_normalize_finding(item))
                if findings:
                    break

        for ckey in ["combination_signals", "compound_risks", "compound_signals"]:
            combos = report.get(ckey, [])
            if isinstance(combos, list):
                for combo in combos:
                    if isinstance(combo, dict):
                        # Build evidence from contributing_findings if available
                        contrib = combo.get("contributing_findings", [])
                        combo_evidence = combo.get("evidence", [])
                        if isinstance(contrib, list) and contrib:
                            for cf in contrib:
                                if isinstance(cf, dict):
                                    combo_evidence.append({
                                        "type": "prior_agent",
                                        "agent": cf.get("agent", ""),
                                        "finding_id": cf.get("finding_id", ""),
                                        "detail": cf.get("detail", str(cf)),
                                    })
                                elif isinstance(cf, str):
                                    combo_evidence.append({"type": "prior_agent", "detail": cf})
                        if isinstance(combo_evidence, str):
                            combo_evidence = [{"type": "inference", "detail": combo_evidence}]

                        findings.append({
                            "finding_id": combo.get("risk_id", combo.get("signal_id", "")),
                            "title": combo.get("risk_title", combo.get("signal_id", "")) + ": " + combo.get("combined_observation", combo.get("title", ""))[:80],
                            "severity": combo.get("severity", "HIGH"),
                            "description": combo.get("combined_observation", combo.get("narrative", combo.get("description", ""))),
                            "evidence": combo_evidence if isinstance(combo_evidence, list) else [],
                            "source_signals": combo.get("source_signals", []),
                            "business_impact": combo.get("deal_implication", ""),
                        })

        for qkey in ["priority_questions_for_next_agents", "priority_questions_for_riley",
                      "priority_questions_for_casey", "priority_questions_for_taylor",
                      "priority_questions_for_drew", "follow_on_questions", "questions"]:
            qs = report.get(qkey, [])
            if isinstance(qs, list):
                for q in qs:
                    q_text = q.get("question", str(q)) if isinstance(q, dict) else str(q)
                    chase_list.append({
                        "question": q_text,
                        "pillar_label": domain_label,
                        "pillar_id": agent_name,
                        "priority": q.get("priority", "medium") if isinstance(q, dict) else "medium",
                        "source_agent": agent_name,
                    })

        domains[agent_name] = {
            "pillar_label": domain_label,
            "grade": grade,
            "domain_summary": summary[:500] if isinstance(summary, str) else "",
            "findings": findings,
            "confidence": report.get("metadata", {}).get("overall_confidence", "—") if isinstance(report.get("metadata"), dict) else "—",
        }

    return {
        "domains": domains,
        "chase_list": chase_list,
        "_source": "agent_outputs",
        "_agents_completed": list(agents_data.keys()),
    }


def _build_chase_text(chase_list: list[dict]) -> str:
    """Build plaintext chase list for copy/download."""
    lines = []
    by_pillar: dict[str, list[dict]] = {}
    for q in chase_list:
        pid = q.get("pillar_label", q.get("pillar_id", "General"))
        by_pillar.setdefault(pid, []).append(q)

    for pillar, questions in by_pillar.items():
        lines.append(f"\n{pillar}")
        lines.append("=" * len(pillar))
        for i, q in enumerate(questions, 1):
            question_text = q.get("question", str(q)) if isinstance(q, dict) else str(q)
            priority = q.get("priority", "medium") if isinstance(q, dict) else "medium"
            source = q.get("source_finding", "") if isinstance(q, dict) else ""
            line = f"{i}. [{priority.upper()}] {question_text}"
            if source:
                line += f" (Source: {source})"
            lines.append(line)

    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# DATA LOADING
# ══════════════════════════════════════════════════════════════════════════════
deals = load_all_deals()
if not deals:
    st.markdown(
        '<div class="di-hero"><h1>📊 Deal Dashboard</h1>'
        '<p class="sub">Deep technical intelligence per deal · Signals → Findings → Chase List</p>'
        '</div>',
        unsafe_allow_html=True,
    )
    st.info("No completed scans with signal data yet. Run a scan from **New Scan** first.")
    st.stop()

# ── Sidebar: clickable deals ────────────────────────────────────────────────
with st.sidebar:
    st.subheader("Deals")
    for deal in deals[:10]:
        company = deal.get("company", "?")
        deal_id = deal.get("deal_id", "unknown")
        rating = deal.get("rating", "UNKNOWN")
        icon = {"RED": "🔴", "YELLOW": "🟡", "GREEN": "🟢"}.get(rating, "⚪")
        if st.button(f"{icon} {company} — {deal_id}", key=f"sidebar_deal_{deal_id}", use_container_width=True):
            st.session_state["selected_deal_override"] = company
            st.rerun()

company_names = [d["company"] for d in deals]
default_idx = 0
if "selected_deal_override" in st.session_state and st.session_state["selected_deal_override"] in company_names:
    default_idx = company_names.index(st.session_state["selected_deal_override"])

selected_company = st.selectbox(
    "Select deal",
    company_names,
    index=default_idx,
    format_func=lambda c: f"{c} — {next((d['deal_id'] for d in deals if d['company'] == c), '')}",
    label_visibility="collapsed",
)

brief = load_brief(selected_company)
domain_data = _load_domain_findings(selected_company)

# ── Pre-compute all data needed across sections ────────────────────────────
deal_info = next((d for d in deals if d["company"] == selected_company), {})
rating = deal_info.get("rating", "UNKNOWN")

all_signals = extract_all_signals(brief) if brief else []
if not all_signals and brief:
    all_signals = brief.get("signals", [])

has_vdr_data = bool(all_signals)
has_agent_data = bool(domain_data and domain_data.get("domains"))

domains = domain_data.get("domains", {}) if domain_data else {}
domain_count = len(domains)
signal_count = deal_info.get("signal_count", 0) or len(all_signals)
finding_count = sum(len(d.get("findings", [])) for d in domains.values())

chase_list = domain_data.get("chase_list", []) if domain_data else []
if not chase_list and domain_data:
    for pid, dinfo in domains.items():
        for q in dinfo.get("questions_for_target", []):
            if isinstance(q, str):
                chase_list.append({
                    "pillar_id": pid,
                    "pillar_label": dinfo.get("pillar_label", pid),
                    "question": q,
                    "priority": "medium",
                })
            elif isinstance(q, dict):
                q["pillar_id"] = pid
                q["pillar_label"] = dinfo.get("pillar_label", pid)
                chase_list.append(q)

question_count = len(chase_list)

# Partial scan awareness
from tools.scan_registry import get_scan as _get_scan_reg
_scan_reg = _get_scan_reg(selected_company)
_is_partial = (
    _scan_reg is not None
    and _scan_reg.get("scan_mode") == "selective"
    and _scan_reg.get("pending_batches")
)
_scanned_doc_n = _scan_reg.get("progress", {}).get("doc_count", 0) if _scan_reg else 0
_total_vdr_n = _scan_reg.get("total_vdr_docs", _scanned_doc_n) if _scan_reg else 0
_pending_batch_n = len(_scan_reg.get("pending_batches", [])) if _scan_reg else 0

# Feedback status
_g1_completed_path = OUTPUTS_DIR / selected_company / "feedback_gate1_completed.json"
_g2_completed_path = OUTPUTS_DIR / selected_company / "feedback_gate2_completed.json"
_g1_feedback = None
_g2_feedback = None
if _g1_completed_path.exists():
    try:
        _g1_feedback = json.loads(_g1_completed_path.read_text(encoding="utf-8"))
    except Exception:
        pass
if _g2_completed_path.exists():
    try:
        _g2_feedback = json.loads(_g2_completed_path.read_text(encoding="utf-8"))
    except Exception:
        pass

# Determine workflow phase for status bar
if not has_vdr_data:
    _workflow_phase = "no_data"
elif not has_agent_data:
    _workflow_phase = "scan_done"
elif not _g1_feedback and not _g2_feedback:
    _workflow_phase = "agents_done"
elif _g1_feedback or _g2_feedback:
    _workflow_phase = "reviewed"
else:
    _workflow_phase = "agents_done"


# ══════════════════════════════════════════════════════════════════════════════
# SECTION A — DEAL STATUS
# ══════════════════════════════════════════════════════════════════════════════

_partial_sub = ""
if _is_partial:
    _partial_sub = (
        f' · ⚡ Partial scan: {_scanned_doc_n}/{_total_vdr_n} docs analysed '
        f'({_pending_batch_n} batch{"es" if _pending_batch_n != 1 else ""} remaining)'
    )

st.markdown(
    f'<div class="di-hero">'
    f'<h1>📊 {selected_company}</h1>'
    f'<p class="sub">{deal_info.get("sector", "")} · {deal_info.get("deal_type", "")} · '
    f'Scanned {deal_info.get("scanned", "")}{_partial_sub}</p>'
    f'</div>',
    unsafe_allow_html=True,
)

# ── Workflow Status Bar ────────────────────────────────────────────────────
# Shows where the deal is in the pipeline + one clear next action

_step_scan_cls = "done" if has_vdr_data else "active"
_step_agents_cls = "done" if has_agent_data else ("active" if has_vdr_data and not has_agent_data else "")
_step_review_cls = "done" if (_g1_feedback or _g2_feedback) else ("active" if has_agent_data else "")

if _workflow_phase == "no_data":
    _bar_cls = "phase-scan"
    _bar_cta = "Run a VDR scan from <strong>New Scan</strong> to begin."
elif _workflow_phase == "scan_done":
    _bar_cls = "phase-agents"
    _bar_cta = "VDR scan complete — ready for deep analysis."
elif _workflow_phase == "agents_done":
    _bar_cls = "phase-review"
    _bar_cta = "Analysis complete — download review workbooks for practitioner sign-off."
elif _workflow_phase == "reviewed":
    _bar_cls = "phase-review"
    _bar_cta = "Practitioner feedback received — recalibration active."
else:
    _bar_cls = "phase-scan"
    _bar_cta = ""

_check = "✅"
_circle = "⬜"

st.markdown(
    f'<div class="workflow-bar {_bar_cls}">'
    f'<span class="step {_step_scan_cls}">{_check if has_vdr_data else _circle} VDR Scan</span>'
    f'<span class="arrow">→</span>'
    f'<span class="step {_step_agents_cls}">{_check if has_agent_data else _circle} Agent Deep Dive</span>'
    f'<span class="arrow">→</span>'
    f'<span class="step {_step_review_cls}">{_check if (_g1_feedback or _g2_feedback) else _circle} Practitioner Review</span>'
    f'<span style="margin-left:auto;font-size:0.85rem">{_bar_cta}</span>'
    f'</div>',
    unsafe_allow_html=True,
)

# Primary CTA button based on workflow phase
if _workflow_phase == "scan_done" and not has_agent_data:
    if st.button("🤖 Launch Agent Deep Diligence →", key="cta_launch_agents", use_container_width=True, type="primary"):
        st.session_state["auto_launch_agents"] = True
        st.switch_page("pages/4_🤖_Agent_Pipeline.py")

# Partial scan banner
if _is_partial:
    st.markdown(
        f'<div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:10px;'
        f'padding:12px 18px;margin-bottom:8px;">'
        f'<span style="font-weight:700;color:#1d4ed8;">⚡ Partial Scan</span>'
        f'<span style="font-size:0.85rem;color:#475569;margin-left:10px;">'
        f'{_pending_batch_n} document categories not yet scanned. '
        f'Go to <strong>New Scan</strong> to add them incrementally.</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

if not has_vdr_data and not has_agent_data:
    st.info("No scan data available for this deal yet. Run a VDR scan from **New Scan** to generate intelligence.")
    st.stop()


# ══════════════════════════════════════════════════════════════════════════════
# SECTION B — AT A GLANCE
# ══════════════════════════════════════════════════════════════════════════════
st.markdown('<div class="section-label">Section B</div>', unsafe_allow_html=True)
st.markdown('<div class="section-title">📋 At a Glance</div>', unsafe_allow_html=True)

# KPI row
k1, k2, k3, k4 = st.columns(4)
for col, label, value, delta in [
    (k1, "Overall Rating", f"{_grade_emoji(rating)} {rating}", "from VDR scan"),
    (k2, "Signals", str(signal_count), f"across {len(set(s.get('pillar_id', s.get('lens_id', 'x')) for s in all_signals))} pillars" if all_signals else "—"),
    (k3, "Findings", str(finding_count), f"from {domain_count} agents" if has_agent_data else "agents not run"),
    (k4, "Chase Questions", str(question_count), "for target company"),
]:
    col.markdown(
        f'<div class="kpi-card"><div class="label">{label}</div>'
        f'<div class="value">{value}</div>'
        f'<div class="delta">{delta}</div></div>',
        unsafe_allow_html=True,
    )

# ── Confidence Distribution (compact) ─────────────────────────────────────
if all_signals:
    conf_counts = Counter()
    for sig in all_signals:
        c = (sig.get("confidence") or "UNKNOWN").upper()
        conf_counts[c] += 1

    total_sigs = len(all_signals)
    high_pct = round(conf_counts.get("HIGH", 0) / total_sigs * 100) if total_sigs else 0
    med_pct = round(conf_counts.get("MEDIUM", 0) / total_sigs * 100) if total_sigs else 0
    low_pct = round((conf_counts.get("LOW", 0) + conf_counts.get("UNKNOWN", 0)) / total_sigs * 100) if total_sigs else 0
    needs_review = conf_counts.get("MEDIUM", 0) + conf_counts.get("LOW", 0) + conf_counts.get("UNKNOWN", 0)

    st.markdown(
        f'<div style="margin:12px 0 4px">'
        f'<span style="font-size:0.78rem;color:#64748b;font-weight:600">Signal Confidence:</span> '
        f'<span style="font-size:0.82rem">🟢 HIGH {conf_counts.get("HIGH",0)} ({high_pct}%) · '
        f'🟡 MEDIUM {conf_counts.get("MEDIUM",0)} ({med_pct}%) · '
        f'🔴 LOW {conf_counts.get("LOW",0) + conf_counts.get("UNKNOWN",0)} ({low_pct}%)'
        f'{"  ·  <strong>👁️ " + str(needs_review) + " need review</strong>" if needs_review else ""}'
        f'</span></div>'
        f'<div class="conf-bar">'
        f'<div class="seg-HIGH" style="width:{high_pct}%"></div>'
        f'<div class="seg-MEDIUM" style="width:{med_pct}%"></div>'
        f'<div class="seg-LOW" style="width:{low_pct}%"></div>'
        f'</div>',
        unsafe_allow_html=True,
    )

# ── Risk Summary — RED signals + CRITICAL/HIGH findings ───────────────────
_red_signals = [s for s in all_signals if s.get("rating", "").upper() == "RED"]
_critical_findings = []
_high_findings = []
for pid, dinfo in domains.items():
    plabel = dinfo.get("pillar_label", PILLAR_LABELS.get(pid, pid))
    for f in dinfo.get("findings", []):
        sev = f.get("severity", "").upper()
        f["_source_pillar"] = plabel
        if sev == "CRITICAL":
            _critical_findings.append(f)
        elif sev == "HIGH":
            _high_findings.append(f)

_has_risks = bool(_red_signals or _critical_findings or _high_findings)

if _has_risks:
    st.markdown(
        '<div class="risk-panel">'
        '<div class="risk-panel-title">⚠️ Items Requiring Attention</div>',
        unsafe_allow_html=True,
    )

    # Critical findings first
    for f in _critical_findings:
        st.markdown(
            f'<div class="risk-item">'
            f'🔴 <strong>CRITICAL</strong> — {f.get("title", "Untitled")}'
            f'<div class="risk-source">Agent finding · {f.get("_source_pillar", "")}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # RED signals
    for s in _red_signals[:10]:
        _s_title = s.get("title", s.get("signal_id", "Untitled"))
        _s_pillar = PILLAR_LABELS.get(
            s.get("pillar_id") or s.get("lens_id") or s.get("lens") or "",
            s.get("pillar_id", ""),
        )
        _s_conf = s.get("confidence", "")
        st.markdown(
            f'<div class="risk-item">'
            f'🔴 <strong>RED</strong> — {_s_title}'
            f'<div class="risk-source">VDR signal · {_s_pillar}'
            f'{" · Confidence: " + _s_conf if _s_conf else ""}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # HIGH findings
    for f in _high_findings[:8]:
        st.markdown(
            f'<div class="risk-item yellow">'
            f'🟠 <strong>HIGH</strong> — {f.get("title", "Untitled")}'
            f'<div class="risk-source">Agent finding · {f.get("_source_pillar", "")}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    if len(_red_signals) > 10:
        st.caption(f"+ {len(_red_signals) - 10} more RED signals — see Domain Intelligence below")
    if len(_high_findings) > 8:
        st.caption(f"+ {len(_high_findings) - 8} more HIGH findings — see Domain Intelligence below")

    st.markdown('</div>', unsafe_allow_html=True)
else:
    st.markdown(
        '<div style="background:#f0fdf4;border:1px solid #86efac;border-radius:12px;'
        'padding:14px 20px;margin:12px 0;font-size:0.88rem;color:#065f46">'
        '✅ No critical or high-severity items detected. Review domain details below for full picture.'
        '</div>',
        unsafe_allow_html=True,
    )


# ══════════════════════════════════════════════════════════════════════════════
# SECTION C — DOMAIN INTELLIGENCE
# ══════════════════════════════════════════════════════════════════════════════
st.markdown('<div class="section-label">Section C</div>', unsafe_allow_html=True)
st.markdown('<div class="section-title">🔬 Domain Intelligence</div>', unsafe_allow_html=True)

# Build unified pillar list from both VDR signals and agent findings
_pillar_map: dict[str, dict] = {}

# Seed from signals
for sig in all_signals:
    pid = sig.get("pillar_id") or sig.get("lens_id") or sig.get("lens") or "Unknown"
    if pid not in _pillar_map:
        _pillar_map[pid] = {
            "pillar_label": PILLAR_LABELS.get(pid, pid),
            "signals": [],
            "findings": [],
            "chase_questions": [],
            "grade": "NO_DATA",
            "confidence": "—",
            "domain_summary": "",
        }
    _pillar_map[pid]["signals"].append(sig)

# Overlay agent domain data
if has_agent_data:
    for pid, dinfo in domains.items():
        plabel = dinfo.get("pillar_label", PILLAR_LABELS.get(pid, pid))
        if pid not in _pillar_map:
            _pillar_map[pid] = {
                "pillar_label": plabel,
                "signals": [],
                "findings": [],
                "chase_questions": [],
                "grade": dinfo.get("grade", "UNKNOWN"),
                "confidence": dinfo.get("confidence", "—"),
                "domain_summary": dinfo.get("domain_summary", ""),
            }
        else:
            _pillar_map[pid]["grade"] = dinfo.get("grade", _pillar_map[pid]["grade"])
            _pillar_map[pid]["confidence"] = dinfo.get("confidence", _pillar_map[pid]["confidence"])
            _pillar_map[pid]["domain_summary"] = dinfo.get("domain_summary", "")
            _pillar_map[pid]["pillar_label"] = plabel

        _pillar_map[pid]["findings"] = dinfo.get("findings", [])

        # Also copy blind_spots, confidence_summary, etc.
        _pillar_map[pid]["blind_spots"] = dinfo.get("blind_spots", [])
        _pillar_map[pid]["confidence_summary"] = dinfo.get("confidence_summary", {})

# Distribute chase questions to pillars
for q in chase_list:
    qpid = q.get("pillar_id", "")
    if qpid in _pillar_map:
        _pillar_map[qpid]["chase_questions"].append(q)

# Sort pillars: RED first, then YELLOW, then GREEN/NO_DATA
def _pillar_sort(item):
    pid, pdata = item
    grade = pdata.get("grade", "UNKNOWN")
    has_red_sigs = any(s.get("rating", "").upper() == "RED" for s in pdata["signals"])
    has_crit_findings = any(f.get("severity", "").upper() == "CRITICAL" for f in pdata["findings"])
    return (
        0 if (grade == "RED" or has_red_sigs or has_crit_findings) else
        1 if grade == "YELLOW" else
        2 if grade == "GREEN" else 3,
        pid,
    )

_sorted_pillars = sorted(_pillar_map.items(), key=_pillar_sort)

if not _sorted_pillars:
    st.info("No domain data available yet. Run a scan to populate.")
else:
    # Overview grid — compact tiles
    st.markdown("**Domain Overview**")
    _n_cols = min(len(_sorted_pillars), 4)
    _overview_cols = st.columns(_n_cols)
    for i, (pid, pdata) in enumerate(_sorted_pillars):
        grade = pdata["grade"]
        gc = _grade_color(grade)
        n_sigs = len(pdata["signals"])
        n_find = len(pdata["findings"])
        n_crit = sum(1 for f in pdata["findings"] if f.get("severity", "").upper() == "CRITICAL")
        n_high = sum(1 for f in pdata["findings"] if f.get("severity", "").upper() == "HIGH")
        n_red = sum(1 for s in pdata["signals"] if s.get("rating", "").upper() == "RED")

        with _overview_cols[i % _n_cols]:
            _severity_note = ""
            if n_crit:
                _severity_note += f"🔴 {n_crit} critical "
            if n_high:
                _severity_note += f"🟠 {n_high} high "
            if n_red:
                _severity_note += f"🔴 {n_red} RED signals"

            st.markdown(
                f'<div class="domain-card">'
                f'<div class="grade" style="color:{gc}">{_grade_emoji(grade)} {grade}</div>'
                f'<div class="name">{pdata["pillar_label"]}</div>'
                f'<div class="stat">{n_sigs} signals · {n_find} findings</div>'
                f'<div class="stat">{_severity_note if _severity_note else "No critical items"}</div>'
                f'<div class="stat">Confidence: {pdata["confidence"]}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    st.markdown("---")

    # ── Per-pillar deep dive cards ────────────────────────────────────────────
    st.markdown("**Domain Deep Dives** — expand any pillar for signals, findings, and questions")

    for pid, pdata in _sorted_pillars:
        grade = pdata["grade"]
        plabel = pdata["pillar_label"]
        sigs = pdata["signals"]
        finds = pdata["findings"]
        questions = pdata["chase_questions"]
        blind_spots = pdata.get("blind_spots", [])
        d_summary = pdata.get("domain_summary", "")

        n_red = sum(1 for s in sigs if s.get("rating", "").upper() == "RED")
        n_crit = sum(1 for f in finds if f.get("severity", "").upper() == "CRITICAL")

        # Pillar header — auto-expand if RED/CRITICAL
        _expand = bool(n_red or n_crit)
        _pillar_tag = f"{_grade_emoji(grade)} **{plabel}** — {grade}"
        _pillar_counts = f"{len(sigs)} signals · {len(finds)} findings · {len(questions)} questions"

        with st.expander(f"{_pillar_tag}  |  {_pillar_counts}", expanded=_expand):

            # Summary + metrics row
            if has_agent_data:
                _m1, _m2, _m3, _m4 = st.columns(4)
                _m1.metric("Grade", f"{_grade_emoji(grade)} {grade}")
                _m2.metric("Confidence", str(pdata["confidence"]))
                _m3.metric("Signals", len(sigs))
                _m4.metric("Findings", len(finds))

            if d_summary:
                st.markdown(
                    f'<div style="background:#f0f9ff;border:1px solid #bfdbfe;border-radius:10px;'
                    f'padding:14px 18px;margin:8px 0;font-size:0.86rem;color:#1e293b;line-height:1.6">'
                    f'{d_summary}</div>',
                    unsafe_allow_html=True,
                )

            # ── Signals ──────────────────────────────────────────────────────
            if sigs:
                st.markdown(f"**📡 Signals** ({len(sigs)})")
                st.caption("Raw extractions from VDR documents")

                rating_order = {"RED": 0, "YELLOW": 1, "GREEN": 2}
                for sig in sorted(sigs, key=lambda s: rating_order.get(s.get("rating", "").upper(), 99)):
                    sig_rating = sig.get("rating", "UNKNOWN").upper()
                    sig_emoji = {"RED": "🔴", "YELLOW": "🟡", "GREEN": "🟢"}.get(sig_rating, "⚪")
                    title = sig.get("title", sig.get("signal_id", "Untitled"))
                    obs = sig.get("observation", "")
                    evidence_quote = sig.get("evidence_quote", "")
                    source_doc = sig.get("source_doc", "")
                    confidence = sig.get("confidence", "")
                    deal_imp = sig.get("deal_implication", "")

                    st.markdown(f"{sig_emoji} **{sig_rating}** — {title}")

                    if obs:
                        st.markdown(
                            f'<div style="font-size:0.86rem;color:#334155;margin:2px 0 4px 20px">{obs}</div>',
                            unsafe_allow_html=True,
                        )

                    if deal_imp:
                        st.markdown(f"<div style='font-size:0.84rem;margin-left:20px'>💼 *{deal_imp}*</div>", unsafe_allow_html=True)

                    if evidence_quote or source_doc:
                        doc_label = source_doc or "Unknown document"
                        quote_html = f"<blockquote>{evidence_quote}</blockquote>" if evidence_quote else ""
                        st.markdown(
                            f'<div class="evidence-box">'
                            f'<span class="doc-name">📄 {doc_label}</span>'
                            f'{quote_html}</div>',
                            unsafe_allow_html=True,
                        )

                    meta_parts = []
                    if confidence:
                        meta_parts.append(f"Confidence: **{confidence}**")
                    if sig.get("signal_id"):
                        meta_parts.append(f"Signal: **{sig['signal_id']}**")
                    if sig.get("catalog_signal_id"):
                        meta_parts.append(f"Catalog: {sig['catalog_signal_id']}")
                    if meta_parts:
                        st.caption(" · ".join(meta_parts))
                    st.markdown("---")

            # ── Findings ─────────────────────────────────────────────────────
            if finds:
                st.markdown(f"**🔎 Findings** ({len(finds)})")
                st.caption("Agent analysis — interpreted conclusions with evidence chains")

                for finding in sorted(finds, key=lambda f: _sev_order(f.get("severity", "LOW"))):
                    f_id = finding.get("finding_id", "")
                    f_title = finding.get("title", "Untitled")
                    f_sev = finding.get("severity", "MEDIUM")
                    f_cat = finding.get("category", "")
                    f_desc = finding.get("description", "")
                    f_impact = finding.get("business_impact", "")
                    f_question = finding.get("question_for_target", "")
                    f_remediation = finding.get("remediation", {})
                    f_evidence = finding.get("evidence", [])
                    f_contradictions = finding.get("contradictions", [])

                    sev_e = _sev_emoji(f_sev)
                    _f_expanded = f_sev in ("CRITICAL", "HIGH")

                    with st.expander(f"{sev_e} {f_sev} — {f_title}  {'`' + f_id + '`' if f_id else ''}", expanded=_f_expanded):
                        if f_cat:
                            st.caption(f"Category: {f_cat.replace('_', ' ').title()}")
                        if f_desc:
                            st.markdown(f_desc)

                        if f_evidence:
                            st.markdown("**Evidence chain:**")
                            for ev in f_evidence:
                                if isinstance(ev, str):
                                    st.markdown(f"- {ev}")
                                    continue
                                ev_type = ev.get("type", "")
                                if ev_type == "signal":
                                    st.markdown(
                                        f'<div class="evidence-box">'
                                        f'<span class="doc-name">📡 Signal: {ev.get("signal_id", "")}</span>'
                                        f'<br><span style="font-size:0.85rem">{ev.get("detail", "")}</span>'
                                        f'</div>',
                                        unsafe_allow_html=True,
                                    )
                                elif ev_type == "document":
                                    doc_name = ev.get("source_doc", "Unknown")
                                    excerpt = ev.get("excerpt", "")
                                    detail = ev.get("detail", "")
                                    quote_html = f"<blockquote>{excerpt}</blockquote>" if excerpt else ""
                                    st.markdown(
                                        f'<div class="evidence-box">'
                                        f'<span class="doc-name">📄 {doc_name}</span>'
                                        f'{quote_html}'
                                        f'<span style="font-size:0.82rem;color:#475569">{detail}</span>'
                                        f'</div>',
                                        unsafe_allow_html=True,
                                    )
                                elif ev_type == "missing":
                                    st.markdown(
                                        f'<div class="evidence-box" style="border-left-color:#dc2626;background:#fef2f2">'
                                        f'<span class="doc-name" style="color:#dc2626">❌ Missing: {ev.get("expected", "")}</span>'
                                        f'<br><span style="font-size:0.82rem;color:#991b1b">{ev.get("detail", "")}</span>'
                                        f'</div>',
                                        unsafe_allow_html=True,
                                    )
                                elif ev_type == "prior_agent":
                                    st.markdown(
                                        f'<div class="evidence-box" style="border-left-color:#6366f1;background:#f0f9ff">'
                                        f'<span class="doc-name" style="color:#4338ca">🤖 {ev.get("agent", "Agent")} → {ev.get("finding_id", "")}</span>'
                                        f'<br><span style="font-size:0.82rem;color:#475569">{ev.get("detail", "")}</span>'
                                        f'</div>',
                                        unsafe_allow_html=True,
                                    )
                                elif ev_type == "inference":
                                    st.markdown(
                                        f'<div class="evidence-box" style="border-left-color:#d97706;background:#fffbeb">'
                                        f'<span class="doc-name" style="color:#92400e">💡 Inference</span>'
                                        f'<br><span style="font-size:0.82rem;color:#475569;font-style:italic">{ev.get("detail", "")}</span>'
                                        f'</div>',
                                        unsafe_allow_html=True,
                                    )

                        # Source signal cross-references
                        if finding.get("source_signals"):
                            _sig_refs = ", ".join(f"`{s}`" for s in finding["source_signals"])
                            st.caption(f"Source signals: {_sig_refs}")

                        if f_contradictions and any(f_contradictions):
                            st.markdown("**Contradictions:**")
                            for c in f_contradictions:
                                if c:
                                    st.warning(f"⚠️ {c}")

                        if f_impact:
                            st.markdown(f"**Business impact:** {f_impact}")

                        if f_remediation and isinstance(f_remediation, dict):
                            effort = f_remediation.get("effort", "")
                            cost = f_remediation.get("cost_estimate", "")
                            rem_desc = f_remediation.get("description", "")
                            if effort or cost:
                                rem_parts = []
                                if effort:
                                    rem_parts.append(f"**Effort:** {effort}")
                                if cost:
                                    rem_parts.append(f"**Cost:** {cost}")
                                st.markdown(" · ".join(rem_parts))
                            if rem_desc:
                                st.caption(rem_desc)

                        if f_question:
                            st.markdown(
                                f'<div style="background:#eff6ff;border:1px solid #bfdbfe;'
                                f'border-radius:8px;padding:10px 14px;margin-top:8px;font-size:0.85rem">'
                                f'💬 <strong>Ask the target:</strong> {f_question}</div>',
                                unsafe_allow_html=True,
                            )

            elif has_agent_data:
                st.info(f"No findings generated for {plabel}.")

            # ── Blind spots ──────────────────────────────────────────────────
            if blind_spots:
                st.markdown("**⚠️ Blind Spots** — areas with no VDR coverage:")
                for bs in blind_spots:
                    st.markdown(f"- {bs}")

            # ── Chase questions for this pillar ──────────────────────────────
            if questions:
                st.markdown(f"**💬 Chase Questions** ({len(questions)})")
                for i, q in enumerate(questions, 1):
                    q_text = q.get("question", str(q)) if isinstance(q, dict) else str(q)
                    priority = q.get("priority", "medium") if isinstance(q, dict) else "medium"
                    p_emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(priority, "⚪")
                    st.markdown(f"{p_emoji} {i}. {q_text}")

            # ── Low-confidence signals ───────────────────────────────────────
            conf_summary = pdata.get("confidence_summary", {})
            low_conf = conf_summary.get("low_confidence_count", 0)
            if low_conf > 0:
                with st.expander(f"⚠️ {low_conf} low-confidence signals — verify manually"):
                    low_sigs = conf_summary.get("low_confidence_signals", [])
                    for sig in low_sigs:
                        st.markdown(f"**{sig.get('signal_id', 'Unknown')}** — {sig.get('observation', '')}")
                        if sig.get("extraction_note"):
                            st.caption(f"Note: {sig['extraction_note']}")


# ══════════════════════════════════════════════════════════════════════════════
# SECTION D — CHASE LIST
# ══════════════════════════════════════════════════════════════════════════════
st.markdown('<div class="section-label">Section D</div>', unsafe_allow_html=True)
st.markdown('<div class="section-title">📣 Chase List — What to Ask the Target</div>', unsafe_allow_html=True)
st.caption("Auto-generated from domain analysis — gaps, contradictions, and missing evidence")

if not chase_list:
    st.info("No chase questions generated yet. Run the full agent pipeline to populate.")
else:
    priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    chase_list_sorted = sorted(
        chase_list,
        key=lambda q: priority_order.get(q.get("priority", "medium"), 99),
    )

    chase_text = _build_chase_text(chase_list_sorted)

    # Action bar
    _btn1, _btn2, _btn3 = st.columns([1, 1, 4])
    with _btn1:
        st.download_button(
            "📄 Download as TXT",
            data=chase_text,
            file_name=f"{selected_company}_chase_list.txt",
            mime="text/plain",
            use_container_width=True,
        )
    with _btn2:
        if st.button("📋 Copy All", use_container_width=True, key="copy_chase"):
            st.session_state["show_chase_copy"] = True

    if st.session_state.get("show_chase_copy"):
        st.code(chase_text, language=None)
        if st.button("Hide", key="hide_chase"):
            st.session_state["show_chase_copy"] = False
            st.rerun()

    # Grouped display
    by_pillar: dict[str, list[dict]] = {}
    for q in chase_list_sorted:
        plabel = q.get("pillar_label", q.get("pillar_id", "General"))
        by_pillar.setdefault(plabel, []).append(q)

    for pillar_label, questions in by_pillar.items():
        st.markdown(f"**{pillar_label}** ({len(questions)} questions)")
        for i, q in enumerate(questions, 1):
            question_text = q.get("question", str(q)) if isinstance(q, dict) else str(q)
            priority = q.get("priority", "medium") if isinstance(q, dict) else "medium"
            rationale = q.get("rationale", "") if isinstance(q, dict) else ""
            source = q.get("source_finding", "") if isinstance(q, dict) else ""

            p_emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(priority, "⚪")
            source_note = f'<span style="font-size:0.75rem;color:#94a3b8"> ({source})</span>' if source else ""
            rationale_html = ""
            if rationale:
                rationale_html = (
                    f'<div style="font-size:0.78rem;color:#64748b;margin-top:2px;'
                    f'padding-left:24px">{rationale}</div>'
                )

            st.markdown(
                f'<div class="chase-item">'
                f'{p_emoji} <strong>{i}.</strong> {question_text}{source_note}'
                f'{rationale_html}</div>',
                unsafe_allow_html=True,
            )

    total_critical = sum(1 for q in chase_list if q.get("priority") == "critical")
    total_high = sum(1 for q in chase_list if q.get("priority") == "high")
    st.caption(
        f"Total: {len(chase_list)} questions · "
        f"{total_critical} critical · {total_high} high priority · "
        f"across {len(by_pillar)} domains"
    )


# ══════════════════════════════════════════════════════════════════════════════
# SECTION E — PRACTITIONER REVIEW & FEEDBACK
# ══════════════════════════════════════════════════════════════════════════════
st.markdown('<div class="section-label">Section E</div>', unsafe_allow_html=True)
st.markdown('<div class="section-title">🔄 Practitioner Review & Feedback</div>', unsafe_allow_html=True)

st.markdown(
    '<div class="practitioner-panel">',
    unsafe_allow_html=True,
)

# ── Step 1: Download Review Workbooks ─────────────────────────────────────
st.markdown("**Step 1 — Download Review Workbooks**")
st.caption("Pre-populated Excel workbooks for practitioner sign-off. Fill verdicts, corrected ratings, and notes.")

_gate1_xlsx = OUTPUTS_DIR / selected_company / "review_gate1.xlsx"
_gate2_xlsx = OUTPUTS_DIR / selected_company / "review_gate2.xlsx"

_dl1, _dl2, _dl3 = st.columns([1, 1, 2])

with _dl1:
    if _gate1_xlsx.exists():
        with open(_gate1_xlsx, "rb") as _f:
            st.download_button(
                "📥 VDR Scan — Signal Review",
                data=_f.read(),
                file_name=f"{selected_company}_vdr_signal_review.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
        if _g1_feedback:
            _g1_acc = _g1_feedback.get("accuracy_metrics", {})
            st.markdown(
                f'<div class="review-badge done">'
                f'✅ Reviewed by <strong>{_g1_feedback.get("practitioner_id", "")}</strong> · '
                f'{_g1_acc.get("accuracy_pct", "—")}% accuracy · '
                f'{_g1_feedback.get("timestamp", "")[:10]}</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div class="review-badge pending">⏳ Awaiting practitioner review</div>',
                unsafe_allow_html=True,
            )
    else:
        if has_vdr_data and st.button("⚙️ Generate VDR Signal Review", use_container_width=True, key="gen_g1"):
            try:
                from tools.practitioner_review import generate_gate1_manifest, save_review_manifest
                from tools.review_exporter import export_gate1_workbook
                _g1_manifest = generate_gate1_manifest(brief, brief.get("deal_id", selected_company), selected_company)
                save_review_manifest(_g1_manifest)
                export_gate1_workbook(_g1_manifest)
                st.success("VDR Signal Review workbook generated!")
                st.rerun()
            except Exception as _exc:
                st.error(f"Failed to generate: {_exc}")
        elif not has_vdr_data:
            st.caption("Run VDR scan first")

with _dl2:

    def _regenerate_gate2_xlsx():
        """Regenerate the Gate 2 Excel from agent outputs using the resilient JSON parser."""
        from tools.practitioner_review import generate_gate2_manifest, save_review_manifest
        from tools.review_exporter import export_gate2_workbook
        from tools.deal_manager import get_agent_output
        _agents_dir = OUTPUTS_DIR / selected_company / "agents"
        _agent_reports = {}
        if _agents_dir.exists():
            for _af in _agents_dir.glob("*.json"):
                _parsed = get_agent_output(
                    brief.get("deal_id", selected_company), _af.stem
                )
                if _parsed:
                    _agent_reports[_af.stem] = _parsed
        _g2_manifest = generate_gate2_manifest(
            _agent_reports, domain_data,
            brief.get("deal_id", selected_company), selected_company,
        )
        save_review_manifest(_g2_manifest)
        # Build signal_id -> metadata lookup so Excel shows actual file names
        _signal_lookup = {}
        for _sig in brief.get("signals", []):
            _sid = _sig.get("signal_id", "")
            if _sid:
                _signal_lookup[_sid] = _sig
        export_gate2_workbook(_g2_manifest, signal_lookup=_signal_lookup)

    if _gate2_xlsx.exists():
        with open(_gate2_xlsx, "rb") as _f:
            st.download_button(
                "📥 Agent Deep Dive — Finding Review",
                data=_f.read(),
                file_name=f"{selected_company}_agent_finding_review.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
        if _g2_feedback:
            _g2_acc = _g2_feedback.get("accuracy_metrics", {})
            st.markdown(
                f'<div class="review-badge done">'
                f'✅ Reviewed by <strong>{_g2_feedback.get("practitioner_id", "")}</strong> · '
                f'{_g2_acc.get("accuracy_pct", "—")}% accuracy · '
                f'{_g2_feedback.get("timestamp", "")[:10]}</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div class="review-badge pending">⏳ Awaiting practitioner review</div>',
                unsafe_allow_html=True,
            )
        # Regenerate button so practitioners get fresh exports after code changes
        if has_agent_data and st.button("🔄 Regenerate Excel", use_container_width=True, key="regen_g2",
                                         help="Re-export with latest findings and source attribution"):
            try:
                _regenerate_gate2_xlsx()
                st.success("Regenerated! Refresh page to download.")
                st.rerun()
            except Exception as _exc:
                st.error(f"Failed to regenerate: {_exc}")
    else:
        if has_agent_data and st.button("⚙️ Generate Agent Finding Review", use_container_width=True, key="gen_g2"):
            try:
                _regenerate_gate2_xlsx()
                st.success("Agent Finding Review workbook generated!")
                st.rerun()
            except Exception as _exc:
                st.error(f"Failed to generate: {_exc}")
        elif not has_agent_data:
            st.caption("Run agent pipeline first")

with _dl3:
    # Review manifest stats
    _g1_manifest_path = OUTPUTS_DIR / selected_company / "practitioner_review_gate1.json"
    _g2_manifest_path = OUTPUTS_DIR / selected_company / "practitioner_review_gate2.json"

    if _g1_manifest_path.exists() or _g2_manifest_path.exists():
        if _g1_manifest_path.exists():
            _g1m = json.loads(_g1_manifest_path.read_text(encoding="utf-8"))
            _g1_urgency = _g1m.get("summary", {}).get("urgency_distribution", {})
            st.markdown(
                f"**VDR Scan:** {_g1m['summary']['total_items']} items — "
                f"🔴 {_g1_urgency.get('CRITICAL', 0)} critical · "
                f"🟠 {_g1_urgency.get('HIGH', 0)} high · "
                f"🟡 {_g1_urgency.get('MEDIUM', 0)} medium"
            )
        if _g2_manifest_path.exists():
            _g2m = json.loads(_g2_manifest_path.read_text(encoding="utf-8"))
            _g2_urgency = _g2m.get("summary", {}).get("urgency_distribution", {})
            _g2_summary = _g2m.get("summary", {})
            st.markdown(
                f"**Agent Deep Dive:** {_g2_summary.get('total_findings', 0)} findings, "
                f"{_g2_summary.get('total_blind_spots', 0)} blind spots — "
                f"🔴 {_g2_urgency.get('CRITICAL', 0)} critical · "
                f"🟠 {_g2_urgency.get('HIGH', 0)} high"
            )
    else:
        st.caption("Review workbooks are generated automatically after scans complete.")

st.markdown("---")

# ── Step 2: Upload Completed Feedback ────────────────────────────────────
st.markdown("**Step 2 — Upload Completed Feedback**")
st.caption("Drop the filled-in Excel here. The system parses verdicts, computes accuracy, and updates recalibration.")

_up_col1, _up_col2 = st.columns([3, 1])
with _up_col1:
    _uploaded_file = st.file_uploader(
        "Drop the completed review Excel here",
        type=["xlsx"],
        key="feedback_upload",
        label_visibility="collapsed",
    )

# Auto-detect gate from uploaded Excel sheet names
_auto_gate = None
_auto_gate_label = ""
if _uploaded_file is not None:
    try:
        from openpyxl import load_workbook as _lwb
        _peek_wb = _lwb(_uploaded_file, read_only=True, data_only=True)
        _sheet_names = _peek_wb.sheetnames
        _peek_wb.close()
        _uploaded_file.seek(0)
        if "Signals" in _sheet_names and "Findings" not in _sheet_names:
            _auto_gate = 1
            _auto_gate_label = "Auto-detected: **VDR Scan** (Signal Review)"
        elif "Findings" in _sheet_names:
            _auto_gate = 2
            _auto_gate_label = "Auto-detected: **Agent Deep Dive** (Finding Review)"
    except Exception:
        pass

with _up_col2:
    if _auto_gate:
        st.markdown(_auto_gate_label)
        _gate_choice = _auto_gate
    else:
        _gate_choice = st.radio("Review type", [1, 2], format_func=lambda x: "VDR Scan" if x == 1 else "Agent Deep Dive", horizontal=True, key="feedback_gate")
    _practitioner_name = st.text_input("Practitioner", value="", key="feedback_practitioner", placeholder="Name")

if _uploaded_file is not None:
    if st.button("🚀 Ingest Feedback", type="primary", use_container_width=True, key="ingest_feedback"):
        try:
            _tmp_path = OUTPUTS_DIR / selected_company / f"_uploaded_review_gate{_gate_choice}.xlsx"
            with open(_tmp_path, "wb") as _f:
                _f.write(_uploaded_file.getvalue())

            from tools.feedback_importer import ingest_feedback
            _result = ingest_feedback(
                filepath=str(_tmp_path),
                deal_id=brief.get("deal_id", selected_company) if brief else selected_company,
                gate=_gate_choice,
                practitioner=_practitioner_name or "practitioner",
                company_name=selected_company,
            )

            _acc = _result["accuracy"]
            st.success(f"Feedback ingested! Reviewed {_acc['reviewed']}/{_acc['total_items']} items.")

            _acc_col1, _acc_col2, _acc_col3, _acc_col4 = st.columns(4)
            _acc_col1.metric("Accuracy", f"{_acc.get('accuracy_pct', 'N/A')}%")
            _acc_col2.metric("Noise Rate", f"{_acc.get('noise_rate_pct', 'N/A')}%")
            _acc_col3.metric("Over-rated", _acc.get("over_rated_count", 0))
            _acc_col4.metric("Under-rated", _acc.get("under_rated_count", 0))

            _learning = _acc.get("learning_signals", [])
            if _learning:
                st.markdown("**Learning Signals:**")
                for _ls in _learning:
                    st.markdown(f"- {_ls}")

            try:
                from tools.recalibration_engine import ingest_deal_feedback
                _deal_id = brief.get("deal_id", selected_company) if brief else selected_company
                ingest_deal_feedback(_deal_id, selected_company)
                st.caption("✅ Cross-deal recalibration state updated.")
            except Exception as _recal_exc:
                st.caption(f"⚠️ Recalibration update skipped: {_recal_exc}")

            st.info(f"Pinecone: {_result['pinecone_updated']} signal verdicts synced.")

        except Exception as _exc:
            st.error(f"Feedback ingestion failed: {_exc}")

st.markdown("---")

# ── Step 3: Recalibration Insights ───────────────────────────────────────
_recal_state_path = OUTPUTS_DIR / "_recalibration_state.json"
_deal_recal_g1 = OUTPUTS_DIR / selected_company / "recalibration_report_gate1.json"
_deal_recal_g2 = OUTPUTS_DIR / selected_company / "recalibration_report_gate2.json"
_has_recal = _recal_state_path.exists() or _deal_recal_g1.exists() or _deal_recal_g2.exists()

if _has_recal:
    st.markdown("**Step 3 — Recalibration Insights**")
    st.caption("How the system is learning from practitioner feedback")

    _recal_labels = {1: "VDR Scan", 2: "Agent Deep Dive"}
    for _gate_n, _recal_path in [(1, _deal_recal_g1), (2, _deal_recal_g2)]:
        if _recal_path.exists():
            _recal = json.loads(_recal_path.read_text(encoding="utf-8"))
            st.markdown(f"**{_recal_labels[_gate_n]} — {selected_company}**")
            _rc1, _rc2, _rc3, _rc4 = st.columns(4)
            _rc1.metric("Accuracy", f"{_recal.get('accuracy_pct', 'N/A')}%")
            _rc2.metric("Noise", f"{_recal.get('noise_rate_pct', 'N/A')}%")
            _rc3.metric("Reviewed", f"{_recal.get('reviewed', 0)}/{_recal.get('total_items', 0)}")
            _rc4.metric("Rating Drifts", len(_recal.get("rating_drifts", [])))

            for _ls in _recal.get("learning_signals", []):
                st.markdown(f"- {_ls}")
            st.markdown("")

    if _recal_state_path.exists():
        try:
            from tools.recalibration_engine import get_recalibration_summary
            _cross = get_recalibration_summary()
            if _cross.get("deals_analyzed", 0) > 0:
                st.markdown(f"**Cross-Deal Intelligence** ({_cross['deals_analyzed']} deal(s))")
                _xc1, _xc2 = st.columns(2)
                _xc1.metric("Signal Accuracy", f"{_cross.get('signal_accuracy_pct', 'N/A')}%",
                            delta=f"{_cross.get('signal_reviews_total', 0)} reviews")
                if _cross.get("finding_accuracy_pct") is not None:
                    _xc2.metric("Finding Accuracy", f"{_cross['finding_accuracy_pct']}%",
                                delta=f"{_cross.get('finding_reviews_total', 0)} reviews")

                for _ls in _cross.get("learning_signals", []):
                    st.markdown(f"- {_ls}")
                for _np in _cross.get("noise_patterns", []):
                    st.warning(f"🔇 {_np.get('recommendation', '')}")
                for _dp in _cross.get("drift_patterns", []):
                    st.info(f"📏 {_dp.get('recommendation', '')}")
        except Exception as _cross_exc:
            st.caption(f"Cross-deal insights unavailable: {_cross_exc}")
else:
    st.caption("Recalibration insights will appear here after feedback is ingested.")

st.markdown('</div>', unsafe_allow_html=True)

# ── DOCX Report (at bottom — final export after review) ──────────────────
from tools.report_export import generate_report

st.markdown("---")
_rpt1, _rpt2 = st.columns([1, 3])
with _rpt1:
    if st.session_state.get("_report_buf"):
        st.download_button(
            "📄 Download DOCX Report",
            data=st.session_state["_report_buf"],
            file_name=st.session_state.get("_report_name", "report.docx"),
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            use_container_width=True,
        )
    else:
        if st.button("📄 Generate DOCX Report", use_container_width=True, key="gen_report"):
            with st.spinner("Building report..."):
                try:
                    buf = generate_report(selected_company)
                    if buf:
                        st.session_state["_report_buf"] = buf
                        st.session_state["_report_name"] = f"{selected_company}_TDD_Report.docx"
                        st.rerun()
                    else:
                        st.error("No scan data found.")
                except Exception as exc:
                    st.error(f"Error: {exc}")
with _rpt2:
    st.caption("Generate the final TDD report as a Word document after completing your review.")
