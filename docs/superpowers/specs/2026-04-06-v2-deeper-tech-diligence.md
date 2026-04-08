# V2 — Deeper Tech Diligence: System Design & PRD

**Date:** 2026-04-06
**Author:** Shiva + Claude
**Status:** DRAFT — Pending Alignment
**Builds on:** `feature/vdr-auto-triage` worktree (Phase 0 / Phase A complete)

---

## 1. Problem Statement

Phase 0 VDR Auto-Triage is working — it scans a VDR folder, extracts signals across 11 lenses, grades completeness, and surfaces compound risks. But practitioner feedback says: **"Go deeper on technology."**

Three specific pain points remain unaddressed:

1. **Signal taxonomy drift.** The working code uses an ad-hoc 11-lens set (Architecture, Codebase, Security...) but Crosslake has now finalized a reclassified **Top 100 Signal Catalog (v1.1)** with a different, validated 11-lens taxonomy. The system must align to this canonical source of truth — every extraction prompt, heatmap, domain slice, and scoring mechanism needs to speak the same language as the practitioners.

2. **The questionnaire chase is brutal.** Crosslake sends an OOTB Due Diligence Request List (DRL) with 5 tabs (Technology, Software Dev & Tools, Systems Security & Infra, R&D Spend, Census Input). Clients return it partially filled, often with shallow answers. Practitioners manually diff what was answered vs. not, judge quality, then go back to ask for more. This cycle repeats 3-5 times per deal. There is no system tracking what % is complete, what improved between versions, or whether answers are actually useful.

3. **VDR document drift.** Between the initial VDR scan and full diligence, new documents appear in the data room. Practitioners need to know what's new without re-reading everything. The current rescan feature detects version changes but doesn't surface a practitioner-friendly diff or connect new documents to existing signal gaps.

**Impact of not solving:** Practitioners spend 2-3 days per deal on questionnaire chase alone. Signal extraction uses a taxonomy that doesn't match the firm's validated methodology. New VDR documents get missed or require full re-triage.

---

## 2. Goals

1. **Canonical signal alignment:** All extraction, scoring, and reporting uses the v1.1 Top 100 Signal Catalog taxonomy. A signal extracted by the system maps directly to a signal ID a Crosslake practitioner would recognize.
2. **Questionnaire completeness in < 60 seconds:** After each DRL Excel upload, the system produces a completeness score (% filled) and quality score (response depth) per tab within one minute. No manual diffing.
3. **Version-over-version tracking:** Every re-upload of the DRL shows exactly what changed — new answers, improved answers, still-empty fields — with a composite readiness score trending over time.
4. **Auto-diff on VDR rescan:** When a new VDR folder is scanned for the same deal, the system automatically produces a changelog (new docs, removed docs, modified docs) and connects new documents to previously identified signal gaps.
5. **Practitioner-ready outputs:** Every new feature produces artifacts a practitioner can act on immediately — chase lists, quality flags, gap-to-signal mappings — without needing to interpret raw data.

---

## 3. Non-Goals

1. **AI-generated questionnaire answers.** The system grades and tracks responses; it does not auto-fill answers on behalf of the target company.
2. **Real-time collaboration / multi-user editing.** This is a single-user local tool. No concurrent editing of questionnaires.
3. **Replacing the DRL template.** We ingest Crosslake's existing Excel template as-is. We don't redesign the questionnaire format.
4. **Full Phase 1 agent orchestration.** This build deepens Phase 0 capabilities. Phase 1 agents (Alex, Morgan, Jordan, etc.) remain future work.
5. **Pinecone / cloud dependencies.** All features work fully local. Signal store integration is orthogonal.

---

## 4. System Design

