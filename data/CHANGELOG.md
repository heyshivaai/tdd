# Signal Catalog Changelog

All changes to `signal_catalog.json` and `signal_pillars.json` are documented here.
Version is tracked inside the JSON (`"version"` field) and by git history.

## v1.4 — 2026-04-07

**Source:** Horizon calibration analysis (practitioner vs agent comparison)

**Added 9 signals** (29 → 38 total):

| Signal ID | Pillar | Name | Why Added |
|-----------|--------|------|-----------|
| OT-05 | OrganizationTalent | Organization Structure & Leadership Alignment | Agent missed org restructure recommendation; had no signal for reporting structure analysis |
| RS-06 | RDSpendAssessment | R&D Spend as Percentage of Revenue | Agent had financial docs but didn't compute R&D % of revenue; practitioners benchmarked at 15% |
| RS-07 | RDSpendAssessment | Customer Revenue Concentration Risk | Agent missed SCA Health at 14% CARR on legacy platform; no customer concentration signal existed |
| TA-06 | TechnologyArchitecture | Multi-Cloud Consolidation & Migration Risk | Agent mentioned GCP in passing; practitioners dedicated a full page to migration risk |
| TA-07 | TechnologyArchitecture | Tech Debt Remediation Itemization | Agent said "tech debt exists" generically; practitioners produced 11-item table with $745K costs |
| TA-08 | TechnologyArchitecture | Development & Enterprise Tooling Landscape | Agent extracted zero tooling inventory; practitioners mapped 30+ tools |
| SP-03 | SDLCProductManagement | Product Portfolio & Market Position | Agent had no product-market context signal; practitioners covered 6 products + 97% retention |
| SC-06 | SecurityCompliance | Data Breach & Incident History | Agent found 31 PHI incidents as ad-hoc observation; making it a catalog signal ensures consistency |
| ID-06 | InfrastructureDeployment | Hosting Cost Breakdown & Growth Trajectory | Agent flagged "cost volatility" but never extracted provider-level monthly figures |

**No signals removed or modified.**

## v1.3 — 2026-04-06

Initial catalog with 29 signals across 7 pillars. Based on Crosslake Top 100 Signal Catalog.
