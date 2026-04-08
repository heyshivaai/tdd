"""
Quinn Schema Guardian — Upload, version, and manage DRL templates and signal catalogs.

Partners upload new templates/catalogs here. Quinn fingerprints them, detects
changes, runs semantic impact analysis via Claude, and shows migration status
across all deals.

Sections:
  1. Upload — drop in new DRL template (Excel) or signal catalog (JSON)
  2. Version History — see all fingerprinted versions, diffs, migration packets
  3. Deal Impact — which deals need reprocessing after a schema change
  4. Semantic Analysis — LLM-powered understanding of what changed and why it matters
"""
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agents.quinn import run_quinn_check
from tools.quinn_schema_engine import (
    fingerprint_drl_template,
    fingerprint_signal_catalog,
    load_fingerprints,
)
from tools.quinn_version_registry import (
    get_migration_summary,
    get_version_registry,
    list_all_deals as quinn_list_deals,
    get_deal_scan_history,
    validate_registry,
)

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Quinn Schema Guardian | TDD Platform",
    page_icon="🔧",
    layout="wide",
)
st.title("🔧 Quinn — Schema Guardian")
st.caption(
    "Upload new DRL templates and signal catalogs. Quinn detects changes, "
    "analyzes impact, and flags deals that need reprocessing."
)

DATA_DIR = PROJECT_ROOT / "data"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
UPLOADS_DIR = PROJECT_ROOT / "uploads" / "quinn"

# Ensure upload directory exists
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

# ── Styles ───────────────────────────────────────────────────────────────────
st.markdown("""
<style>
.quinn-hero {
    background: linear-gradient(135deg, #1e1b4b 0%, #312e81 60%, #4338ca 100%);
    border-radius: 14px; padding: 28px 32px 24px; margin-bottom: 20px; color: #e0e7ff;
}
.quinn-hero h2 { font-size: 1.3rem; font-weight: 800; margin: 0 0 4px; color: #e0e7ff; }
.quinn-hero .sub { font-size: 0.82rem; color: #a5b4fc; margin: 0; }
.version-badge {
    display: inline-block; background: #e0e7ff; color: #3730a3;
    border-radius: 6px; padding: 2px 10px; font-weight: 700; font-size: 0.82rem;
}
.change-breaking { color: #dc2626; font-weight: 700; }
.change-compatible { color: #16a34a; font-weight: 700; }
</style>
""", unsafe_allow_html=True)


# ── Helper: current versions ─────────────────────────────────────────────────

def _get_current_versions() -> dict:
    """Read current fingerprints to show active versions."""
    fps = load_fingerprints()
    return {
        "drl_version": fps.get("drl_template", {}).get("version", "—"),
        "drl_hash": fps.get("drl_template", {}).get("schema_hash", "—")[:12],
        "catalog_version": fps.get("signal_catalog", {}).get("version", "—"),
        "catalog_hash": fps.get("signal_catalog", {}).get("schema_hash", "—")[:12],
        "last_checked": fps.get("saved_at", "—"),
    }


# ── KPI Row ──────────────────────────────────────────────────────────────────

versions = _get_current_versions()
summary = get_migration_summary()

kpi1, kpi2, kpi3, kpi4 = st.columns(4)
with kpi1:
    st.metric("DRL Template", f"v{versions['drl_version']}", help=f"Hash: {versions['drl_hash']}")
with kpi2:
    st.metric("Signal Catalog", f"v{versions['catalog_version']}", help=f"Hash: {versions['catalog_hash']}")
with kpi3:
    st.metric("Tracked Deals", summary["total_deals"])
with kpi4:
    reprocess_count = summary["by_status"].get("requires_reprocessing", 0)
    blocked_count = summary["by_status"].get("blocked", 0)
    if blocked_count > 0:
        st.metric("Action Required", f"{blocked_count} blocked", delta=f"+{reprocess_count} reprocess", delta_color="inverse")
    elif reprocess_count > 0:
        st.metric("Action Required", f"{reprocess_count} reprocess", delta_color="inverse")
    else:
        st.metric("Action Required", "None ✓")

st.markdown("---")

# ── Tabs ─────────────────────────────────────────────────────────────────────

tab_upload, tab_history, tab_impact, tab_analysis = st.tabs([
    "📤 Upload", "📜 Version History", "🎯 Deal Impact", "🧠 Semantic Analysis"
])

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1: UPLOAD
# ═══════════════════════════════════════════════════════════════════════════════