### 4.1 Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Streamlit Dashboard                         │
│  ┌──────────┐  ┌──────────────┐  ┌──────────┐  ┌───────────────┐  │
│  │ New Scan  │  │Deal Dashboard│  │ Doc      │  │ Market Intel  │  │
│  │  (VDR)   │  │ (Gates)      │  │ Intake   │  │               │  │
│  └────┬─────┘  └──────┬───────┘  └────┬─────┘  └───────────────┘  │
│       │               │               │                            │
│  ┌────┴───────────────┴───────────────┴──────────────────────┐     │
│  │              NEW: Questionnaire Tracker Tab                │     │
│  │  ┌─────────────┐  ┌──────────────┐  ┌─────────────────┐  │     │
│  │  │ DRL Upload  │  │ Completeness │  │ Quality Grader  │  │     │
│  │  │ & Version   │  │ Dashboard    │  │ & Trend View    │  │     │
│  │  │ Detector    │  │              │  │                 │  │     │
│  │  └──────┬──────┘  └──────┬───────┘  └────────┬────────┘  │     │
│  └─────────┼────────────────┼───────────────────┼────────────┘     │
└────────────┼────────────────┼───────────────────┼──────────────────┘
             │                │                   │
   ┌─────────▼────────────────▼───────────────────▼──────────────┐
   │                      TOOLS LAYER                            │
   │                                                             │
   │  ┌─────────────────┐  ┌──────────────────┐                  │
   │  │ NEW:            │  │ NEW:             │                  │
   │  │ drl_parser.py   │  │ drl_grader.py   │                  │
   │  │ - parse tabs    │  │ - completeness   │                  │
   │  │ - detect fields │  │ - depth scoring  │                  │
   │  │ - version diff  │  │ - composite      │                  │
   │  └────────┬────────┘  └────────┬─────────┘                  │
   │           │                    │                             │
   │  ┌────────▼────────────────────▼─────────────────────────┐  │
   │  │ NEW: drl_version_store.py                             │  │
   │  │ - per-deal version history                            │  │
   │  │ - field-level diff engine                             │  │
   │  │ - trend computation                                   │  │
   │  └───────────────────────────────────────────────────────┘  │
   │                                                             │
   │  ┌───────────────────────────────────────────────────────┐  │
   │  │ MODIFIED: signal_extractor.py                         │  │
   │  │ - v1.1 lens taxonomy                                  │  │
   │  │ - 100 signal IDs in extraction prompt                 │  │
   │  └───────────────────────────────────────────────────────┘  │
   │                                                             │
   │  ┌───────────────────────────────────────────────────────┐  │
   │  │ MODIFIED: vdr_grader.py, cross_referencer.py          │  │
   │  │ - v1.1 lens alignment                                 │  │
   │  │ - domain slices remapped                              │  │
   │  └───────────────────────────────────────────────────────┘  │
   │                                                             │
   │  ┌───────────────────────────────────────────────────────┐  │
   │  │ ENHANCED: vdr_triage.py (agent)                       │  │
   │  │ - auto-diff on rescan (changelog generation)          │  │
   │  │ - gap-to-new-doc matching                             │  │
   │  └───────────────────────────────────────────────────────┘  │
   └─────────────────────────────────────────────────────────────┘
             │
   ┌─────────▼───────────────────────────────────────────────────┐
   │                      DATA LAYER                             │
   │                                                             │
   │  MODIFIED:                                                  │
   │  ├── data/signal_lenses_v1.1.json   (new canonical lenses) │
   │  ├── data/signal_catalog_v1.1.json  (100 signal defs)      │
   │  ├── data/drl_template_schema.json  (tab/field definitions) │
   │                                                             │
   │  PER-DEAL (outputs/<company>/):                             │
   │  ├── questionnaire/                                         │
   │  │   ├── drl_v1.xlsx, drl_v2.xlsx, ...                     │
   │  │   ├── drl_state.json       (latest parsed state)        │
   │  │   ├── drl_history.json     (version log + scores)       │
   │  │   └── drl_diff_v1_v2.json  (field-level diff)           │
   │  ├── vdr_changelog_v1_v2.json (doc-level diff)             │
   │  └── vdr_intelligence_brief.json (updated w/ v1.1 lenses)  │
   └─────────────────────────────────────────────────────────────┘
