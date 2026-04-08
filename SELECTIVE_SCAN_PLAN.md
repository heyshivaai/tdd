# Selective Scan Architecture — "Scan What Matters First"

## The Problem

640 documents × 50 API calls × rate limiting = ~2 hours before a partner sees anything.
Partners don't need all 640 docs analyzed to start forming a view. They need the **tech-relevant** documents scanned first, findings on screen in 20-30 minutes, then the option to drill into remaining categories on demand.

---

## Design: Three-Phase Selective Scan

### Phase 1 — Instant Classification (0 API calls, <5 seconds)

**What happens:** The moment a VDR path is provided, the structure mapper runs (already instant) and classifies every document into batch groups using the existing `batch_rules.json`. We add a new concept: **scan tiers**.

```
TIER 1 — "Core Tech" (auto-selected, scan immediately)
├── security_pen_tests      → SecurityCompliance
├── security_compliance     → SecurityCompliance
├── security_posture        → SecurityCompliance + InfrastructureDeployment
├── infra_cloud_costs       → InfrastructureDeployment + RDSpendAssessment
├── infra_architecture      → TechnologyArchitecture + InfrastructureDeployment
├── infra_resilience        → InfrastructureDeployment
├── product_overview        → TechnologyArchitecture + SDLCProductManagement + DataAIReadiness
└── sdlc_process            → SDLCProductManagement + TechnologyArchitecture

TIER 2 — "Supporting Context" (user picks)
├── human_resources         → OrganizationTalent
├── commercial_vendors      → SecurityCompliance + RDSpendAssessment
└── sales_market            → SDLCProductManagement + RDSpendAssessment

TIER 3 — "Uncategorised" (user picks)
└── general                 → unknown relevance
```

**Why this split:** Tier 1 covers 5 of 7 pillars completely and partially covers the remaining 2. A partner gets a substantive tech view from Tier 1 alone. Tier 2 adds organizational and commercial context. Tier 3 is the long tail.

**No Quinn needed here.** The existing batch_rules.json already classifies by filename/path patterns. Quinn's role stays upstream (template/catalog versioning). Adding an AI classification step before scanning would add latency and complexity for marginal gain — the pattern matching is already accurate for well-structured VDRs.

### Phase 2 — Priority Scan (Tier 1 only, ~30-45 min for 400 docs)

**What happens:** Pipeline runs exactly as today, but only processes selected batches. Unselected batches are skipped entirely — no reading, no extraction, no API calls.

After Tier 1 completes:
- Domain analysis runs on the 7 pillars (with whatever signal coverage Tier 1 provides)
- Cross-reference synthesizes findings
- VDR grade is calculated (marked as "partial" since not all docs scanned)
- Deal Intel page lights up with signals, findings, chase list

**The partner can now work** while remaining documents wait.

### Phase 3 — On-Demand Incremental Scan (user triggers per-category)

**What happens:** Partner reviews Tier 1 findings, then goes back to the scan page. They see:

```
✅ Scanned (Tier 1)                          Remaining
─────────────────────                        ─────────────
✓ Security — Pen Tests (12 docs, 8 signals)  ☐ Organisation & Talent (45 docs)
✓ Security — Compliance (23 docs, 14 signals) ☐ Commercial — Vendors (67 docs)
✓ Security — Posture (18 docs, 11 signals)   ☐ Commercial — Sales/GTM (89 docs)
✓ Infra — Cloud Costs (34 docs, 6 signals)   ☐ Uncategorised (23 docs)
✓ Infra — Architecture (28 docs, 19 signals)
✓ Infra — DR/BC (15 docs, 5 signals)         [Scan Selected →]
✓ Product — Overview (41 docs, 22 signals)
✓ Engineering — SDLC (31 docs, 12 signals)

Total: 202 docs scanned | 97 signals | 438 docs remaining
```

Partner checks the boxes they want, hits "Scan Selected", and those batches process incrementally. Existing signals and domain findings are preserved — the new batch results merge into the existing scan.

---

## New Scan Page UI Redesign

### Before Preview (unchanged)
Deal details form + VDR path input → [Preview VDR]

### After Preview (NEW: batch picker)

