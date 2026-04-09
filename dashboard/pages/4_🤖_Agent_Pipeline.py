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
    # Re-run full chain from scratch
    if st.button("🔄 Re-run Full Chain", use_container_width=True,
                 disabled=(completed == 0 and next_agent is not None),
                 help="Reset all agents and run the entire chain from scratch"):
        # Reset all agents to pending
        for agent_def_r in AGENT_CHAIN:
            update_agent_status(selected_deal_id, agent_def_r["name"], "pending")

        if "running_chain" not in st.session_state:
            st.session_state.running_chain = False

        st.session_state.running_chain = True

        def _rerun_chain_thread(deal_id):
            """Re-run entire chain from scratch."""
            try:
                import anthropic
                from dotenv import load_dotenv

                load_dotenv()
                api_key = os.environ.get("ANTHROPIC_API_KEY")
                if not api_key:
                    st.session_state.running_chain = False
                    return

                seed_deal_state_from_vdr(deal_id)
                client = anthropic.Anthropic(api_key=api_key)

                for agent_def_r in AGENT_CHAIN:
                    try:
                        run_agent(deal_id, agent_def_r["name"], client)
                    except Exception:
                        pass

                st.session_state.running_chain = False
            except Exception:
                st.session_state.running_chain = False

        thread = threading.Thread(
            target=_rerun_chain_thread,
            args=(selected_deal_id,),
            daemon=True,
        )
        thread.start()
        st.rerun()

action_col3, _ = st.columns(2)
with action_col3:
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
from datetime import datetime as _dt