```

### 4.2 Component Design

#### 4.2.1 Feature 1: v1.1 Signal Taxonomy Alignment

**What changes:**

The v1.1 catalog defines 100 signals across 11 lenses. The current code uses a different 11-lens taxonomy. This is a **schema migration** — every component that references lens IDs must update.

**New data files:**

`data/signal_lenses_v1.1.json` — replaces current `signal_lenses.json`:

```json
{
  "version": "1.1",
  "lenses": [
    {
      "id": "StrategyRoadmap",
      "label": "Strategy & Roadmap Alignment",
      "signal_count": 8,
      "signal_ids": ["SA-01", "SA-02", "SA-03", "SA-04", "SA-05", "SA-06", "SA-07", "SA-08"],
      "temporal_mix": {"current_health": 3, "dual": 3, "future_readiness": 2}
    },
    {
      "id": "TechnologyArchitecture",
      "label": "Technology & Architecture",
      "signal_count": 10,
      "signal_ids": ["TA-01", "TA-02", "TA-03", "TA-04", "TA-05", "TA-06", "TA-07", "TA-08", "TA-09", "TA-10"]
    },
    {
      "id": "EngineeringDelivery",
      "label": "Engineering & Delivery",
      "signal_count": 10,
      "signal_ids": ["ED-01", "ED-02", "ED-03", "ED-04", "ED-05", "ED-06", "ED-07", "ED-08", "ED-09", "ED-10"]
    },
    {
      "id": "OperationalEfficiency",
      "label": "Operational Efficiency & Scalability",
      "signal_count": 8,
      "signal_ids": ["OE-01", "OE-02", "OE-03", "OE-04", "OE-05", "OE-06", "OE-07", "OE-08"]
    },
    {
      "id": "InfrastructureTechnology",
      "label": "Infrastructure & Technology",
      "signal_count": 8,
      "signal_ids": ["IT-01", "IT-02", "IT-03", "IT-04", "IT-05", "IT-06", "IT-07", "IT-08"]
    },
    {
      "id": "CybersecurityCompliance",
      "label": "Cybersecurity & Compliance",
      "signal_count": 10,
      "signal_ids": ["CC-01", "CC-02", "CC-03", "CC-04", "CC-05", "CC-06", "CC-07", "CC-08", "CC-09", "CC-10"]
    },
    {
      "id": "OrganizationTalent",
      "label": "Organization & Talent",
      "signal_count": 10,
      "signal_ids": ["OT-01", "OT-02", "OT-03", "OT-04", "OT-05", "OT-06", "OT-07", "OT-08", "OT-09", "OT-10"]
    },
    {
      "id": "ProductCustomerExperience",
      "label": "Product & Customer Experience",
      "signal_count": 10,
      "signal_ids": ["PC-01", "PC-02", "PC-03", "PC-04", "PC-05", "PC-06", "PC-07", "PC-08", "PC-09", "PC-10"]
    },
    {
      "id": "DataAIReadiness",
      "label": "Data & AI Readiness",
      "signal_count": 10,
      "signal_ids": ["DA-01", "DA-02", "DA-03", "DA-04", "DA-05", "DA-06", "DA-07", "DA-08", "DA-09", "DA-10"]
    },
    {
      "id": "ThirdPartyVendorRisk",
      "label": "Third-Party & Vendor Risk",
      "signal_count": 8,
      "signal_ids": ["TV-01", "TV-02", "TV-03", "TV-04", "TV-05", "TV-06", "TV-07", "TV-08"]
    },
    {
      "id": "ValueCreationPotential",
      "label": "Value Creation Potential",
      "signal_count": 8,
      "signal_ids": ["VC-01", "VC-02", "VC-03", "VC-04", "VC-05", "VC-06", "VC-07", "VC-08"]
    }
  ]
}
```

`data/signal_catalog_v1.1.json` — full 100 signal definitions parsed from the Excel catalog:

```json
{
  "version": "1.1",
  "signals": [
    {
      "signal_id": "SA-01",
      "lens_id": "StrategyRoadmap",
      "name": "Technology Modernization Index",
      "technical_definition": "...",
      "conviction_weight": "High",
      "temporal_orientation": "Current Health",
      "primary_data_sources": ["..."],
      "contextual_modifiers": "...",
      "interpretation_guidance": "..."
    }
  ]
}
```

**Files modified:**

| File | Change |
|------|--------|
| `data/signal_lenses.json` | Replaced by `signal_lenses_v1.1.json` |
| `tools/signal_extractor.py` | Extraction prompt references v1.1 lens IDs and signal definitions. Claude is asked to map observations to specific signal IDs (SA-01, TA-01, etc.) when possible. |
| `prompts/vdr_signal_extraction.txt` | Updated to include v1.1 lens taxonomy and signal catalog as context. Prompt instructs: "Map each finding to the closest signal from the catalog. Use the signal_id if there is a clear match. If the observation doesn't map to any catalog signal, assign the lens_id and mark `catalog_match: false`." |
| `prompts/vdr_cross_reference.txt` | Domain slices remapped to v1.1 groupings (see below). |
| `tools/cross_referencer.py` | Domain slices updated: `security_slice` → CybersecurityCompliance + ThirdPartyVendorRisk; `infra_slice` → InfrastructureTechnology + OperationalEfficiency; `product_slice` → ProductCustomerExperience + StrategyRoadmap; NEW `engineering_slice` → TechnologyArchitecture + EngineeringDelivery; NEW `data_ai_slice` → DataAIReadiness. |
| `tools/vdr_grader.py` | Coverage breadth dimension now counts v1.1 lenses. |
| `tools/practitioner_recommender.py` | Specialist mapping updated to v1.1 lens IDs. |
| `dashboard/utils/data_loader.py` | `LENS_NAMES` list updated. |
| All dashboard pages | Lens references updated. |

**Backward compatibility:** Old HORIZON outputs retain old lens names. A `lens_migration_map.json` provides old→new mapping so existing reports can be displayed with either taxonomy.

```json
{
  "Architecture": "TechnologyArchitecture",
  "Codebase": "EngineeringDelivery",
  "Security": "CybersecurityCompliance",
  "Product": "ProductCustomerExperience",
  "DevOps": "OperationalEfficiency",
  "Team": "OrganizationTalent",
  "Data": "DataAIReadiness",
  "CommercialTech": "ThirdPartyVendorRisk",
  "AIMLReadiness": "DataAIReadiness",
  "RegulatoryCompliance": "CybersecurityCompliance",
  "FinancialCost": "ValueCreationPotential"
}
```

**Signal extraction output (updated):**

```json
{
  "signal_id": "SIG-001",
  "catalog_signal_id": "CC-03",
  "catalog_match": true,
  "lens_id": "CybersecurityCompliance",
  "lens_label": "Cybersecurity & Compliance",
  "rating": "RED",
  "confidence": "HIGH",
  "temporal_orientation": "Current Health",
  "title": "SOC2 Type II audit expired 14 months ago",
  "observation": "...",
  "evidence_quote": "...",
  "source_doc": "...",
  "deal_implication": "...",
  "conviction_weight": "High"
}
```

---

#### 4.2.2 Feature 2: OOTB Questionnaire Tracking System

**Workflow:**

```
Practitioner sends DRL Excel to target company
                    │
                    ▼
    Company returns partially-filled DRL (v1)
                    │
                    ▼
    ┌───────────────────────────────────┐
    │  Practitioner uploads DRL to UI   │
    │  (Excel re-upload each version)   │
    └───────────────┬───────────────────┘
                    │
                    ▼
    ┌───────────────────────────────────┐
    │  drl_parser.py                    │
    │  - Detects 5 tabs                 │
    │  - Extracts field-level data      │
    │  - Normalizes to canonical schema │
    └───────────────┬───────────────────┘
                    │
                    ▼
    ┌───────────────────────────────────┐
    │  drl_version_store.py             │
    │  - Assigns version number         │
    │  - Saves raw Excel + parsed state │
    │  - If v2+: computes field diff    │
    └───────────────┬───────────────────┘
                    │
                    ▼
    ┌───────────────────────────────────┐
    │  drl_grader.py                    │
    │  - Completeness: % fields filled  │
    │  - Depth: response quality score  │
    │  - Composite: (0.5 × C) + (0.5 × D) │
    │  - Per-tab and overall grades     │
    └───────────────┬───────────────────┘
                    │
                    ▼
    ┌───────────────────────────────────┐
    │  Dashboard: Questionnaire Tracker │
    │  - Per-tab completeness bars      │
    │  - Quality heatmap                │
    │  - Version trend chart            │
    │  - Gap list → chase email draft   │
    └───────────────────────────────────┘
