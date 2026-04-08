"""
New Scan — launch a VDR triage scan from the dashboard.

Updated to work with deal_manager. Collects VDR path and deal metadata,
then kicks off run_triage() in a background thread. Progress is streamed
via the scan_registry.
"""
import os
import sys
import threading
import time
from pathlib import Path

import streamlit as st

# Ensure project root is on sys.path so agents/tools imports work
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.scan_registry import register_scan, update_scan, get_scan, get_all_scans
from tools.deal_manager import list_deals, get_deal, update_deal

# ── Page config ─────────────────────────────────────────────────────────────
st.set_page_config(page_title="New Scan | TDD Platform", page_icon="🚀", layout="wide")
st.title("🚀 New VDR Scan")
st.caption("Launch a technology due diligence scan against a Virtual Data Room.")

# ── Discover existing VDR folders for convenience ───────────────────────────
VDR_ROOT = PROJECT_ROOT / "VDR"
vdr_choices = []
if VDR_ROOT.exists():
    for p in sorted(VDR_ROOT.iterdir()):
        if p.is_dir():
            vdr_choices.append(str(p))

# ── Sidebar: deals and scans ────────────────────────────────────────────────
with st.sidebar:
    st.subheader("Deals & Scans")
    all_deals = list_deals()

    if all_deals:
        st.caption("Active Deals")
        for deal in all_deals[:5]:
            deal_id = deal.get("deal_id", "unknown")
            company = deal.get("company_name", "Unknown")
            scan_status = deal.get("scan_status", "not_started")

            status_icon = {
                "not_started": "⚪",
                "in_progress": "🔄",
                "completed": "✅",
                "failed": "❌",
            }.get(scan_status, "❓")

            st.text(f"{status_icon} {deal_id} — {company}")

    st.divider()
    st.caption("Recent Scans")
    all_scans = get_all_scans()
    if all_scans:
        for company, rec in sorted(all_scans.items(), key=lambda x: x[1].get("started_at", ""), reverse=True)[:5]:
            status = rec.get("status", "unknown")
            icon = {"running": "🔄", "completed": "✅", "failed": "❌", "stale": "⚠️"}.get(status, "❓")
            st.text(f"{icon} {company} — {status}")
    else:
        st.caption("No scans yet.")

# ── Scan form ───────────────────────────────────────────────────────────────
st.markdown("---")
st.subheader("Scan Configuration")

# Deal selector
all_deals = list_deals()
deal_options = {d["deal_id"]: d for d in all_deals} if all_deals else {}

if not deal_options:
    st.info("No deals found. Go to **🆕 New Deal** to create one first.")
    st.stop()

selected_deal_id = st.selectbox(
    "Select Deal",
    options=list(deal_options.keys()),
    help="Choose which deal to scan.",
)

selected_deal = deal_options[selected_deal_id]

# Pre-fill deal metadata
col1, col2 = st.columns(2)

with col1:
    st.metric("Company", selected_deal["company_name"])
    st.metric("Sector", selected_deal["sector"])

with col2:
    st.metric("Deal Type", selected_deal["deal_type"])
    deal_status = selected_deal.get("scan_status", "not_started")
    st.metric("Scan Status", deal_status)

st.markdown("---")

# VDR path and optional overrides
col1, col2 = st.columns(2)

with col1:
    vdr_mode = st.radio("VDR Location", ["Use deal's VDR", "Select from project", "Enter path manually"], horizontal=True)

    if vdr_mode == "Use deal's VDR":
        if selected_deal.get("vdr_path"):
            vdr_path = selected_deal["vdr_path"]
            st.caption(f"Using: {vdr_path}")
        else:
            st.warning("Deal has no VDR path configured.")
            vdr_path = ""
    elif vdr_mode == "Select from project" and vdr_choices:
        vdr_path = st.selectbox("VDR Folder", options=vdr_choices, key="vdr_select")
    else:
        vdr_path = st.text_input(
            "VDR Path",
            value=selected_deal.get("vdr_path", ""),
            placeholder=r"C:\Users\...\VDR\Company-Name",
            help="Absolute path to the VDR root folder on your machine.",
            key="vdr_manual",
        )

with col2:
    st.write("")  # Spacer
    st.write("")  # Spacer
    update_vdr = st.checkbox("Update deal's VDR path", value=False)

company_name = selected_deal["company_name"]
deal_id = selected_deal_id
sector = selected_deal["sector"]
deal_type = selected_deal["deal_type"]