```
┌─────────────────────────────────────────────────────────────────────┐
│  VDR Preview: Horizon Healthcare — 640 documents mapped            │
│                                                                     │
│  ┌─ Scan Scope ──────────────────────────────────────────────────┐ │
│  │                                                                │ │
│  │  CORE TECH (recommended — covers 5/7 pillars)                 │ │
│  │  ☑ Security — Pen Tests ................ 12 docs    ⬡⬡       │ │
│  │  ☑ Security — Compliance ............... 23 docs    ⬡⬡       │ │
│  │  ☑ Security — Posture & Controls ....... 18 docs    ⬡⬡⬡      │ │
│  │  ☑ Infra — Cloud Costs ................ 34 docs    ⬡⬡       │ │
│  │  ☑ Infra — Architecture & Monitoring ... 28 docs    ⬡⬡⬡      │ │
│  │  ☑ Infra — DR / BC / Change Mgmt ...... 15 docs    ⬡        │ │
│  │  ☑ Product — Overview & AI ............. 41 docs    ⬡⬡⬡      │ │
│  │  ☑ Engineering — SDLC & Deployment ..... 31 docs    ⬡⬡       │ │
│  │                                                    ────────── │ │
│  │                                           202 docs selected   │ │
│  │                                                                │ │
│  │  SUPPORTING CONTEXT                                           │ │
│  │  ☐ Organisation & Talent ............... 45 docs    ⬡        │ │
│  │  ☐ Commercial — Vendors & Licensing .... 67 docs    ⬡⬡       │ │
│  │  ☐ Commercial — Sales, GTM & Pricing ... 89 docs    ⬡⬡       │ │
│  │                                                                │ │
│  │  UNCATEGORISED                                                │ │
│  │  ☐ Uncategorised ....................... 237 docs   ?         │ │
│  │                                                                │ │
│  │  [Select All]  [Core Tech Only]  [Deselect All]               │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                     │
│  Estimated time: ~25 min (202 docs) │ Pillar coverage: 5/7 full   │
│                                                                     │
│  [ Start Scan → ]                                                  │
└─────────────────────────────────────────────────────────────────────┘
```

The ⬡ symbols represent pillar coverage dots — each dot = one pillar this batch contributes to. Partners can see at a glance which batches feed which analysis.

### Post-Scan: Incremental View

After a partial scan completes, the New Scan page shows a **split view**:

**Left column — Already Scanned:**
Each batch shows: label, doc count, signal count, grade contribution. Green checkmarks. Read-only.

**Right column — Remaining:**
Checkboxes for each unscanned batch. Doc count, estimated time per batch. "Scan Selected" button at bottom.

When an incremental scan runs:
- New batch results merge into existing `signal_timeline/`
- Domain analysis re-runs with expanded signal set
- Cross-reference re-runs to update brief
- VDR grade recalculates (partial → fuller)
- Deal Intel page updates with richer findings

---

## Data Model Changes

### scan_registry.json — New Fields

```json
{
  "HORIZON": {
    "status": "completed",
    "scan_mode": "selective",           // NEW: "full" | "selective"
    "scanned_batches": [                // NEW: which batches were processed
      "security_pen_tests",
      "security_compliance",
      "security_posture",
      "infra_cloud_costs",
      "infra_architecture",
      "infra_resilience",
      "product_overview",
      "sdlc_process"
    ],
    "pending_batches": [                // NEW: what's left to scan
      "human_resources",
      "commercial_vendors",
      "sales_market",
      "general"
    ],
    "total_docs": 640,
    "scanned_docs": 202,               // NEW: docs actually processed
    "version": 3,
    "progress": {
      "batches_total": 8,              // only selected batches
      "batches_done": 8,
      "signals_found": 97
    }
  }
}
```

### batch_tiers.json — New Config File

```json
{
  "tiers": {
    "core_tech": {
      "label": "Core Tech",
      "description": "Technology, security, infrastructure, and engineering documents",
      "auto_select": true,
      "batch_groups": [
        "security_pen_tests",
        "security_compliance",
        "security_posture",
        "infra_cloud_costs",
        "infra_architecture",
        "infra_resilience",
        "product_overview",
        "sdlc_process"
      ]
    },
    "supporting_context": {
      "label": "Supporting Context",
      "description": "Organisational, commercial, and vendor documents",
      "auto_select": false,
      "batch_groups": [
        "human_resources",
        "commercial_vendors",
        "sales_market"
      ]
    },
    "uncategorised": {
      "label": "Uncategorised",
      "description": "Documents that didn't match any known pattern",
      "auto_select": false,
      "batch_groups": [
        "general"
      ]
    }
  }
}
```

---

## Pipeline Changes (agents/vdr_triage.py)

### New Parameter: `selected_batches`

```python
def run_triage(
    vdr_path: str,
    company_name: str,
    deal_id: str,
    sector: str,
    deal_type: str,
    version: int | None = None,
    selected_batches: list[str] | None = None,  # NEW
    merge_into_existing: bool = False,           # NEW — for incremental scans
) -> dict:
```

