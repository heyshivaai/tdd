"""
Quinn Semantic Analyzer — LLM-powered impact analysis for schema changes.

Goes beyond structural diffs to understand what template/catalog changes
*mean* for diligence quality: signal coverage gaps, deal outcome risk,
practitioner workflow impact, and recommended actions.

Why: Structural diffs tell you *what* changed; semantic analysis tells you
*why it matters*. A removed signal might be trivial or deal-breaking depending
on its conviction weight and how many active deals rely on it.

Usage:
    from tools.quinn_semantic_analyzer import analyze_schema_changes

    result = analyze_schema_changes(
        fingerprints=current_fps,
        migration_packets={"drl": drl_packet, "catalog": catalog_packet},
        migration_summary=summary,
    )
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
MAX_TOKENS = 8192


def analyze_schema_changes(
    fingerprints: dict,
    migration_packets: dict,
    migration_summary: dict,
    deal_context: Optional[dict] = None,
) -> dict:
    """
    Run Claude-powered semantic analysis on schema changes.

    Analyzes the meaning and impact of structural changes detected by the
    Quinn schema engine, producing actionable guidance for practitioners.

    Args:
        fingerprints: Current schema fingerprints (from load_fingerprints())
        migration_packets: {"drl": packet_or_None, "catalog": packet_or_None}
        migration_summary: Output from get_migration_summary()
        deal_context: Optional dict with active deal info for contextual analysis

    Returns:
        {
            "timestamp": ISO-8601,
            "executive_summary": str (2-3 paragraph overview),
            "signal_coverage_impact": str (which signals gained/lost, gaps created),
            "deal_quality_assessment": str (how this affects in-flight deal quality),
            "recommended_actions": [
                {"action": str, "priority": "high"|"medium"|"low", "rationale": str}
            ],
            "reprocessing_guidance": str (which deals, what order, what to watch),
            "risk_assessment": str (worst case if changes are ignored),
            "raw_changes": list (structural changes passed to Claude),
        }
    """
    # Collect all structural changes
    changes = []
    drl_packet = migration_packets.get("drl")
    catalog_packet = migration_packets.get("catalog")

    if drl_packet and isinstance(drl_packet, dict):
        changes.extend(drl_packet.get("changes", []))
    if catalog_packet and isinstance(catalog_packet, dict):
        changes.extend(catalog_packet.get("changes", []))

    # Load signal catalog for context on signal importance
    catalog_context = _load_catalog_context()

    # Build the prompt
    prompt = _build_analysis_prompt(
        fingerprints=fingerprints,
        changes=changes,
        drl_packet=drl_packet,
        catalog_packet=catalog_packet,
        migration_summary=migration_summary,
        catalog_context=catalog_context,
        deal_context=deal_context,
    )

    # Call Claude
    try:
        import anthropic
        from dotenv import load_dotenv

        load_dotenv()

        client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )

        raw_text = response.content[0].text
        result = _parse_analysis_response(raw_text, changes)
        result["timestamp"] = datetime.now(timezone.utc).isoformat()
        result["raw_changes"] = changes

        # Save result
        _save_analysis(result)

        return result

    except Exception as exc:
        logger.error("Semantic analysis failed: %s", exc)
        return _fallback_analysis(changes, migration_summary)


def analyze_current_state() -> dict:
    """
    Analyze the current schema state without requiring detected changes.

    Useful for generating a baseline assessment of signal coverage and
    template completeness.

    Returns:
        Same shape as analyze_schema_changes().
    """
    catalog_context = _load_catalog_context()
    fingerprints = {}

    try:
        from tools.quinn_schema_engine import load_fingerprints
        fingerprints = load_fingerprints()
    except Exception:
        pass

    prompt = _build_baseline_prompt(fingerprints, catalog_context)

    try:
        import anthropic
        from dotenv import load_dotenv

        load_dotenv()

        client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )

        raw_text = response.content[0].text
        result = _parse_analysis_response(raw_text, [])
        result["timestamp"] = datetime.now(timezone.utc).isoformat()
        result["analysis_type"] = "baseline"

        _save_analysis(result)
        return result

    except Exception as exc:
        logger.error("Baseline analysis failed: %s", exc)
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "executive_summary": f"Baseline analysis could not be completed: {exc}",
            "signal_coverage_impact": "",
            "deal_quality_assessment": "",
            "recommended_actions": [],
            "reprocessing_guidance": "",
            "risk_assessment": "",
            "raw_changes": [],
        }


# ── Prompt Construction ──────────────────────────────────────────────────────

def _build_analysis_prompt(
    fingerprints: dict,
    changes: list[dict],
    drl_packet: Optional[dict],
    catalog_packet: Optional[dict],
    migration_summary: dict,
    catalog_context: dict,
    deal_context: Optional[dict],
) -> str:
    """Build the semantic analysis prompt for Claude."""

    changes_text = json.dumps(changes, indent=2) if changes else "No structural changes detected."
    summary_text = json.dumps(migration_summary, indent=2)
    catalog_text = json.dumps(catalog_context, indent=2) if catalog_context else "Catalog context unavailable."
    deal_text = json.dumps(deal_context, indent=2) if deal_context else "No specific deal context provided."

    drl_summary = ""
    if drl_packet:
        drl_summary = (
            f"DRL Template: {drl_packet.get('from_version', '?')} → {drl_packet.get('to_version', '?')}, "
            f"{drl_packet.get('breaking_changes_count', 0)} breaking, "
            f"{drl_packet.get('compatible_changes_count', 0)} compatible"
        )

    catalog_summary = ""
    if catalog_packet:
        catalog_summary = (
            f"Signal Catalog: {catalog_packet.get('from_version', '?')} → {catalog_packet.get('to_version', '?')}, "
            f"{catalog_packet.get('breaking_changes_count', 0)} breaking, "
            f"{catalog_packet.get('compatible_changes_count', 0)} compatible"
        )

    # Current fingerprint state
    fp_state = ""
    if fingerprints:
        drl_fp = fingerprints.get("drl_template", {})
        cat_fp = fingerprints.get("signal_catalog", {})
        fp_state = (
            f"Current DRL: v{drl_fp.get('version', '?')}, "
            f"{drl_fp.get('template_stats', {}).get('total_tabs', '?')} tabs, "
            f"{drl_fp.get('template_stats', {}).get('total_fields', '?')} fields\n"
            f"Current Catalog: v{cat_fp.get('version', '?')}, "
            f"{cat_fp.get('catalog_stats', {}).get('total_pillars', '?')} pillars, "
            f"{cat_fp.get('catalog_stats', {}).get('total_signals', '?')} signals"
        )

    return f"""You are Quinn, the Schema Guardian for a PE technology due diligence platform.