```

##### NEW TOOL: `tools/drl_parser.py`

**Purpose:** Parse the Crosslake OOTB DRL Excel file into a structured, version-comparable format.

**Tab schema** (`data/drl_template_schema.json`):

```json
{
  "version": "1.0",
  "tabs": {
    "Technology": {
      "id": "technology",
      "type": "request_list",
      "key_columns": {
        "function": "Function",
        "request": "Request",
        "date_requested": "Date Requested",
        "date_responded": "Date Responded",
        "dataroom_location": "Dataroom Location"
      },
      "field_identification": "each_row_is_a_field",
      "maps_to_lenses": ["StrategyRoadmap", "TechnologyArchitecture", "EngineeringDelivery", "CybersecurityCompliance", "OperationalEfficiency"],
      "maps_to_signals": ["SA-01", "SA-02", "SA-03", "TA-01", "TA-02", "TA-03", "TA-04", "CC-01", "CC-03"]
    },
    "SoftwareDevTools": {
      "id": "software_dev_tools",
      "type": "inventory_table",
      "key_columns": {
        "id": "ID",
        "function": "Function",
        "tool_name": "Tool/Product Name",
        "version": "Version",
        "num_users": "# Users",
        "annual_cost": "Annual Licensing Cost"
      },
      "field_identification": "each_row_is_a_field",
      "expected_row_count": 13,
      "maps_to_lenses": ["EngineeringDelivery", "TechnologyArchitecture"],
      "maps_to_signals": ["ED-01", "ED-02", "ED-03", "TA-05"]
    },
    "SystemsSecurityInfra": {
      "id": "systems_security_infra",
      "type": "inventory_table",
      "key_columns": {
        "system_name": "IT System Detail",
        "vendor": "Vendor/Provider",
        "version": "Version",
        "hosting": "Hosting (Cloud/On-Prem)",
        "annual_cost": "Annual Cost",
        "contract_end": "Contract End Date",
        "users": "# Users"
      },
      "field_identification": "each_row_is_a_field",
      "maps_to_lenses": ["InfrastructureTechnology", "CybersecurityCompliance", "ThirdPartyVendorRisk"],
      "maps_to_signals": ["IT-01", "IT-02", "IT-03", "CC-05", "CC-06", "TV-01", "TV-02"]
    },
    "RDSpend": {
      "id": "rd_spend",
      "type": "financial_table",
      "key_columns": {
        "category": "Category",
        "actual_2024": "2024 Actual",
        "actual_2025": "2025 Actual",
        "budget_2026": "2026 Budgeted",
        "ytd_2026": "2026 YTD",
        "annualized_2026": "2026 Annualized"
      },
      "field_identification": "each_row_is_a_field",
      "maps_to_lenses": ["ValueCreationPotential", "StrategyRoadmap"],
      "maps_to_signals": ["SA-02", "VC-01", "VC-02"]
    },
    "CensusInput": {
      "id": "census_input",
      "type": "roster_table",
      "key_columns": {
        "sno": "S.No.",
        "name": "Employee Name",
        "location": "Location",
        "country": "Country",
        "job_title": "Job Title",
        "team": "Team"
      },
      "field_identification": "row_count_matters",
      "maps_to_lenses": ["OrganizationTalent"],
      "maps_to_signals": ["OT-01", "OT-02", "OT-03", "OT-04", "OT-05"]
    }
  }
}
```

**Parser output** (`drl_state.json`):

```json
{
  "deal_id": "HORIZON",
  "version": 1,
  "uploaded_at": "2026-04-06T14:30:00Z",
  "source_filename": "Updated_Technical Diligence DRL 0307_v2.xlsx",
  "tabs": {
    "technology": {
      "total_fields": 28,
      "filled_fields": 12,
      "empty_fields": 16,
      "completeness_pct": 42.9,
      "fields": [
        {
          "field_id": "TECH-001",
          "function": "Product Management & Strategy",
          "request": "Product roadmap including key initiatives...",
          "date_requested": "2026-03-07",
          "date_responded": null,
          "dataroom_location": null,
          "status": "EMPTY",
          "depth_score": 0,
          "maps_to_signals": ["SA-08"]
        },
        {
          "field_id": "TECH-002",
          "function": "Organization",
          "request": "Org chart for technology team...",
          "date_requested": "2026-03-07",
          "date_responded": "2026-03-15",
          "dataroom_location": "Folder 3.2",
          "status": "ANSWERED",
          "depth_score": 7,
          "maps_to_signals": ["OT-01", "OT-02"]
        }
      ]
    },
    "software_dev_tools": {
      "total_fields": 13,
      "filled_fields": 8,
      "empty_fields": 5,
      "completeness_pct": 61.5,
      "fields": []
    },
    "systems_security_infra": {
      "total_fields": 20,
      "filled_fields": 0,
      "empty_fields": 20,
      "completeness_pct": 0.0,
      "fields": []
    },
    "rd_spend": {
      "total_fields": 8,
      "filled_fields": 0,
      "empty_fields": 8,
      "completeness_pct": 0.0,
      "fields": []
    },
    "census_input": {
      "total_fields": 1,
      "filled_fields": 0,
      "empty_fields": 1,
      "completeness_pct": 0.0,
      "row_count": 0,
      "fields": []
    }
  },
  "overall": {
    "total_fields": 70,
    "filled_fields": 20,
    "empty_fields": 50,
    "completeness_pct": 28.6,
    "depth_score": 5.2,
    "composite_score": 33.8,
    "grade": "D"
  }
}
```

##### NEW TOOL: `tools/drl_grader.py`

**Purpose:** Score DRL responses on two equally-weighted dimensions.

**Completeness scoring (50% weight):**

| Tab Type | "Filled" means |
|----------|----------------|
| `request_list` (Technology) | `date_responded` is non-null AND `dataroom_location` is non-null |
| `inventory_table` (Software Dev, Systems Security) | Row has ≥ 3 of its key columns populated |
| `financial_table` (R&D Spend) | Row has ≥ 2 year columns populated |
| `roster_table` (Census) | Row count > 0 AND ≥ 80% of rows have all 5 required columns |

**Depth scoring (50% weight):**

Each filled field gets a depth score 1-10:

| Score | Criteria |
|-------|----------|
| 1-2 | Single word or "Yes/No" only |
| 3-4 | Brief phrase, no supporting detail |
| 5-6 | Sentence-level answer with some specifics |
| 7-8 | Paragraph with evidence references or data points |
| 9-10 | Detailed response with document references, metrics, or linked VDR files |

For `request_list` tabs, depth is assessed by:
- Whether `dataroom_location` actually points to a real VDR path (cross-referenced with document inventory)
- Whether multiple related items reference each other
- Whether dates are recent (< 6 months old)

For `inventory_table` tabs, depth is assessed by:
- Whether version numbers are specific (not "latest" or blank)
- Whether cost figures are provided (not just tool names)
- Whether user counts are present

For `financial_table`, depth is:
- Whether all year columns are filled (not just current year)
- Whether product-wise breakdown is provided
- Whether actuals vs. budget are distinguished

For `roster_table`, depth is:
- Row completeness (% of columns filled per row)
- Whether job titles are specific (not "Engineer" but "Senior Backend Engineer")
- Whether team assignments are present

**Composite score:** `(0.5 × completeness_pct) + (0.5 × depth_score_normalized_to_100)`

**Grade thresholds:**

| Grade | Composite Score | Practitioner Action |
|-------|----------------|---------------------|
| A | 85-100 | Sufficient to proceed to deep diligence |
| B | 70-84 | Minor gaps — targeted follow-up |
| C | 55-69 | Significant gaps — structured chase needed |
| D | 40-54 | Inadequate — send formal gap notice |
| F | 0-39 | Unusable — escalate to deal lead |

##### NEW TOOL: `tools/drl_version_store.py`

**Purpose:** Track DRL versions and compute field-level diffs.

**Version history** (`drl_history.json`):

```json
{
  "deal_id": "HORIZON",
  "versions": [
    {
      "version": 1,
      "uploaded_at": "2026-03-15T10:00:00Z",
      "filename": "DRL_v1.xlsx",
      "overall_completeness": 28.6,
      "overall_depth": 5.2,
      "overall_composite": 33.8,
      "grade": "D",
      "tab_scores": {
        "technology": {"completeness": 42.9, "depth": 6.1, "composite": 41.5},
        "software_dev_tools": {"completeness": 61.5, "depth": 4.8, "composite": 43.2},
        "systems_security_infra": {"completeness": 0.0, "depth": 0.0, "composite": 0.0},
        "rd_spend": {"completeness": 0.0, "depth": 0.0, "composite": 0.0},
        "census_input": {"completeness": 0.0, "depth": 0.0, "composite": 0.0}
      }
    },
    {
      "version": 2,
      "uploaded_at": "2026-03-22T14:00:00Z",
      "filename": "DRL_v2.xlsx",
      "overall_completeness": 58.3,
      "overall_depth": 6.8,
      "overall_composite": 55.6,
      "grade": "C",
      "tab_scores": {},
      "delta_from_previous": {
        "completeness_delta": "+29.7%",
        "depth_delta": "+1.6",
        "composite_delta": "+21.8",
        "fields_newly_filled": 21,
        "fields_improved": 5,
        "fields_regressed": 0,
        "fields_still_empty": 29
      }
    }
  ]
}
```

**Field-level diff** (`drl_diff_v1_v2.json`):

```json
{
  "from_version": 1,
  "to_version": 2,
  "generated_at": "2026-03-22T14:05:00Z",
  "summary": {
    "fields_newly_filled": 21,
    "fields_improved": 5,
    "fields_unchanged": 15,
    "fields_regressed": 0,
    "fields_still_empty": 29
  },
  "changes": [
    {
      "field_id": "TECH-005",
      "tab": "technology",
      "request": "Application architecture block diagram...",
      "change_type": "NEWLY_FILLED",
      "old_status": "EMPTY",
      "new_status": "ANSWERED",
      "new_depth_score": 7,
      "dataroom_location": "Folder 4.1/arch-diagram.pdf",
      "maps_to_signals": ["TA-01", "TA-02"]
    },
    {
      "field_id": "TECH-002",
      "tab": "technology",
      "request": "Org chart for technology team...",
      "change_type": "IMPROVED",
      "old_depth_score": 5,
      "new_depth_score": 8,
      "improvement_note": "Added headcount breakdown by function"
    }
  ],
  "still_empty": [
    {
      "field_id": "TECH-012",
      "tab": "technology",
      "request": "Penetration test results...",
      "urgency": "CRITICAL",
      "maps_to_signals": ["CC-03", "CC-04"],
      "chase_language": "Please provide penetration test results. This is a critical requirement for our security assessment."
    }
  ]
}
```

##### Dashboard: Questionnaire Tracker (New Page or Tab)

**Location:** `dashboard/pages/5_📋_Questionnaire_Tracker.py`

**Layout:**

```
┌─────────────────────────────────────────────────────────────────┐
│  📋 Questionnaire Tracker — DRL Completeness & Quality          │
│  [Select Deal ▼]  [Upload New DRL Version 📤]                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐        │
│  │ Overall  │  │Complete- │  │ Depth    │  │ Version  │        │
│  │ Grade: C │  │ness: 58% │  │ Score:6.8│  │ 2 of ?   │        │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘        │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Version Trend Chart                                      │   │
│  │  📈 Completeness + Depth + Composite over versions        │   │
│  │  [v1: 34] ──── [v2: 56] ──── [v3: ?]                     │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Per-Tab Breakdown                                        │   │
│  │                                                           │   │
│  │  Technology          ██████████░░░░░░░░░░  58%  (B)       │   │
│  │  Software Dev & Tools ████████░░░░░░░░░░░░  43%  (D)       │   │
│  │  Systems Security     ████████████░░░░░░░░  65%  (C)       │   │
│  │  R&D Spend           ██░░░░░░░░░░░░░░░░░░  12%  (F)       │   │
│  │  Census Input        █████████████████░░░  82%  (B)       │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  What Changed (v1 → v2)                                   │   │
│  │  ✅ 21 fields newly filled                                │   │
│  │  ⬆️ 5 fields improved in depth                            │   │
│  │  ⏳ 29 fields still empty (12 CRITICAL)                   │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Outstanding Items — Chase List                           │   │
│  │  🔴 CRITICAL: Pen test results (CC-03, CC-04)             │   │
│  │  🔴 CRITICAL: SOC2 Type II (CC-01)                        │   │
│  │  🟠 HIGH: Cloud infrastructure costs (IT-03, VC-01)       │   │
│  │  🟡 MEDIUM: Product roadmap detail (SA-08)                │   │
│  │                                                           │   │
│  │  [📧 Generate Chase Email]  [📋 Export Gap Report]         │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Signal Coverage Map                                      │   │
│  │  Which v1.1 signals can we assess from current responses? │   │
│  │                                                           │   │
│  │  StrategyRoadmap:     SA-01 ✅ SA-02 ⏳ SA-03 ❌ ...     │   │
│  │  CybersecurityCompl:  CC-01 ❌ CC-02 ✅ CC-03 ❌ ...     │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

