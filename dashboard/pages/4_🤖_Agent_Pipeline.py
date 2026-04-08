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
)
from agents.orchestrator import (
    AGENT_CHAIN,
    get_next_agent,
    run_agent,
    get_agent_by_name,
)

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

# ── Detailed agent status ────────────────────────────────────────────────────
st.markdown("---")
st.subheader("Agent Details")

for agent_def in AGENT_CHAIN:
    agent_name = agent_def["name"]
    agent_label = agent_def["label"]
    agent_desc = agent_def["description"]
    agent_info = agent_statuses.get(agent_name, {})

    status = agent_info.get("status", "pending")
    completed_at = agent_info.get("completed_at")

    with st.expander(f"{agent_label} — {status.upper()}"):
        col1, col2 = st.columns([2, 1])

        with col1:
            st.markdown(agent_desc)
            if completed_at:
                st.caption(f"Completed: {completed_at}")

        with col2:
            if status == "completed":
                st.success("✅ Complete")

                # Try to load and display output summary
                output = get_agent_output(selected_deal_id, agent_name)
                if output:
                    if "risk_score" in output:
                        st.metric("Risk Score", f"{output['risk_score']}/10")
                    if "findings" in output and output["findings"]:
                        st.caption(f"Findings: {len(output['findings'])} items")

            elif status == "running":
                st.info("⏳ Running")
            elif status == "failed":
                st.error("❌ Failed")
            else:
                st.write("⚪ Pending")
