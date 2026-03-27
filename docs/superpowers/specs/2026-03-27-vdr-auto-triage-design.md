# VDR Auto-Triage — Design Spec
**Date:** 2026-03-27
**Status:** Approved — v2 (completeness check, signal intelligence layer, pervasive feedback loop added)
**Pilot target:** HORIZON (HST Pathways) — VDR in `VDR/` directory

---

## 1. Problem Statement

Crosslake practitioners spend the first hours of every TDD engagement orienting themselves inside a VDR — figuring out what's there, what matters, and where to start. This is high-cost, low-differentiation work. VDR Auto-Triage automates this orientation layer using AI, surfacing signals before any human begins reading, and compounding practitioner productivity across every engagement.

Two compounding mechanisms make this more than a one-time scan:
1. **VDR Completeness Check** — surfaces what's *missing* from the VDR so practitioners can issue a targeted request list immediately, not days later
2. **Signal Intelligence Layer** — every scan's signals are stored and fed back into future scans; practitioner feedback at every phase sharpens accuracy over time

---

## 2. Full TDD Lifecycle (End-to-End)

The feedback loop is not confined to Phase 0. Every phase where AI produces output has a feedback surface. Practitioner ratings at each gate flow into the Signal Intelligence Layer, improving the next engagement across the full lifecycle.

```
PHASE 0: VDR AUTO-TRIAGE          ← First build (this spec)
│  Input:  VDR folder + prior deal patterns from Signal Intelligence Layer
│  Output A: VDR Intelligence Brief (JSON) — feeds all downstream agents
│  Output B: Heatmap + Prioritized Reading List (Markdown) — practitioner view
│  Output C: VDR Completeness Report — missing documents + chase list
│
│  [HUMAN GATE 1] Practitioner:
│    → validates/dismisses signals (explicit rating: CONFIRMED / NOISE / UNCERTAIN)
│    → reviews completeness gap list, sends request to target company
│    → feedback written to Signal Intelligence Layer
│
PHASE 1: ALEX — Intake & Profile
│  Input: Deal intake + VDR Intelligence Brief + similar-deal patterns
│  [Feedback] Practitioner corrects company profile, adjusts risk weightings
│    → delta written to Signal Intelligence Layer
│
PHASE 2: MORGAN — Public Signals
│  Input: Alex deal state + VDR Brief
│  [Feedback] Practitioner marks public signals as confirmed / contradicted by VDR
│    → contradiction patterns stored for future cross-referencing
│
PHASE 3: JORDAN — Repo Health     (skip if no repo access)
│  [Feedback] Practitioner notes where repo signals confirm/contradict VDR findings
│
PHASE 4: RILEY — Security
│  Input: Deal state + VDR security_slice (pre-digested)
│  [HUMAN GATE 2] Practitioner:
│    → rates each security signal (CONFIRMED / NOISE / NEEDS-VERIFICATION)
│    → adds practitioner commentary to high-severity signals
│    → feedback written to Signal Intelligence Layer
│
PHASE 5: CASEY — Code Quality
│  [Feedback] Practitioner rates code quality signals post-discovery
│
PHASE 6: TAYLOR — Infrastructure
│  Input: Deal state + VDR infra_slice (pre-digested)
│  [Feedback] Practitioner rates infra signals post-discovery
│    → cloud cost anomaly patterns stored for benchmarking
│
PHASE 7: DREW — Benchmarking
│  Input: Deal state + Signal Intelligence Layer (cross-deal patterns, vertical data)
│  [HUMAN GATE 3] Deal lead:
│    → validates benchmark comparisons
│    → approves or adjusts deal scenarios
│    → final ratings written to Signal Intelligence Layer
│
PHASE 8: SAM — Synthesis
   Input: All outputs + VDR Brief + practitioner feedback accumulated
   [Post-report feedback] After PE report delivered:
     → Practitioner records which signals proved material post-close
     → Outcome data (deal done / walked / renegotiated) written to layer
     → This is the highest-value feedback — ground truth for the system
```

**Principle:** AI proposes, practitioner disposes. Every disposal — confirmation or dismissal — makes the next engagement smarter.

