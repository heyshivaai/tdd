"""
Recalibration Engine: analyzes feedback patterns across deals to produce
cumulative learning signals that improve future scans.

This is the long-term memory of the feedback loop. While feedback_importer.py
handles a single deal's feedback, the recalibration engine looks across ALL
deals to find systemic patterns:

  - Which pillars consistently generate noise?
  - Does the system over-rate or under-rate specific signal types?
  - Are HIGH confidence signals actually more accurate than MEDIUM?
  - Which agents are reliable vs. which need better data sources?

Outputs:
  - outputs/_recalibration_state.json — cumulative accuracy state across deals
  - Formatted recalibration insights for dashboard display

Why: Single-deal feedback is useful but noisy. Cross-deal patterns are where
the real calibration value lives. "This signal type was NOISE in 4 of 6 deals"
is a much stronger signal than "this was NOISE in one deal."
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).parent.parent / "outputs"
STATE_PATH = OUTPUT_DIR / "_recalibration_state.json"


def _load_state() -> dict:
    """Load or initialize the cumulative recalibration state."""
    if STATE_PATH.exists():
        with open(STATE_PATH) as f:
            return json.load(f)
    return {
        "version": 1,
        "last_updated": None,
        "deals_analyzed": [],
        "cumulative_gate1": {
            "total_reviewed": 0,
            "confirmed": 0,
            "noise": 0,
            "uncertain": 0,
            "over_rated": 0,
            "under_rated": 0,
            "pillar_stats": {},
            "confidence_stats": {},
        },
        "cumulative_gate2": {
            "total_reviewed": 0,
            "confirmed": 0,
            "noise": 0,
            "uncertain": 0,
            "over_rated": 0,
            "under_rated": 0,
            "agent_stats": {},
            "domain_stats": {},
        },
        "learning_signals": [],
        "noise_patterns": [],
        "drift_patterns": [],
    }


def _save_state(state: dict) -> None:
    """Write the cumulative recalibration state to disk."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    state["last_updated"] = datetime.now(timezone.utc).isoformat()
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, default=str)
    logger.info("Recalibration state saved to %s", STATE_PATH)


def ingest_deal_feedback(deal_id: str, company_name: str) -> dict:
    """
    Ingest a deal's completed feedback into the cumulative recalibration state.

    Reads feedback_gate{1,2}_completed.json from the deal's output folder
    and merges accuracy metrics into the cross-deal aggregate.

    Args:
        deal_id: Deal identifier.
        company_name: Company output folder name.

    Returns:
        Updated recalibration state dict.
    """
    state = _load_state()
    deal_dir = OUTPUT_DIR / company_name

    # Skip if already ingested
    if deal_id in state["deals_analyzed"]:
        logger.info("Deal %s already in recalibration state — updating", deal_id)
        # Remove old data to re-ingest (idempotent)
        # We don't track per-deal deltas, so just re-aggregate below

    state["deals_analyzed"] = list(set(state["deals_analyzed"]) | {deal_id})

    # Gate 1 feedback
    gate1_path = deal_dir / "feedback_gate1_completed.json"
    if gate1_path.exists():
        with open(gate1_path) as f:
            gate1 = json.load(f)
        _merge_gate1(state, gate1, deal_id)

    # Gate 2 feedback
    gate2_path = deal_dir / "feedback_gate2_completed.json"
    if gate2_path.exists():
        with open(gate2_path) as f:
            gate2 = json.load(f)
        _merge_gate2(state, gate2, deal_id)

    # Regenerate cross-deal learning signals
    state["learning_signals"] = _generate_cross_deal_signals(state)
    state["noise_patterns"] = _identify_noise_patterns(state)
    state["drift_patterns"] = _identify_drift_patterns(state)

    _save_state(state)
    return state


def _merge_gate1(state: dict, feedback: dict, deal_id: str) -> None:
    """Merge a single deal's Gate 1 feedback into cumulative stats."""
    cum = state["cumulative_gate1"]

    for rating in feedback.get("signal_ratings", []):
        verdict = rating.get("verdict", "")
        if not verdict:
            continue

        cum["total_reviewed"] += 1
        if verdict == "CONFIRMED":
            cum["confirmed"] += 1
        elif verdict == "NOISE":
            cum["noise"] += 1
        elif verdict == "UNCERTAIN":
            cum["uncertain"] += 1

        # Rating drift
        corrected = rating.get("corrected_rating")
        original = rating.get("original_rating", "")
        if corrected and corrected != original:
            severity_order = {"RED": 3, "YELLOW": 2, "GREEN": 1}
            if severity_order.get(original.upper(), 0) > severity_order.get(corrected.upper(), 0):
                cum["over_rated"] += 1
            else:
                cum["under_rated"] += 1

        # Per-pillar
        pillar = rating.get("pillar", "unknown")
        if pillar not in cum["pillar_stats"]:
            cum["pillar_stats"][pillar] = {
                "confirmed": 0, "noise": 0, "uncertain": 0, "total": 0,
                "deals": [],
            }
        ps = cum["pillar_stats"][pillar]
        ps["total"] += 1
        ps[verdict.lower()] = ps.get(verdict.lower(), 0) + 1
        if deal_id not in ps["deals"]:
            ps["deals"].append(deal_id)

        # Per-confidence
        conf = (rating.get("original_confidence") or "unknown").upper()
        if conf not in cum["confidence_stats"]:
            cum["confidence_stats"][conf] = {
                "confirmed": 0, "noise": 0, "uncertain": 0, "total": 0,
            }
        cs = cum["confidence_stats"][conf]
        cs["total"] += 1
        cs[verdict.lower()] = cs.get(verdict.lower(), 0) + 1