### Batch Filtering Logic

```python
# After structure mapping
all_batch_groups = vdr_map["batch_groups"]

if selected_batches:
    # Only process selected batches
    active_batches = {k: v for k, v in all_batch_groups.items() if k in selected_batches}
    pending_batches = [k for k in all_batch_groups if k not in selected_batches]
else:
    # Full scan — process everything
    active_batches = all_batch_groups
    pending_batches = []

# Register with selective metadata
register_scan(
    company_name=company_name,
    scan_mode="selective" if selected_batches else "full",
    scanned_batches=list(active_batches.keys()),
    pending_batches=pending_batches,
    doc_count=sum(len(docs) for docs in active_batches.values()),
    batch_count=len(active_batches),
    ...
)
```

### Incremental Merge Logic

```python
if merge_into_existing:
    # Load existing signals from prior partial scan
    existing_signals = _load_existing_signals(company_name)
    all_signals_flat = existing_signals + new_signals_flat

    # Merge into existing scan entry (don't create new version)
    update_scan_batches(
        company_name,
        newly_scanned=list(active_batches.keys()),
    )
else:
    all_signals_flat = new_signals_flat
```

After incremental merge:
- Domain analysis re-runs with ALL signals (old + new)
- Cross-reference re-synthesizes
- Grade recalculates with broader coverage
- Brief updates with new insights

---

## Deal Intel Page Updates

### Partial Scan Indicator

When scan_mode is "selective" and pending_batches is non-empty, the Deal Intel hero shows:

```
┌──────────────────────────────────────────────────────────────┐
│  Horizon Healthcare — Deal Intel                             │
│  ⚡ Partial scan: 202/640 docs analyzed (Core Tech)          │
│  4 document categories available for additional scanning →   │
└──────────────────────────────────────────────────────────────┘
```

The "→" links back to New Scan page where they can trigger incremental scans.

### Pillar Coverage Gaps

Pillars with incomplete data show a "partial coverage" badge:
- OrganizationTalent: "⚠️ No HR documents scanned — add Organisation & Talent batch for full coverage"
- RDSpendAssessment: "⚠️ Partial — vendor/licensing documents not yet scanned"

These are actionable nudges, not just warnings.

---

## Implementation Plan

### Step 1: Config + Data Model (30 min)
- Create `data/batch_tiers.json`
- Add `scan_mode`, `scanned_batches`, `pending_batches`, `scanned_docs` to scan_registry schema
- Add `update_scan_batches()` function to scan_registry.py
- Add `_load_existing_signals()` helper to vdr_triage.py

### Step 2: Pipeline — Selective + Incremental (1 hour)
- Add `selected_batches` and `merge_into_existing` params to `run_triage()`
- Add batch filtering logic after structure mapping
- Add incremental merge logic for signals, domain analysis, cross-reference
- Update CLI to accept `--batches` flag (comma-separated batch IDs)
- Ensure checkpoints work correctly with partial scans

### Step 3: New Scan UI — Batch Picker (1.5 hours)
- Load batch_tiers.json for tier grouping
- Render checkbox grid with tier headers, doc counts, pillar dots
- Quick-select buttons: "Core Tech Only", "Select All", "Deselect All"
- Time/cost estimate updates dynamically based on selection
- Pass selected_batches to pipeline subprocess
- Post-scan: show scanned vs remaining split view
- "Scan Selected" button for incremental runs (passes merge_into_existing=True)

### Step 4: Deal Intel — Partial Scan Awareness (30 min)
- Read scan_mode and pending_batches from registry
- Show partial scan indicator in hero
- Show per-pillar coverage gaps with actionable links to New Scan
- All existing functionality (signals, findings, chase list) works unchanged

### Step 5: Verification (30 min)
- Test: Core Tech only scan on Horizon VDR
- Test: Incremental scan adding human_resources batch
- Test: Verify domain findings merge correctly
- Test: Verify Deal Intel renders partial + full states
- Test: Verify grade recalculates on incremental merge

---

## What This Gets You

**Before:** 640 docs → 2 hours → partner sees results
**After:** 202 Core Tech docs → 25-30 min → partner sees findings, starts working → adds more categories on demand

The partner is in control. They see what's been scanned, what's left, and they choose when to go deeper. No wasted API calls on marketing decks when they need the pen test results.

---

## What This Does NOT Change

- Signal extraction quality (same prompts, same model)
- Domain analysis depth (same 7 pillar agents)
- Output contract (same JSON shape)
- Quinn's role (still upstream template/catalog versioning)
- Scoring rubric (same 4-dimension grading, just marked "partial" when incomplete)
