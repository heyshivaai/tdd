"""
Deal Dashboard — domain-intelligence layout.

Primary post-scan view. Three layers:
  Layer 1: Signals per domain (raw extractions, click-through to doc excerpts)
  Layer 2: Findings per domain (domain agent analysis, evidence chains)
  Layer 3: Chase list (auto-generated questions, copy / download)

Data sources:
  - domain_findings.json  (7 pillars, findings, chase list)
  - signal checkpoints    (raw signals per batch)
  - vdr_intelligence_brief.json (overall rating, signal index — optional fallback)
  - _scan_registry.json   (scan status, partial scan awareness)

Pillars are dynamic — read from domain_findings.json, not hardcoded.
"""

import json
import sys
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
    border-radius: 14px; padding: 32px 36px 28px; margin-bottom: 22px; color: #f8fafc;
}
.di-hero h1 { font-size: 1.6rem; font-weight: 800; margin: 0 0 4px; color: #f8fafc; }
.di-hero .sub { font-size: 0.85rem; color: #94a3b8; margin: 0; }

/* KPI cards */
.kpi-card {
    background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px;
    padding: 14px 16px; text-align: center;
}
.kpi-card .label { font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.06em;
    color: #64748b; font-weight: 600; margin-bottom: 3px; }
.kpi-card .value { font-size: 1.45rem; font-weight: 800; color: #0f172a; }
.kpi-card .delta { font-size: 0.72rem; color: #64748b; margin-top: 2px; }

/* Domain tile */
.domain-tile {
    background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 12px;
    padding: 18px 20px; margin-bottom: 12px; transition: border-color .15s;
    cursor: pointer;
}
.domain-tile:hover { border-color: #94a3b8; }
.domain-tile .grade { font-size: 1.3rem; font-weight: 800; }
.domain-tile .name { font-size: 0.95rem; font-weight: 700; color: #0f172a; }
.domain-tile .stat { font-size: 0.78rem; color: #64748b; }

/* Severity badges */
.sev-CRITICAL { background:#fef2f2; color:#dc2626; border:1px solid #fca5a5; }
.sev-HIGH     { background:#fff7ed; color:#ea580c; border:1px solid #fdba74; }
.sev-MEDIUM   { background:#fffbeb; color:#d97706; border:1px solid #fcd34d; }
.sev-LOW      { background:#f0fdf4; color:#16a34a; border:1px solid #86efac; }
.sev-badge {
    display:inline-block; border-radius:12px; padding:2px 10px;
    font-size:0.75rem; font-weight:700; letter-spacing:.03em;
}

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

/* Finding card */
.finding-card {
    background: #ffffff; border: 1px solid #e2e8f0; border-radius: 10px;
    padding: 16px 20px; margin-bottom: 12px;
}

/* Chase list */
.chase-item {
    background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px;
    padding: 10px 14px; margin-bottom: 8px;
}

/* Section header */
.section-hdr {
    font-size: 1.05rem; font-weight: 700; color: #0f172a;
    border-bottom: 2px solid #e2e8f0; padding-bottom: 6px; margin: 24px 0 12px;
}
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# SCAN MONITOR — shows running, completed, failed scans across all deals
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
                    icon = "🔄"
                    color = "#2563eb"
                    detail = (
                        f"Phase: **{phase}** | "
                        f"Batches: **{batches_done}/{batches_total}** | "
                        f"Signals: **{signals}** | Docs: **{doc_count}**"
                    )
                    if batches_resumed:
                        detail += f" | Resumed: **{batches_resumed}**"
                elif status == "completed":
                    icon = "✅"
                    color = "#16a34a"
                    rating = scan.get("rating", "")
                    detail = f"Rating: **{rating}** | Signals: **{signals}** | Docs: **{doc_count}**"
                elif status == "failed":
                    icon = "❌"
                    color = "#dc2626"
                    error = scan.get("error", "Unknown error")
                    detail = f"Error: {error[:120]}"
                else:
                    icon = "⏸️"
                    color = "#6b7280"
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


# ── Helpers ──────────────────────────────────────────────────────────────────
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


def _load_domain_findings(company_name: str) -> dict | None:
    """Load domain_findings.json for a company."""
    path = OUTPUTS_DIR / company_name / "domain_findings.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


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

# Deal selector
company_names = [d["company"] for d in deals]

# Check for override from sidebar click
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

# ── Hero ─────────────────────────────────────────────────────────────────────
deal_info = next((d for d in deals if d["company"] == selected_company), {})
rating = deal_info.get("rating", "UNKNOWN")
rating_color = _grade_color(rating)

domain_count = 0
finding_count = 0
signal_count = deal_info.get("signal_count", 0)
question_count = 0

if domain_data:
    domains = domain_data.get("domains", {})
    domain_count = len(domains)
    finding_count = sum(len(d.get("findings", [])) for d in domains.values())
    question_count = len(domain_data.get("chase_list", []))

# ── Partial scan awareness ───────────────────────────────────────────────────
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

_partial_sub = ""
if _is_partial:
    _partial_sub = (
        f' · ⚡ Partial scan: {_scanned_doc_n}/{_total_vdr_n} docs analysed '
        f'({_pending_batch_n} batch{"es" if _pending_batch_n != 1 else ""} remaining)'
    )

st.markdown(
    f'<div class="di-hero">'
    f'<h1>📊 Deal Dashboard — {selected_company}</h1>'
    f'<p class="sub">{deal_info.get("sector", "")} · {deal_info.get("deal_type", "")} · '
    f'Scanned {deal_info.get("scanned", "")}{_partial_sub}</p>'
    f'</div>',
    unsafe_allow_html=True,
)

# Partial scan banner with link to New Scan
if _is_partial:
    st.markdown(
        f'<div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:10px;'
        f'padding:12px 18px;margin-bottom:16px;">'
        f'<span style="font-weight:700;color:#1d4ed8;">⚡ Partial Scan</span>'
        f'<span style="font-size:0.85rem;color:#475569;margin-left:10px;">'
        f'{_pending_batch_n} document categories not yet scanned. '
        f'Go to <strong>New Scan</strong> to add them incrementally.</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

# KPIs
k1, k2, k3, k4 = st.columns(4)
for col, label, value, delta in [
    (k1, "Overall Rating", f"{_grade_emoji(rating)} {rating}", "from VDR scan"),
    (k2, "Signals Extracted", str(signal_count), "across all domains"),
    (k3, "Domain Findings", str(finding_count), f"from {domain_count} pillars"),
    (k4, "Questions Generated", str(question_count), "for target company"),
]:
    col.markdown(
        f'<div class="kpi-card"><div class="label">{label}</div>'
        f'<div class="value">{value}</div>'
        f'<div class="delta">{delta}</div></div>',
        unsafe_allow_html=True,
    )

# ── Report Download ─────────────────────────────────────────────────────────
from tools.report_export import generate_report

dl_col1, dl_col2, dl_col3 = st.columns([1, 1, 4])
with dl_col1:
    if st.button("📥 Generate DOCX Report", use_container_width=True):
        with st.spinner("Building report…"):
            try:
                buf = generate_report(selected_company)
                if buf:
                    st.session_state["_report_buf"] = buf
                    st.session_state["_report_name"] = (
                        f"{selected_company}_TDD_Report.docx"
                    )
                else:
                    st.error("Report generation failed — no scan data found.")
            except Exception as exc:
                st.error(f"Report generation error: {exc}")

if st.session_state.get("_report_buf"):
    with dl_col2:
        st.download_button(
            "⬇ Download Report",
            data=st.session_state["_report_buf"],
            file_name=st.session_state.get("_report_name", "report.docx"),
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            use_container_width=True,
        )

# ══════════════════════════════════════════════════════════════════════════════
# TWO-LAYER INTELLIGENCE: VDR Scan (Phase 0) + Agent Deep Diligence (Phase 1)
# ══════════════════════════════════════════════════════════════════════════════

all_signals = extract_all_signals(brief) if brief else []
# Also try loading signals directly from brief["signals"] if extract_all_signals returns empty
if not all_signals and brief:
    all_signals = brief.get("signals", [])

has_vdr_data = bool(all_signals)
has_agent_data = bool(domain_data and domain_data.get("domains"))

if not has_vdr_data and not has_agent_data:
    st.info(
        "No scan data available for this deal yet. "
        "Run a VDR scan from **New Scan** to generate intelligence."
    )
    st.stop()

# Main tabs for the two intelligence layers
phase_tabs = st.tabs([
    f"🔍 VDR Scan — {len(all_signals)} signals" if has_vdr_data else "🔍 VDR Scan — pending",
    f"🤖 Agent Deep Diligence — {len(domain_data.get('domains', {})) if has_agent_data else 0} pillars" if has_agent_data else "🤖 Agent Deep Diligence — not run yet",
])

# ── TAB 1: VDR Scan Results ────────────────────────────────────────────────
with phase_tabs[0]:
    if not has_vdr_data:
        st.info("No VDR scan data yet. Run a scan from **New Scan**.")
    else:
        # Pillar breakdown from signals
        from collections import Counter
        pillar_counts = Counter()
        rating_counts = Counter()
        for sig in all_signals:
            pid = sig.get("pillar_id") or sig.get("lens_id") or sig.get("lens") or "Unknown"
            pillar_counts[pid] += 1
            r = sig.get("rating", "UNKNOWN").upper()
            rating_counts[r] += 1

        # Rating summary
        r1, r2, r3, r4 = st.columns(4)
        r1.metric("🔴 RED", rating_counts.get("RED", 0))
        r2.metric("🟡 YELLOW", rating_counts.get("YELLOW", 0))
        r3.metric("🟢 GREEN", rating_counts.get("GREEN", 0))
        r4.metric("Total Signals", len(all_signals))

        st.markdown("---")

        # Pillar signal heatmap
        st.markdown("**Signal Distribution by Pillar**")
        pillar_cols = st.columns(min(len(pillar_counts), 4)) if pillar_counts else []
        for i, (pid, count) in enumerate(pillar_counts.most_common()):
            plabel = PILLAR_LABELS.get(pid, pid)
            with pillar_cols[i % len(pillar_cols)] if pillar_cols else st.container():
                red_n = sum(1 for s in all_signals if (s.get("pillar_id") or s.get("lens_id") or s.get("lens")) == pid and s.get("rating", "").upper() == "RED")
                st.metric(plabel, f"{count} signals", delta=f"{red_n} RED" if red_n else "0 RED", delta_color="inverse" if red_n else "off")

        st.markdown("---")

        # Signal inventory table
        st.markdown("**Signal Inventory**")
        for sig in sorted(all_signals, key=lambda s: {"RED": 0, "YELLOW": 1, "GREEN": 2}.get(s.get("rating", "").upper(), 3)):
            rating = sig.get("rating", "UNKNOWN").upper()
            pid = sig.get("pillar_id") or sig.get("lens_id") or sig.get("lens") or "Unknown"
            plabel = PILLAR_LABELS.get(pid, pid)
            title = sig.get("title", sig.get("signal_id", "Untitled"))
            obs = sig.get("observation", "")
            evidence = sig.get("evidence_quote", "")
            source = sig.get("source_doc", "")
            confidence = sig.get("confidence", "")

            rc = {"RED": "#dc2626", "YELLOW": "#d97706", "GREEN": "#16a34a"}.get(rating, "#94a3b8")
            with st.expander(f"{'🔴' if rating == 'RED' else '🟡' if rating == 'YELLOW' else '🟢'} **{title}** — {plabel} · {rating}"):
                if obs:
                    st.markdown(obs)
                if evidence:
                    st.markdown(f"> *\"{evidence}\"*")
                meta_parts = []
                if source:
                    meta_parts.append(f"Source: **{source}**")
                if confidence:
                    meta_parts.append(f"Confidence: **{confidence}**")
                if sig.get("signal_id"):
                    meta_parts.append(f"Signal: **{sig['signal_id']}**")
                if meta_parts:
                    st.caption(" · ".join(meta_parts))

        # CTA to launch agents
        if not has_agent_data:
            st.markdown("---")
            st.markdown("### Ready for Deep Diligence?")
            st.markdown("The VDR scan extracts signals from documents. The **8-Agent Pipeline** goes deeper — each specialist agent analyzes a different domain and produces structured findings with evidence chains.")
            if st.button("🤖 Launch Agent Deep Diligence →", key="launch_agents_from_dashboard", use_container_width=True, type="primary"):
                st.session_state["auto_launch_agents"] = True
                st.switch_page("pages/4_🤖_Agent_Pipeline.py")

# ── TAB 2: Agent Deep Diligence Results ────────────────────────────────────
with phase_tabs[1]:
    if not has_agent_data:
        st.info("Agent deep diligence has not been run yet for this deal.")
        st.markdown("The 8-agent pipeline (Alex → Sam) performs domain-specific analysis across all 7 pillars, producing structured findings, evidence chains, and a prioritized chase list.")
        if st.button("🤖 Launch Agent Pipeline", key="launch_agents_tab2", use_container_width=True, type="primary"):
            st.session_state["auto_launch_agents"] = True
            st.switch_page("pages/4_🤖_Agent_Pipeline.py")
    else:
        # Domain deep dive code — moved inside this else block
        _agent_data_present = True  # noqa: F841 — ensures valid indented block

        # Build pillar list from domain findings (dynamic) or fall back to signals
        if domain_data and domain_data.get("domains"):
            domains = domain_data["domains"]
            pillar_order = sorted(
                domains.keys(),
                key=lambda pid: {"RED": 0, "YELLOW": 1, "GREEN": 2, "NO_DATA": 3, "UNKNOWN": 4}.get(
                    domains[pid].get("grade", "UNKNOWN"), 5
                ),
            )
        else:
            domains = {}
            seen_pillars = {}
            for sig in all_signals:
                pid = sig.get("pillar_id") or sig.get("lens_id") or sig.get("lens") or "Unknown"
                if pid not in seen_pillars:
                    seen_pillars[pid] = PILLAR_LABELS.get(pid, pid)
            pillar_order = list(seen_pillars.keys())

        if not pillar_order:
            st.warning("No domain data available.")
            st.stop()

        # Domain overview grid
        st.markdown("**Domain overview** — click a tab below for deep dive")
        overview_cols = st.columns(min(len(pillar_order), 4))
        for i, pid in enumerate(pillar_order):
            domain_info = domains.get(pid, {})
            grade = domain_info.get("grade", "UNKNOWN")
            plabel = domain_info.get("pillar_label", PILLAR_LABELS.get(pid, pid))
            findings = domain_info.get("findings", [])
            critical = sum(1 for f in findings if f.get("severity") == "CRITICAL")
            high = sum(1 for f in findings if f.get("severity") == "HIGH")
            pillar_signals = [s for s in all_signals if (s.get("pillar_id") or s.get("lens_id") or s.get("lens")) == pid]

            with overview_cols[i % len(overview_cols)]:
                gc = _grade_color(grade)
                st.markdown(
                    f'<div class="domain-tile">'
                    f'<div class="grade" style="color:{gc}">{_grade_emoji(grade)} {grade}</div>'
                    f'<div class="name">{plabel}</div>'
                    f'<div class="stat">{len(pillar_signals)} signals · {len(findings)} findings</div>'
                    f'<div class="stat">{critical} critical · {high} high</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

        # Tabbed deep dives
        tab_labels = [
            f"{_grade_emoji(domains.get(pid, {}).get('grade', 'UNKNOWN'))} {PILLAR_LABELS.get(pid, pid)}"
            for pid in pillar_order
        ]
        tabs = st.tabs(tab_labels)

        for tab, pid in zip(tabs, pillar_order):
            with tab:
                domain_info = domains.get(pid, {})
                plabel = domain_info.get("pillar_label", PILLAR_LABELS.get(pid, pid))
                grade = domain_info.get("grade", "UNKNOWN")
                findings = domain_info.get("findings", [])
                pillar_signals = [
                    s for s in all_signals
                    if (s.get("pillar_id") or s.get("lens_id") or s.get("lens")) == pid
                ]

                # Domain header
                d_summary = domain_info.get("domain_summary", "")
                docs_analyzed = domain_info.get("documents_analyzed", 0)
                confidence = domain_info.get("confidence", 0)

                h1, h2, h3, h4 = st.columns(4)
                h1.metric("Grade", f"{_grade_emoji(grade)} {grade}")
                h2.metric("Confidence", f"{confidence:.0%}" if isinstance(confidence, (int, float)) else str(confidence))
                h3.metric("Documents Analyzed", docs_analyzed)
                h4.metric("Findings", len(findings))

                if d_summary:
                    st.markdown(
                        f'<div style="background:#f0f9ff;border:1px solid #bfdbfe;border-radius:10px;'
                        f'padding:16px 20px;margin:10px 0;font-size:0.88rem;color:#1e293b;line-height:1.6">'
                        f'{d_summary}</div>',
                        unsafe_allow_html=True,
                    )

                # ── SIGNALS (Layer 1) ────────────────────────────────────────────
                st.markdown(f"### 📡 Signals ({len(pillar_signals)})")
                st.caption("Raw extractions from VDR documents — what the scan found")

                if not pillar_signals:
                    st.info(f"No signals extracted for {plabel}. The VDR may lack coverage for this domain.")
                else:
                    rating_order = {"RED": 0, "YELLOW": 1, "GREEN": 2}
                    sorted_signals = sorted(pillar_signals, key=lambda s: rating_order.get(s.get("rating", ""), 99))

                    for sig in sorted_signals:
                        sig_rating = sig.get("rating", "UNKNOWN")
                        sig_emoji = {"RED": "🔴", "YELLOW": "🟡", "GREEN": "🟢"}.get(sig_rating, "⚪")
                        sig_id = sig.get("signal_id", "")
                        title = sig.get("title", "Untitled signal")
                        observation = sig.get("observation", "")
                        source_doc = sig.get("source_doc", "")
                        evidence_quote = sig.get("evidence_quote", "")
                        deal_imp = sig.get("deal_implication", "")
                        confidence = sig.get("confidence", "")
                        catalog_id = sig.get("catalog_signal_id", "")

                        with st.expander(f"{sig_emoji} {sig_rating} — {title}  `{sig_id}`", expanded=False):
                            if observation:
                                st.markdown(observation)

                            if deal_imp:
                                st.markdown(f"**Deal implication:** {deal_imp}")

                            if confidence:
                                st.markdown(f"**Confidence:** {confidence}")

                            if catalog_id:
                                st.caption(f"Catalog match: {catalog_id}")

                            if source_doc or evidence_quote:
                                st.markdown("**Evidence:**")
                                doc_label = source_doc if source_doc else "Unknown document"
                                quote_html = ""
                                if evidence_quote:
                                    quote_html = f"<blockquote>{evidence_quote}</blockquote>"
                                st.markdown(
                                    f'<div class="evidence-box">'
                                    f'<span class="doc-name">📄 {doc_label}</span>'
                                    f'{quote_html}'
                                    f'</div>',
                                    unsafe_allow_html=True,
                                )

                st.divider()

                # ── FINDINGS (Layer 2) ───────────────────────────────────────────
                st.markdown(f"### 🔎 Findings ({len(findings)})")
                st.caption("Domain agent analysis — interpreted conclusions with evidence chains")

                if not findings:
                    if domain_info.get("_error"):
                        st.error(f"Domain analysis failed for {plabel}. Re-run the scan to retry.")
                    elif grade == "NO_DATA":
                        st.info(f"No signals to analyze for {plabel}.")
                    else:
                        st.info("No findings generated. The scan may need to be re-run with the latest code.")
                else:
                    sorted_findings = sorted(findings, key=lambda f: _sev_order(f.get("severity", "LOW")))

                    for finding in sorted_findings:
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

                        sev_emoji = _sev_emoji(f_sev)

                        with st.expander(
                            f"{sev_emoji} {f_sev} — {f_title}  `{f_id}`",
                            expanded=(f_sev in ("CRITICAL", "HIGH")),
                        ):
                            if f_cat:
                                st.caption(f"Category: {f_cat.replace('_', ' ').title()}")

                            if f_desc:
                                st.markdown(f_desc)

                            # Evidence chain
                            if f_evidence:
                                st.markdown("**Evidence chain:**")
                                for ev in f_evidence:
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

                            # Contradictions
                            if f_contradictions and any(f_contradictions):
                                st.markdown("**Contradictions:**")
                                for c in f_contradictions:
                                    if c:
                                        st.warning(f"⚠️ {c}")

                            # Business impact
                            if f_impact:
                                st.markdown(f"**Business impact:** {f_impact}")

                            # Remediation
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

                            # Question for target
                            if f_question:
                                st.markdown(
                                    f'<div style="background:#eff6ff;border:1px solid #bfdbfe;'
                                    f'border-radius:8px;padding:10px 14px;margin-top:8px;font-size:0.85rem">'
                                    f'💬 <strong>Ask the target:</strong> {f_question}</div>',
                                    unsafe_allow_html=True,
                                )

                # Blind spots
                blind_spots = domain_info.get("blind_spots", [])
                if blind_spots:
                    st.markdown("**Blind spots** — areas with no VDR coverage:")
                    for bs in blind_spots:
                        st.markdown(f"- ⚠️ {bs}")

                # Low-confidence signals — verify manually
                conf_summary = domain_info.get("confidence_summary", {})
                low_conf = conf_summary.get("low_confidence_count", 0)
                if low_conf > 0:
                    with st.expander(f"⚠️ {low_conf} low-confidence signals — verify manually"):
                        low_sigs = conf_summary.get("low_confidence_signals", [])
                        for sig in low_sigs:
                            st.markdown(f"**{sig.get('signal_id', 'Unknown')}** — {sig.get('observation', '')}")
                            if sig.get("extraction_note"):
                                st.caption(f"Note: {sig['extraction_note']}")


# ══════════════════════════════════════════════════════════════════════════════
# CHASE LIST (Layer 3)
# ══════════════════════════════════════════════════════════════════════════════

st.divider()
st.markdown('<p class="section-hdr">📣 What to Ask the Target</p>', unsafe_allow_html=True)
st.caption("Auto-generated from domain analysis — gaps, contradictions, and missing evidence")

chase_list = domain_data.get("chase_list", []) if domain_data else []

# Also gather questions from findings if chase_list is empty
if not chase_list and domain_data:
    for pid, dinfo in domain_data.get("domains", {}).items():
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

if not chase_list:
    st.info("No chase questions generated. Run a scan with the latest code to enable domain analysis.")
else:
    # Sort by priority
    priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    chase_list_sorted = sorted(
        chase_list,
        key=lambda q: priority_order.get(q.get("priority", "medium"), 99),
    )

    # Action buttons
    chase_text = _build_chase_text(chase_list_sorted)

    btn_col1, btn_col2, btn_col3 = st.columns([1, 1, 4])
    with btn_col1:
        st.download_button(
            "📄 Download as TXT",
            data=chase_text,
            file_name=f"{selected_company}_chase_list.txt",
            mime="text/plain",
            use_container_width=True,
        )
    with btn_col2:
        if st.button("📋 Copy All", use_container_width=True):
            st.session_state["show_chase_copy"] = True

    if st.session_state.get("show_chase_copy"):
        st.code(chase_text, language=None)
        if st.button("Hide"):
            st.session_state["show_chase_copy"] = False
            st.rerun()

    # Display grouped by pillar
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

            priority_emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(priority, "⚪")

            source_note = f'<span style="font-size:0.75rem;color:#94a3b8"> ({source})</span>' if source else ""
            rationale_html = ""
            if rationale:
                rationale_html = (
                    f'<div style="font-size:0.78rem;color:#64748b;margin-top:2px;'
                    f'padding-left:24px">{rationale}</div>'
                )

            st.markdown(
                f'<div class="chase-item">'
                f'{priority_emoji} <strong>{i}.</strong> {question_text}{source_note}'
                f'{rationale_html}'
                f'</div>',
                unsafe_allow_html=True,
            )

    # Summary
    total_critical = sum(1 for q in chase_list if q.get("priority") == "critical")
    total_high = sum(1 for q in chase_list if q.get("priority") == "high")
    st.caption(
        f"Total: {len(chase_list)} questions · "
        f"{total_critical} critical · {total_high} high priority · "
        f"across {len(by_pillar)} domains"
    )

# ══════════════════════════════════════════════════════════════════════════════
# SCAN QUALITY — low-confidence signals and extraction issues
# ══════════════════════════════════════════════════════════════════════════════

if domain_data:
    scan_meta = domain_data.get("_metadata", {})
    overall_conf = domain_data.get("confidence_summary", {})

    # Low-confidence docs (from extraction quality)
    low_conf_docs = scan_meta.get("low_confidence_docs", [])
    if low_conf_docs:
        with st.expander(f"⚠️ {len(low_conf_docs)} documents with low extraction quality"):
            for doc in low_conf_docs:
                st.text(f"{doc.get('file_path', 'unknown')} — {doc.get('quality', 'unknown')}")

    # Overall signal confidence summary
    if overall_conf and overall_conf.get("low_confidence_count", 0) > 0:
        low_n = overall_conf["low_confidence_count"]
        low_pct = overall_conf.get("low_confidence_pct", 0)
        with st.expander(f"⚠️ {low_n} low-confidence signals across all domains ({low_pct}%)"):
            st.caption(
                "These signals are based on ambiguous or incomplete evidence. "
                "A practitioner should verify them against the source documents."
            )
            for sig in overall_conf.get("low_confidence_signals", []):
                sig_id = sig.get("signal_id", "?")
                title = sig.get("title", "")
                note = sig.get("extraction_note", "")
                src = sig.get("source_doc", "")
                st.markdown(f"**{sig_id}** — {title}")
                if note:
                    st.caption(f"Note: {note}")
                if src:
                    st.caption(f"Source: {src}")