---

## 3. Phase 0: VDR Auto-Triage — Architecture

### 3.1 Processing Pipeline

```
INPUT: VDR folder path + expected_docs checklist (from signal_lenses.json)
    │
    ▼
STEP 1: STRUCTURE MAPPER
  - Walk full folder tree
  - Inventory every file (name, type, size, path, VDR section)
  - Compare inventory against expected_docs checklist by deal type
  - Output: document_inventory list + gap_list (missing expected docs)
    │
    ▼
STEP 2: DOCUMENT READER
  - Extract text from PDFs via PyPDF2
  - Chunk large documents (max 8,000 tokens per chunk)
  - Preserve source metadata (filename, section, page range)
    │
    ▼
STEP 3: SIGNAL EXTRACTOR  (core AI step)
  - Query Signal Intelligence Layer for similar prior deals
    (Pinecone semantic search: "healthcare SaaS security signals")
  - Inject top-matching prior patterns into extraction prompt as context
  - Group documents into batches by type/section (see 3.2)
  - One Claude API call per batch — cross-document context within batch
  - Each signal returns: lens, rating (RED/YELLOW/GREEN), confidence
    (HIGH/MEDIUM/LOW), title, observation, evidence_quote, source_doc,
    deal_implication, similar_prior_signal_id (if matched from layer)
    │
    ▼
STEP 4: CROSS-REFERENCER  (single Claude call)
  - Input: all signals from Step 3 + document inventory + gap_list
  - Tasks:
    1. Identify compound risks (2+ signals from different docs/lenses)
    2. Surface contradictions (doc A claims X, doc B implies not-X)
    3. Generate prioritized reading list (signal density + severity + gap urgency)
    4. Produce domain slices (security_slice, infra_slice, product_slice)
    5. Classify each gap as CRITICAL / HIGH / MEDIUM with a request rationale
    │
    ▼
OUTPUTS (written to /outputs/<company_name>/)
  A. vdr_intelligence_brief.json       ← feeds downstream agents
  B. vdr_triage_report.md              ← practitioner heatmap + reading list
  C. vdr_completeness_report.md        ← missing docs + chase list

  + feedback_session.json (empty shell) ← practitioner fills this in at Gate 1
```

### 3.2 Document Batching Strategy

Documents are grouped before signal extraction to give Claude cross-document context within a related set:

| Batch Group | VDR Sections Included |
|---|---|
| `security_pen_tests` | All pen test reports |
| `security_compliance` | SOC2, HITRUST, ISP, security plan |
| `security_posture` | Cyber dashboards, conditional access, backups |
| `infra_cloud_costs` | AWS bills, CSpire bills |
| `infra_architecture` | Data flow diagrams, system architecture, monitoring |
| `infra_resilience` | DR/BC plans, change management, data retention |
| `product_overview` | Product one-pagers, AI architecture docs |
| `sdlc_process` | SDLC docs, deployment docs, open source policy |
| `commercial_vendors` | Vendor lists, proprietary software, TCPA |
| `sales_market` | Pipeline, GTM, pricing, NPS, CSAT |

Batches map naturally to the domain slices that Riley and Taylor consume downstream.

---

## 4. Data Contracts

### 4.1 Per-Batch Signal Extraction (intermediate, not persisted to files)

```json
{
  "batch_id": "security_pen_tests",
  "documents": ["pen_test_cc.pdf", "pen_test_echart.pdf"],
  "signals": [
    {
      "signal_id": "SIG-001",
      "lens": "Security",
      "rating": "RED",
      "confidence": "HIGH",
      "title": "Persistent critical findings across 3 pen tests",
      "observation": "...",
      "evidence_quote": "...",
      "source_doc": "pen_test_external.pdf",
      "deal_implication": "...",
      "similar_prior_signal_id": "DEAL-007-SIG-004"
    }
  ],
  "batch_summary": "..."
}
```

### 4.2 VDR Intelligence Brief (final, feeds downstream agents)