with tab_upload:
    st.subheader("Upload New Template or Catalog")
    st.markdown(
        "Drop in a new DRL template (`.xlsx`) or signal catalog (`.json`). "
        "Quinn will fingerprint it, compare against the current version, and "
        "generate a migration packet if changes are detected."
    )

    upload_col1, upload_col2 = st.columns(2)

    with upload_col1:
        st.markdown("#### DRL Template (Excel)")
        drl_file = st.file_uploader(
            "Upload DRL template",
            type=["xlsx", "xls"],
            key="drl_upload",
            help="The Deal Response Library template Excel file",
        )

        if drl_file is not None:
            # Save to uploads directory
            drl_dest = UPLOADS_DIR / f"drl_template_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.xlsx"
            drl_dest.write_bytes(drl_file.getbuffer())
            st.success(f"Saved: {drl_dest.name}")
            st.session_state["quinn_drl_path"] = str(drl_dest)

    with upload_col2:
        st.markdown("#### Signal Catalog (JSON)")
        catalog_file = st.file_uploader(
            "Upload signal catalog",
            type=["json"],
            key="catalog_upload",
            help="The signal catalog JSON file",
        )

        if catalog_file is not None:
            catalog_dest = UPLOADS_DIR / f"signal_catalog_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
            catalog_dest.write_bytes(catalog_file.getbuffer())
            st.success(f"Saved: {catalog_dest.name}")
            st.session_state["quinn_catalog_path"] = str(catalog_dest)

    st.markdown("---")

    # Optional: associate with a deal
    deal_id_input = st.text_input(
        "Deal ID (optional)",
        help="If provided, Quinn will register this deal with the new versions.",
        placeholder="e.g., DEAL002",
    )

    # Run Quinn check button
    run_disabled = (
        "quinn_drl_path" not in st.session_state
        and "quinn_catalog_path" not in st.session_state
    )

    if st.button("🔍 Run Quinn Check", type="primary", disabled=run_disabled, use_container_width=True):
        with st.spinner("Quinn is analyzing schemas..."):
            drl_path = st.session_state.get("quinn_drl_path", "")
            catalog_path = st.session_state.get("quinn_catalog_path", "")

            result = run_quinn_check(
                drl_template_path=drl_path,
                catalog_path=catalog_path,
                deal_id=deal_id_input or "",
            )

            st.session_state["quinn_last_result"] = result

        if result["status"] == "success":
            if result["changes_detected"]:
                st.warning("⚠️ Schema changes detected!")

                if result.get("drl_migration_packet"):
                    pkt = result["drl_migration_packet"]
                    st.markdown(
                        f"**DRL Template:** {pkt['from_version']} → {pkt['to_version']} — "
                        f"<span class='change-breaking'>{pkt['breaking_changes_count']} breaking</span>, "
                        f"<span class='change-compatible'>{pkt['compatible_changes_count']} compatible</span>",
                        unsafe_allow_html=True,
                    )

                if result.get("catalog_migration_packet"):
                    pkt = result["catalog_migration_packet"]
                    st.markdown(
                        f"**Catalog:** {pkt['from_version']} → {pkt['to_version']} — "
                        f"<span class='change-breaking'>{pkt['breaking_changes_count']} breaking</span>, "
                        f"<span class='change-compatible'>{pkt['compatible_changes_count']} compatible</span>",
                        unsafe_allow_html=True,
                    )

                # Show affected deals
                all_affected = set(
                    result["affected_deals"].get("drl_template", [])
                    + result["affected_deals"].get("signal_catalog", [])
                )
                if all_affected:
                    st.error(f"Affected deals: {', '.join(sorted(all_affected))}")
            else:
                st.success("✅ No schema changes detected. All deals remain compatible.")

            if result.get("recommendations"):
                st.markdown("**Recommendations:**")
                for rec in result["recommendations"]:
                    st.markdown(f"- {rec}")

            if result.get("errors"):
                st.error("Errors encountered:")
                for err in result["errors"]:
                    st.markdown(f"- {err}")

            # Show raw result in expander
            with st.expander("Raw Quinn Output"):
                st.json(result)
        else:
            st.error(f"Quinn check failed: {result.get('errors', ['Unknown error'])}")

    # Quick check against current files (no upload needed)
    st.markdown("---")
    st.markdown("#### Quick Check — Current Files")
    st.caption("Run Quinn against the current DRL template schema and signal catalog without uploading new files.")

    if st.button("🔄 Check Current Schemas", use_container_width=True):
        with st.spinner("Checking current schemas..."):
            result = run_quinn_check(
                catalog_path=str(DATA_DIR / "signal_catalog.json"),
                deal_id=deal_id_input or "",
            )
            st.session_state["quinn_last_result"] = result

        if result["changes_detected"]:
            st.warning("Changes detected since last check — see Version History for details.")
        else:
            st.success("✅ Current schemas match the last fingerprint. No changes.")


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2: VERSION HISTORY
# ═══════════════════════════════════════════════════════════════════════════════

