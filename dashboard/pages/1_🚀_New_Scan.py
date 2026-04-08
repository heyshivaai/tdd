"""
New Scan — preview VDR, pick batches, launch selective or full scan.

Flow:
1. Select deal → VDR path is pre-filled
2. Click "Preview VDR" → instant classification into tiers/batches
3. Review batch breakdown, pick which tiers/batches to scan
4. Click "Launch Scan" → runs selected batches only
5. Live progress with step-by-step KPIs
"""
import json
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
from tools.structure_mapper import map_vdr_structure
from tools.signal_extractor import BATCH_TO_PILLARS

DATA_DIR = PROJECT_ROOT / "data"
BATCH_RULES_PATH = DATA_DIR / "batch_rules.json"
BATCH_TIERS_PATH = DATA_DIR / "batch_tiers.json"

# ── Page config ─────────────────────────────────────────────────────────────
st.set_page_config(page_title="New Scan | TDD Platform", page_icon="🚀", layout="wide")
st.title("🚀 VDR Scan")
st.caption("Preview your VDR, select batches, and launch a targeted or full scan.")

# ── Discover existing VDR folders ───────────────────────────────────────────
VDR_ROOT = PROJECT_ROOT / "VDR"
vdr_choices = []
if VDR_ROOT.exists():
    for p in sorted(VDR_ROOT.iterdir()):
        if p.is_dir():
            vdr_choices.append(str(p))

# ── Sidebar ─────────────────────────────────────────────────────────────────
with st.sidebar:
    st.subheader("Deals & Scans")
    all_deals_sidebar = list_deals()
    if all_deals_sidebar:
        st.caption("Active Deals")
        for deal in all_deals_sidebar[:5]:
            deal_sid = deal.get("deal_id", "unknown")
            company = deal.get("company_name", "?")
            scan_status = deal.get("scan_status", "not_started")
            icon = {"not_started": "⚪", "in_progress": "🔄", "completed": "✅", "failed": "❌"}.get(scan_status, "❓")
            if st.button(f"{icon} {company} — {deal_sid}", key=f"sidebar_deal_{deal_sid}", use_container_width=True):
                st.session_state["selected_deal_override"] = deal_sid
                st.rerun()

    st.divider()
    st.caption("Recent Scans")
    all_scans = get_all_scans()
    if all_scans:
        for company, rec in sorted(all_scans.items(), key=lambda x: x[1].get("started_at", ""), reverse=True)[:5]:
            status = rec.get("status", "unknown")
            icon = {"running": "🔄", "completed": "✅", "failed": "❌", "stale": "⚠️"}.get(status, "❓")
            st.text(f"{icon} {company} — {status}")

# ── Deal selector ───────────────────────────────────────────────────────────
st.markdown("---")
all_deals = list_deals()
deal_options = {d["deal_id"]: d for d in all_deals} if all_deals else {}

if not deal_options:
    st.info("No deals found. Go to **🆕 New Deal** to create one first.")
    st.stop()

# If a deal was clicked in sidebar, pre-select it
default_index = 0
deal_keys = list(deal_options.keys())
if "selected_deal_override" in st.session_state and st.session_state["selected_deal_override"] in deal_keys:
    default_index = deal_keys.index(st.session_state["selected_deal_override"])

selected_deal_id = st.selectbox("Select Deal", options=deal_keys, index=default_index)
selected_deal = deal_options[selected_deal_id]

col1, col2 = st.columns(2)
with col1:
    st.metric("Company", selected_deal["company_name"])
    st.metric("Sector", selected_deal["sector"])
with col2:
    st.metric("Deal Type", selected_deal["deal_type"])
    st.metric("Scan Status", selected_deal.get("scan_status", "not_started"))

st.markdown("---")

# ── VDR path ────────────────────────────────────────────────────────────────
vdr_mode = st.radio("VDR Location", ["Use deal's VDR", "Select from project", "Enter path manually"], horizontal=True)

if vdr_mode == "Use deal's VDR":
    vdr_path = selected_deal.get("vdr_path", "")
    if vdr_path:
        st.caption(f"Using: {vdr_path}")
    else:
        st.warning("Deal has no VDR path. Select another option.")
