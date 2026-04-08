# System Design: PE Technology Due Diligence Platform

**Version**: 1.3 (v1.3 Signal Catalog, 7-pillar taxonomy)
**Date**: 2026-04-06
**Author**: Shiva / RentAI
**Status**: Production (Phase 0 + Phase 4 live)

---

## 1. Requirements

### 1.1 Functional Requirements

The system automates the first pass of technology due diligence for PE acquisitions — the work a Crosslake practitioner does in the first 48 hours after receiving a Virtual Data Room (VDR).

**Core capabilities:**

- **F1 — VDR Ingestion**: Accept a folder of documents in any structure (flat, hierarchical, zipped), extract text from PDF, DOCX, XLSX, PPTX, CSV, TXT, and MD files, and auto-extract ZIP archives.
- **F2 — Batch Classification**: Assign every document to a semantic batch group based on filename and folder path, mapping each batch to one or more of the 7 Crosslake diligence pillars.
- **F3 — Signal Extraction**: Send each batch to Claude with pillar-scoped prompt context, extracting structured signals (observations with severity, evidence, and canonical signal IDs from the v1.3 catalog of 29 signals).
- **F4 — Cross-Reference Synthesis**: Aggregate all signals in a single Claude call to identify compound risks, prioritized reading lists, domain-specific deep dives, and assessment blind spots.
- **F5 — Completeness Assessment**: Compare VDR contents against sector-specific expected document lists, flag missing documents by urgency tier (CRITICAL / HIGH / MEDIUM), detect stale documents, generate chase list with verbatim request language.
- **F6 — Quality Grading**: Deterministically score the VDR across four dimensions (Presence 40%, Readability 25%, Coverage 20%, Yield 15%) into an A–F grade.
- **F7 — Practitioner Recommendation**: Deterministically score which specialist types (security, infrastructure, product, data, engineering, commercial, team, value creation) should be assigned, with effort estimates.
- **F8 — Versioned Rescans**: Detect prior scans, compute document diffs, generate changelogs, archive versioned manifests.
- **F9 — DRL Processing**: Parse filled Deal Response Library (questionnaire) Excel files, score response completeness and depth per tab, grade A–F, track versions across multiple submissions.
- **F10 — Schema Governance (Quinn)**: Watch for changes to the DRL template and signal catalog, compute structural fingerprints and diffs, generate migration packets, maintain a deal-version compatibility matrix.
- **F11 — Dashboard**: Streamlit-based portfolio view with deal cards, pillar heatmaps, signal drill-downs, new scan interface with live preview, questionnaire tracker, and cross-deal market intelligence.

### 1.2 Non-Functional Requirements

| Dimension | Target | Rationale |
|---|---|---|
| **Latency** | Full scan < 15 min for a 500-doc VDR | Practitioners need results within a working session, not overnight |
| **Cost** | < $5 per scan (API spend) | PE firms run 20–50 scans/year; must be negligible vs. practitioner day-rate |
| **Accuracy** | Compound risk recall > 80% vs. manual review | The system's value collapses if it misses what a human would catch |
| **Availability** | Single-user, local-first | No multi-tenancy needed yet; runs on practitioner's machine |
| **Auditability** | Every scan version retained with manifest + changelog | Diligence findings may be referenced in investment memos and legal proceedings |

### 1.3 Constraints

- **Team size**: Solo developer (Shiva), so architectural decisions favor simplicity and testability over distributed-systems elegance.
- **AI model**: Claude Sonnet 4 (claude-sonnet-4-20250514). Rate-limited by tokens-per-minute; the pipeline must respect this.
- **No database**: All state lives in the filesystem (JSON, Markdown, Excel). This is intentional — every output is human-readable and git-friendly.
- **Offline-capable for preview**: The preview / classification / grading path must work without an API key. Only signal extraction and cross-referencing need Claude.
- **Crosslake methodology**: Signal taxonomy, scoring rubrics, and questionnaire structure are externally defined. The system conforms to them, not the other way around.

---

## 2. High-Level Architecture

