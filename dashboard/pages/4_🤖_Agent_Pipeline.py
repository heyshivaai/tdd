"""
Agent Pipeline — run and monitor the 8-agent Phase 1 chain.

Displays the agent chain visually, tracks progress, shows output summaries,
and provides buttons to run the next agent or the full chain sequentially.
Uses threading for background execution.
"""
import os
import sys
import threading
import time
from pathlib import Path

import streamlit as st

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.deal_manager import (
    list_deals,
    get_deal,
    get_agent_progress,
    get_agent_output,
    update_agent_status,
    seed_deal_state_from_vdr,
)
from agents.orchestrator import (
    AGENT_CHAIN,
    get_next_agent,
    run_agent,
    get_agent_by_name,
)
from tools.quinn_version_registry import get_version_registry

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(page_title="Agent Pipeline | TDD Platform", page_icon="🤖", layout="wide")
st.title("🤖 Agent Pipeline")
st.caption("Monitor the 8-agent Phase 1 pipeline and trigger next agents.")

# ── Sidebar: deals ───────────────────────────────────────────────────────────
with st.sidebar:
    st.subheader("Deals")
    all_deals = list_deals()

    if not all_deals:
        st.info("No deals found. Go to **🆕 New Deal** to create one first.")
        st.stop()

    deal_options = {d["deal_id"]: d for d in all_deals}

    # Clickable deal buttons
    st.caption("Active Deals")
    for deal in all_deals[:10]:
        deal_sid = deal.get("deal_id", "unknown")
        company = deal.get("company_name", "?")
        if st.button(f"{company} — {deal_sid}", key=f"sidebar_deal_{deal_sid}", use_container_width=True):
            st.session_state["selected_deal_override"] = deal_sid
            st.rerun()

    st.divider()

    # Deal selector with override logic
    deal_keys = list(deal_options.keys())
    default_index = 0
    if "selected_deal_override" in st.session_state and st.session_state["selected_deal_override"] in deal_keys:
        default_index = deal_keys.index(st.session_state["selected_deal_override"])

    selected_deal_id = st.selectbox(
        "Select Deal",
        options=deal_keys,
        index=default_index,
        help="Choose which deal to manage.",
    )

if not selected_deal_id:
    st.info("Select a deal from the sidebar to get started.")
    st.stop()

selected_deal = get_deal(selected_deal_id)
if not selected_deal:
    st.error(f"Deal not found: {selected_deal_id}")
    st.stop()

# ── Deal header ──────────────────────────────────────────────────────────────
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Deal ID", selected_deal_id)
with col2:
    st.metric("Company", selected_deal["company_name"])
with col3:
    st.metric("Sector", selected_deal["sector"])
with col4:
    st.metric("Deal Type", selected_deal["deal_type"])

st.markdown("---")

# ── Quinn schema version check ──────────────────────────────────────────────
try:
    quinn_reg = get_version_registry(selected_deal_id)
    migration_status = quinn_reg.get("migration_status", "unknown")
    if migration_status == "requires_reprocessing":
        st.warning(
            "⚠️ **Schema Change Alert:** This deal was processed with an older template/catalog version. "
            "Consider re-running the VDR scan before running agents. "
            f"(Template: v{quinn_reg.get('template_version', '?')}, "
            f"Catalog: v{quinn_reg.get('catalog_version', '?')})"
        )
    elif migration_status == "blocked":
        st.error(
            "🚫 **Schema Blocked:** This deal requires manual intervention due to breaking schema changes. "
            "Visit the Quinn Schema Guardian page for details."
        )
except Exception:
    pass  # Quinn integration is non-blocking

# ── Agent progress data ──────────────────────────────────────────────────────
# get_agent_progress returns a flat dict: {agent_name: {status, ...}} or empty dict
raw_progress = get_agent_progress(selected_deal_id)

# If it has the nested "agents" key (future format), use it directly;
# otherwise build the derived fields from the flat dict.
if "agents" in raw_progress:
    agent_statuses = raw_progress["agents"]
    completed = raw_progress.get("completed", 0)
    total = raw_progress.get("total", len(AGENT_CHAIN))
    percentage = raw_progress.get("percentage", 0)