elif vdr_mode == "Select from project" and vdr_choices:
    vdr_path = st.selectbox("VDR Folder", options=vdr_choices, key="vdr_select")
else:
    vdr_path = st.text_input("VDR Path", value=selected_deal.get("vdr_path", ""), key="vdr_manual")

company_name = selected_deal["company_name"]
deal_id = selected_deal_id
sector = selected_deal["sector"]
deal_type = selected_deal["deal_type"]

# Validation
vdr_valid = bool(vdr_path) and Path(vdr_path).exists()
if vdr_path and not Path(vdr_path).exists():
    st.warning(f"VDR path does not exist: `{vdr_path}`")

# ── Session state ───────────────────────────────────────────────────────────
if "preview_data" not in st.session_state:
    st.session_state.preview_data = None
if "scan_running" not in st.session_state:
    st.session_state.scan_running = False
if "scan_company" not in st.session_state:
    st.session_state.scan_company = None

# ── PHASE 1: Preview VDR ───────────────────────────────────────────────────
st.markdown("---")
st.subheader("Step 1: Preview VDR")

if st.button("🔍 Preview VDR", disabled=not vdr_valid, type="secondary", use_container_width=True):
    with st.spinner("Classifying documents..."):
        vdr_map = map_vdr_structure(vdr_path, str(BATCH_RULES_PATH))
        inventory = vdr_map["inventory"]
        batch_groups = vdr_map["batch_groups"]

        # Load tier config
        tiers = {}
        if BATCH_TIERS_PATH.exists():
            with open(BATCH_TIERS_PATH, encoding="utf-8") as f:
                tier_config = json.load(f)
            tiers = tier_config.get("tiers", {})

        # Classify batches into tiers
        tier_batches = {"core_tech": {}, "supporting_context": {}, "uncategorised": {}}
        tier_meta = {}
        for tier_id, tier_def in tiers.items():
            tier_meta[tier_id] = tier_def
            tier_batch_names = set(tier_def.get("batch_groups", []))
            for bg_name, bg_docs in batch_groups.items():
                if bg_name in tier_batch_names:
                    tier_batches[tier_id][bg_name] = bg_docs

        # Anything not in a defined tier goes to uncategorised
        classified = set()
        for tb in tier_batches.values():
            classified.update(tb.keys())
        for bg_name, bg_docs in batch_groups.items():
            if bg_name not in classified:
                tier_batches["uncategorised"][bg_name] = bg_docs

        st.session_state.preview_data = {
            "inventory": inventory,
            "batch_groups": batch_groups,
            "tier_batches": tier_batches,
            "tier_meta": tier_meta,
            "vdr_path": vdr_path,
        }

    st.rerun()