### 2.1 Component Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                         STREAMLIT DASHBOARD                        │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ │
│  │ New Scan │ │  Deal    │ │  Doc     │ │  Market  │ │  DRL     │ │
│  │ + Preview│ │Dashboard │ │ Intake   │ │  Intel   │ │ Tracker  │ │
│  └────┬─────┘ └────┬─────┘ └──────────┘ └────┬─────┘ └────┬─────┘ │
│       │            │                          │            │       │
│       └────────────┴──────────┬───────────────┴────────────┘       │
│                               │ data_loader.py                     │
└───────────────────────────────┼─────────────────────────────────────┘
                                │ reads outputs/
                                │
┌───────────────────────────────┼─────────────────────────────────────┐
│                        ORCHESTRATION LAYER                         │
│                               │                                    │
│  ┌────────────────────────────┴────────────────────────────────┐   │
│  │              vdr_triage.py (Phase 0 Agent)                  │   │
│  │  Step 1: structure_mapper → Step 2: completeness_checker    │   │
│  │  Step 3: document_reader + signal_extractor (per batch)     │   │
│  │  Step 4: cross_referencer → grader → recommender → writer   │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                    │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │              quinn.py (Phase 4 Agent)                       │   │
│  │  Template Watch → Catalog Watch → Impact Analysis           │   │
│  │  Version Registry → Migration Packets                       │   │
│  └─────────────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────────────┘
                                │
                                │ uses
                                ▼
┌────────────────────────────────────────────────────────────────────┐
│                          TOOLS LAYER                               │
│                                                                    │
│  ┌─────────────────┐  ┌──────────────────┐  ┌──────────────────┐  │
│  │ Structure       │  │ Document         │  │ Signal           │  │
│  │ Mapper          │  │ Reader           │  │ Extractor        │  │
│  │ (classify docs) │  │ (PDF/DOCX/XLSX)  │  │ (Claude per-batch│) │
│  └─────────────────┘  └──────────────────┘  └──────────────────┘  │
│                                                                    │
│  ┌─────────────────┐  ┌──────────────────┐  ┌──────────────────┐  │
│  │ Cross           │  │ VDR              │  │ Practitioner     │  │
│  │ Referencer      │  │ Grader           │  │ Recommender      │  │
│  │ (Claude synth.) │  │ (deterministic)  │  │ (deterministic)  │  │
│  └─────────────────┘  └──────────────────┘  └──────────────────┘  │
│                                                                    │
│  ┌─────────────────┐  ┌──────────────────┐  ┌──────────────────┐  │
│  │ Completeness    │  │ DRL Parser       │  │ Quinn Schema     │  │
│  │ Checker         │  │ + Grader         │  │ Engine           │  │
│  │ (gap detection) │  │ (questionnaire)  │  │ (fingerprinting) │  │
│  └─────────────────┘  └──────────────────┘  └──────────────────┘  │
│                                                                    │
│  ┌─────────────────┐  ┌──────────────────┐  ┌──────────────────┐  │
│  │ Report Writer   │  │ Rate Limiter     │  │ Signal Store     │  │
│  │ (JSON + MD)     │  │ (TPM budget)     │  │ (cross-deal)     │  │
│  └─────────────────┘  └──────────────────┘  └──────────────────┘  │
└────────────────────────────────────────────────────────────────────┘
                                │
                                │ reads / writes
                                ▼
┌────────────────────────────────────────────────────────────────────┐
│                        DATA / CONFIG LAYER                         │
│                                                                    │
│  data/                          outputs/<company>/                 │
│  ├── batch_rules.json           ├── vdr_intelligence_brief.json   │
│  ├── expected_docs.json         ├── vdr_triage_report.md          │
│  ├── signal_catalog_v1.3.json   ├── vdr_completeness_report.md    │
│  ├── signal_pillars_v1.3.json   ├── _manifest.json                │
│  ├── lens_migration_map.json    ├── _changelog.md                 │
│  ├── drl_template_schema.json   ├── scan_history.json             │
│  └── drl_versions/              └── feedback_gate1.json           │
│                                                                    │
│  prompts/                                                          │
│  ├── vdr_signal_extraction.txt                                    │
│  ├── vdr_cross_reference.txt                                      │
│  └── vdr_completeness.txt                                         │
└────────────────────────────────────────────────────────────────────┘
```

### 2.2 Data Flow (Phase 0 Pipeline)

```
VDR Folder (PDFs, DOCX, XLSX, ZIPs)
    │
    ▼