**Key interactions:**
- Upload DRL Excel → system auto-detects version, parses, grades, diffs
- Per-tab expandable detail showing every field with status badge
- "Generate Chase Email" button → produces copy-pasteable text listing all CRITICAL/HIGH empty fields with request language
- Signal coverage map shows which of the 100 signals have supporting data from the questionnaire

---

#### 4.2.3 Feature 3: VDR Auto-Diff on Rescan

**Current state:** `vdr_triage.py` already detects rescans via `scan_history.json` and generates a `_changelog.md`. But it's a basic file-list diff — no signal-aware analysis.

**Enhancement:**

When a rescan is triggered (same deal_id, new VDR path or updated folder):

1. **Document-level diff** (deterministic, no AI):
   - New documents (in v2 but not v1)
   - Removed documents (in v1 but not v2)
   - Modified documents (same name, different size/hash)
   - Unchanged documents

2. **Gap-resolution matching** (deterministic + light AI):
   - For each `CRITICAL`/`HIGH` gap from the completeness report, check if any new document resolves it
   - Output: "GAP-003 (Penetration test) → POSSIBLY RESOLVED by `pen_test_2026_q1.pdf` (new)"

3. **Signal delta** (AI-powered, only for new/modified docs):
   - Re-extract signals only from new and modified documents (not the entire VDR)
   - Compare new signals against prior signal index
   - Output: "12 new signals extracted, 3 are RED (2 in CybersecurityCompliance, 1 in ThirdPartyVendorRisk)"