def _merge_gate2(state: dict, feedback: dict, deal_id: str) -> None:
    """Merge a single deal's Gate 2 feedback into cumulative stats."""
    cum = state["cumulative_gate2"]

    for rating in feedback.get("finding_ratings", []):
        verdict = rating.get("verdict", "")
        if not verdict:
            continue

        cum["total_reviewed"] += 1
        if verdict == "CONFIRMED":
            cum["confirmed"] += 1
        elif verdict == "NOISE":
            cum["noise"] += 1
        elif verdict == "UNCERTAIN":
            cum["uncertain"] += 1

        # Severity drift
        adjusted = rating.get("adjusted_severity")
        original = rating.get("original_severity", "")
        if adjusted and adjusted != original:
            severity_order = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}
            if severity_order.get(original.upper(), 0) > severity_order.get(adjusted.upper(), 0):
                cum["over_rated"] += 1
            else:
                cum["under_rated"] += 1

        # Per-agent
        agent = rating.get("agent", "unknown")
        if agent not in cum["agent_stats"]:
            cum["agent_stats"][agent] = {
                "confirmed": 0, "noise": 0, "uncertain": 0, "total": 0,
                "deals": [], "confidence_levels": [],
            }
        ag = cum["agent_stats"][agent]
        ag["total"] += 1
        ag[verdict.lower()] = ag.get(verdict.lower(), 0) + 1
        if deal_id not in ag["deals"]:
            ag["deals"].append(deal_id)
        agent_conf = rating.get("agent_confidence", "")
        if agent_conf and agent_conf not in ag["confidence_levels"]:
            ag["confidence_levels"].append(agent_conf)

        # Per-domain
        domain = rating.get("domain", "unknown")
        if domain not in cum["domain_stats"]:
            cum["domain_stats"][domain] = {
                "confirmed": 0, "noise": 0, "uncertain": 0, "total": 0,
            }
        ds = cum["domain_stats"][domain]
        ds["total"] += 1
        ds[verdict.lower()] = ds.get(verdict.lower(), 0) + 1


def _generate_cross_deal_signals(state: dict) -> list[str]:
    """Generate learning signals from cross-deal aggregated feedback."""
    signals = []
    num_deals = len(state["deals_analyzed"])

    # Gate 1 cumulative
    g1 = state["cumulative_gate1"]
    if g1["total_reviewed"] > 0:
        acc = round(g1["confirmed"] / g1["total_reviewed"] * 100, 1)
        noise = round(g1["noise"] / g1["total_reviewed"] * 100, 1)
        signals.append(
            f"Signal extraction across {num_deals} deal(s): {acc}% accuracy, {noise}% noise rate "
            f"({g1['total_reviewed']} signals reviewed)"
        )
        if g1["over_rated"] > g1["under_rated"] * 2:
            signals.append(
                f"Systematic over-rating: {g1['over_rated']} signals downgraded vs "
                f"{g1['under_rated']} upgraded across all deals"
            )
        if g1["under_rated"] > g1["over_rated"] * 2:
            signals.append(
                f"Systematic under-rating: {g1['under_rated']} signals upgraded vs "
                f"{g1['over_rated']} downgraded — may be missing critical signals"
            )

    # Gate 2 cumulative
    g2 = state["cumulative_gate2"]
    if g2["total_reviewed"] > 0:
        acc = round(g2["confirmed"] / g2["total_reviewed"] * 100, 1)
        signals.append(
            f"Agent findings across {num_deals} deal(s): {acc}% accuracy "
            f"({g2['total_reviewed']} findings reviewed)"
        )

    # Confidence calibration check
    conf_stats = g1.get("confidence_stats", {})
    if "HIGH" in conf_stats and "MEDIUM" in conf_stats:
        h = conf_stats["HIGH"]
        m = conf_stats["MEDIUM"]
        if h["total"] >= 5 and m["total"] >= 3:
            h_acc = round(h["confirmed"] / h["total"] * 100, 1)
            m_acc = round(m["confirmed"] / m["total"] * 100, 1)
            if m_acc > h_acc:
                signals.append(
                    f"CONFIDENCE INVERSION: MEDIUM ({m_acc}%) more accurate than HIGH ({h_acc}%) "
                    f"across {num_deals} deal(s) — confidence scoring needs recalibration"
                )
            elif h_acc - m_acc > 20:
                signals.append(
                    f"Confidence well-calibrated: HIGH ({h_acc}%) significantly more accurate "
                    f"than MEDIUM ({m_acc}%)"
                )

    return signals