```json
{
  "company_name": "string",
  "deal_id": "string",
  "vdr_scan_timestamp": "ISO string",
  "overall_signal_rating": "RED | YELLOW | GREEN",
  "lens_heatmap": {
    "Security": {
      "rating": "RED | YELLOW | GREEN",
      "signal_count": "number",
      "red_count": "number",
      "top_signal": "string"
    }
  },
  "compound_risks": [
    {
      "risk_id": "CR-01",
      "title": "string",
      "contributing_signals": ["SIG-001", "SIG-008"],
      "severity": "CRITICAL | HIGH | MEDIUM",
      "narrative": "string"
    }
  ],
  "prioritized_reading_list": [
    {
      "rank": "number",
      "document": "string",
      "vdr_section": "string",
      "reason": "string",
      "estimated_read_time_mins": "number",
      "top_signal_preview": "string"
    }
  ],
  "domain_slices": {
    "security_slice": { "signals": [], "summary": "string", "overall_rating": "string" },
    "infra_slice": { "signals": [], "summary": "string", "overall_rating": "string" },
    "product_slice": { "signals": [], "summary": "string", "overall_rating": "string" }
  },
  "document_inventory": [
    {
      "filename": "string",
      "vdr_section": "string",
      "batch_group": "string",
      "signal_count": "number",
      "top_rating": "RED | YELLOW | GREEN | NONE"
    }
  ]
}
```

### 4.3 VDR Completeness Report (Output C — practitioner chase list)

```json
{
  "deal_id": "string",
  "deal_type": "PE acquisition | growth equity | pre-LOI scan",
  "sector": "string",
  "missing_documents": [
    {
      "gap_id": "GAP-001",
      "urgency": "CRITICAL | HIGH | MEDIUM",
      "expected_document": "Pen test for primary application (eChart)",
      "reason_expected": "13 other application surfaces have pen tests; primary application absent",
      "request_language": "Please provide the most recent penetration test report for eChart, including remediation status for all findings."
    }
  ],
  "present_but_incomplete": [
    {
      "document": "SOC 2 Type 2 Report",
      "issue": "Report period ended 14 months ago — outside 12-month currency window",
      "request_language": "Please confirm whether a more recent SOC 2 audit is in progress or available."
    }
  ],
  "completeness_score": "number (0-100)",
  "chase_list_summary": "string — 3-sentence practitioner brief on what to ask for and why"
}
```

### 4.4 Practitioner Feedback Record (written after each Human Gate)

```json
{
  "deal_id": "string",
  "phase": "0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8",
  "gate": "1 | 2 | 3 | post_report",
  "practitioner_id": "string",
  "timestamp": "ISO string",
  "signal_ratings": [
    {
      "signal_id": "SIG-001",
      "verdict": "CONFIRMED | NOISE | UNCERTAIN",
      "practitioner_note": "string (optional)",
      "corrected_rating": "RED | YELLOW | GREEN | null"
    }
  ],
  "phase_accuracy_score": "number (0-100, practitioner's overall assessment)",
  "missed_signals": [
    {
      "description": "string — signal AI missed that practitioner found",
      "lens": "string",
      "rating": "RED | YELLOW | GREEN"
    }
  ],
  "outcome_data": {
    "deal_outcome": "closed | walked | renegotiated | pending",
    "signals_proved_material": ["SIG-001", "SIG-008"],
    "signals_proved_immaterial": ["SIG-003"]
  }
}
```

---

## 5. Signal Intelligence Layer (Cross-Engagement Learning)

The flywheel that makes every scan smarter than the last.

### 5.1 Architecture

```
VDR Scan N completes
        │
        ▼
┌──────────────────────────────────┐
│  SIGNAL STORE (Pinecone)         │
│                                  │
│  Each signal embedded as vector  │
│  Metadata: deal_id, sector,      │
│  lens, rating, confidence,       │
│  phase, practitioner_verdict,    │
│  outcome_data                    │
└──────────┬───────────────────────┘
           │
    ┌──────┴──────────────────────────────────┐
    │              │                          │
    ▼              ▼                          ▼
PATTERN        CALIBRATION              BENCHMARKING
DETECTION      ENGINE                   ENGINE
    │              │                          │
"This combo    Practitioner             "HORIZON security
appeared in    marked SIG-003           posture is 2nd
4 prior        as NOISE 8/10            quartile vs 14
healthcare     times → lower            prior healthcare
SaaS deals     initial confidence       SaaS deals"
and all were   for this signal
CRITICAL"      type in future
```