else:
    agent_statuses = raw_progress
    total = len(AGENT_CHAIN)
    completed = sum(1 for v in agent_statuses.values() if isinstance(v, dict) and v.get("status") == "completed")
    percentage = (completed / total * 100) if total > 0 else 0

# ── Progress bar ─────────────────────────────────────────────────────────────
st.subheader(f"Pipeline Progress: {completed}/{total} agents")
st.progress(percentage / 100, text=f"{percentage:.0f}% complete")

# ── Visual pipeline ──────────────────────────────────────────────────────────
st.markdown("---")
st.subheader("Agent Chain")

# Display agents in a horizontal flow
pipeline_cols = st.columns(len(AGENT_CHAIN))

for i, agent_def in enumerate(AGENT_CHAIN):
    agent_name = agent_def["name"]
    agent_label = agent_def["label"]
    agent_status = agent_statuses.get(agent_name, {}).get("status", "pending")

    # Determine icon and color
    status_icon = {
        "pending": "⚪",
        "running": "🔄",
        "completed": "✅",
        "failed": "❌",
    }.get(agent_status, "❓")

    with pipeline_cols[i]:
        with st.container(border=True):
            st.markdown(f"### {status_icon}")
            st.caption(agent_label.split(" — ")[0])
            st.text(agent_status.upper())

st.markdown("---")

# ── Control buttons ──────────────────────────────────────────────────────────
st.subheader("Actions")

action_col1, action_col2 = st.columns(2)

with action_col1:
    next_agent = get_next_agent(selected_deal_id)
    if next_agent:
        agent_def = get_agent_by_name(next_agent)
        btn_label = f"▶️ Run {agent_def['label'].split(' — ')[0]}"
    else:
        btn_label = "✅ All agents complete"

    if st.button(btn_label, disabled=(next_agent is None), type="primary", use_container_width=True):
        if next_agent:
            if "running_agent" not in st.session_state:
                st.session_state.running_agent = None

            st.session_state.running_agent = next_agent

            def _run_agent_thread(deal_id, agent_name):
                """Run agent in background thread."""
                try:
                    import anthropic
                    from dotenv import load_dotenv

                    load_dotenv()
                    api_key = os.environ.get("ANTHROPIC_API_KEY")
                    if not api_key:
                        update_agent_status(deal_id, agent_name, "failed")
                        return

                    # Seed deal state with VDR data before first agent
                    seed_deal_state_from_vdr(deal_id)

                    client = anthropic.Anthropic(api_key=api_key)

                    # Run the agent
                    output = run_agent(deal_id, agent_name, client)

                    st.session_state.running_agent = None
                except Exception as exc:
                    update_agent_status(deal_id, agent_name, "failed")
                    st.session_state.running_agent = None

            thread = threading.Thread(
                target=_run_agent_thread,
                args=(selected_deal_id, next_agent),
                daemon=True,
            )
            thread.start()
            st.rerun()

with action_col2:
    if st.button("🚀 Run Full Chain", disabled=(next_agent is None), use_container_width=True):
        if next_agent:
            if "running_chain" not in st.session_state:
                st.session_state.running_chain = False

            st.session_state.running_chain = True

            def _run_chain_thread(deal_id, start_agent):
                """Run remaining chain in background."""
                try:
                    import anthropic
                    from dotenv import load_dotenv

                    load_dotenv()
                    api_key = os.environ.get("ANTHROPIC_API_KEY")
                    if not api_key:
                        st.session_state.running_chain = False
                        return

                    # Seed deal state with VDR data before agents run
                    seed_deal_state_from_vdr(deal_id)

                    client = anthropic.Anthropic(api_key=api_key)

                    # Run all agents from start_agent to sam
                    for agent_def in AGENT_CHAIN:
                        agent_name = agent_def["name"]

                        # Only run agents starting from start_agent onward
                        if AGENT_CHAIN.index(agent_def) >= [a["name"] for a in AGENT_CHAIN].index(start_agent):
                            current_status = agent_statuses.get(agent_name, {}).get("status", "pending")
                            if current_status != "completed":
                                try:
                                    run_agent(deal_id, agent_name, client)
                                except Exception:
                                    pass

                    st.session_state.running_chain = False
                except Exception:
                    st.session_state.running_chain = False

            thread = threading.Thread(
                target=_run_chain_thread,
                args=(selected_deal_id, next_agent),
                daemon=True,
            )
            thread.start()
            st.rerun()