def _identify_noise_patterns(state: dict) -> list[dict]:
    """Identify pillars/agents that consistently generate false positives."""
    patterns = []

    # Gate 1: pillar noise
    for pillar, stats in state["cumulative_gate1"].get("pillar_stats", {}).items():
        if stats["total"] >= 3:
            noise_pct = round(stats.get("noise", 0) / stats["total"] * 100, 1)
            if noise_pct > 25:
                patterns.append({
                    "type": "pillar_noise",
                    "entity": pillar,
                    "noise_pct": noise_pct,
                    "sample_size": stats["total"],
                    "across_deals": len(stats.get("deals", [])),
                    "recommendation": f"Tighten extraction thresholds for '{pillar}' — "
                                      f"{noise_pct}% noise across {len(stats.get('deals', []))} deal(s)",
                })

    # Gate 2: agent noise
    for agent, stats in state["cumulative_gate2"].get("agent_stats", {}).items():
        if stats["total"] >= 3:
            noise_pct = round(stats.get("noise", 0) / stats["total"] * 100, 1)
            if noise_pct > 30:
                conf_levels = stats.get("confidence_levels", [])
                patterns.append({
                    "type": "agent_noise",
                    "entity": agent,
                    "noise_pct": noise_pct,
                    "sample_size": stats["total"],
                    "across_deals": len(stats.get("deals", [])),
                    "typical_confidence": conf_levels,
                    "recommendation": f"Agent '{agent}' generates {noise_pct}% noise "
                                      f"(typical confidence: {', '.join(conf_levels)}) — "
                                      f"consider gating output when data sources are unavailable",
                })

    return patterns


def _identify_drift_patterns(state: dict) -> list[dict]:
    """Identify systematic rating drift patterns."""
    patterns = []

    g1 = state["cumulative_gate1"]
    if g1["total_reviewed"] >= 5:
        total_drifts = g1["over_rated"] + g1["under_rated"]
        if total_drifts > 0:
            drift_pct = round(total_drifts / g1["total_reviewed"] * 100, 1)
            direction = "over" if g1["over_rated"] > g1["under_rated"] else "under"
            patterns.append({
                "type": "signal_rating_drift",
                "drift_pct": drift_pct,
                "direction": direction,
                "over_rated": g1["over_rated"],
                "under_rated": g1["under_rated"],
                "recommendation": (
                    f"Signal ratings drift {direction} in {drift_pct}% of cases — "
                    f"adjust rating calibration in extraction prompt"
                ),
            })

    g2 = state["cumulative_gate2"]
    if g2["total_reviewed"] >= 5:
        total_drifts = g2["over_rated"] + g2["under_rated"]
        if total_drifts > 0:
            drift_pct = round(total_drifts / g2["total_reviewed"] * 100, 1)
            direction = "over" if g2["over_rated"] > g2["under_rated"] else "under"
            patterns.append({
                "type": "finding_severity_drift",
                "drift_pct": drift_pct,
                "direction": direction,
                "over_rated": g2["over_rated"],
                "under_rated": g2["under_rated"],
                "recommendation": (
                    f"Finding severity drifts {direction} in {drift_pct}% of cases — "
                    f"adjust domain analysis severity thresholds"
                ),
            })

    return patterns


def get_recalibration_summary() -> dict:
    """
    Return the current recalibration state summary for dashboard display.

    Designed to be called by the UI/API layer to show practitioners
    how the system is learning over time.
    """
    state = _load_state()

    g1 = state["cumulative_gate1"]
    g2 = state["cumulative_gate2"]

    g1_accuracy = (
        round(g1["confirmed"] / g1["total_reviewed"] * 100, 1)
        if g1["total_reviewed"] > 0 else None
    )
    g2_accuracy = (
        round(g2["confirmed"] / g2["total_reviewed"] * 100, 1)
        if g2["total_reviewed"] > 0 else None
    )

    return {
        "deals_analyzed": len(state["deals_analyzed"]),
        "last_updated": state.get("last_updated"),
        "signal_accuracy_pct": g1_accuracy,
        "signal_reviews_total": g1["total_reviewed"],
        "finding_accuracy_pct": g2_accuracy,
        "finding_reviews_total": g2["total_reviewed"],
        "learning_signals": state.get("learning_signals", []),
        "noise_patterns": state.get("noise_patterns", []),
        "drift_patterns": state.get("drift_patterns", []),
    }