### 5.2 What Gets Stored

Every signal extracted — across all 8 phases, not just Phase 0 — is embedded and stored:

| Event | What's stored |
|---|---|
| Phase 0 signal extracted | Signal vector + metadata (lens, rating, confidence, sector, deal_type) |
| Phase 0 gap identified | Gap vector + deal_type + sector |
| Human Gate feedback | Practitioner verdicts linked to signal IDs |
| Post-report outcome | Materiality verdicts (proved real vs. proved noise) |
| Any phase signal | Phase number + agent name + signal content |

### 5.3 How Prior Patterns Improve New Scans

Before each Claude API call (at any phase), the system:

1. **Queries Pinecone** for semantically similar signals from prior deals in the same sector and deal type
2. **Injects top-3 matching patterns** into the prompt as context: `"In 3 similar prior deals, this combination of factors was rated CRITICAL and proved material post-close"`
3. **Adjusts confidence thresholds** based on practitioner feedback history for this signal type

This means:
- Deal 1 in healthcare SaaS: cold start, baseline signals
- Deal 5: system recognises patterns, surfaces compound risks faster
- Deal 20: high-confidence signals in known patterns, attention focused on novel/unexpected findings
- Deal 50+: proprietary intelligence asset — Crosslake knows things about healthcare SaaS deals that no competitor can replicate from first principles

### 5.4 Feedback Loop Mechanics

**Explicit feedback** (practitioner actively rates at each Human Gate):
- CLI: `python -m tools.feedback --deal HORIZON --phase 0 --signal SIG-001 --verdict CONFIRMED`
- Each rating immediately updates the signal's metadata in Pinecone

**Implicit feedback** (inferred from downstream usage):
- If a Phase 0 signal appears verbatim in Sam's final PE report → marked CONFIRMED
- If a Phase 0 signal is never referenced in any downstream output → flagged for practitioner review
- If a practitioner adds a "missed signal" at Gate 2 that wasn't in Gate 1 → stored as a detection gap for that signal type

**Outcome feedback** (highest value — post-close ground truth):
- After deal closes, practitioner records which signals proved material
- This outcome data has the highest weight in future calibration
- Over time, the system learns which signal combinations are predictive vs. noise

---

## 6. File & Folder Layout

```
/agents/
  vdr_triage.py              ← Phase 0 orchestrator (CLI entry point)

/tools/
  document_reader.py         ← PDF extraction + chunking (PyPDF2)
  structure_mapper.py        ← Folder walk + inventory + gap detection
  signal_extractor.py        ← Per-batch Claude API call + signal parsing
  cross_referencer.py        ← Cross-doc Claude call + output assembly
  completeness_checker.py    ← Compares inventory vs expected_docs → gap report
  report_writer.py           ← Renders .md outputs from brief JSON
  signal_store.py            ← Pinecone read/write: embed signals, query patterns
  feedback_collector.py      ← CLI feedback capture + Pinecone update

/prompts/
  vdr_signal_extraction.txt  ← Per-batch extraction prompt (with prior-pattern slot)
  vdr_cross_reference.txt    ← Cross-referencing prompt
  vdr_completeness.txt       ← Gap classification + request language generation

/outputs/
  HORIZON/
    vdr_intelligence_brief.json
    vdr_triage_report.md
    vdr_completeness_report.md
    feedback_gate1.json       ← Practitioner fills in at Gate 1
    feedback_gate2.json       ← Practitioner fills in at Gate 2
    feedback_gate3.json       ← Deal lead fills in at Gate 3
    feedback_post_report.json ← Post-close outcome data

/data/
  signal_lenses.json          ← 11 lenses with definitions
  batch_rules.json            ← Folder pattern → batch group mapping
  expected_docs.json          ← Expected documents by deal_type + sector
```

---

## 7. CLI Interface