def _build_agent_report_md(agent_name: str, agent_label: str, company: str,
                            grade: str, confidence: str, summary_text: str,
                            findings: list, report: dict, completed_at: str) -> str:
    """Build a polished Markdown report for a single agent."""
    lines = []
    lines.append(f"# {agent_label}")
    lines.append(f"**Company:** {company}  ")
    lines.append(f"**Agent:** {agent_name}  ")
    lines.append(f"**Grade:** {grade}  ")
    lines.append(f"**Confidence:** {confidence}  ")
    if completed_at:
        lines.append(f"**Completed:** {completed_at[:16].replace('T', ' ')}  ")
    lines.append("")

    if summary_text:
        lines.append("## Executive Summary")
        lines.append(summary_text)
        lines.append("")

    if findings:
        sev_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
        sorted_findings = sorted(findings, key=lambda x: sev_order.get(x.get("severity", "LOW").upper(), 99))

        lines.append(f"## Findings ({len(sorted_findings)})")
        lines.append("")

        for idx, f in enumerate(sorted_findings, 1):
            f_title = f.get("title", f.get("finding", f.get("observation", "Untitled")))
            f_sev = f.get("severity", f.get("rating", f.get("risk_level", "MEDIUM"))).upper()
            f_desc = f.get("description", f.get("detail", f.get("observation", "")))
            f_impact = f.get("deal_implication", f.get("business_impact", f.get("impact", "")))
            f_evidence = f.get("evidence", f.get("evidence_quote", ""))
            f_remediation = f.get("remediation", {})
            f_question = f.get("question_for_target", "")
            f_confidence = f.get("confidence", "")

            sev_tag = {"CRITICAL": "🔴 CRITICAL", "HIGH": "🟠 HIGH", "MEDIUM": "🟡 MEDIUM", "LOW": "🟢 LOW"}.get(f_sev, f_sev)
            lines.append(f"### {idx}. [{sev_tag}] {f_title}")
            lines.append("")

            if f_desc:
                lines.append(f_desc)
                lines.append("")

            # Evidence
            if f_evidence and isinstance(f_evidence, str):
                lines.append(f"**Evidence:** *\"{f_evidence}\"*")
                lines.append("")
            elif f_evidence and isinstance(f_evidence, list):
                lines.append("**Evidence:**")
                for ev in f_evidence:
                    if not isinstance(ev, dict):
                        continue
                    ev_type = ev.get("type", "")
                    ev_detail = ev.get("detail", "")
                    if ev_type == "signal":
                        lines.append(f"- 📡 **Signal {ev.get('signal_id', '')}:** {ev_detail}")
                    elif ev_type == "document":
                        _doc = ev.get("source_doc", "Unknown")
                        _excerpt = ev.get("excerpt", "")
                        lines.append(f"- 📄 **{_doc}:** {ev_detail}")
                        if _excerpt:
                            lines.append(f'  > *"{_excerpt}"*')
                    elif ev_type == "prior_agent":
                        lines.append(f"- 🤖 **{ev.get('agent', 'Agent')} → {ev.get('finding_id', '')}:** {ev_detail}")
                    elif ev_type == "missing":
                        lines.append(f"- ❌ **Missing — {ev.get('expected', '')}:** {ev_detail}")
                    elif ev_type == "inference":
                        lines.append(f"- 💡 *{ev_detail}*")
                lines.append("")

            # Source signals
            src_sigs = f.get("source_signals", [])
            if src_sigs:
                lines.append(f"**Source Signals:** {', '.join(src_sigs)}")
                lines.append("")

            if f_impact:
                lines.append(f"**Business Impact:** {f_impact}")
                lines.append("")

            if f_confidence:
                reason = f.get("confidence_reason", "")
                lines.append(f"**Confidence:** {f_confidence}" + (f" — {reason}" if reason else ""))
                lines.append("")

            if isinstance(f_remediation, dict) and f_remediation:
                lines.append(f"**Remediation:** {f_remediation.get('recommendation', f_remediation.get('action', str(f_remediation)))}")
                lines.append("")

            if f_question:
                lines.append(f"**Question for Target:** {f_question}")
                lines.append("")

            lines.append("---")
            lines.append("")

    # Chase questions
    if report:
        agent_questions = []
        for qkey in ["priority_questions_for_next_agents", "priority_questions_for_riley",
                      "priority_questions_for_casey", "priority_questions_for_taylor",
                      "priority_questions_for_drew", "follow_on_questions", "questions"]:
            qs = report.get(qkey, [])
            if isinstance(qs, list) and qs:
                agent_questions = qs
                break

        if agent_questions:
            lines.append("## Questions for Downstream Agents")
            lines.append("")
            for i, q in enumerate(agent_questions, 1):
                q_text = q.get("question", str(q)) if isinstance(q, dict) else str(q)
                lines.append(f"{i}. {q_text}")
            lines.append("")

    lines.append("---")
    lines.append(f"*Generated by TDD Platform on {_dt.now().strftime('%Y-%m-%d %H:%M')}*")
    return "\n".join(lines)

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

        # Findings — check top-level lists first
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

        # Also check tasks > task_N > findings (riley, casey, taylor structure)
        if not findings:
            tasks_val = report.get("tasks", {})
            if isinstance(tasks_val, dict):
                for task_key, task_data in tasks_val.items():
                    if isinstance(task_data, dict):
                        task_findings = task_data.get("findings", [])
                        if isinstance(task_findings, list):
                            for tf in task_findings:
                                if isinstance(tf, dict):
                                    findings.append(tf)

        # Compound risks as additional findings (top-level or inside tasks)
        _compound_sources = [report]
        # Drew nests compound risks under task_2_compound_risks
        tasks_dict = report.get("tasks", {})
        if isinstance(tasks_dict, dict):
            for tk, tv in tasks_dict.items():
                if isinstance(tv, dict):
                    _compound_sources.append(tv)

        for _src in _compound_sources:
            for ckey in ["combination_signals", "compound_risks", "compound_signals"]:
                combos = _src.get(ckey, [])
                if isinstance(combos, list):
                    for combo in combos:
                        if isinstance(combo, dict):
                            findings.append({
                                "title": combo.get("signal_id", combo.get("risk_id", "")) + ": " + combo.get("combined_observation", combo.get("title", combo.get("narrative", "")))[:80],
                                "severity": combo.get("severity", "HIGH"),
                                "description": combo.get("combined_observation", combo.get("narrative", "")),
                                "evidence": combo.get("contributing_findings", combo.get("evidence", "")),
                                "source_signals": combo.get("source_signals", []),
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
                # Offer re-run for failed agents
                if st.button(f"🔄 Re-run {agent_name}", key=f"rerun_failed_{agent_name}", use_container_width=True):
                    update_agent_status(selected_deal_id, agent_name, "pending")
                    st.session_state.running_agent = agent_name

                    def _rerun_single(deal_id, a_name):
                        try:
                            import anthropic
                            from dotenv import load_dotenv
                            load_dotenv()
                            api_key = os.environ.get("ANTHROPIC_API_KEY")
                            if not api_key:
                                update_agent_status(deal_id, a_name, "failed")
                                st.session_state.running_agent = None
                                return
                            seed_deal_state_from_vdr(deal_id)
                            client = anthropic.Anthropic(api_key=api_key)
                            run_agent(deal_id, a_name, client)
                            st.session_state.running_agent = None
                        except Exception:
                            update_agent_status(deal_id, a_name, "failed")
                            st.session_state.running_agent = None

                    thread = threading.Thread(target=_rerun_single, args=(selected_deal_id, agent_name), daemon=True)
                    thread.start()
                    st.rerun()
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

        # Download raw JSON + Re-run buttons
        _btn_col1, _btn_col2, _btn_col3 = st.columns(3)
        with _btn_col1:
            if output:
                _md_report = _build_agent_report_md(
                    agent_name=agent_name,
                    agent_label=agent_label,
                    company=selected_deal["company_name"],
                    grade=grade,
                    confidence=str(confidence),
                    summary_text=summary_text,
                    findings=findings,
                    report=report,
                    completed_at=completed_at or "",
                )
                st.download_button(
                    f"📥 Download report",
                    data=_md_report.encode("utf-8"),
                    file_name=f"{selected_deal['company_name']}_{agent_name}_report.md",
                    mime="text/markdown",
                    use_container_width=True,
                    key=f"dl_{agent_name}",
                )
        with _btn_col2:
            if st.button(f"🔄 Re-run {agent_name}", key=f"rerun_{agent_name}", use_container_width=True,
                         help=f"Reset and re-run this agent only"):
                update_agent_status(selected_deal_id, agent_name, "pending")
                st.session_state.running_agent = agent_name

                def _rerun_one(deal_id, a_name):
                    try:
                        import anthropic
                        from dotenv import load_dotenv
                        load_dotenv()
                        api_key = os.environ.get("ANTHROPIC_API_KEY")
                        if not api_key:
                            update_agent_status(deal_id, a_name, "failed")
                            st.session_state.running_agent = None
                            return
                        seed_deal_state_from_vdr(deal_id)
                        client = anthropic.Anthropic(api_key=api_key)
                        run_agent(deal_id, a_name, client)
                        st.session_state.running_agent = None
                    except Exception:
                        update_agent_status(deal_id, a_name, "failed")
                        st.session_state.running_agent = None

                thread = threading.Thread(target=_rerun_one, args=(selected_deal_id, agent_name), daemon=True)
                thread.start()
                st.rerun()
        with _btn_col3:
            # "Re-run from here" — reset this agent + all downstream, then run chain
            _agent_idx = [a["name"] for a in AGENT_CHAIN].index(agent_name)
            _downstream_names = [a["name"] for a in AGENT_CHAIN[_agent_idx:]]
            _downstream_count = len(_downstream_names)
            if st.button(f"🔄 Re-run from here ({_downstream_count} agents)", key=f"rerun_from_{agent_name}",
                         use_container_width=True,
                         help=f"Reset {agent_name} and all downstream agents, then run chain"):
                for _dn in _downstream_names:
                    update_agent_status(selected_deal_id, _dn, "pending")

                st.session_state.running_chain = True

                def _rerun_from(deal_id, downstream):
                    try:
                        import anthropic
                        from dotenv import load_dotenv
                        load_dotenv()
                        api_key = os.environ.get("ANTHROPIC_API_KEY")
                        if not api_key:
                            st.session_state.running_chain = False
                            return
                        seed_deal_state_from_vdr(deal_id)
                        client = anthropic.Anthropic(api_key=api_key)
                        for a_name in downstream:
                            try:
                                run_agent(deal_id, a_name, client)
                            except Exception:
                                pass
                        st.session_state.running_chain = False
                    except Exception:
                        st.session_state.running_chain = False

                thread = threading.Thread(target=_rerun_from, args=(selected_deal_id, _downstream_names), daemon=True)
                thread.start()
                st.rerun()

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