with tab_history:
    st.subheader("Version History")

    fps = load_fingerprints()

    if not fps:
        st.info("No fingerprints recorded yet. Upload a template or catalog to get started.")
    else:
        hist_col1, hist_col2 = st.columns(2)

        with hist_col1:
            st.markdown("#### DRL Template")
            drl_fp = fps.get("drl_template")
            if drl_fp:
                st.markdown(f"**Version:** {drl_fp.get('version', '—')}")
                st.markdown(f"**Hash:** `{drl_fp.get('schema_hash', '—')[:16]}...`")
                st.markdown(f"**Fingerprinted:** {drl_fp.get('timestamp', '—')}")

                stats = drl_fp.get("template_stats", {})
                st.markdown(
                    f"**Structure:** {stats.get('total_tabs', 0)} tabs, "
                    f"{stats.get('total_columns', 0)} columns, "
                    f"{stats.get('total_fields', 0)} fields"
                )

                with st.expander("Tab Details"):
                    for tab in drl_fp.get("tabs", []):
                        st.markdown(
                            f"- **{tab['tab_name']}**: {tab['field_count']} fields, "
                            f"{tab['expected_row_count']} rows"
                        )
            else:
                st.caption("No DRL template fingerprinted yet.")

        with hist_col2:
            st.markdown("#### Signal Catalog")
            cat_fp = fps.get("signal_catalog")
            if cat_fp:
                st.markdown(f"**Version:** {cat_fp.get('version', '—')}")
                st.markdown(f"**Hash:** `{cat_fp.get('schema_hash', '—')[:16]}...`")
                st.markdown(f"**Fingerprinted:** {cat_fp.get('timestamp', '—')}")

                stats = cat_fp.get("catalog_stats", {})
                st.markdown(
                    f"**Structure:** {stats.get('total_pillars', 0)} pillars, "
                    f"{stats.get('total_signals', 0)} signals"
                )

                with st.expander("Pillar Details"):
                    for pillar in cat_fp.get("pillars", []):
                        st.markdown(
                            f"- **{pillar['pillar_label']}** ({pillar['pillar_id']}): "
                            f"{pillar['signal_count']} signals"
                        )
            else:
                st.caption("No signal catalog fingerprinted yet.")

        st.markdown("---")
        st.markdown(f"**Last saved:** {fps.get('saved_at', '—')}")

    # Show last Quinn check result if available
    if "quinn_last_result" in st.session_state:
        st.markdown("---")
        st.markdown("#### Last Check Result")
        result = st.session_state["quinn_last_result"]

        if result.get("drl_migration_packet"):
            with st.expander("DRL Migration Packet"):
                pkt = result["drl_migration_packet"]
                for change in pkt.get("changes", []):
                    impact_class = "change-breaking" if change["impact"] == "BREAKING" else "change-compatible"
                    st.markdown(
                        f"- <span class='{impact_class}'>[{change['impact']}]</span> "
                        f"**{change['type']}**: {change['reason']}",
                        unsafe_allow_html=True,
                    )
                    if change.get("mitigation"):
                        st.caption(f"  Mitigation: {change['mitigation']}")

        if result.get("catalog_migration_packet"):
            with st.expander("Catalog Migration Packet"):
                pkt = result["catalog_migration_packet"]
                for change in pkt.get("changes", []):
                    impact_class = "change-breaking" if change["impact"] == "BREAKING" else "change-compatible"
                    st.markdown(
                        f"- <span class='{impact_class}'>[{change['impact']}]</span> "
                        f"**{change['type']}**: {change['reason']}",
                        unsafe_allow_html=True,
                    )


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3: DEAL IMPACT
# ═══════════════════════════════════════════════════════════════════════════════