```bash
# Run triage on a VDR folder
python -m agents.vdr_triage \
  --vdr-path "VDR/HST Pathways-Diligence-HORIZON - VDR (1)" \
  --company HORIZON \
  --deal-id DEAL-001 \
  --sector healthcare-saas \
  --deal-type pe-acquisition

# Collect practitioner feedback at Gate 1
python -m tools.feedback_collector \
  --deal DEAL-001 \
  --phase 0 \
  --gate 1

# Query signal intelligence for a new deal
python -m tools.signal_store query \
  --sector healthcare-saas \
  --lens Security \
  --top 5
```

---

## 8. Reusability from Existing Agents

| Existing Asset | Reuse Decision |
|---|---|
| Alex prompt | Enhance — prepend VDR Brief + top prior-deal patterns |
| Riley prompt | Enhance — prepend security_slice + prior security signals |
| Taylor prompt | Enhance — prepend infra_slice + prior infra signals |
| Drew prompt | Enhance — query Signal Intelligence Layer for benchmarks |
| Sam prompt | Enhance — include accumulated practitioner feedback summary |
| Morgan, Jordan, Casey | Unchanged for now |
| Deal-state JSON chain | VDR Intelligence Brief becomes v0; feedback_records accumulate alongside |
| requirements.txt | Add: pinecone-client |

---

## 9. What's Out of Scope (This Spec)

- DOCX support (PDFs only for pilot)
- Web UI / dashboard rendering
- Insurance MGA benchmarking workstream (separate spec)
- Automated VDR ingestion from external portals (Intralinks, Datasite)
- Multi-deal portfolio view (PortfolioView analogue — future spec)

---

## 10. Success Criteria for HORIZON Pilot

### Coverage & Completeness
1. **Document coverage:** 100% of PDFs inventoried; ≥95% successfully extracted (not just listed)
2. **Lens coverage:** Signals identified across ≥8 of 11 lenses — no lens left blank where documents exist for it
3. **Gap detection:** Completeness report identifies ≥3 genuinely missing or stale documents, each with a specific, usable request-language string a practitioner could send verbatim

### Signal Quality
4. **Signal-to-noise:** A practitioner reviewing the top 20 signals agrees ≥80% are legitimate deal-relevant observations — not hallucinations or generic statements
5. **Evidence traceability:** 100% of RED and YELLOW signals include a verbatim quote traceable to a specific page and document — zero unanchored assertions
6. **Contradiction detection:** If the VDR contains conflicting signals (e.g., SOC2 certified but pen test shows critical open findings), these are explicitly flagged — not averaged away

### Prioritization & Compound Intelligence
7. **Prioritization accuracy:** Top 10 prioritised documents validated by a practitioner as "would have read first anyway" — at least 7 of 10 match
8. **Compound risk depth:** ≥3 compound risks identified, each spanning ≥2 documents from *different* batch groups — not within the same section
9. **Actionable discovery questions:** Triage report surfaces ≥5 specific questions grounded directly in VDR findings — a practitioner can walk into a discovery session armed with these

### Practitioner Utility
10. **Time-to-orientation:** A practitioner using only the triage report can brief a deal lead on the top 3 risks in under 10 minutes, without opening a single VDR document
11. **Downstream agent readiness:** `security_slice` and `infra_slice` are independently usable — a practitioner reading only a slice understands the relevant risk picture without the full brief

### Feedback Loop Validation
12. **Feedback capture:** Gate 1 feedback collection works end-to-end — practitioner ratings for ≥10 signals are captured and written to Pinecone successfully
13. **Pattern retrieval:** For a second test run on a different (synthetic) deal in the same sector, the system retrieves ≥1 relevant prior signal pattern from Pinecone and injects it into the extraction prompt
14. **Implicit feedback:** At least 1 Phase 0 signal is correctly auto-confirmed as CONFIRMED because it appears in Sam's final output in Phase 8

### Cost & Performance
15. **Cost ceiling:** Full HORIZON scan completes under $15 total API cost and under 20 minutes wall-clock time
16. **Reproducibility:** Running triage twice on the same VDR produces the same overall lens ratings and the same top 5 signals — confirming prompt stability