# ── Running status ───────────────────────────────────────────────────────────
if "running_agent" in st.session_state and st.session_state.running_agent:
    st.markdown("---")
    agent_running = st.session_state.running_agent
    agent_def = get_agent_by_name(agent_running)

    with st.status(f"Running {agent_def['label']}...", expanded=True) as status:
        st.write(f"Agent: {agent_running}")
        st.write(f"Deal: {selected_deal_id}")

        # Simulate progress
        progress_placeholder = st.empty()
        for pct in range(0, 101, 10):
            progress_placeholder.progress(pct / 100)
            time.sleep(1)

        time.sleep(2)
        st.rerun()

if "running_chain" in st.session_state and st.session_state.running_chain:
    st.markdown("---")
    with st.status("Running full agent chain...", expanded=True) as status:
        st.write(f"Deal: {selected_deal_id}")
        st.write(f"Starting from: {next_agent}")

        # Simulate progress
        progress_placeholder = st.empty()
        for pct in range(0, 101, 10):
            progress_placeholder.progress(pct / 100)
            time.sleep(1)

        time.sleep(2)
        st.rerun()

# ── Detailed agent reports ─────────────────────────────────────────────────
st.markdown("---")
st.subheader("Agent Reports")
st.caption("Expand any agent to see full findings, evidence chains, and download the raw report.")

import json as _json

# Report key mapping — agent name to the key inside the JSON that holds the report
_REPORT_KEYS = {
    "alex": "alex",
    "morgan": "morgan_intelligence_report",
    "jordan": "jordan_repository_report",
    "riley": "riley_security_report",
    "casey": "casey_code_quality_report",
    "taylor": "taylor_infrastructure_report",
    "drew": "drew_benchmarking_report",
    "sam": "sam_final_report",
}

_RATING_MAP = {
    "CRITICAL": "RED", "CONCERNING": "YELLOW", "STRONG": "GREEN",
    "ADEQUATE": "GREEN", "RED": "RED", "YELLOW": "YELLOW", "GREEN": "GREEN",
}

_GRADE_EMOJI = {"RED": "🔴", "YELLOW": "🟡", "GREEN": "🟢"}
_SEV_EMOJI = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🟢"}