Your role is to analyze schema changes to the DRL (Deal Response Library) template
and signal catalog, and provide semantic impact analysis for practitioners.

## Current State
{fp_state}

## Schema Changes Detected
{drl_summary}
{catalog_summary}

### Structural Changes
{changes_text}

## Migration Summary (All Deals)
{summary_text}

## Signal Catalog Context (for importance assessment)
{catalog_text}

## Active Deal Context
{deal_text}

## Your Task

Analyze these schema changes and produce a structured assessment. Think like a
senior PE tech diligence practitioner — what do these changes mean for deal quality?

Respond in valid JSON with this exact shape:
{{
    "executive_summary": "2-3 paragraphs: what changed, why it matters, what to do",
    "signal_coverage_impact": "Which signals were added/removed/modified? What coverage gaps does this create or close? Reference specific signal IDs.",
    "deal_quality_assessment": "How do these changes affect the quality of in-flight diligence? Are any deals at risk of incomplete analysis?",
    "recommended_actions": [
        {{
            "action": "what to do",
            "priority": "high|medium|low",
            "rationale": "why this matters"
        }}
    ],
    "reprocessing_guidance": "Which deals should be reprocessed? In what order? What should practitioners watch for?",
    "risk_assessment": "What happens if these changes are ignored? Worst-case scenario for deal quality."
}}