with tab_impact:
    st.subheader("Deal Impact Dashboard")

    summary = get_migration_summary()

    if summary["total_deals"] == 0:
        st.info("No deals registered with Quinn yet. Deals are registered automatically during VDR scans.")
    else:
        # Status breakdown
        status_col1, status_col2, status_col3, status_col4 = st.columns(4)

        with status_col1:
            st.metric("Compatible", summary["by_status"].get("compatible", 0))
        with status_col2:
            st.metric("Needs Reprocessing", summary["by_status"].get("requires_reprocessing", 0))
        with status_col3:
            st.metric("Blocked", summary["by_status"].get("blocked", 0))
        with status_col4:
            st.metric("Unknown", summary["by_status"].get("unknown", 0))

        st.markdown("---")

        # Deals table
        st.markdown("#### All Tracked Deals")
        deals = quinn_list_deals()

        for deal_id in deals:
            reg = get_version_registry(deal_id)
            status = reg.get("migration_status", "unknown")

            status_icon = {
                "compatible": "✅",
                "requires_reprocessing": "⚠️",
                "blocked": "🚫",
                "unknown": "❓",
            }.get(status, "❓")

            with st.expander(f"{status_icon} {deal_id} — {status}"):
                info_col1, info_col2 = st.columns(2)
                with info_col1:
                    st.markdown(f"**Template Version:** {reg.get('template_version', '—')}")
                    st.markdown(f"**Catalog Version:** {reg.get('catalog_version', '—')}")
                with info_col2:
                    st.markdown(f"**First Registered:** {reg.get('first_registered', '—')}")
                    st.markdown(f"**Migration Status:** {status}")

                # Scan history
                scans = get_deal_scan_history(deal_id)
                if scans:
                    st.markdown("**Scan History:**")
                    for scan in scans[-5:]:  # Show last 5 scans
                        st.caption(
                            f"  {scan.get('scan_id', '—')} — "
                            f"template v{scan.get('template_version', '?')}, "
                            f"catalog v{scan.get('catalog_version', '?')} — "
                            f"{scan.get('timestamp', '—')}"
                        )

        # Registry health check
        st.markdown("---")
        if st.button("🩺 Validate Registry"):
            is_valid, errors = validate_registry()
            if is_valid:
                st.success("✅ Registry is valid.")
            else:
                st.error(f"Registry has {len(errors)} error(s):")
                for err in errors:
                    st.markdown(f"- {err}")


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 4: SEMANTIC ANALYSIS
# ═══════════════════════════════════════════════════════════════════════════════

with tab_analysis:
    st.subheader("🧠 Semantic Impact Analysis")
    st.markdown(
        "Claude analyzes schema changes beyond structural diffs — understanding "
        "what the changes *mean* for diligence quality, signal coverage, and deal outcomes."
    )

    # Check if we have a recent Quinn result with changes
    last_result = st.session_state.get("quinn_last_result")

    if not last_result or not last_result.get("changes_detected"):
        st.info(
            "No schema changes to analyze. Upload a new template or catalog in the "
            "**Upload** tab, then come back here for semantic analysis."
        )

        # Allow manual trigger on current state
        if st.button("🧠 Analyze Current Schema State", use_container_width=True):
            st.session_state["quinn_run_semantic"] = True
            st.rerun()
    else:
        st.markdown("---")
        st.markdown("#### Changes Detected — Ready for Analysis")

        changes = []
        if last_result.get("drl_migration_packet"):
            changes.extend(last_result["drl_migration_packet"].get("changes", []))
        if last_result.get("catalog_migration_packet"):
            changes.extend(last_result["catalog_migration_packet"].get("changes", []))

        if changes:
            st.markdown(f"**{len(changes)} structural changes** detected. Click below for Claude's semantic analysis.")

            for c in changes[:10]:
                impact_color = "🔴" if c["impact"] == "BREAKING" else "🟢"
                st.markdown(f"- {impact_color} **{c['type']}** — {c['reason']}")

    if st.button("🧠 Run Semantic Analysis", type="primary", use_container_width=True, key="run_semantic"):
        with st.spinner("Claude is analyzing the impact of schema changes..."):
            try:
                from tools.quinn_semantic_analyzer import analyze_schema_changes

                fps = load_fingerprints()
                analysis = analyze_schema_changes(
                    fingerprints=fps,
                    migration_packets={
                        "drl": (last_result or {}).get("drl_migration_packet"),
                        "catalog": (last_result or {}).get("catalog_migration_packet"),
                    },
                    migration_summary=get_migration_summary(),
                )

                st.session_state["quinn_semantic_result"] = analysis

            except ImportError:
                st.error("Semantic analyzer not available. Ensure tools/quinn_semantic_analyzer.py exists.")
            except Exception as exc:
                st.error(f"Analysis failed: {exc}")

    # Display semantic analysis result
    if "quinn_semantic_result" in st.session_state:
        analysis = st.session_state["quinn_semantic_result"]

        st.markdown("---")

        if analysis.get("executive_summary"):
            st.markdown("#### Executive Summary")
            st.markdown(analysis["executive_summary"])

        if analysis.get("signal_coverage_impact"):
            st.markdown("#### Signal Coverage Impact")
            st.markdown(analysis["signal_coverage_impact"])

        if analysis.get("deal_quality_assessment"):
            st.markdown("#### Deal Quality Assessment")
            st.markdown(analysis["deal_quality_assessment"])

        if analysis.get("recommended_actions"):
            st.markdown("#### Recommended Actions")
            for action in analysis["recommended_actions"]:
                priority = action.get("priority", "medium")
                icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(priority, "⚪")
                st.markdown(f"- {icon} **{action.get('action', '')}** — {action.get('rationale', '')}")

        if analysis.get("reprocessing_guidance"):
            st.markdown("#### Reprocessing Guidance")
            st.markdown(analysis["reprocessing_guidance"])

        with st.expander("Raw Analysis"):
            st.json(analysis)
