"""
How It Works — visual workflow guide explaining the VDR Triage platform
end-to-end process for practitioners and stakeholders.
"""
import streamlit as st

st.set_page_config(page_title="How It Works · VDR Triage", page_icon="🗺️", layout="wide")

# ── Styles ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* Hero */
.wf-hero {
    background: linear-gradient(135deg, #0f172a 0%, #1e293b 60%, #334155 100%);
    border-radius: 14px; padding: 32px 36px 28px; margin-bottom: 28px; color: #f8fafc;
}
.wf-hero h1 { font-size: 1.6rem; font-weight: 800; margin: 0 0 4px; color: #f8fafc; }
.wf-hero .sub { font-size: 0.88rem; color: #94a3b8; margin: 0; line-height: 1.5; }

/* Phase card */
.phase-card {
    background: #ffffff;
    border: 2px solid #e2e8f0;
    border-radius: 14px;
    padding: 24px 28px 20px;
    margin-bottom: 8px;
    position: relative;
    transition: border-color .15s, box-shadow .15s;
}
.phase-card:hover { border-color: #94a3b8; box-shadow: 0 4px 16px rgba(0,0,0,0.06); }
.phase-card .phase-num {
    display: inline-block;
    background: #1e3a5f;
    color: #ffffff;
    font-weight: 800;
    font-size: 0.75rem;
    padding: 3px 10px;
    border-radius: 20px;
    letter-spacing: 0.06em;
    margin-bottom: 8px;
}
.phase-card .phase-title {
    font-size: 1.15rem;
    font-weight: 700;
    color: #0f172a;
    margin: 0 0 8px;
}
.phase-card .phase-desc {
    font-size: 0.88rem;
    color: #475569;
    line-height: 1.6;
    margin: 0 0 12px;
}

/* Step row */
.step-row {
    display: flex;
    align-items: flex-start;
    gap: 12px;
    padding: 10px 0;
    border-bottom: 1px solid #f1f5f9;
}
.step-row:last-child { border-bottom: none; }
.step-icon {
    flex-shrink: 0;
    width: 36px; height: 36px;
    border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: 1rem;
}
.step-text { flex: 1; }
.step-text .step-name {
    font-weight: 700; font-size: 0.88rem; color: #0f172a; margin: 0;
}
.step-text .step-detail {
    font-size: 0.82rem; color: #64748b; margin: 2px 0 0; line-height: 1.5;
}
.step-output {
    flex-shrink: 0;
    background: #f0fdf4; border: 1px solid #bbf7d0;
    border-radius: 8px; padding: 4px 10px;
    font-size: 0.75rem; font-weight: 600; color: #15803d;
    white-space: nowrap;
}

/* Connector arrow */
.connector {
    text-align: center;
    padding: 4px 0;
    color: #94a3b8;
    font-size: 1.4rem;
    line-height: 1;
}

/* Pillar badge */
.pillar-badge {
    display: inline-block;
    padding: 4px 12px;
    border-radius: 20px;
    font-size: 0.78rem;
    font-weight: 700;
    margin: 3px 4px;
}
.pb-ta  { background: #dbeafe; color: #1d4ed8; border: 1px solid #93c5fd; }
.pb-sc  { background: #fef2f2; color: #dc2626; border: 1px solid #fca5a5; }
.pb-id  { background: #fefce8; color: #a16207; border: 1px solid #fde047; }
.pb-da  { background: #f0fdf4; color: #15803d; border: 1px solid #86efac; }
.pb-sp  { background: #faf5ff; color: #7c3aed; border: 1px solid #c4b5fd; }
.pb-rd  { background: #fff7ed; color: #c2410c; border: 1px solid #fed7aa; }
.pb-ot  { background: #f0f9ff; color: #0369a1; border: 1px solid #7dd3fc; }

/* Decision point */
.decision-box {
    background: #eff6ff;
    border: 2px dashed #3b82f6;
    border-radius: 10px;
    padding: 14px 18px;
    margin: 8px 0;
}
.decision-box .decision-icon { font-size: 1.1rem; margin-right: 6px; }
.decision-box .decision-text {
    font-size: 0.85rem; color: #1e40af; font-weight: 600;
}

/* Timing badge */
.timing {
    display: inline-block;
    background: #f8fafc; border: 1px solid #e2e8f0;
    border-radius: 6px; padding: 2px 8px;
    font-size: 0.72rem; font-weight: 600; color: #64748b;
}
</style>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════
# HERO
# ══════════════════════════════════════════════════════════════════════════
st.markdown(
    '<div class="wf-hero">'
    '<h1>🗺️ How It Works</h1>'
    '<p class="sub">End-to-end workflow — from VDR access to actionable deal intelligence.<br>'
    'AI handles the heavy lifting. You retain control at every decision point.</p>'
    '</div>',
    unsafe_allow_html=True,
)

# ══════════════════════════════════════════════════════════════════════════
# PHASE A: SETUP
# ══════════════════════════════════════════════════════════════════════════
st.markdown(
    '<div class="phase-card">'
    '<span class="phase-num">PHASE A</span>'
    '<p class="phase-title">📁 Deal Setup</p>'
    '<p class="phase-desc">'
    'Configure the deal and point the platform at the VDR. This takes under a minute.'
    '</p>'
    #
    '<div class="step-row">'
    '  <div class="step-icon" style="background:#dbeafe;">📂</div>'
    '  <div class="step-text">'
    '    <p class="step-name">Mount VDR Folder</p>'
    '    <p class="step-detail">Point to the local or mounted VDR directory. The system inventories every file — name, type, size, path, and section.</p>'
    '  </div>'
    '  <span class="step-output">All files indexed</span>'
    '</div>'
    #
    '<div class="step-row">'
    '  <div class="step-icon" style="background:#fef3c7;">⚙️</div>'
    '  <div class="step-text">'
    '    <p class="step-name">Configure Deal</p>'
    '    <p class="step-detail">Enter company name, sector, and deal type (growth equity, buyout, carve-out). This calibrates the AI\'s analysis lens.</p>'
    '  </div>'
    '  <span class="step-output">Deal profile set</span>'
    '</div>'
    #
    '<div class="step-row">'
    '  <div class="step-icon" style="background:#e0e7ff;">📋</div>'
    '  <div class="step-text">'
    '    <p class="step-name">Upload DRL Excel (Optional)</p>'
    '    <p class="step-detail">Upload the OOTB Due Diligence Request List. The system parses all questions and categorizes each as Complete, Open, In Process, or Unknown.</p>'
    '  </div>'
    '  <span class="step-output">568 questions parsed</span>'
    '</div>'
    '</div>',
    unsafe_allow_html=True,
)

st.markdown('<div class="connector">▼</div>', unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════
# PHASE B: SCAN
# ══════════════════════════════════════════════════════════════════════════
st.markdown(
    '<div class="phase-card">'
    '<span class="phase-num">PHASE B</span>'
    '<p class="phase-title">🔍 VDR Scan Execution</p>'
    '<p class="phase-desc">'
    'The AI reads, extracts, and analyzes VDR documents. A Core Tech scan completes in ~25 minutes.'
    '</p>'
    #
    '<div class="step-row">'
    '  <div class="step-icon" style="background:#fef3c7;">🎯</div>'
    '  <div class="step-text">'
    '    <p class="step-name">Select Batches <span class="timing">~30 seconds</span></p>'
    '    <p class="step-detail">'
    '      3-tier batch picker: <strong>Core Tech</strong> (auto-selected — product, security, pen tests), '
    '      <strong>Supporting Context</strong> (infra, HR/org), and <strong>Uncategorised</strong>. '
    '      Start with Core Tech for the fastest first read.'
    '    </p>'
    '  </div>'
    '  <span class="step-output">3 batches / 104 docs</span>'
    '</div>'
    #
    '<div class="step-row">'
    '  <div class="step-icon" style="background:#dbeafe;">📑</div>'
    '  <div class="step-text">'
    '    <p class="step-name">Structure Map + Completeness <span class="timing">&lt; 1 sec</span></p>'
    '    <p class="step-detail">'
    '      Deterministic inventory. Checks what\'s there vs. what\'s expected for the deal type. '
    '      Surfaces gaps immediately — no AI needed.'
    '    </p>'
    '  </div>'
    '  <span class="step-output">84/100 completeness</span>'
    '</div>'
    #
    '<div class="step-row">'
    '  <div class="step-icon" style="background:#fef2f2;">🤖</div>'
    '  <div class="step-text">'
    '    <p class="step-name">Signal Extraction <span class="timing">15-25 min</span></p>'
    '    <p class="step-detail">'
    '      Documents are chunked and sent to Claude API in token-aware sub-batches (max 150K tokens each). '
    '      Up to 3 concurrent calls. The v1.4 Signal Catalog (38 signals, 7 pillars) is injected into every prompt. '
    '      Checkpoints saved after each sub-batch — scans resume after failure.'
    '    </p>'
    '  </div>'
    '  <span class="step-output">70-90 signals</span>'
    '</div>'
    #
    '<div class="step-row">'
    '  <div class="step-icon" style="background:#f0fdf4;">🏷️</div>'
    '  <div class="step-text">'
    '    <p class="step-name">Pillar Normalization <span class="timing">&lt; 1 sec</span></p>'
    '    <p class="step-detail">'
    '      3-strategy pipeline: catalog prefix lookup → explicit name mapping (50+ entries) → keyword matching. '
    '      Ensures every signal maps to one of 7 canonical pillars.'
    '    </p>'
    '  </div>'
    '  <span class="step-output">7 pillars mapped</span>'
    '</div>'
    #
    '<div class="step-row">'
    '  <div class="step-icon" style="background:#faf5ff;">🔬</div>'
    '  <div class="step-text">'
    '    <p class="step-name">Domain Analysis <span class="timing">5-10 min</span></p>'
    '    <p class="step-detail">'
    '      7 domain agents run in parallel — one per pillar. Each produces findings with evidence chains, '
    '      severity ratings (CRITICAL/HIGH/MEDIUM/LOW), business impact, and questions for the target.'
    '    </p>'
    '  </div>'
    '  <span class="step-output">domain_findings.json</span>'
    '</div>'
    #
    '<div class="step-row">'
    '  <div class="step-icon" style="background:#fff7ed;">🔗</div>'
    '  <div class="step-text">'
    '    <p class="step-name">Cross-Reference + Brief <span class="timing">2-3 min</span></p>'
    '    <p class="step-detail">'
    '      Signals and findings cross-referenced. Compound risks identified across pillars. '
    '      Overall rating (RED/YELLOW/GREEN), heatmap, and executive narrative produced.'
    '    </p>'
    '  </div>'
    '  <span class="step-output">Intelligence brief</span>'
    '</div>'
    '</div>',
    unsafe_allow_html=True,
)

st.markdown('<div class="connector">▼</div>', unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════
# PHASE C: REVIEW
# ══════════════════════════════════════════════════════════════════════════
st.markdown(
    '<div class="phase-card">'
    '<span class="phase-num">PHASE C</span>'
    '<p class="phase-title">📊 Practitioner Review</p>'
    '<p class="phase-desc">'
    'The Deal Dashboard populates with three layers of intelligence. Review, validate, and decide what to chase.'
    '</p>'
    #
    '<div class="step-row">'
    '  <div class="step-icon" style="background:#dbeafe;">📈</div>'
    '  <div class="step-text">'
    '    <p class="step-name">KPI Overview</p>'
    '    <p class="step-detail">'
    '      Overall rating, total signals, domain findings count, and chase questions — at a glance.'
    '    </p>'
    '  </div>'
    '</div>'
    #
    '<div class="step-row">'
    '  <div class="step-icon" style="background:#fef3c7;">🔎</div>'
    '  <div class="step-text">'
    '    <p class="step-name">Domain Deep Dives</p>'
    '    <p class="step-detail">'
    '      Click through pillar tabs (sorted RED first). Each shows: grade, signals with evidence quotes, '
    '      findings with evidence chains, and blind spots.'
    '    </p>'
    '  </div>'
    '</div>'
    #
    '<div class="step-row">'
    '  <div class="step-icon" style="background:#f0fdf4;">📣</div>'
    '  <div class="step-text">'
    '    <p class="step-name">Chase List</p>'
    '    <p class="step-detail">'
    '      Auto-generated questions grouped by pillar and sorted by priority. '
    '      Download as TXT or copy to clipboard.'
    '    </p>'
    '  </div>'
    '</div>'
    #
    '<div class="step-row">'
    '  <div class="step-icon" style="background:#faf5ff;">📥</div>'
    '  <div class="step-text">'
    '    <p class="step-name">Download Report</p>'
    '    <p class="step-detail">'
    '      Generate a professional DOCX with cover page, executive summary, domain deep dives, '
    '      chase list, signal inventory, and appendix. Ready to share with the deal team.'
    '    </p>'
    '  </div>'
    '</div>'
    '</div>',
    unsafe_allow_html=True,
)

st.markdown('<div class="connector">▼</div>', unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════
# PHASE D: CHASE & ITERATE
# ══════════════════════════════════════════════════════════════════════════
st.markdown(
    '<div class="phase-card">'
    '<span class="phase-num">PHASE D</span>'
    '<p class="phase-title">🔄 Chase & Iterate</p>'
    '<p class="phase-desc">'
    'Send targeted requests, add document batches incrementally, and re-scan as new information arrives.'
    '</p>'
    #
    '<div class="step-row">'
    '  <div class="step-icon" style="background:#dbeafe;">📧</div>'
    '  <div class="step-text">'
    '    <p class="step-name">Send Chase List</p>'
    '    <p class="step-detail">'
    '      Use the auto-generated questions to send targeted requests. Each question links back to the '
    '      specific finding, pillar, and evidence that triggered it.'
    '    </p>'
    '  </div>'
    '</div>'
    #
    '<div class="step-row">'
    '  <div class="step-icon" style="background:#fef3c7;">➕</div>'
    '  <div class="step-text">'
    '    <p class="step-name">Incremental Scan</p>'
    '    <p class="step-detail">'
    '      Add remaining batch groups (Supporting Context, Uncategorised) from the New Scan page. '
    '      New signals merge into existing findings — prior results are never wiped.'
    '    </p>'
    '  </div>'
    '</div>'
    #
    '<div class="step-row">'
    '  <div class="step-icon" style="background:#f0fdf4;">📄</div>'
    '  <div class="step-text">'
    '    <p class="step-name">Final Report</p>'
    '    <p class="step-detail">'
    '      When coverage is sufficient, generate the final DOCX report reflecting full scan results.'
    '    </p>'
    '  </div>'
    '</div>'
    '</div>',
    unsafe_allow_html=True,
)

st.markdown("---")

# ══════════════════════════════════════════════════════════════════════════
# 7 PILLARS
# ══════════════════════════════════════════════════════════════════════════
st.markdown(
    '<div style="text-align:center;margin:20px 0 8px;">'
    '<span style="font-size:1.1rem;font-weight:700;color:#0f172a;">The 7 Canonical Pillars</span><br>'
    '<span style="font-size:0.82rem;color:#64748b;">Every signal maps to one of these domains</span>'
    '</div>',
    unsafe_allow_html=True,
)

st.markdown(
    '<div style="text-align:center;margin-bottom:20px;">'
    '<span class="pillar-badge pb-ta">Technology & Architecture</span>'
    '<span class="pillar-badge pb-sc">Security & Compliance</span>'
    '<span class="pillar-badge pb-id">Infrastructure & Deployment</span>'
    '<span class="pillar-badge pb-da">Data & AI Readiness</span>'
    '<span class="pillar-badge pb-sp">SDLC & Product Mgmt</span>'
    '<span class="pillar-badge pb-rd">R&D Spend Assessment</span>'
    '<span class="pillar-badge pb-ot">Organization & Talent</span>'
    '</div>',
    unsafe_allow_html=True,
)

st.markdown("---")

# ══════════════════════════════════════════════════════════════════════════
# THREE-LAYER INTELLIGENCE
# ══════════════════════════════════════════════════════════════════════════
st.markdown(
    '<div style="text-align:center;margin:20px 0 16px;">'
    '<span style="font-size:1.1rem;font-weight:700;color:#0f172a;">Three-Layer Intelligence Stack</span><br>'
    '<span style="font-size:0.82rem;color:#64748b;">Raw extractions → Interpreted conclusions → Actionable questions</span>'
    '</div>',
    unsafe_allow_html=True,
)

l1, l2, l3 = st.columns(3)

with l1:
    st.markdown(
        '<div style="background:#f8fafc;border:2px solid #e2e8f0;border-radius:12px;padding:20px;text-align:center;min-height:220px;">'
        '<div style="font-size:2rem;margin-bottom:8px;">📡</div>'
        '<div style="font-size:1rem;font-weight:700;color:#0f172a;">Layer 1: Signals</div>'
        '<div style="font-size:0.82rem;color:#64748b;margin-top:8px;line-height:1.6;">'
        'Raw extractions from VDR documents.<br>'
        'Rating: RED / YELLOW / GREEN<br>'
        'Evidence quote + source doc<br>'
        'Mapped to catalog signal ID'
        '</div>'
        '</div>',
        unsafe_allow_html=True,
    )

with l2:
    st.markdown(
        '<div style="background:#f8fafc;border:2px solid #3b82f6;border-radius:12px;padding:20px;text-align:center;min-height:220px;">'
        '<div style="font-size:2rem;margin-bottom:8px;">🔎</div>'
        '<div style="font-size:1rem;font-weight:700;color:#0f172a;">Layer 2: Findings</div>'
        '<div style="font-size:0.82rem;color:#64748b;margin-top:8px;line-height:1.6;">'
        'Domain agent analysis.<br>'
        'Severity: CRITICAL → LOW<br>'
        'Evidence chains + contradictions<br>'
        'Business impact + remediation'
        '</div>'
        '</div>',
        unsafe_allow_html=True,
    )

with l3:
    st.markdown(
        '<div style="background:#f8fafc;border:2px solid #16a34a;border-radius:12px;padding:20px;text-align:center;min-height:220px;">'
        '<div style="font-size:2rem;margin-bottom:8px;">📣</div>'
        '<div style="font-size:1rem;font-weight:700;color:#0f172a;">Layer 3: Chase List</div>'
        '<div style="font-size:0.82rem;color:#64748b;margin-top:8px;line-height:1.6;">'
        'Auto-generated questions.<br>'
        'Grouped by pillar + priority<br>'
        'Linked to source findings<br>'
        'Download as TXT or DOCX'
        '</div>'
        '</div>',
        unsafe_allow_html=True,
    )

st.markdown("---")

# ══════════════════════════════════════════════════════════════════════════
# KEY DESIGN PRINCIPLES
# ══════════════════════════════════════════════════════════════════════════
st.markdown(
    '<div style="text-align:center;margin:20px 0 16px;">'
    '<span style="font-size:1.1rem;font-weight:700;color:#0f172a;">Design Principles</span>'
    '</div>',
    unsafe_allow_html=True,
)

p1, p2, p3, p4 = st.columns(4)

principles = [
    (p1, "🔍", "Full Traceability", "Every conclusion traces back to a source document and evidence quote. No black-box outputs."),
    (p2, "🛡️", "Nothing Lost", "Versioned archives ensure prior scan results are never overwritten. Every run is preserved."),
    (p3, "⚡", "Incremental", "Start with Core Tech in 25 min. Add batches later. New results merge — no full rescan needed."),
    (p4, "🎯", "Practitioner First", "AI proposes, practitioner disposes. Every output is designed for immediate action."),
]

for col, icon, title, desc in principles:
    with col:
        st.markdown(
            f'<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;'
            f'padding:18px;text-align:center;min-height:160px;">'
            f'<div style="font-size:1.5rem;margin-bottom:6px;">{icon}</div>'
            f'<div style="font-size:0.92rem;font-weight:700;color:#0f172a;">{title}</div>'
            f'<div style="font-size:0.8rem;color:#64748b;margin-top:6px;line-height:1.5;">{desc}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

# Footer
st.markdown(
    '<div style="text-align:center;margin-top:32px;padding:16px;color:#94a3b8;font-size:0.78rem;">'
    'VDR Triage Platform · Built for Crosslake Technology Due Diligence'
    '</div>',
    unsafe_allow_html=True,
)