Be specific. Reference signal IDs, pillar names, and deal IDs where applicable.
If no changes were detected, provide a baseline assessment of current schema health."""


def _build_baseline_prompt(fingerprints: dict, catalog_context: dict) -> str:
    """Build a prompt for baseline schema health assessment."""

    fp_state = ""
    if fingerprints:
        drl_fp = fingerprints.get("drl_template", {})
        cat_fp = fingerprints.get("signal_catalog", {})
        fp_state = json.dumps({
            "drl_template": {
                "version": drl_fp.get("version"),
                "stats": drl_fp.get("template_stats"),
                "tabs": [t.get("tab_name") for t in drl_fp.get("tabs", [])],
            },
            "signal_catalog": {
                "version": cat_fp.get("version"),
                "stats": cat_fp.get("catalog_stats"),
                "pillars": [
                    {"id": p.get("pillar_id"), "label": p.get("pillar_label"), "count": p.get("signal_count")}
                    for p in cat_fp.get("pillars", [])
                ],
            },
        }, indent=2)

    catalog_text = json.dumps(catalog_context, indent=2) if catalog_context else "Unavailable."

    return f"""You are Quinn, the Schema Guardian for a PE technology due diligence platform.
Provide a baseline health assessment of the current schema configuration.

## Current Fingerprints
{fp_state}

## Signal Catalog
{catalog_text}

## Your Task

Assess the current schema health. Are there coverage gaps? Is the signal catalog
well-structured for PE tech diligence? Are there obvious missing pillars or signals?

Respond in valid JSON:
{{
    "executive_summary": "Current schema health overview",
    "signal_coverage_impact": "Assessment of signal coverage completeness",
    "deal_quality_assessment": "How well does this schema support quality diligence?",
    "recommended_actions": [
        {{"action": "...", "priority": "high|medium|low", "rationale": "..."}}
    ],
    "reprocessing_guidance": "N/A for baseline assessment",
    "risk_assessment": "Known gaps or risks in current schema configuration"
}}"""


# ── Response Parsing ─────────────────────────────────────────────────────────

def _parse_analysis_response(raw_text: str, changes: list[dict]) -> dict:
    """Parse Claude's response into the expected structure."""

    # Try to extract JSON from the response
    try:
        # Look for JSON block
        if "```json" in raw_text:
            json_start = raw_text.index("```json") + 7
            json_end = raw_text.index("```", json_start)
            parsed = json.loads(raw_text[json_start:json_end].strip())
        elif "{" in raw_text:
            # Find the outermost JSON object
            brace_start = raw_text.index("{")
            brace_count = 0
            brace_end = brace_start
            for i, ch in enumerate(raw_text[brace_start:], start=brace_start):
                if ch == "{":
                    brace_count += 1
                elif ch == "}":
                    brace_count -= 1
                    if brace_count == 0:
                        brace_end = i + 1
                        break
            parsed = json.loads(raw_text[brace_start:brace_end])
        else:
            raise ValueError("No JSON found in response")

        # Ensure all expected keys exist
        result = {
            "executive_summary": parsed.get("executive_summary", ""),
            "signal_coverage_impact": parsed.get("signal_coverage_impact", ""),
            "deal_quality_assessment": parsed.get("deal_quality_assessment", ""),
            "recommended_actions": parsed.get("recommended_actions", []),
            "reprocessing_guidance": parsed.get("reprocessing_guidance", ""),
            "risk_assessment": parsed.get("risk_assessment", ""),
        }

        # Validate recommended_actions shape
        validated_actions = []
        for action in result["recommended_actions"]:
            if isinstance(action, dict):
                validated_actions.append({
                    "action": str(action.get("action", "")),
                    "priority": str(action.get("priority", "medium")),
                    "rationale": str(action.get("rationale", "")),
                })
            elif isinstance(action, str):
                validated_actions.append({
                    "action": action,
                    "priority": "medium",
                    "rationale": "",
                })
        result["recommended_actions"] = validated_actions

        return result

    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("Failed to parse semantic analysis JSON: %s", exc)
        return {
            "executive_summary": raw_text[:2000],
            "signal_coverage_impact": "",
            "deal_quality_assessment": "",
            "recommended_actions": [],
            "reprocessing_guidance": "",
            "risk_assessment": "",
            "_parse_error": str(exc),
        }