# ── Validation ──────────────────────────────────────────────────────────────
ready = True
warnings = []
if not company_name:
    warnings.append("Company name is required.")
    ready = False
if not deal_id:
    warnings.append("Deal ID is required.")
    ready = False
if not vdr_path:
    warnings.append("VDR path is required.")
    ready = False
elif not Path(vdr_path).exists():
    warnings.append(f"VDR path does not exist: `{vdr_path}`")
    ready = False

# ── Launch button ───────────────────────────────────────────────────────────
st.markdown("---")

if warnings:
    for w in warnings:
        st.warning(w)

# Session state for tracking the running scan
if "scan_running" not in st.session_state:
    st.session_state.scan_running = False
if "scan_company" not in st.session_state:
    st.session_state.scan_company = None


def _run_scan_thread(vdr_path: str, company: str, deal_id: str, sector: str, deal_type: str):
    """Run triage in a background thread, updating scan_registry as it goes."""
    try:
        import anthropic
        from dotenv import load_dotenv
        load_dotenv()

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            update_scan(company, status="failed", error="ANTHROPIC_API_KEY not set")
            return

        client = anthropic.Anthropic(api_key=api_key)

        from agents.vdr_triage import run_triage
        brief, completeness = run_triage(
            vdr_path=vdr_path,
            company_name=company,
            deal_id=deal_id,
            sector=sector,
            deal_type=deal_type,
            client=client,
        )

        rating = brief.get("overall_signal_rating", "unknown")
        total_signals = sum(
            len(b.get("signals", []))
            for b in brief.get("batch_results", [])
        )
        update_scan(
            company,
            status="completed",
            phase="done",
            rating=rating,
            progress={"signals_found": total_signals},
        )
    except Exception as exc:
        update_scan(company, status="failed", error=str(exc)[:500])


if st.button("🚀 Launch Scan", disabled=not ready or st.session_state.scan_running, type="primary", use_container_width=True):
    # Update deal's VDR path if user changed it
    if update_vdr and vdr_path:
        update_deal(deal_id, vdr_path=vdr_path)

    # Register in scan_registry
    vdr_doc_count = sum(1 for _ in Path(vdr_path).rglob("*") if _.is_file()) if Path(vdr_path).exists() else 0
    register_scan(
        company_name=company_name.upper(),
        deal_id=deal_id,
        sector=sector,
        deal_type=deal_type,
        scan_mode="full",
        total_vdr_docs=vdr_doc_count,
    )

    # Update deal status
    update_deal(deal_id, scan_status="in_progress", current_phase="vdr_scan")

    st.session_state.scan_running = True
    st.session_state.scan_company = company_name.upper()

    thread = threading.Thread(
        target=_run_scan_thread,
        args=(vdr_path, company_name.upper(), deal_id, sector, deal_type),
        daemon=True,
    )
    thread.start()
    st.rerun()

# ── Progress display ────────────────────────────────────────────────────────
if st.session_state.scan_running and st.session_state.scan_company:
    company = st.session_state.scan_company
    st.markdown("---")
    st.subheader(f"Scan in progress: {company}")

    progress_placeholder = st.empty()
    status_placeholder = st.empty()

    scan = get_scan(company)
    if scan:
        status = scan.get("status", "unknown")
        phase = scan.get("phase", "starting")
        progress = scan.get("progress", {})

        if status == "completed":
            st.session_state.scan_running = False
            st.success(f"✅ Scan complete! Rating: **{scan.get('rating', 'N/A')}** — "
                       f"{progress.get('signals_found', 0)} signals extracted.")
            st.info("Head to **📊 Deal Dashboard** in the sidebar to view the full results.")

        elif status == "failed":
            st.session_state.scan_running = False
            st.error(f"❌ Scan failed: {scan.get('error', 'Unknown error')}")

        else:
            # Still running
            batches_done = progress.get("batches_done", 0)
            batches_total = progress.get("batches_total", 0)
            pct = batches_done / batches_total if batches_total > 0 else 0

            progress_placeholder.progress(pct, text=f"Phase: {phase}")
            status_placeholder.markdown(
                f"**Batches:** {batches_done}/{batches_total} · "
                f"**Signals found:** {progress.get('signals_found', 0)} · "
                f"**Docs processed:** {progress.get('doc_count', 0)}"
            )

            # Auto-refresh while running
            time.sleep(3)
            st.rerun()