for agent_def in AGENT_CHAIN:
    agent_name = agent_def["name"]
    agent_label = agent_def["label"]
    agent_desc = agent_def.get("description", agent_def.get("label", ""))
    agent_info = agent_statuses.get(agent_name, {})

    status = agent_info.get("status", "pending")
    completed_at = agent_info.get("completed_at")

    # Load output for completed agents
    output = get_agent_output(selected_deal_id, agent_name) if status == "completed" else None

    # Extract report from the nested structure
    report = None
    grade = "—"
    confidence = "—"
    findings = []
    summary_text = ""

    if output:
        report_key = _REPORT_KEYS.get(agent_name, agent_name)
        report = output.get(report_key, output)

        # Grade
        raw_rating = (
            report.get("overall_domain_rating")
            or report.get("overall_rating")
            or report.get("domain_rating")
            or "UNKNOWN"
        )
        grade = _RATING_MAP.get(raw_rating.upper(), raw_rating.upper()) if raw_rating else "—"

        # Confidence
        meta = report.get("metadata", {})
        if isinstance(meta, dict):
            confidence = meta.get("overall_confidence", "—")

        # Summary
        summary_text = (
            report.get("overall_domain_summary")
            or report.get("executive_summary")
            or report.get("summary")
            or ""
        )
        if isinstance(summary_text, dict):
            summary_text = summary_text.get("summary", str(summary_text))
        elif not isinstance(summary_text, str):
            summary_text = str(summary_text)

        # Findings
        for fkey in ["domain_findings", "findings", "key_findings", "critical_findings"]:
            val = report.get(fkey, [])
            if isinstance(val, list):
                for item in val:
                    if isinstance(item, dict):
                        sub = item.get("findings", [])
                        if sub and isinstance(sub, list):
                            for sf in sub:
                                if isinstance(sf, dict):
                                    findings.append(sf)
                        else:
                            findings.append(item)
                if findings:
                    break

        # Compound risks as additional findings
        for ckey in ["combination_signals", "compound_risks", "compound_signals"]:
            combos = report.get(ckey, [])
            if isinstance(combos, list):
                for combo in combos:
                    if isinstance(combo, dict):
                        findings.append({
                            "title": combo.get("signal_id", "") + ": " + combo.get("combined_observation", combo.get("title", ""))[:80],
                            "severity": combo.get("severity", "HIGH"),
                            "description": combo.get("combined_observation", combo.get("narrative", "")),
                        })

    # Build expander label
    if status == "completed" and grade != "—":
        _g_emoji = _GRADE_EMOJI.get(grade, "⚪")
        _n_crit = sum(1 for f in findings if f.get("severity", "").upper() == "CRITICAL")
        _n_high = sum(1 for f in findings if f.get("severity", "").upper() == "HIGH")
        _severity_hint = ""
        if _n_crit:
            _severity_hint += f" · 🔴 {_n_crit} critical"
        if _n_high:
            _severity_hint += f" · 🟠 {_n_high} high"
        _expander_label = f"{_g_emoji} {agent_label} — {grade} · {len(findings)} findings{_severity_hint}"
    elif status == "completed":
        _expander_label = f"✅ {agent_label} — COMPLETE"
    elif status == "running":
        _expander_label = f"🔄 {agent_label} — RUNNING"
    elif status == "failed":
        _expander_label = f"❌ {agent_label} — FAILED"
    else:
        _expander_label = f"⚪ {agent_label} — PENDING"

    _auto_expand = status == "completed" and any(
        f.get("severity", "").upper() in ("CRITICAL", "HIGH") for f in findings
    )

    with st.expander(_expander_label, expanded=_auto_expand):

        if status != "completed":
            st.markdown(agent_desc)
            if status == "running":
                st.info("⏳ Agent is currently running...")
            elif status == "failed":
                st.error("❌ Agent failed. Check logs or re-run.")
            else:
                st.caption("Agent has not run yet.")
            continue

        # ── Completed agent: show full report ────────────────────────────
        # Metrics row
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Grade", f"{_GRADE_EMOJI.get(grade, '⚪')} {grade}")
        m2.metric("Confidence", str(confidence))
        m3.metric("Findings", len(findings))
        if completed_at:
            m4.metric("Completed", completed_at[:16].replace("T", " ") if len(completed_at) > 16 else completed_at)
        else:
            m4.metric("Status", "✅ Complete")

        # Summary
        if summary_text:
            st.markdown(
                f'<div style="background:#f0f9ff;border:1px solid #bfdbfe;border-radius:10px;'
                f'padding:14px 18px;margin:8px 0;font-size:0.86rem;color:#1e293b;line-height:1.6">'
                f'{summary_text[:800]}</div>',
                unsafe_allow_html=True,
            )

        # Download raw JSON
        if output:
            _json_bytes = _json.dumps(output, indent=2, default=str).encode("utf-8")
            st.download_button(
                f"📥 Download {agent_name} report (JSON)",
                data=_json_bytes,
                file_name=f"{selected_deal['company_name']}_{agent_name}_report.json",
                mime="application/json",
                use_container_width=True,
                key=f"dl_{agent_name}",
            )

        # Findings
        if findings:
            st.markdown(f"**Findings** ({len(findings)})")

            _sev_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
            for f in sorted(findings, key=lambda x: _sev_order.get(x.get("severity", "LOW").upper(), 99)):
                f_title = f.get("title", f.get("finding", f.get("observation", "Untitled")))
                f_sev = f.get("severity", f.get("rating", f.get("risk_level", "MEDIUM"))).upper()
                f_desc = f.get("description", f.get("detail", f.get("observation", "")))
                f_impact = f.get("deal_implication", f.get("business_impact", f.get("impact", "")))
                f_evidence = f.get("evidence", f.get("evidence_quote", ""))
                sev_e = _SEV_EMOJI.get(f_sev, "⚪")

                st.markdown(f"{sev_e} **{f_sev}** — {f_title}")
                if f_desc:
                    st.markdown(
                        f'<div style="font-size:0.86rem;color:#334155;margin:2px 0 6px 20px">{f_desc[:500]}</div>',
                        unsafe_allow_html=True,
                    )
                if f_impact:
                    st.markdown(f"<div style='font-size:0.84rem;margin-left:20px;color:#92400e'>💼 {f_impact}</div>", unsafe_allow_html=True)

                # Render evidence — handle both legacy string and structured array
                if f_evidence and isinstance(f_evidence, str):
                    st.markdown(
                        f'<div style="background:#f1f5f9;border-left:3px solid #3b82f6;border-radius:6px;'
                        f'padding:8px 12px;margin:4px 0 8px 20px;font-size:0.84rem;font-style:italic;color:#334155">'
                        f'"{f_evidence[:300]}"</div>',
                        unsafe_allow_html=True,
                    )
                elif f_evidence and isinstance(f_evidence, list):
                    for ev in f_evidence:
                        if not isinstance(ev, dict):
                            continue
                        ev_type = ev.get("type", "")
                        ev_detail = ev.get("detail", "")
                        if ev_type == "signal":
                            st.markdown(
                                f'<div style="background:#f1f5f9;border-left:3px solid #3b82f6;border-radius:6px;'
                                f'padding:8px 12px;margin:4px 0 4px 20px;font-size:0.84rem">'
                                f'📡 <strong>Signal {ev.get("signal_id", "")}</strong>: {ev_detail}</div>',
                                unsafe_allow_html=True,
                            )
                        elif ev_type == "document":
                            _doc = ev.get("source_doc", "Unknown")
                            _excerpt = ev.get("excerpt", "")
                            _quote = f'<br><em>"{_excerpt[:200]}"</em>' if _excerpt else ""
                            st.markdown(
                                f'<div style="background:#f1f5f9;border-left:3px solid #3b82f6;border-radius:6px;'
                                f'padding:8px 12px;margin:4px 0 4px 20px;font-size:0.84rem">'
                                f'📄 <strong>{_doc}</strong>: {ev_detail}{_quote}</div>',
                                unsafe_allow_html=True,
                            )
                        elif ev_type == "prior_agent":
                            st.markdown(
                                f'<div style="background:#f0f9ff;border-left:3px solid #6366f1;border-radius:6px;'
                                f'padding:8px 12px;margin:4px 0 4px 20px;font-size:0.84rem">'
                                f'🤖 <strong>{ev.get("agent", "Agent")} → {ev.get("finding_id", "")}</strong>: {ev_detail}</div>',
                                unsafe_allow_html=True,
                            )
                        elif ev_type == "missing":
                            st.markdown(
                                f'<div style="background:#fef2f2;border-left:3px solid #dc2626;border-radius:6px;'
                                f'padding:8px 12px;margin:4px 0 4px 20px;font-size:0.84rem;color:#991b1b">'
                                f'❌ <strong>Missing: {ev.get("expected", "")}</strong> — {ev_detail}</div>',
                                unsafe_allow_html=True,
                            )
                        elif ev_type == "inference":
                            st.markdown(
                                f'<div style="background:#fffbeb;border-left:3px solid #d97706;border-radius:6px;'
                                f'padding:8px 12px;margin:4px 0 4px 20px;font-size:0.84rem">'
                                f'💡 <em>{ev_detail[:300]}</em></div>',
                                unsafe_allow_html=True,
                            )
                st.markdown("---")
        else:
            st.caption("No structured findings extracted from this agent's report.")

        # Chase questions generated by this agent
        if report:
            _agent_questions = []
            for qkey in ["priority_questions_for_next_agents", "priority_questions_for_riley",
                          "priority_questions_for_casey", "priority_questions_for_taylor",
                          "priority_questions_for_drew", "follow_on_questions", "questions"]:
                qs = report.get(qkey, [])
                if isinstance(qs, list) and qs:
                    _agent_questions = qs
                    break

            if _agent_questions:
                st.markdown(f"**Questions for next agents** ({len(_agent_questions)})")
                for i, q in enumerate(_agent_questions[:10], 1):
                    q_text = q.get("question", str(q)) if isinstance(q, dict) else str(q)
                    st.markdown(f"{i}. {q_text}")
                if len(_agent_questions) > 10:
                    st.caption(f"+ {len(_agent_questions) - 10} more — download full report for details.")
