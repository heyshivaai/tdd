"""
Questionnaire Tracker — DRL completeness, quality, and version management.

Practitioners upload Crosslake OOTB DRL Excel files, view completeness/quality grades,
track version-over-version progress, and generate chase emails.

Layout:
  1. Deal selector + DRL Excel upload
  2. KPI cards (Overall Grade, Completeness %, Depth Score, Version #)
  3. Version trend chart
  4. Per-tab breakdown with progress bars
  5. What Changed section (v2+)
  6. Outstanding Items / Chase List
  7. Generate Chase Email button
  8. Signal Coverage Map
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

# Setup sys.path for imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.drl_parser import parse_drl_excel
from tools.drl_grader import grade_drl
from tools.drl_version_store import (
    store_drl_version,
    get_drl_history,
    compute_field_diff,
    save_field_diff,
)
from tools.deal_manager import list_deals

# ─────────────────────────────────────────────────────────────────────────────
# PAGE CONFIG & STYLES
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Questionnaire Tracker | TDD Platform",
    page_icon="📋",
    layout="wide",
)

st.markdown("""
<style>
/* Hero */
.drl-hero {
    background: linear-gradient(135deg, #0f172a 0%, #1e293b 60%, #334155 100%);
    border-radius: 14px; padding: 24px 28px; margin-bottom: 20px; color: #f8fafc;
}
.drl-hero h1 { font-size: 1.5rem; font-weight: 800; margin: 0 0 4px; color: #f8fafc; }
.drl-hero .sub { font-size: 0.85rem; color: #94a3b8; margin: 0; }

/* KPI cards */
.kpi-card {
    background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px;
    padding: 16px 18px; text-align: center; box-shadow: 0 1px 3px rgba(0,0,0,0.05);
}
.kpi-card .label { font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.06em;
    color: #64748b; font-weight: 600; margin-bottom: 4px; }
.kpi-card .value { font-size: 1.5rem; font-weight: 800; color: #0f172a; }
.kpi-card .delta { font-size: 0.72rem; color: #64748b; margin-top: 3px; }
.kpi-card.grade-A { border-top: 3px solid #16a34a; }
.kpi-card.grade-B { border-top: 3px solid #2563eb; }
.kpi-card.grade-C { border-top: 3px solid #d97706; }
.kpi-card.grade-D { border-top: 3px solid #ea580c; }
.kpi-card.grade-F { border-top: 3px solid #dc2626; }

/* Grade badge */
.grade-badge {
    display: inline-block; font-size: 1.3rem; font-weight: 800;
    border-radius: 8px; padding: 4px 12px;
}
.grade-A { background: #dcfce7; color: #16a34a; }
.grade-B { background: #dbeafe; color: #2563eb; }
.grade-C { background: #fef3c7; color: #d97706; }
.grade-D { background: #fed7aa; color: #ea580c; }
.grade-F { background: #fee2e2; color: #dc2626; }

/* Progress bar */
.progress-container { margin: 8px 0; }
.progress-label { font-size: 0.85rem; font-weight: 600; color: #0f172a; margin-bottom: 4px; }

/* Severity badges */
.sev-CRITICAL { background: #fef2f2; color: #dc2626; border: 1px solid #fca5a5; }
.sev-HIGH { background: #fff7ed; color: #ea580c; border: 1px solid #fdba74; }
.sev-MEDIUM { background: #fffbeb; color: #d97706; border: 1px solid #fcd34d; }
.sev-badge {
    display: inline-block; border-radius: 6px; padding: 2px 10px;
    font-size: 0.75rem; font-weight: 700;
}

/* Tab breakdown card */
.tab-card {
    background: #ffffff; border: 1px solid #e2e8f0; border-radius: 10px;
    padding: 16px; margin-bottom: 12px;
}
.tab-card .tab-name { font-size: 0.95rem; font-weight: 700; color: #0f172a; margin-bottom: 8px; }
.tab-card .stats { font-size: 0.85rem; color: #64748b; }

/* Section header */
.section-hdr {
    font-size: 1.05rem; font-weight: 700; color: #0f172a;
    border-bottom: 2px solid #e2e8f0; padding-bottom: 8px; margin: 20px 0 12px;
}

/* Chase item */
.chase-item {
    background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px;
    padding: 12px 14px; margin-bottom: 8px;
}

/* Signal coverage */
.signal-row { font-size: 0.9rem; margin: 6px 0; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="drl-hero">
    <h1>📋 Questionnaire Tracker</h1>
    <p class="sub">DRL Completeness & Quality, Version Control, Chase Management</p>
</div>
""", unsafe_allow_html=True)

# ── Sidebar: clickable deals ────────────────────────────────────────────────
with st.sidebar:
    st.subheader("Deals")
    all_deals = list_deals()
    if all_deals:
        st.caption("Available Deals")
        for deal in all_deals[:10]:
            deal_sid = deal.get("deal_id", "unknown")
            company = deal.get("company_name", "?")
            if st.button(f"{company} — {deal_sid}", key=f"sidebar_deal_{deal_sid}", use_container_width=True):
                st.session_state["selected_deal_override"] = deal_sid
                st.rerun()

# ─────────────────────────────────────────────────────────────────────────────
# INPUT SECTION: Deal selector + DRL upload
# ─────────────────────────────────────────────────────────────────────────────
st.markdown('<div class="section-hdr">Upload DRL Excel</div>', unsafe_allow_html=True)

col1, col2 = st.columns([2, 3])

with col1:
    # Deal selector with dropdown
    all_deals = list_deals()
    deal_options = {d["deal_id"]: d for d in all_deals} if all_deals else {}

    if deal_options:
        deal_keys = list(deal_options.keys())
        default_index = 0
        if "selected_deal_override" in st.session_state and st.session_state["selected_deal_override"] in deal_keys:
            default_index = deal_keys.index(st.session_state["selected_deal_override"])

        deal_id = st.selectbox(
            "Select Deal",
            options=deal_keys,
            index=default_index,
            format_func=lambda d: f"{deal_options[d]['company_name']} — {d}",
            help="Choose a deal or enter manually below",
        )
        st.session_state.selected_deal_id = deal_id
    else:
        deal_id = st.text_input(
            "Deal ID",
            value=st.session_state.get("selected_deal_id", ""),
            placeholder="e.g., HORIZON, ACME-001",
            help="Used to organize and track DRL versions for this deal.",
        )
        st.session_state.selected_deal_id = deal_id

with col2:
    uploaded_file = st.file_uploader(
        "Select DRL Excel File (.xlsx)",
        type=["xlsx"],
        help="Upload the Crosslake OOTB Due Diligence Request List.",
    )

# ─────────────────────────────────────────────────────────────────────────────
# PROCESS UPLOAD
# ─────────────────────────────────────────────────────────────────────────────
if uploaded_file and deal_id:
    with st.spinner("Parsing DRL Excel..."):
        try:
            # Save uploaded file to outputs directory
            output_dir = Path("outputs") / deal_id / "questionnaire"
            output_dir.mkdir(parents=True, exist_ok=True)

            # Save with timestamp to preserve multiple uploads
            upload_timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            temp_filepath = output_dir / f"drl_{upload_timestamp}.xlsx"
            with open(temp_filepath, "wb") as f:
                f.write(uploaded_file.getbuffer())

            # Parse the Excel file
            parsed_state = parse_drl_excel(str(temp_filepath))

            # Grade the parsed state
            grades = grade_drl(parsed_state)

            # Store version and maintain history
            version_info = store_drl_version(deal_id, parsed_state, grades)

            # Show success message
            st.success(f"✅ DRL v{version_info['version']} uploaded and graded!")

            # Store in session state for display below
            st.session_state.current_parsed_state = parsed_state
            st.session_state.current_grades = grades
            st.session_state.current_version_info = version_info

        except Exception as e:
            st.error(f"❌ Error processing DRL: {str(e)}")
            st.stop()

# ─────────────────────────────────────────────────────────────────────────────
# LOAD AND DISPLAY RESULTS
# ─────────────────────────────────────────────────────────────────────────────
if not deal_id:
    st.info("👉 Enter a Deal ID and upload a DRL Excel file to get started.")
    st.stop()

# Retrieve history for this deal
history = get_drl_history(deal_id)
latest_version = len(history.get("versions", []))

if latest_version == 0:
    st.info("📭 No DRL versions found for this deal yet. Upload an Excel file above to begin.")
    st.stop()

# Determine which version to display (either from upload or most recent)
if "current_version_info" in st.session_state:
    display_version = st.session_state.current_version_info["version"]
    parsed_state = st.session_state.current_parsed_state
    grades = st.session_state.current_grades
else:
    # Load the most recent version from disk
    display_version = latest_version
    output_dir = Path("outputs") / deal_id / "questionnaire"
    state_path = output_dir / f"drl_state_v{display_version}.json"
    with open(state_path, "r") as f:
        parsed_state = json.load(f)
    # Reconstruct grades from history entry
    history_entry = history["versions"][-1]
    grades = {
        "deal_id": deal_id,
        "version": display_version,
        "tab_scores": history_entry.get("tab_scores", {}),
        "overall": {
            "completeness_pct": history_entry.get("overall_completeness", 0),
            "depth_score": history_entry.get("overall_depth", 0),
            "composite_score": history_entry.get("overall_composite", 0),
            "grade": history_entry.get("grade", "F"),
        },
    }

overall = grades.get("overall", {})
grade = overall.get("grade", "F")
completeness = overall.get("completeness_pct", 0)
depth = overall.get("depth_score", 0)

# ─────────────────────────────────────────────────────────────────────────────
# KPI CARDS ROW
# ─────────────────────────────────────────────────────────────────────────────
st.markdown('<div class="section-hdr">Key Metrics</div>', unsafe_allow_html=True)

kpi_cols = st.columns(4)

# Overall Grade
with kpi_cols[0]:
    grade_class = f"grade-{grade}"
    st.markdown(f"""
    <div class="kpi-card {grade_class}">
        <div class="label">Overall Grade</div>
        <div class="value"><span class="grade-badge {grade_class}">{grade}</span></div>
        <div class="delta">{overall.get('composite_score', 0):.1f} composite</div>
    </div>
    """, unsafe_allow_html=True)

# Completeness
with kpi_cols[1]:
    st.markdown(f"""
    <div class="kpi-card">
        <div class="label">Completeness</div>
        <div class="value">{completeness:.0f}%</div>
        <div class="delta">{parsed_state.get('overall', {}).get('filled_fields', 0)} / {parsed_state.get('overall', {}).get('total_fields', 0)} fields</div>
    </div>
    """, unsafe_allow_html=True)

# Depth Score
with kpi_cols[2]:
    st.markdown(f"""
    <div class="kpi-card">
        <div class="label">Depth Score</div>
        <div class="value">{depth:.1f}</div>
        <div class="delta">out of 10</div>
    </div>
    """, unsafe_allow_html=True)

# Version
with kpi_cols[3]:
    st.markdown(f"""
    <div class="kpi-card">
        <div class="label">Version #</div>
        <div class="value">{display_version}</div>
        <div class="delta">of {latest_version} total</div>
    </div>
    """, unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# VERSION TREND CHART (if multiple versions)
# ─────────────────────────────────────────────────────────────────────────────
if latest_version > 1:
    st.markdown('<div class="section-hdr">Version Trend</div>', unsafe_allow_html=True)

    # Build trend data
    trend_data = []
    for v in history["versions"]:
        trend_data.append({
            "Version": f"v{v['version']}",
            "Completeness": v.get("overall_completeness", 0),
            "Depth": v.get("overall_depth", 0) * 10,  # Scale to 0-100
            "Composite": v.get("overall_composite", 0),
        })

    df_trend = pd.DataFrame(trend_data)

    # Line chart
    st.line_chart(
        df_trend.set_index("Version")[["Completeness", "Depth", "Composite"]],
        height=300,
    )

# ─────────────────────────────────────────────────────────────────────────────
# PER-TAB BREAKDOWN
# ─────────────────────────────────────────────────────────────────────────────
st.markdown('<div class="section-hdr">Per-Tab Breakdown</div>', unsafe_allow_html=True)

# Map tab IDs to human-readable names
TAB_NAMES = {
    "technology": "Technology",
    "software_dev_tools": "Software Development & Tools",
    "systems_security_infra": "Systems & Security Infrastructure",
    "rd_spend": "R&D Spend",
    "census_input": "Census & Team Data",
}

for tab_id, tab_data in parsed_state.get("tabs", {}).items():
    total = tab_data.get("total_fields", 0)
    filled = tab_data.get("filled_fields", 0)
    completeness_pct = tab_data.get("completeness_pct", 0)

    # Get grade from tab_scores
    tab_score = grades.get("tab_scores", {}).get(tab_id, {})
    tab_grade = tab_score.get("grade", "F")
    tab_grade_class = f"grade-{tab_grade}"

    tab_name = TAB_NAMES.get(tab_id, tab_id)

    col1, col2, col3 = st.columns([3, 1, 1])

    with col1:
        st.markdown(f"""
        <div class="tab-card">
            <div class="tab-name">{tab_name}</div>
            <div class="progress-container">
                <div class="progress-label">{completeness_pct:.0f}% ({filled}/{total} fields)</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        # Progress bar
        st.progress(completeness_pct / 100.0)

    with col3:
        st.markdown(f"""
        <div style="text-align: center; padding: 8px 0;">
            <span class="grade-badge {tab_grade_class}">{tab_grade}</span>
        </div>
        """, unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# WHAT CHANGED (v2+)
# ─────────────────────────────────────────────────────────────────────────────
if display_version > 1:
    st.markdown('<div class="section-hdr">What Changed</div>', unsafe_allow_html=True)

    # Compute diff from v1 to current
    try:
        diff = compute_field_diff(deal_id, 1, display_version)
        summary = diff.get("summary", {})

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric(
                "✅ Newly Filled",
                summary.get("fields_newly_filled", 0),
            )

        with col2:
            st.metric(
                "⬆️ Improved",
                summary.get("fields_improved", 0),
            )

        with col3:
            st.metric(
                "⏳ Still Empty",
                summary.get("fields_still_empty", 0),
            )

        with col4:
            st.metric(
                "↔️ Unchanged",
                summary.get("fields_unchanged", 0),
            )

        # Show delta from previous version if available
        prev_version = history["versions"][-2] if len(history["versions"]) > 1 else None
        if prev_version:
            delta_info = history["versions"][-1].get("delta_from_previous", {})
            if delta_info:
                st.caption(
                    f"📊 Completeness: {delta_info.get('completeness_delta', 'N/A')} | "
                    f"Depth: {delta_info.get('depth_delta', 'N/A')}"
                )

    except Exception as e:
        st.warning(f"Could not compute diff: {str(e)}")

# ─────────────────────────────────────────────────────────────────────────────
# OUTSTANDING ITEMS / CHASE LIST
# ─────────────────────────────────────────────────────────────────────────────
st.markdown('<div class="section-hdr">Outstanding Items — Chase List</div>', unsafe_allow_html=True)

# Identify still-empty fields and their urgency
still_empty_items = []
for tab_id, tab_data in parsed_state.get("tabs", {}).items():
    for field in tab_data.get("fields", []):
        if field.get("status") == "EMPTY":
            signals = field.get("maps_to_signals", [])

            # Determine urgency based on signal mapping
            urgency = "MEDIUM"
            critical_signals = ["CC-03", "CC-04", "CC-05", "TA-01"]
            high_signals = ["TA-02", "TA-03", "SA-01", "SA-02"]

            if any(s in signals for s in critical_signals):
                urgency = "CRITICAL"
            elif any(s in signals for s in high_signals):
                urgency = "HIGH"

            still_empty_items.append({
                "field_id": field.get("field_id"),
                "tab": tab_id,
                "request": field.get("request", ""),
                "urgency": urgency,
                "signals": signals,
            })

# Sort by urgency (CRITICAL first)
urgency_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2}
still_empty_items.sort(key=lambda x: urgency_order.get(x["urgency"], 3))

if still_empty_items:
    # Group by urgency
    for urgency_level in ["CRITICAL", "HIGH", "MEDIUM"]:
        items_at_level = [x for x in still_empty_items if x["urgency"] == urgency_level]
        if not items_at_level:
            continue

        emoji = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡"}.get(urgency_level, "⚪")
        st.markdown(f"**{emoji} {urgency_level}** ({len(items_at_level)} items)")

        for item in items_at_level:
            sev_class = f"sev-{item['urgency']}"
            signals_str = ", ".join(item["signals"]) if item["signals"] else "N/A"
            st.markdown(f"""
            <div class="chase-item">
                <strong>{item['field_id']}</strong> — {item['request']}<br/>
                <small>Signals: {signals_str}</small>
            </div>
            """, unsafe_allow_html=True)
else:
    st.success("✅ All fields answered! No outstanding items.")

# ─────────────────────────────────────────────────────────────────────────────
# GENERATE CHASE EMAIL
# ─────────────────────────────────────────────────────────────────────────────
st.markdown('<div class="section-hdr">Generate Chase Email</div>', unsafe_allow_html=True)

if st.button("📧 Generate Chase Email", use_container_width=False):
    # Build email content
    email_lines = [
        f"Subject: Due Diligence Request List (DRL) v{display_version} — Action Required",
        "",
        "Dear Management Team,",
        "",
        f"Thank you for submitting DRL v{display_version}. We have reviewed the responses and ",
        "identified items requiring additional detail or clarification.",
        "",
        "Current Status:",
        f"  • Overall Grade: {grade}",
        f"  • Completeness: {completeness:.0f}%",
        f"  • Fields Answered: {parsed_state.get('overall', {}).get('filled_fields', 0)} / {parsed_state.get('overall', {}).get('total_fields', 0)}",
        "",
        "Outstanding Items by Priority:",
        "",
    ]

    # Group by urgency
    for urgency_level in ["CRITICAL", "HIGH", "MEDIUM"]:
        items_at_level = [x for x in still_empty_items if x["urgency"] == urgency_level]
        if not items_at_level:
            continue

        emoji_map = {"CRITICAL": "[CRITICAL]", "HIGH": "[HIGH]", "MEDIUM": "[MEDIUM]"}
        email_lines.append(f"{emoji_map.get(urgency_level, '[MEDIUM]')}:")

        for item in items_at_level:
            email_lines.append(f"  • {item['field_id']}: {item['request']}")

        email_lines.append("")

    # Closing
    email_lines.extend([
        "Please provide the missing information or clarifications by [DATE].",
        "Contact us if you have any questions.",
        "",
        "Best regards,",
        "Due Diligence Team",
    ])

    email_text = "\n".join(email_lines)

    # Display in text area for copy
    st.text_area(
        "Chase Email (copy-pasteable):",
        value=email_text,
        height=400,
        disabled=True,
    )

    # Download button
    st.download_button(
        label="📥 Download as .txt",
        data=email_text,
        file_name=f"{deal_id}_drl_chase_v{display_version}.txt",
        mime="text/plain",
    )

# ─────────────────────────────────────────────────────────────────────────────
# SIGNAL COVERAGE MAP
# ─────────────────────────────────────────────────────────────────────────────
st.markdown('<div class="section-hdr">Signal Coverage Map</div>', unsafe_allow_html=True)

st.caption("Which v1.1 signals can we assess from current DRL responses?")

# Group fields by their mapped signals
signal_to_fields = {}
for tab_id, tab_data in parsed_state.get("tabs", {}).items():
    for field in tab_data.get("fields", []):
        signals = field.get("maps_to_signals", [])
        status = field.get("status", "EMPTY")

        for signal in signals:
            if signal not in signal_to_fields:
                signal_to_fields[signal] = {"answered": 0, "empty": 0}

            if status == "ANSWERED":
                signal_to_fields[signal]["answered"] += 1
            else:
                signal_to_fields[signal]["empty"] += 1

# Group by signal category (first 2 chars)
signal_groups = {}
for signal, counts in signal_to_fields.items():
    category = signal[:2]
    if category not in signal_groups:
        signal_groups[category] = []

    # Determine icon
    if counts["answered"] > 0 and counts["empty"] == 0:
        icon = "✅"
    elif counts["answered"] > 0:
        icon = "⏳"
    else:
        icon = "❌"

    signal_groups[category].append((signal, icon))

# Display by category
for category in sorted(signal_groups.keys()):
    signals = signal_groups[category]
    signal_str = " ".join([f"{sig} {icon}" for sig, icon in signals])
    st.markdown(f"<div class='signal-row'><strong>{category}:</strong> {signal_str}</div>", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# FOOTER
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("---")
st.caption(
    f"📋 Questionnaire Tracker | Deal: **{deal_id}** | "
    f"Version: **v{display_version}** | "
    f"Last Updated: {history['versions'][-1].get('uploaded_at', 'N/A')}"
)
