# VDR Auto-Triage — Design Spec
**Date:** 2026-03-27
**Status:** Approved
**Pilot target:** HORIZON (HST Pathways) — VDR in `VDR/` directory

---

## 1. Problem Statement

Crosslake practitioners spend the first hours of every TDD engagement orienting themselves inside a VDR — figuring out what's there, what matters, and where to start. This is high-cost, low-differentiation work. VDR Auto-Triage automates this orientation layer using AI, surfacing signals before any human begins reading, and compounding practitioner productivity across every engagement.

---

## 2. Full TDD Lifecycle (End-to-End)

```
PHASE 0: VDR AUTO-TRIAGE          ← First build (this spec)
│  Input:  VDR folder
│  Output A: VDR Intelligence Brief (JSON) — feeds all downstream agents
│  Output B: Heatmap + Prioritized Reading List (Markdown) — practitioner view
│  [HUMAN GATE 1] Practitioner reviews heatmap, validates top signals
│
PHASE 1: ALEX — Intake & Profile  (existing, enhanced with VDR Brief)
│
PHASE 2: MORGAN — Public Signals  (existing, unchanged)
│
PHASE 3: JORDAN — Repo Health     (existing, skip if no repo access)
│
PHASE 4: RILEY — Security         (existing, enhanced with security_slice)
│  [HUMAN GATE 2] Practitioner reviews security signals, adds context
│
PHASE 5: CASEY — Code Quality     (existing, unchanged)
│
PHASE 6: TAYLOR — Infrastructure  (existing, enhanced with infra_slice)
│
PHASE 7: DREW — Benchmarking      (existing, enhanced with external vertical data)
│  [HUMAN GATE 3] Deal lead reviews draft findings, approves synthesis scope
│
PHASE 8: SAM — Synthesis          (existing, full context including VDR Brief)
   Output: PE-ready report (scorecard, compound risks, deal scenarios)
```

**Human-in-the-loop design:** Three natural gates — after triage, after security, before synthesis. Not continuous, not fully autonomous.

---

## 3. Phase 0: VDR Auto-Triage — Architecture

### 3.1 Processing Pipeline

```
INPUT: VDR folder path
    │
    ▼
STEP 1: STRUCTURE MAPPER
  - Walk full folder tree
  - Inventory every file (name, type, size, path, VDR section)
  - Output: document_inventory list
    │
    ▼
STEP 2: DOCUMENT READER
  - Extract text from PDFs via PyPDF2
  - Chunk large documents (max 8,000 tokens per chunk)
  - Preserve source metadata (filename, section, page range)
    │
    ▼
STEP 3: SIGNAL EXTRACTOR  (core AI step)
  - Group documents into batches by type/section
    e.g. "security_pen_tests", "security_compliance", "infra_cloud_costs"
  - One Claude API call per batch (cross-document context within batch)
  - Prompt maps signals to 11 lenses: Architecture, Codebase, Security,
    Product, DevOps, Team, Data, Commercial Tech, plus AI/ML Readiness,
    Regulatory/Compliance, Financial/Cost
  - Each signal returns: lens, rating (RED/YELLOW/GREEN), confidence
    (HIGH/MEDIUM/LOW), title, observation, evidence_quote, source_doc,
    deal_implication
    │
    ▼
STEP 4: CROSS-REFERENCER  (single Claude call)
  - Input: all signals from Step 3 + document inventory
  - Tasks:
    1. Identify compound risks (2+ signals from different docs/lenses
       pointing at same underlying issue = amplified severity)
    2. Surface contradictions (doc A claims X, doc B implies not-X)
    3. Generate prioritized reading list ranked by signal density + severity
    4. Produce domain slices (security_slice, infra_slice, product_slice)
    │
    ▼
OUTPUTS (written to /outputs/<company_name>/)
  - vdr_intelligence_brief.json
  - vdr_triage_report.md
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

Batches map naturally to the domain slices that Riley and Taylor will consume downstream.

---

## 4. Data Contracts

### 4.1 Per-Batch Signal Extraction (intermediate, not persisted)

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
      "deal_implication": "..."
    }
  ],
  "batch_summary": "..."
}
```

### 4.2 VDR Intelligence Brief (final, feeds downstream agents)

```json
{
  "company_name": "string",
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
    "security_slice": {
      "signals": [],
      "summary": "string",
      "overall_rating": "string"
    },
    "infra_slice": {
      "signals": [],
      "summary": "string",
      "overall_rating": "string"
    },
    "product_slice": {
      "signals": [],
      "summary": "string",
      "overall_rating": "string"
    }
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

---

## 5. File & Folder Layout

New files to be created (within existing project structure):

```
/agents/
  vdr_triage.py          ← Phase 0 orchestrator (CLI entry point)

/tools/
  document_reader.py     ← PDF text extraction + chunking (PyPDF2)
  structure_mapper.py    ← VDR folder walk + file inventory + batch grouping
  signal_extractor.py    ← Per-batch Claude API call + signal parsing
  cross_referencer.py    ← Final cross-doc Claude call + output assembly
  report_writer.py       ← Renders vdr_triage_report.md from brief JSON

/prompts/
  vdr_signal_extraction.txt   ← Prompt template for per-batch extraction
  vdr_cross_reference.txt     ← Prompt template for cross-referencing

/outputs/
  HORIZON/                    ← Auto-created per company
    vdr_intelligence_brief.json
    vdr_triage_report.md

/data/
  signal_lenses.json     ← 11 lenses with definitions (drives prompt context)
  batch_rules.json       ← Maps folder patterns → batch group names
```

---

## 6. CLI Interface

```bash
# Run triage on a VDR folder
python -m agents.vdr_triage --vdr-path "VDR/HST Pathways-Diligence-HORIZON - VDR (1)" --company HORIZON

# Output lands in outputs/HORIZON/
```

---

## 7. Reusability from Existing Agents

| Existing Asset | Reuse Decision |
|---|---|
| Alex prompt | Enhance in Phase 1 — add VDR Brief as input context |
| Riley prompt | Enhance in Phase 4 — prepend security_slice summary |
| Taylor prompt | Enhance in Phase 6 — prepend infra_slice summary |
| Drew prompt | Use as-is for benchmarking; extend for Insurance MGA vertical |
| Sam prompt | Use as-is; VDR Brief gives richer evidence base |
| Morgan, Jordan, Casey | Unchanged for now |
| Deal-state JSON chain | VDR Intelligence Brief becomes v0 in the chain |
| requirements.txt | All dependencies already present (PyPDF2, anthropic, pydantic) |

---

## 8. What's Out of Scope (This Spec)

- DOCX support (PDFs only for pilot)
- Web UI / dashboard rendering
- Pinecone vector storage (simple JSON output for pilot)
- Insurance MGA benchmarking workstream (separate spec)
- Automated git pull / VDR ingestion from external sources
- Cost tracking / token usage reporting

---

## 9. Success Criteria for HORIZON Pilot

1. All 120 HORIZON VDR documents processed without errors
2. `vdr_intelligence_brief.json` produced with signals across all applicable lenses
3. `vdr_triage_report.md` readable by a practitioner in under 5 minutes
4. Prioritized reading list ranks security docs (pen tests, SOC2) at the top — matches what an expert would prioritize manually
5. At least 2 compound risks identified that span multiple documents
6. Total API cost under $10 for a full HORIZON scan