4. **Dashboard integration:**
   - Version selector dropdown on Deal Dashboard
   - Changelog panel showing new/removed/modified docs
   - Signal delta summary
   - Gap resolution status (which gaps are now closed)

**VDR changelog output** (`vdr_changelog_v1_v2.json`):

```json
{
  "deal_id": "HORIZON",
  "from_version": 1,
  "to_version": 2,
  "generated_at": "2026-04-06T15:00:00Z",
  "document_changes": {
    "added": [
      {
        "filename": "pen_test_2026_q1.pdf",
        "vdr_section": "Security",
        "size_bytes": 524288,
        "batch_group": "security_pen_tests",
        "resolves_gaps": ["GAP-003"]
      }
    ],
    "removed": [],
    "modified": [
      {
        "filename": "org_chart_tech_team.pdf",
        "vdr_section": "Organization",
        "size_change_bytes": 12000,
        "batch_group": "product_overview"
      }
    ],
    "unchanged_count": 42
  },
  "gap_resolution": {
    "gaps_resolved": 2,
    "gaps_remaining": 5,
    "details": [
      {
        "gap_id": "GAP-003",
        "expected_document": "Penetration test",
        "resolved_by": "pen_test_2026_q1.pdf",
        "confidence": "HIGH"
      }
    ]
  },
  "signal_delta": {
    "new_signals": 12,
    "by_rating": {"RED": 3, "YELLOW": 5, "GREEN": 4},
    "by_lens": {
      "CybersecurityCompliance": 5,
      "ThirdPartyVendorRisk": 3,
      "OrganizationTalent": 4
    },
    "notable": [
      {
        "signal_id": "SIG-045",
        "catalog_signal_id": "CC-03",
        "title": "Critical vulnerability in external pen test",
        "rating": "RED",
        "source_doc": "pen_test_2026_q1.pdf"
      }
    ]
  },
  "updated_metrics": {
    "completeness_score_before": 72,
    "completeness_score_after": 85,
    "vdr_grade_before": "C",
    "vdr_grade_after": "B",
    "lenses_covered_before": 8,
    "lenses_covered_after": 10
  }
}
```