┌──────────────────────────┐
│   1. Structure Mapper    │  Local only. No API.
│   batch_rules.json ──────│──→ Assigns each doc to 1 of 13 batch groups
│   ZIP auto-extraction    │──→ Extracts archives to temp dir
│                          │──→ Returns: inventory[], batch_groups{}
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│  2. Completeness Checker │  Local only. No API.
│  expected_docs.json ─────│──→ Sector-specific expected doc list
│                          │──→ Keyword matching + staleness check
│                          │──→ Returns: gap_report, chase_list
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│  3. Signal Extraction    │  Claude API × N batches (rate-limited)
│  FOR EACH batch group:   │
│    document_reader ──────│──→ Extract text, chunk to ≤32k chars
│    signal_extractor ─────│──→ Inject pillar defs + catalog signals
│                          │──→ Claude returns structured signals
│                          │──→ Rate limiter paces API calls
│  Returns: batch_results[]│
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│  4. Cross-Reference      │  Claude API × 1 (synthesis call)
│  All signals aggregated ─│──→ Claude sees everything at once
│                          │──→ Identifies compound risks
│                          │──→ Generates reading list + blind spots
│                          │──→ Returns: raw intelligence brief
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│  5. Deterministic Post-  │  Local only. No API.
│     Processing           │
│  vdr_grader ─────────────│──→ 4-dimension weighted score → A-F grade
│  practitioner_recommender│──→ Specialist scoring → effort estimates
│  blind_spot_merger ──────│──→ Combine AI + pipeline blind spots
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│  6. Report Writer +      │  Local only. No API.
│     Versioning           │
│  write briefs ───────────│──→ JSON + Markdown reports
│  manifest + changelog ───│──→ Version metadata, diffs vs prior scan
│  scan_history ───────────│──→ Append to version log
└──────────────────────────┘
```

### 2.3 API Contracts

**Claude API call pattern (signal extraction):**
- Model: `claude-sonnet-4-20250514`
- Max tokens: 4,096 per batch call
- Max chunks per call: 15 (each chunk ≤ 32k chars)
- Prompt template: `prompts/vdr_signal_extraction.txt` with `{pillar_definitions}`, `{catalog_signals}`, `{document_chunks}` injected
- Expected response: JSON array of signal objects

**Claude API call pattern (cross-reference):**
- Model: `claude-sonnet-4-20250514`
- Max tokens: 8,192
- Single call with all signals aggregated
- Prompt template: `prompts/vdr_cross_reference.txt`
- Expected response: Full intelligence brief JSON

**Output data contract (VDR Intelligence Brief):**
```json
{
  "company_name": "string",
  "deal_id": "string",
  "sector": "string",
  "deal_type": "string",
  "vdr_scan_timestamp": "ISO-8601",
  "overall_signal_rating": "RED | YELLOW | GREEN | UNKNOWN",
  "vdr_grade": "A | B | C | D | F",
  "lens_heatmap": {
    "<pillar_id>": {
      "rating": "RED | YELLOW | GREEN",
      "signal_count": "int",
      "red_count": "int",
      "top_signal": "string"
    }
  },
  "compound_risks": [],
  "prioritized_reading_list": [],
  "domain_slices": {},
  "signal_index": [],
  "material_signals": [],
  "assessment_blind_spots": [],
  "vdr_quality_grade": {},
  "practitioner_recommendation": []
}
```

### 2.4 Storage Choices

All state is filesystem-based by design.

| What | Format | Location | Why |
|---|---|---|---|
| Scan results | JSON + Markdown | `outputs/<company>/` | Human-readable, diffable, git-friendly |
| Batch rules | JSON | `data/batch_rules.json` | Pattern list, easy to extend |
| Signal catalog | JSON | `data/signal_catalog_v1.3.json` | Externally defined by Crosslake, versioned by Quinn |
| DRL responses | JSON | `data/drl_versions/<deal>/` | Per-submission snapshots for diff tracking |
| Template schemas | JSON | `data/drl_schema_history/` | Fingerprinted versions for migration |
| Scoring config | Python | `tools/scoring_config.py` | Constants with inline documentation |
| Prompts | Text files | `prompts/` | Separates prompt engineering from code |

**No database** — this is deliberate. At current scale (single user, <50 deals/year), a filesystem store has these advantages: every artifact is directly inspectable, version-controllable, and portable. The tradeoff is discussed in Section 5.

---

## 3. Component Deep Dives

### 3.1 Structure Mapper (`tools/structure_mapper.py`)

**Problem**: VDR folder structures vary wildly between deals. Some use numbered sections (1.1 Corporate, 1.8 Product & Technology), some use flat folders (Legal, Tech), some dump everything in root. The pipeline needs a consistent batch grouping regardless of source structure.

**Design**:
- Walk directory tree recursively
- If ZIP files found, extract to temp directory and include extracted files
- For each file, build a `match_text` from the full relative path (not just filename)
- Match `match_text` against ordered rules in `batch_rules.json`
- First matching rule wins; unmatched files go to `"general"` batch
- Return inventory (all files with metadata) and batch_groups (files grouped by batch ID)

**Key decision — full-path matching**: Early versions matched on filename only. This failed for VDRs with hierarchical folder structures where `"contract.pdf"` in `1.6 Material Contracts/` and `"contract.pdf"` in `1.8 Product & Technology/` should land in different batches. Matching against `"1.6 material contracts/contract.pdf"` solves this.

**Key decision — rule ordering**: Rules are evaluated top-to-bottom, first match wins. More specific rules (e.g., `"pen test"`) appear before general ones (e.g., `"corporate"`). This prevents false assignment of `"penetration test report.pdf"` to the corporate catch-all.

### 3.2 Signal Extractor (`tools/signal_extractor.py`)

**Problem**: Each batch of documents needs to be analyzed by Claude with the right context — only the pillar definitions and catalog signals relevant to that batch, not all 29 signals.

**Design**:
- `BATCH_TO_PILLARS` maps each batch group to 1-3 pillar IDs
- At extraction time, filter the v1.3 signal catalog to only signals belonging to the batch's pillars
- Inject filtered pillar definitions + catalog signals into the prompt template
- Cap at 15 chunks per API call to stay under ~20k tokens
- If a batch exceeds 15 chunks, make multiple calls and merge results
- Rate limiter paces calls based on TPM budget from `.env`

**Why batch-scoped pillar injection matters**: If you send Claude all 29 signals for every batch, two things happen. First, the prompt gets bigger than needed (cost). Second, Claude tries to find signals that aren't there — a batch of insurance policies will never contain CI/CD maturity signals, but Claude will try if you ask. Scoping the catalog down keeps extraction precise.

**Trade-off**: Occasionally a document in one batch contains evidence for a pillar not in that batch's scope. For example, a vendor contract (commercial_vendors batch) might mention SOC2 compliance details. The cross-referencer catches these in Step 4 because it sees all signals together. But the original extraction may miss the nuance. This is acceptable — the reading list directs practitioners to the source document anyway.

### 3.3 Cross-Referencer (`tools/cross_referencer.py`)

**Problem**: Individual batch extractions have no cross-batch context. A SOC2 gap in the security batch combined with a cloud migration in the infra batch might constitute a compound risk that neither batch would flag alone.

**Design**:
- Collect all signals from all batches, deduplicate by signal ID
- Build a single prompt with all signals + inventory + gap report
- One Claude call (8,192 max tokens) to synthesize:
  - Compound risks (multi-signal patterns)
  - Prioritized reading list (top 5-7 docs with estimated read time)
  - Domain slices (per-domain deep dives)
  - Pillar heatmap (RED/YELLOW/GREEN per pillar)
  - Blind spots (what the VDR doesn't cover)
- After Claude returns, merge AI-detected blind spots with pipeline-detected ones
- Attach deterministic VDR grade and practitioner recommendations (no API needed)

**Why one call, not seven**: A per-pillar synthesis would produce seven calls but lose cross-pillar intelligence. The most valuable findings — compound risks — are inherently cross-pillar. One call is also cheaper.

**Trade-off**: The 8,192 token output limit constrains how much detail Claude can produce. For very large VDRs with 100+ signals, Claude must prioritize. This is acceptable because the intelligence brief is a triage tool, not a final report — it tells practitioners where to look, not everything there is to find.

### 3.4 VDR Grader (`tools/vdr_grader.py`)

**Problem**: Partners need to know how trustworthy a scan is. A grade-C scan from an incomplete VDR is fundamentally different from a grade-A scan that found the same signal count.

**Design — four dimensions, deliberately weighted**:

1. **Document Presence (40%)** — Are the expected documents there? Weighted by urgency tier (CRITICAL docs count 3x, HIGH 2x, MEDIUM 1x). This is the single most important dimension because missing documents represent unknown unknowns.

2. **Document Readability (25%)** — Of the documents present, what fraction yielded at least one signal? A VDR full of scanned-image PDFs with no OCR is present but useless.

3. **Coverage Breadth (20%)** — How many of the 7 pillars have at least one signal? A VDR that deeply covers security but has zero product docs gives a skewed picture.

4. **Signal Extraction Yield (15%)** — Signals per document vs. a 2.5 benchmark. Low yield might mean documents are shallow or the extractor is struggling.

**Override rules**: Regulated sectors (healthcare-saas, fintech, insurtech) cap at grade C if any CRITICAL security document is missing, regardless of the weighted score. A healthcare company without a HIPAA risk assessment cannot get a B.

### 3.5 Batch-to-Pillar Mapping

This is the linchpin of the classification layer. The mapping determines which signals Claude looks for in which documents. Current mapping (v1.3):

```
Batch Group              → Pillar Coverage
─────────────────────────────────────────────────────────────────
security_pen_tests       → SecurityCompliance
security_compliance      → SecurityCompliance
security_posture         → SecurityCompliance, InfrastructureDeployment
infra_cloud_costs        → InfrastructureDeployment, RDSpendAssessment
infra_architecture       → TechnologyArchitecture, InfrastructureDeployment
infra_resilience         → InfrastructureDeployment
product_overview         → TechnologyArchitecture, SDLCProductManagement, DataAIReadiness
sdlc_process             → SDLCProductManagement, TechnologyArchitecture
human_resources          → OrganizationTalent
commercial_vendors       → SecurityCompliance, RDSpendAssessment
sales_market             → SDLCProductManagement, RDSpendAssessment
general                  → (all pillars — fallback)
```

**Design principle**: A batch should only claim a pillar if the documents in that batch would genuinely let a practitioner form a view on that pillar. Over-mapping dilutes the prompt context. Under-mapping creates false blind spots (as we discovered with TechnologyArchitecture missing from product_overview).

### 3.6 Quinn Agent (`agents/quinn.py`)

**Problem**: The DRL template and signal catalog are externally maintained artifacts that change periodically. When the template adds a new tab or the catalog adds a signal, every in-flight deal needs to know whether its existing data is still compatible.

**Design**:
- **Template Watch**: Parse DRL Excel → extract structural fingerprint (tab names, column headers, field counts) → compare against prior fingerprint → if changed, generate migration packet
- **Catalog Watch**: Parse signal catalog JSON → fingerprint (pillar IDs, signal IDs, counts) → same diff logic
- **Version Registry**: Each deal is tagged with the template_version and catalog_version it was last processed against. When either changes, Quinn identifies affected deals and their migration status
- **Migration Packets**: Describe what changed (fields added/removed/renamed), what needs re-processing, and what is backward-compatible

**Trade-off**: Quinn adds complexity. But without it, template changes silently break the DRL parser (hardcoded row ranges, column indices), and practitioners discover this only when results look wrong.

### 3.7 DRL Pipeline (`tools/drl_parser.py`, `tools/drl_grader.py`)

**Problem**: The DRL (Deal Response Library) is a structured questionnaire that target companies fill out. It has 137 fields across 5 tabs. Practitioners need to know: how completely was it filled? Which areas need follow-up?

**Design**:
- **Parser**: Uses Quinn's schema to locate cells. Reads each tab, extracts field values, computes per-field depth scores (0.0 empty → 0.3 bare minimum → 0.6 acceptable → 1.0 detailed). Numeric values score 0.8 (concrete data points are valuable even if short).
- **Grader**: Two-dimensional scoring — Completeness (50%, percentage of fields filled) + Depth (50%, average depth score). Per-tab breakdown + composite. Chase list of high-priority unfilled items.
- **Version Store**: Each DRL submission is versioned. Diffs show what improved between v1 and v2 of a company's responses.

---

## 4. Scale & Reliability

### 4.1 Load Estimation

| Metric | Current | Design ceiling |
|---|---|---|
| VDR documents per scan | 100-500 | ~2,000 |
| Document size | 50 KB – 50 MB | 200 MB (Excel) |
| Batch groups per scan | 6-13 | 13 max |
| Claude API calls per scan | 8-15 (extraction) + 1 (cross-ref) | ~40 + 1 |
| Tokens per scan | ~200k input, ~50k output | ~800k in, ~200k out |
| API cost per scan | $1-3 | ~$8-10 |
| Concurrent users | 1 | 1 (local-first) |
| Deals per year | 20-50 | 200 |

### 4.2 Rate Limiting

The `RateLimiter` reads `ANTHROPIC_RATE_LIMIT_TPM` from `.env` and paces API calls to stay within the tokens-per-minute budget. Before each Claude call, it estimates the token count for the next request and waits if the budget would be exceeded. This prevents 429 errors without adding unnecessary delay between calls.

**Smart pausing**: The limiter only pauses when needed. A batch of 3 small documents (5k tokens) runs immediately; a batch of 15 large chunks (18k tokens) might wait 10-30 seconds if the previous call was also large.

### 4.3 Failure Handling

| Failure mode | Current behavior | Impact |
|---|---|---|
| Claude API error on one batch | Batch returns empty signals, pipeline continues | Reduced signal coverage for that batch; logged as warning |
| Claude returns malformed JSON | `_extract_json()` attempts repair; falls back to empty result | Same as above |
| Unreadable document (encrypted PDF, corrupted XLSX) | `extract_text()` returns empty chunks; batch skipped for that doc | Document appears in inventory but yields no signals; readability score penalized |
| ZIP extraction fails | Warning logged, archive skipped | Documents inside that ZIP are invisible to the scan |
| Missing API key | Hard exit before pipeline starts | CLI prints error message |

**What's NOT handled well** (known gaps):

- No retry logic on transient API failures (429, 500, network timeout). The rate limiter prevents 429s proactively, but if one slips through, the batch fails.
- Batch failures are silent — the pipeline continues and produces a brief with partial data. The VDR grade's readability dimension will penalize this, but there's no explicit "3 batches failed" warning in the output.
- No circuit breaker. If the API is persistently down, the pipeline will attempt all batches and fail each one rather than fast-failing after N consecutive errors.

### 4.4 Observability

- **Logging**: Python `logging` module at INFO level throughout the pipeline. Each step logs document counts, signal counts, tokens used, and timing.
- **Manifests**: Every scan writes a `_manifest.json` with inventory, assessment metrics, and version metadata. These are the audit trail.
- **Scan history**: `scan_history.json` tracks the version progression — rating, signal count, and completeness score at each version.
- **No metrics/alerting**: This is a local tool, not a service. There's no Prometheus, no Grafana, no PagerDuty. If a scan fails, the practitioner sees it in the terminal.

---

## 5. Trade-off Analysis

### 5.1 Filesystem vs. Database

**Chose**: Filesystem (JSON + Markdown files)
**Trade-off**:

| Filesystem wins | Database wins |
|---|---|
| Every artifact is human-readable | Structured queries across deals |
| Git-diffable, version-controllable | Concurrent access |
| Zero setup, zero dependencies | Cross-deal aggregation |
| Portable — zip and share | Referential integrity |

**Revisit when**: Multi-user access is needed, or cross-deal analytics require querying signal patterns across 50+ deals. At that point, a SQLite or Postgres store with JSON columns would be the natural migration path. The filesystem artifacts would become the "source of truth" export format.

### 5.2 One Cross-Reference Call vs. Per-Pillar Calls

**Chose**: One aggregated call
**Trade-off**: Gains cross-pillar compound risk detection (the most valuable output). Loses depth — 8,192 output tokens across all pillars means each pillar gets ~1,200 tokens of analysis. A per-pillar approach would give each pillar its own 4k+ token budget.

**Revisit when**: Signal counts regularly exceed 100, and practitioners report that domain slices feel thin. Solution: add a "deep dive" mode that does per-pillar follow-up calls after the initial cross-reference.

### 5.3 Deterministic Grading vs. AI Grading

**Chose**: Deterministic (rule-based) for VDR grading and practitioner recommendation.
**Trade-off**: Deterministic scoring is reproducible, auditable, and free. But it can't capture qualitative factors — a VDR might have all expected documents but they're all 2-page summaries instead of detailed reports. The readability and yield dimensions partially compensate for this.

**Revisit when**: Partners challenge specific grades. The override mechanism (e.g., "regulated sector caps at C without HIPAA report") is the escape valve.

### 5.4 Batch Grouping vs. Per-Document Analysis

**Chose**: Group documents into batches, one Claude call per batch.
**Trade-off**: Batching gives cross-document context within a group (e.g., comparing two pen test reports) and keeps API cost manageable. But documents that don't fit neatly into one batch lose context — a vendor contract might contain security information that the commercial_vendors batch won't look for.

**Revisit when**: API costs drop enough to make per-document analysis feasible, or a "dual-pass" approach where the first pass classifies and the second pass extracts with full pillar scope.

### 5.5 v1.3 Signal Catalog (29 signals) vs. v1.1 (100 signals)

**Chose**: v1.3 with 29 signals across 7 pillars (down from 11 lenses, 100 signals).
**Trade-off**: Fewer signals means less granularity — v1.1 could distinguish "database backup policy" from "disaster recovery testing" as separate signals, while v1.3 bundles them under InfrastructureDeployment. But fewer signals means higher inter-rater reliability (different Claude calls are more likely to agree on signal assignment) and lower prompt token cost.

**Revisit when**: Practitioners report that the 29-signal taxonomy is too coarse for specific domain deep dives. Solution: hierarchical catalog with 29 top-level signals and optional sub-signals for specialists.

---

## 6. What to Revisit as the System Grows

### 6.1 Near-term (next 3 months)

- **Retry logic**: Add exponential backoff for transient Claude API failures. Current pipeline is fragile against network hiccups.
- **Batch failure surfacing**: When a batch extraction fails, propagate this as a visible warning in the intelligence brief and dashboard, not just a log line.
- **Hardcoded Excel row ranges**: Quinn was built to solve this, but 9 instances of hardcoded row references remain in the DRL parser. These break silently when the template changes.
- **Dashboard testing**: 0 automated tests for the 5 Streamlit pages. Low risk today (local tool), but will become a liability as the dashboard gets more complex.

### 6.2 Medium-term (3-6 months)

- **Multi-user access**: If a second practitioner needs simultaneous access, the filesystem store needs locking or a migration to SQLite. The dashboard would need authentication.
- **Cross-deal intelligence**: The Market Intel page is stub-level. Real cross-deal analytics (e.g., "how does this company's security posture compare to the last 10 healthcare-saas deals we scanned?") requires a queryable signal store, not just per-deal JSON files.
- **OCR layer**: Some VDRs contain scanned-image PDFs. The current pipeline gets zero text from these. An OCR pre-processing step (Tesseract or a cloud OCR service) would recover these documents.
- **Incremental rescans**: Currently, a rescan re-processes every document. For large VDRs where only 10 of 500 documents changed, this wastes API budget. Manifest-based diff could skip unchanged documents.

### 6.3 Long-term (6-12 months)

- **Full Diligence Agent (Phase 1)**: Deep-dive analysis across all 8 domains, with interview preparation guides and technical questionnaire generation. This is the next major agent after Phase 0 + Phase 4.
- **Value Creation Agent (Phase 5)**: Post-acquisition 100-day plans, modernization roadmaps, and cost optimization recommendations. Requires deal-close context that Phase 0 doesn't have.
- **Hosted deployment**: Moving from local-first to a hosted service for PE firms. This triggers database migration, auth, multi-tenancy, and audit-logging requirements simultaneously.
- **Model routing**: Different pipeline steps have different quality/cost/speed requirements. Signal extraction might run on Haiku (cheap, fast, sufficient quality for structured extraction). Cross-referencing needs Sonnet (synthesis quality matters). Grading is already deterministic.

---

## Appendix A: File Inventory

| Path | Lines | Purpose |
|---|---|---|
| `agents/vdr_triage.py` | 586 | Phase 0 orchestrator |
| `agents/quinn.py` | 478 | Schema governance agent |
| `tools/structure_mapper.py` | 148 | VDR classification |
| `tools/document_reader.py` | 225 | Multi-format text extraction |
| `tools/signal_extractor.py` | 434 | Claude batch extraction |
| `tools/cross_referencer.py` | 313 | Claude synthesis |
| `tools/vdr_grader.py` | 339 | Deterministic A-F grading |
| `tools/completeness_checker.py` | 281 | Gap detection |
| `tools/practitioner_recommender.py` | 344 | Specialist scoring |
| `tools/drl_parser.py` | 447 | DRL questionnaire parsing |
| `tools/drl_grader.py` | 338 | DRL response scoring |
| `tools/quinn_schema_engine.py` | 847 | Template fingerprinting |
| `tools/quinn_version_registry.py` | 405 | Version compatibility matrix |
| `tools/report_writer.py` | 181 | JSON + Markdown output |
| `tools/scoring_config.py` | 117 | Centralized scoring constants |
| `tools/rate_limiter.py` | ~80 | TPM-based API pacing |
| `tools/signal_store.py` | ~100 | Cross-deal signal patterns |
| `dashboard/app.py` | ~200 | Streamlit home page |
| `dashboard/pages/` (5 files) | ~2,000 | Dashboard pages |
| `dashboard/utils/data_loader.py` | ~300 | Output file reader |
| `tests/` (2 files) | ~1,200 | 151 tests |

**Total**: ~8,500 lines of Python across 24 tool files, 2 agents, 5 dashboard pages, and 2 test suites.

## Appendix B: v1.3 Signal Taxonomy

**7 Pillars, 29 Signals:**

| Pillar | ID Prefix | Signal Count | Focus |
|---|---|---|---|
| TechnologyArchitecture | TA | 5 | Scalability, resilience, complexity, cloud posture, tech debt |
| SecurityCompliance | SC | 5 | SOC2, HIPAA, pen testing, vulnerability mgmt, OSS risk |
| OrganizationTalent | OT | 4 | Team structure, seniority mix, key-person risk, hiring |
| DataAIReadiness | DA | 3 | Data models, ML maturity, AI governance |
| RDSpendAssessment | RS | 5 | R&D spend ratio, capitalization, vendor costs, staffing |
| InfrastructureDeployment | ID | 5 | Cloud infra, DR/BC, CI/CD, observability |
| SDLCProductManagement | SP | 2 | SDLC maturity, deployment velocity, product roadmap |