# ── PHASE 2: Batch picker ──────────────────────────────────────────────────
if st.session_state.preview_data:
    preview = st.session_state.preview_data
    inventory = preview["inventory"]
    batch_groups = preview["batch_groups"]
    tier_batches = preview["tier_batches"]
    tier_meta = preview["tier_meta"]

    # Summary KPIs
    st.subheader("VDR Overview")
    k1, k2, k3 = st.columns(3)
    k1.metric("Total Documents", len(inventory))
    k2.metric("Batch Groups", len(batch_groups))
    total_size_mb = sum(d.get("size_bytes", 0) for d in inventory) / (1024 * 1024)
    k3.metric("Total Size", f"{total_size_mb:.1f} MB")

    # Tier breakdown with checkboxes
    st.markdown("---")
    st.subheader("Step 2: Select Batches to Scan")

    selected_batches = []

    tier_order = [
        ("core_tech", "🟢 Tier 1 — Core Tech", True),
        ("supporting_context", "🟡 Tier 2 — Supporting Context", False),
        ("uncategorised", "⚪ Tier 3 — Uncategorised", False),
    ]

    for tier_id, tier_label, default_selected in tier_order:
        batches = tier_batches.get(tier_id, {})
        if not batches:
            continue

        tier_def = tier_meta.get(tier_id, {})
        total_docs = sum(len(docs) for docs in batches.values())
        est_time = tier_def.get("estimated_minutes", "?")

        with st.expander(f"{tier_label} — {total_docs} docs, ~{est_time} min", expanded=(tier_id == "core_tech")):
            st.caption(tier_def.get("description", ""))

            # Select all for this tier
            select_all = st.checkbox(
                f"Select all {tier_label.split('—')[1].strip()} batches",
                value=default_selected,
                key=f"tier_all_{tier_id}",
            )

            for bg_name, bg_docs in sorted(batches.items()):
                doc_count = len(bg_docs)
                size_mb = sum(d.get("size_bytes", 0) for d in bg_docs) / (1024 * 1024)

                checked = st.checkbox(
                    f"**{bg_name}** — {doc_count} docs ({size_mb:.1f} MB)",
                    value=select_all,
                    key=f"batch_{tier_id}_{bg_name}",
                )
                if checked:
                    selected_batches.append(bg_name)

                # Show sample filenames
                if doc_count > 0:
                    sample = [d["filename"] for d in bg_docs[:3]]
                    remaining = doc_count - len(sample)
                    sample_text = ", ".join(sample)
                    if remaining > 0:
                        sample_text += f", +{remaining} more"
                    st.caption(f"   Files: {sample_text}")

    # Selection summary
    st.markdown("---")
    total_selected_docs = sum(
        len(batch_groups[bg]) for bg in selected_batches if bg in batch_groups
    )
    s1, s2, s3 = st.columns(3)
    s1.metric("Selected Batches", len(selected_batches))
    s2.metric("Selected Documents", total_selected_docs)
    s3.metric("Skipping", f"{len(inventory) - total_selected_docs} docs")

    # ── Pillar coverage map ─────────────────────────────────────────────────
    PILLAR_LABELS = {
        "TechnologyArchitecture": "Technology & Architecture",
        "SecurityCompliance": "Security & Compliance",
        "OrganizationTalent": "Organization & Talent",
        "DataAIReadiness": "Data & AI Readiness",
        "RDSpendAssessment": "R&D Spend Assessment",
        "InfrastructureDeployment": "Infrastructure & Deployment",
        "SDLCProductManagement": "SDLC & Product Management",
    }

    # Calculate which pillars are covered by selected batches
    covered_pillars = set()
    for bg in selected_batches:
        for pillar in BATCH_TO_PILLARS.get(bg, []):
            covered_pillars.add(pillar)

    all_pillars_covered = set()
    for bg in batch_groups:
        for pillar in BATCH_TO_PILLARS.get(bg, []):
            all_pillars_covered.add(pillar)

    st.markdown("---")
    st.subheader("Pillar Coverage")
    st.caption("Which of the 7 pillars will be covered by the selected batches:")

    pcols = st.columns(len(PILLAR_LABELS))
    for i, (pid, plabel) in enumerate(PILLAR_LABELS.items()):
        with pcols[i]:
            if pid in covered_pillars:
                st.markdown(f"✅ **{plabel}**")
            elif pid in all_pillars_covered:
                st.markdown(f"⚪ ~~{plabel}~~")
            else:
                st.markdown(f"❌ {plabel}")

    covered_count = len(covered_pillars)
    st.caption(f"**{covered_count}/7 pillars** covered by selected batches")

    # ── PHASE 3: Launch scan ────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("Step 3: Launch Scan")

    scan_mode = "selective" if len(selected_batches) < len(batch_groups) else "full"
    st.caption(f"Mode: **{scan_mode}** scan — {len(selected_batches)}/{len(batch_groups)} batches selected")

    def _run_scan_thread(vdr_path, company, deal_id, sector, deal_type, selected_batches):
        """Run triage in a background thread with selected batches."""
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
                selected_batches=selected_batches if selected_batches else None,
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
                progress={"signals_found": total_signals, "step": "Scan complete"},
            )
            try:
                update_deal(deal_id, scan_status="completed", current_phase="scan_complete")
            except Exception:
                pass
        except Exception as exc:
            update_scan(company, status="failed", error=str(exc)[:500])
            try:
                update_deal(deal_id, scan_status="failed")
            except Exception:
                pass

    launch_disabled = not selected_batches or st.session_state.scan_running
    if st.button("🚀 Launch Scan", disabled=launch_disabled, type="primary", use_container_width=True):
        # Update deal VDR path if different
        if vdr_path != selected_deal.get("vdr_path"):
            update_deal(deal_id, vdr_path=vdr_path)

        vdr_doc_count = sum(1 for _ in Path(vdr_path).rglob("*") if _.is_file())
        register_scan(
            company_name=company_name.upper(),
            deal_id=deal_id,
            sector=sector,
            deal_type=deal_type,
            scan_mode=scan_mode,
            total_vdr_docs=vdr_doc_count,
            selected_batches=selected_batches,
        )

        update_deal(deal_id, scan_status="in_progress", current_phase="vdr_scan")

        st.session_state.scan_running = True
        st.session_state.scan_company = company_name.upper()

        thread = threading.Thread(
            target=_run_scan_thread,
            args=(vdr_path, company_name.upper(), deal_id, sector, deal_type, selected_batches),
            daemon=True,
        )
        thread.start()
        st.rerun()