---

### 4.3 Data Flow: How the Three Features Connect

```
DRL Questionnaire Upload                    VDR Rescan
        │                                       │
        ▼                                       ▼
  drl_parser.py                          structure_mapper.py
        │                                       │
        ▼                                       ▼
  drl_grader.py                          doc-level diff engine
        │                                       │
        ▼                                       ▼
  drl_version_store.py                   gap-resolution matcher
        │                                       │
        ├───────────────┬───────────────────────┘
        │               │
        ▼               ▼
   ┌────────────────────────────────┐
   │  SIGNAL COVERAGE MAP           │
   │                                │
   │  For each of 100 v1.1 signals: │
   │  - VDR evidence? ✅/❌         │
   │  - DRL response? ✅/❌         │
   │  - Quality grade (if yes)      │
   │  - Gap chase priority          │
   └────────────────────────────────┘
```

The **Signal Coverage Map** is the unifying artifact. It shows, for each of the 100 catalog signals, whether evidence exists from the VDR scan, the questionnaire, or both — and grades the quality. This becomes the practitioner's single source of truth for "what do I know, what don't I know, and what should I chase next."

---

## 5. Trade-Off Analysis

| Decision | Choice | Alternative Considered | Why |
|----------|--------|----------------------|-----|
| DRL ingestion via Excel re-upload | Chosen | In-app form | Practitioners already have the Excel workflow. Re-upload is zero training cost. Diffing Excel versions is automatable. |
| Depth scoring: deterministic heuristics | Chosen | Claude API call per field | 70 fields × 5 versions = 350 API calls per deal just for grading. Heuristic rules (word count, reference detection, specificity checks) get 80% accuracy at zero cost. |
| v1.1 lenses as hard replacement | Chosen | Soft mapping / dual taxonomy | Maintaining two taxonomies adds complexity everywhere. Clean break is better — migration map handles old data. |
| Auto-diff (not on-demand) | Chosen | Manual comparison | Practitioners forget to diff. Auto-diff on every rescan means the changelog is always there. Zero cognitive overhead. |
| Signal extraction: incremental on rescan | Chosen | Full re-extraction | Re-extracting all 40+ documents costs $10-15 and 20 minutes. Extracting only new/modified docs costs ~$2 and 5 minutes. Prior signals are preserved. |

---

## 6. Implementation Plan

### Phase 1: Signal Taxonomy Migration (estimated: 1 session)

