"""
TDD Platform — Technology Due Diligence Dashboard

Main Streamlit app entry point. Pages are auto-discovered from dashboard/pages/.

Usage:
    streamlit run dashboard/app.py
"""
import streamlit as st
from pathlib import Path

st.set_page_config(
    page_title="TDD Platform",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Landing page ─────────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
    .hero {
        text-align: center;
        padding: 60px 20px 40px 20px;
    }
    .hero h1 {
        font-size: 2.4rem;
        font-weight: 800;
        margin-bottom: 8px;
    }
    .hero .sub {
        font-size: 1.1rem;
        color: #64748b;
        margin-bottom: 30px;
    }
    .card-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
        gap: 16px;
        padding: 0 20px;
    }
    .card {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 20px;
        transition: box-shadow 0.2s;
    }
    .card:hover {
        box-shadow: 0 4px 12px rgba(0,0,0,0.08);
    }
    .card h3 {
        margin: 0 0 8px 0;
        font-size: 1.1rem;
    }
    .card p {
        margin: 0;
        font-size: 0.88rem;
        color: #475569;
        line-height: 1.5;
    }
    </style>

    <div class="hero">
        <h1>🔍 TDD Platform</h1>
        <p class="sub">Technology Due Diligence — AI-powered VDR analysis for PE practitioners</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# Quick links
st.markdown(
    """
    <div class="card-grid">
        <div class="card">
            <h3>📊 Deal Dashboard</h3>
            <p>View domain findings, signal heatmaps, and chase lists for completed scans.
            Deep dive into each pillar with evidence chains.</p>
        </div>
        <div class="card">
            <h3>🗺️ How It Works</h3>
            <p>Step-by-step walkthrough of the scan pipeline — from VDR mount to
            practitioner-ready reports.</p>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown("---")
st.caption("Use the sidebar to navigate between pages.")