# ── Live progress display ───────────────────────────────────────────────────
if st.session_state.scan_running and st.session_state.scan_company:
    company = st.session_state.scan_company
    st.markdown("---")
    st.subheader(f"📡 Live Scan: {company}")

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

            st.markdown("")
            next1, next2 = st.columns(2)
            with next1:
                if st.button("📊 View Results on Deal Dashboard", use_container_width=True, type="primary"):
                    st.switch_page("pages/2_📊_Deal_Dashboard.py")
            with next2:
                if st.button("🤖 Launch Agent Deep Diligence →", use_container_width=True):
                    st.session_state["selected_deal_override"] = scan.get("deal_id", "")
                    st.session_state["auto_launch_agents"] = True
                    st.switch_page("pages/4_🤖_Agent_Pipeline.py")

        elif status == "failed":
            st.session_state.scan_running = False
            st.error(f"❌ Scan failed: {scan.get('error', 'Unknown error')}")

        else:
            # ── 4-Stage Pipeline View ──────────────────────────────
            batches_done = progress.get("batches_done", 0)
            batches_total = progress.get("batches_total", 0)
            step_text = progress.get("step", f"Phase: {phase}")

            # Define stages with their phase keys and icons
            STAGES = [
                {"key": "mapping_vdr",        "icon": "📂", "label": "Structure Map",     "desc": "Inventory all files, assign to batches"},
                {"key": "completeness_check",  "icon": "📋", "label": "Completeness",      "desc": "Check what's present vs. expected"},
                {"key": "signal_extraction",   "icon": "🤖", "label": "Signal Extraction",  "desc": "AI reads docs, maps to 38 signals"},
                {"key": "cross_referencing",   "icon": "🔗", "label": "Cross-Reference",    "desc": "Compound risk analysis + brief"},
            ]

            # Determine stage status based on current phase
            phase_order = ["starting", "mapping_vdr", "completeness_check", "signal_extraction", "cross_referencing", "writing_outputs"]
            current_idx = phase_order.index(phase) if phase in phase_order else 0

            # Render stage cards in a row
            stage_cols = st.columns(4)
            for i, stage in enumerate(STAGES):
                stage_phase_idx = phase_order.index(stage["key"]) if stage["key"] in phase_order else i + 1
                with stage_cols[i]:
                    if current_idx > stage_phase_idx:
                        # Completed
                        st.markdown(
                            f'<div style="background:#f0fdf4;border:2px solid #22c55e;border-radius:12px;padding:16px;text-align:center;min-height:140px;">'
                            f'<div style="font-size:1.5rem;">{stage["icon"]}</div>'
                            f'<div style="font-weight:700;color:#15803d;font-size:0.9rem;margin:6px 0 4px;">✅ {stage["label"]}</div>'
                            f'<div style="font-size:0.75rem;color:#16a34a;">{stage["desc"]}</div>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )
                    elif current_idx == stage_phase_idx:
                        # Active
                        st.markdown(
                            f'<div style="background:#eff6ff;border:2px solid #3b82f6;border-radius:12px;padding:16px;text-align:center;min-height:140px;box-shadow:0 0 12px rgba(59,130,246,0.25);">'
                            f'<div style="font-size:1.5rem;">{stage["icon"]}</div>'
                            f'<div style="font-weight:700;color:#1d4ed8;font-size:0.9rem;margin:6px 0 4px;">🔄 {stage["label"]}</div>'
                            f'<div style="font-size:0.75rem;color:#2563eb;">{stage["desc"]}</div>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )
                    else:
                        # Pending
                        st.markdown(
                            f'<div style="background:#f8fafc;border:2px solid #e2e8f0;border-radius:12px;padding:16px;text-align:center;min-height:140px;opacity:0.6;">'
                            f'<div style="font-size:1.5rem;">{stage["icon"]}</div>'
                            f'<div style="font-weight:700;color:#94a3b8;font-size:0.9rem;margin:6px 0 4px;">⏳ {stage["label"]}</div>'
                            f'<div style="font-size:0.75rem;color:#94a3b8;">{stage["desc"]}</div>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )

            st.markdown("")

            # Overall progress bar
            phase_pct = {
                "starting": 0.0,
                "mapping_vdr": 0.05,
                "completeness_check": 0.15,
                "signal_extraction": 0.2 + (0.6 * (batches_done / batches_total if batches_total > 0 else 0)),
                "cross_referencing": 0.85,
                "writing_outputs": 0.95,
            }.get(phase, 0.0)
            st.progress(phase_pct, text=step_text)

            # KPI row
            kpi1, kpi2, kpi3, kpi4 = st.columns(4)
            kpi1.metric("Documents", progress.get("doc_count", "—"))
            kpi2.metric("Batches", f"{batches_done}/{batches_total}" if batches_total else "—")
            kpi3.metric("Signals Found", progress.get("signals_found", 0))
            kpi4.metric("Completeness", f"{progress.get('completeness_score', '—')}/100")

            # ── Timing & ETA row ──────────────────────────────────
            timing = scan.get("timing", {})
            elapsed_sec = timing.get("elapsed_seconds", 0)
            eta_sec = timing.get("eta_seconds")
            avg_batch = timing.get("avg_batch_seconds")

            # Format elapsed as MM:SS
            started_str = scan.get("started_at", "")
            if started_str:
                try:
                    from datetime import datetime as _dt, timezone as _tz
                    started_dt = _dt.fromisoformat(started_str.replace("Z", "+00:00"))
                    elapsed_sec = (_dt.now(_tz.utc) - started_dt).total_seconds()
                except (ValueError, TypeError):
                    pass
            elapsed_min, elapsed_s = divmod(int(elapsed_sec), 60)
            elapsed_str = f"{elapsed_min}m {elapsed_s:02d}s"

            t1, t2, t3 = st.columns(3)
            t1.metric("⏱️ Elapsed", elapsed_str)
            if avg_batch and batches_done > 0:
                avg_min, avg_s = divmod(int(avg_batch), 60)
                t2.metric("⚡ Avg/Batch", f"{avg_min}m {avg_s:02d}s" if avg_min > 0 else f"{int(avg_batch)}s")
            else:
                t2.metric("⚡ Avg/Batch", "calculating..." if phase == "signal_extraction" else "—")
            if eta_sec is not None and eta_sec > 0:
                eta_min, eta_s = divmod(int(eta_sec), 60)
                t3.metric("🏁 ETA", f"~{eta_min}m {eta_s:02d}s remaining")
            elif batches_done > 0 and batches_done >= batches_total and phase in ("cross_referencing", "writing_outputs"):
                t3.metric("🏁 ETA", "Wrapping up...")
            else:
                t3.metric("🏁 ETA", "—")

            # Current activity detail
            current_batch = progress.get("current_batch", "")
            if current_batch:
                st.caption(f"Currently processing: **{current_batch}**")

            gaps = progress.get("gaps_found")
            if gaps is not None:
                st.caption(f"Gaps identified: {gaps}")

            time.sleep(3)
            st.rerun()
