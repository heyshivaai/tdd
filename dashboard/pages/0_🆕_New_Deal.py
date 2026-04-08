"""
New Deal — create a new deal and configure intake data.

Collects company name, deal ID, sector, deal type, and intake questionnaire
responses. Creates deal record in deal_manager and provides confirmation
with links to next steps (VDR Scan or Agent Pipeline).
"""
import os
import sys
from pathlib import Path

import streamlit as st

# Ensure project root is on sys.path so agents/tools imports work
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.deal_manager import create_deal, list_deals

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(page_title="New Deal | TDD Platform", page_icon="🆕", layout="wide")
st.title("🆕 Create New Deal")
st.caption("Set up a new PE deal and collect intake data.")

# ── Sidebar: existing deals ───────────────────────────────────────────────────
with st.sidebar:
    st.subheader("Existing Deals")
    deals = list_deals()
    if deals:
        for deal in deals:
            deal_id = deal.get("deal_id", "unknown")
            company = deal.get("company_name", "Unknown")
            scan_status = deal.get("scan_status", "not_started")
            
            status_icon = {
                "not_started": "⚪",
                "in_progress": "🔄",
                "chain_running": "🔄",
                "completed": "✅",
                "chain_complete": "✅",
                "failed": "❌",
            }.get(scan_status, "❓")
            
            st.text(f"{status_icon} {deal_id} — {company}")
    else:
        st.caption("No deals yet. Create your first deal below.")

# ── Deal creation form ───────────────────────────────────────────────────────
st.markdown("---")
st.subheader("Deal Details")

col1, col2 = st.columns(2)

with col1:
    deal_id = st.text_input(
        "Deal ID",
        placeholder="e.g. DEAL-001",
        help="Unique identifier for this deal (cannot be changed after creation).",
    )
    company_name = st.text_input(
        "Company Name",
        placeholder="e.g. HORIZON",
        help="Name of the company being evaluated.",
    )
    sector = st.selectbox(
        "Sector",
        options=[
            "healthcare-saas",
            "fintech",
            "enterprise-saas",
            "cybersecurity",
            "data-infrastructure",
            "edtech",
            "insurtech",
            "logistics-tech",
            "other",
        ],
        help="Industry sector — drives expected document matching and signal lenses.",
    )

with col2:
    deal_type = st.selectbox(
        "Deal Type",
        options=[
            "pe-acquisition",
            "growth-equity",
            "carve-out",
            "merger",
            "recapitalization",
            "other",
        ],
        help="Type of transaction — affects diligence weighting.",
    )
    vdr_path = st.text_input(
        "VDR Path (optional)",
        placeholder=r"C:\Users\...\VDR\Company-Name",
        help="Absolute path to the Virtual Data Room (can be added later).",
    )

# ── Intake Data Section ──────────────────────────────────────────────────────
st.markdown("---")
st.subheader("Intake Data")
st.caption("Capture company profile information. All fields are optional and can be updated later.")

intake_col1, intake_col2 = st.columns(2)

with intake_col1:
    revenue = st.text_input(
        "Annual Revenue",
        placeholder="e.g. $50M, $500M, etc.",
        help="Latest annual revenue (or revenue range).",
    )
    employee_count = st.text_input(
        "Employee Count",
        placeholder="e.g. 100, 50-100, etc.",
        help="Current headcount or range.",
    )
    products = st.text_area(
        "Products/Services",
        placeholder="Describe the company's main products or services.",
        help="Brief description of product-market fit.",
    )
    customer_base = st.text_input(
        "Customer Base",
        placeholder="e.g. Mid-market SaaS, Enterprise, SMB, etc.",
        help="Primary customer segment or verticals.",
    )

with intake_col2:
    market_position = st.text_input(
        "Market Position",
        placeholder="e.g. Leader, Challenger, Niche, etc.",
        help="Competitive positioning and market share estimate.",
    )
    geography = st.text_input(
        "Primary Geography",
        placeholder="e.g. US, EU, Global, etc.",
        help="Primary markets and geographic expansion.",
    )
    tech_stack = st.text_area(
        "Tech Stack Signals",
        placeholder="e.g. Python, React, AWS, PostgreSQL, etc.",
        help="Known or assumed technology choices.",
    )

github_url = st.text_input(
    "Public GitHub URL (optional)",
    placeholder="e.g. https://github.com/company/repo",
    help="Link to public repositories for code signal analysis.",
)

strategic_moves = st.text_area(
    "Recent Strategic Moves",
    placeholder="e.g. Recent acquisition, product launch, funding round, partnership, etc.",
    help="Recent news, announcements, or strategic initiatives.",
)

# ── Validation ──────────────────────────────────────────────────────────────
st.markdown("---")
ready = True
warnings = []

if not deal_id:
    warnings.append("Deal ID is required.")
    ready = False
elif any(d.get("deal_id") == deal_id for d in list_deals()):
    warnings.append(f"Deal ID already exists: {deal_id}")
    ready = False

if not company_name:
    warnings.append("Company name is required.")
    ready = False

if warnings:
    for w in warnings:
        st.warning(w)

# ── Create Deal button ───────────────────────────────────────────────────────
if st.button("✅ Create Deal", disabled=not ready, type="primary", use_container_width=True):
    # Build intake data dict
    intake_data = {
        "revenue": revenue,
        "employee_count": employee_count,
        "products": products,
        "customer_base": customer_base,
        "market_position": market_position,
        "geography": geography,
        "tech_stack": tech_stack,
        "github_url": github_url,
        "strategic_moves": strategic_moves,
    }

    # Create the deal
    try:
        deal = create_deal(
            deal_id=deal_id,
            company_name=company_name,
            sector=sector,
            deal_type=deal_type,
            vdr_path=vdr_path,
            intake_data=intake_data,
        )

        st.success(f"✅ Deal created: **{deal_id}** — {company_name}")

        st.markdown("---")
        st.subheader("Next Steps")

        col_next1, col_next2, col_next3 = st.columns(3)

        with col_next1:
            st.markdown("### 🚀 Run VDR Scan")
            st.caption("Launch a triage scan against the Virtual Data Room.")
            if st.button("Go to VDR Scan", key="goto_scan", use_container_width=True):
                st.switch_page("pages/1_🚀_New_Scan.py")

        with col_next2:
            st.markdown("### 🤖 Run Agent Pipeline")
            st.caption("Execute the 8-agent Phase 1 pipeline.")
            if st.button("Go to Agent Pipeline", key="goto_pipeline", use_container_width=True):
                st.switch_page("pages/4_🤖_Agent_Pipeline.py")

        with col_next3:
            st.markdown("### 📋 Questionnaire Tracker")
            st.caption("Track DRL completeness and document collection.")
            if st.button("Go to DRL Tracker", key="goto_drl", use_container_width=True):
                st.switch_page("pages/3_📋_Questionnaire_Tracker.py")

    except Exception as exc:
        st.error(f"❌ Failed to create deal: {exc}")