# ── Helpers ──────────────────────────────────────────────────────────────────

def _load_catalog_context() -> dict:
    """Load signal catalog summary for context in analysis."""
    catalog_path = DATA_DIR / "signal_catalog.json"
    if not catalog_path.exists():
        return {}

    try:
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        # Summarize for prompt (don't send full catalog)
        signals_summary = []
        for sig in catalog.get("signals", []):
            signals_summary.append({
                "signal_id": sig.get("signal_id"),
                "name": sig.get("name"),
                "pillar": sig.get("pillar_name"),
                "conviction_weight": sig.get("conviction_weight"),
                "temporal_orientation": sig.get("temporal_orientation"),
            })
        return {
            "version": catalog.get("version"),
            "total_signals": catalog.get("total_signals"),
            "total_pillars": catalog.get("total_pillars"),
            "signals": signals_summary,
        }
    except Exception as exc:
        logger.warning("Failed to load catalog context: %s", exc)
        return {}


def _save_analysis(result: dict) -> None:
    """Save semantic analysis result to outputs."""
    dest = OUTPUTS_DIR / "_quinn_semantic_analysis.json"
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Semantic analysis saved to %s", dest)


def _fallback_analysis(changes: list[dict], migration_summary: dict) -> dict:
    """Generate a basic analysis without LLM when Claude is unavailable."""
    breaking = [c for c in changes if c.get("impact") == "BREAKING"]
    compatible = [c for c in changes if c.get("impact") == "COMPATIBLE"]

    summary_parts = []
    if breaking:
        summary_parts.append(
            f"{len(breaking)} breaking change(s) detected: "
            + "; ".join(c.get("reason", "unknown") for c in breaking[:5])
        )
    if compatible:
        summary_parts.append(
            f"{len(compatible)} compatible change(s) detected."
        )
    if not changes:
        summary_parts.append("No structural changes detected in the current schema.")

    reprocess_deals = migration_summary.get("deals_by_status", {}).get("requires_reprocessing", [])

    actions = []
    if breaking:
        actions.append({
            "action": "Review breaking changes and assess deal impact",
            "priority": "high",
            "rationale": f"{len(breaking)} breaking changes could affect signal extraction quality",
        })
    if reprocess_deals:
        actions.append({
            "action": f"Reprocess {len(reprocess_deals)} affected deals",
            "priority": "high",
            "rationale": "Deals processed with old schema may have incomplete signals",
        })

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "executive_summary": " ".join(summary_parts) + " (Fallback analysis — Claude unavailable.)",
        "signal_coverage_impact": f"Breaking changes: {len(breaking)}, Compatible: {len(compatible)}",
        "deal_quality_assessment": f"{len(reprocess_deals)} deals may need reprocessing.",
        "recommended_actions": actions,
        "reprocessing_guidance": (
            f"Reprocess these deals: {', '.join(reprocess_deals)}" if reprocess_deals
            else "No deals require reprocessing."
        ),
        "risk_assessment": (
            "Breaking changes may cause signal extraction failures on next scan."
            if breaking else "No immediate risk."
        ),
        "raw_changes": changes,
        "_fallback": True,
    }