| # | Task | Files | Test |
|---|------|-------|------|
| 1.1 | Parse v1.1 Excel catalog → `signal_catalog_v1.1.json` | Script + data file | Verify 100 signals, 11 lenses |
| 1.2 | Create `signal_lenses_v1.1.json` | Data file | Schema validation |
| 1.3 | Create `lens_migration_map.json` | Data file | Old→new mapping for all 11 |
| 1.4 | Update `signal_extractor.py` + extraction prompt | tools + prompts | Unit test with sample batch |
| 1.5 | Update `cross_referencer.py` + domain slices | tools + prompts | Unit test with sample signals |
| 1.6 | Update `vdr_grader.py` coverage breadth | tools | Unit test |
| 1.7 | Update `practitioner_recommender.py` | tools | Unit test |
| 1.8 | Update `data_loader.py` LENS_NAMES + all dashboard pages | dashboard | Visual check |
| 1.9 | Run full HORIZON rescan with v1.1 taxonomy | Integration test | Compare output quality vs. v1.0 |

### Phase 2: DRL Questionnaire Tracking (estimated: 2 sessions)

| # | Task | Files | Test |
|---|------|-------|------|
| 2.1 | Create `data/drl_template_schema.json` | Data file | Schema validation |
| 2.2 | Build `tools/drl_parser.py` — tab detection + field extraction | New tool | Unit test with real DRL Excel |
| 2.3 | Build `tools/drl_grader.py` — completeness + depth + composite | New tool | Unit test: empty DRL = F, full DRL = A |
| 2.4 | Build `tools/drl_version_store.py` — version log + field diff | New tool | Unit test: upload v1, upload v2, verify diff |
| 2.5 | Build `dashboard/pages/5_📋_Questionnaire_Tracker.py` | New page | Visual check: KPIs, bars, diff, chase list |
| 2.6 | Wire "Generate Chase Email" with request language | Dashboard | Copy-paste test |
| 2.7 | Build Signal Coverage Map (connects DRL + VDR) | Dashboard + tool | Check 100 signals mapped |
| 2.8 | Integration test: upload DRL v1, then v2, verify full workflow | E2E | Scores, diff, chase list all correct |

### Phase 3: VDR Auto-Diff Enhancement (estimated: 1 session)

| # | Task | Files | Test |
|---|------|-------|------|
| 3.1 | Enhance `vdr_triage.py` rescan: document-level diff engine | Agent | Unit test with 2 VDR snapshots |
| 3.2 | Add gap-resolution matching to completeness checker | Tools | Unit test: new doc resolves GAP |
| 3.3 | Incremental signal extraction (new/modified docs only) | Signal extractor | Unit test: only new docs sent to Claude |
| 3.4 | Generate `vdr_changelog_v1_v2.json` | Agent output | Schema validation |
| 3.5 | Dashboard: version selector + changelog panel | Dashboard | Visual check |
| 3.6 | Dashboard: signal delta summary on Deal Dashboard | Dashboard | Visual check |
| 3.7 | Integration test: scan v1, add docs, rescan v2, verify changelog | E2E | All diff artifacts correct |

### Phase 4: Verification & Polish (estimated: 0.5 session)

| # | Task |
|---|------|
| 4.1 | Full HORIZON end-to-end: VDR scan → DRL upload → rescan with new docs |
| 4.2 | Verify Signal Coverage Map shows data from both VDR and DRL sources |
| 4.3 | Verify all dashboard pages use v1.1 lens names consistently |
| 4.4 | Run existing test suite — ensure no regressions |
| 4.5 | Update CLAUDE.md with new tool descriptions and data contracts |

---

## 7. Open Questions

| # | Question | Owner | Blocking? |
|---|----------|-------|-----------|
| 1 | The v1.1 Excel has "Partner Feedback" columns (Relevance, Weight Adjustment, Data Source Comments, General Notes). Should we ingest these as signal metadata or ignore for now? | Shiva | No |
| 2 | The DRL "Technology" tab has 28 items. Should we assign urgency (CRITICAL/HIGH/MEDIUM) to each, or treat all equally? Urgency would improve chase list prioritization. | Shiva | No — can default to MEDIUM and override later |
| 3 | Census tab: what's the minimum headcount for a "filled" response? Is 5 rows enough or do we need the full 200? | Shiva | No — default to "any rows > 0 = partially filled" |
| 4 | Should the Signal Coverage Map be a standalone dashboard page or a tab within Deal Dashboard? | Shiva | No — start as a section in Questionnaire Tracker, can promote later |
| 5 | For the v1.1 migration, should we re-run the HORIZON scan immediately or keep old outputs and only use v1.1 for new scans? | Shiva | Yes — affects whether we need migration code for old outputs |

---

## 8. Success Criteria

1. **Taxonomy:** All 100 v1.1 signals are loadable. Extraction prompt produces `catalog_signal_id` matches for ≥60% of observations on a real VDR scan.
2. **DRL Tracking:** Upload the real HORIZON DRL → system produces per-tab completeness, depth scores, and overall grade within 30 seconds (no AI calls needed for grading).
3. **DRL Versioning:** Upload v1 then v2 → system shows field-level diff with correct counts of newly_filled, improved, still_empty.
4. **Chase List:** Generate chase email covers all CRITICAL/HIGH empty fields with practitioner-ready language and signal ID references.
5. **VDR Diff:** Rescan a VDR with 3 new documents → changelog correctly identifies additions, matches ≥1 against prior gaps, extracts signals only from new docs.
6. **Signal Coverage Map:** For HORIZON, shows which of 100 signals have evidence from VDR, DRL, or both.
7. **No regressions:** Existing Phase 0 scan pipeline, grading, and dashboard still work.
