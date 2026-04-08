# ADR-001: Two-Phase Pipeline Architecture (VDR Scan + Agent Deep Diligence)

**Status:** Accepted
**Date:** 2026-04-08
**Deciders:** Shiva (Platform Lead), RentAI Engineering

---

## Context

The TDD platform automates technology due diligence for PE acquisitions. A typical engagement involves two distinct analytical phases with different data sources, depth requirements, and time constraints:

1. **Phase 0 (VDR Scan)**: Rapid triage of 10-50 documents from a Virtual Data Room. Time-sensitive (hours, not days). Goal: surface deal-breaker signals, assess completeness, generate a prioritized reading list. Runs before the PE firm commits resources.

2. **Phase 1 (Agent Deep Diligence)**: Deep domain analysis across 8 specialist areas. Runs after Phase 0 confirms the deal is worth investigating. Each domain requires different expertise (security, infrastructure, code quality, organization, etc.) and builds on prior agents' findings.

The key architectural question: should these be a single monolithic pipeline, two independent systems, or a connected two-phase architecture with a shared data contract?

---

## Decision

Implement a **connected two-phase architecture** where Phase 0 and Phase 1 are independently executable but share a common deal state and data contract. Phase 0 outputs feed directly into Phase 1 via a state-seeding bridge (`seed_deal_state_from_vdr`).

### Data Flow

```
VDR Documents
    |
    v
[Phase 0: VDR Triage Agent]
    |-- Step 1: Structure Mapper (batch classification)
    |-- Step 2: Completeness Checker (gap analysis)
    |-- Step 3: Signal Extractor (per-batch Claude calls)
    |-- Step 4: Cross-Referencer (single synthesis call)
    |
    v
vdr_intelligence_brief.json  ──>  seed_deal_state_from_vdr()
                                        |
                                        v
                                [Phase 1: 8-Agent Chain]
                                    |-- Alex (Intake & Profile)
                                    |-- Morgan (Public Signals)
                                    |-- Jordan (Repo Analysis)
                                    |-- Riley (Security)
                                    |-- Casey (Code Quality)
                                    |-- Taylor (Infrastructure)
                                    |-- Drew (Benchmarking)
                                    |-- Sam (Report Synthesis)
                                        |
                                        v
                                deal_state.json + agents/*.json
                                        |
                                        v
                                [Report Generator]
                                        |
                                        v
                                TDD_Report.docx
```

### State Architecture

Each deal gets a folder at `outputs/<deal_id>/` containing:

| File | Owner | Purpose |
|------|-------|---------|
| `deal_meta.json` | Deal Manager | Metadata: company, sector, status, timestamps |
| `deal_state.json` | Deal Manager | Cumulative state: intake + VDR scan + all agent outputs |
| `vdr_intelligence_brief.json` | VDR Triage | Full Phase 0 output: signals, compound risks, reading list |
| `vdr_completeness_report.md` | Completeness Checker | Gap analysis in human-readable format |
| `vdr_triage_report.md` | Report Writer | Practitioner-facing scan summary |
| `agents/<name>.json` | Orchestrator | Per-agent structured output |
| `feedback_gate1.json` | Report Writer | Practitioner feedback shell |

---

## Options Considered

### Option A: Monolithic Pipeline

| Dimension | Assessment |
|-----------|------------|
| Complexity | Low |
| Cost | Lower (fewer API calls for state transfer) |
| Scalability | Poor (all-or-nothing execution) |
| Resilience | Poor (failure anywhere restarts everything) |

**Pros:** Simpler state management, no Phase 0/1 boundary to maintain, single orchestrator.
**Cons:** Cannot run Phase 0 alone for quick screening. Cannot resume Phase 1 if one agent fails. Longer minimum execution time. Cannot parallelize agent work in future.

### Option B: Two Independent Systems

| Dimension | Assessment |
|-----------|------------|
| Complexity | High |
| Cost | Higher (duplicate infrastructure, separate state stores) |
| Scalability | Good (fully independent) |
| Resilience | Good (isolated failure domains) |

**Pros:** Clean separation, can evolve independently, no coupling.
**Cons:** Loses the signal continuity that makes the TDD valuable. Agents can't reference VDR evidence. Duplicate deal management. User sees two disconnected experiences.

### Option C: Connected Two-Phase (Chosen)

| Dimension | Assessment |
|-----------|------------|
| Complexity | Medium |
| Cost | Moderate (shared infrastructure, one API client) |
| Scalability | Good (phases run independently, agents chain sequentially) |
| Resilience | Good (Phase 0 checkpoint/resume, Phase 1 skip-completed agents) |

**Pros:** Phase 0 runs standalone for quick screening. Phase 1 builds on Phase 0 signals. Agents accumulate state progressively. Report generator merges both phases. Shared deal lifecycle.
**Cons:** State-seeding bridge adds complexity. Two orchestrators to maintain. Signal format must stay compatible across phases.

---

## Trade-off Analysis

### Why Not Monolithic

The PE use case demands a "fast screen, then go deep" workflow. Partners need Phase 0 results in under an hour to decide whether to allocate analyst time. A monolithic pipeline would force them to wait for the full 8-agent chain (30-60 minutes) before seeing anything.

### Why Not Fully Independent

The highest-value insight in TDD comes from tracing findings back to VDR evidence. If Phase 1 agents can't see Phase 0 signals, they lose the ability to say "the org chart shows 40% contractors (SIG-008) which compounds with the missing DR plan (SIG-013)." This evidence traceability is what makes the platform better than a generic LLM chat.

### The Bridge Pattern

The `seed_deal_state_from_vdr()` function in `deal_manager.py` is the critical bridge. It reads the VDR intelligence brief and injects its contents (signals, compound risks, lens heatmap, domain slices) into the deal state under a `vdr_scan` key. This means:

- Phase 0 writes to its own file (`vdr_intelligence_brief.json`)
- Phase 1 reads from the unified deal state (`deal_state.json`)
- Neither phase knows about the other's internals
- The bridge is the only coupling point

---

## Key Design Decisions Within This Architecture

### D1: File-Based State (Not Database)

**Rationale:** Single-tenant deployment for PE firms. Deals are independent (no cross-deal queries needed in v1). JSON files are inspectable, diffable, and require zero infrastructure. Trade-off: no concurrent write safety (documented in ENGINEERING_REVIEW.md as a known issue to address with file locking).

### D2: Sequential Agent Chain (Not Parallel)

**Rationale:** Each agent builds on prior agents' findings. Morgan validates Alex's hypothesis. Jordan provides repo context for Riley's security assessment. This sequential dependency is inherent to the TDD methodology — a security review without knowing the tech stack is meaningless. Trade-off: slower execution (~5 min per agent, ~40 min total). Future optimization: agents within the same dependency tier could run in parallel (e.g., Jordan and Riley both depend on Morgan but not on each other).

### D3: Claude API as Sole LLM (No Model Mixing)

**Rationale:** Consistency in reasoning quality matters more than cost optimization for PE diligence. All extraction and analysis uses `claude-sonnet-4-20250514`. Trade-off: higher API cost per deal (~$2-5 for Phase 0, ~$8-15 for Phase 1). Future consideration: use Haiku for structure mapping and completeness checking where deep reasoning isn't needed.

### D4: Pinecone Optional (Graceful Degradation)

**Rationale:** The Signal Intelligence Layer (cross-deal pattern matching) is valuable but not required for single-deal analysis. Lazy import with cached availability check means scans work in local-only mode. Trade-off: no cross-deal intelligence without Pinecone. Acceptable because most PE firms analyze deals independently.

### D5: MAX_TOKENS Sized for Full Output

**Rationale:** The cross-referencer must output the complete intelligence brief (compound risks, reading list, contradictions, domain slices, lens heatmap) in a single response. MAX_TOKENS set to 16,384 with automatic retry at 24,576 if response is truncated. Signal extractor set to 8,192 per batch. Trade-off: higher API cost per call. But truncated output is worse than expensive output — a partial brief with missing compound risks is actively misleading.

### D6: deal_id as Canonical Folder Name

**Rationale:** The deal system uses `deal_id` ("Project Jewel") as the folder name in `outputs/`. All writers (brief, report, completeness, feedback) use `deal_id` from the brief for consistent file placement. `company_name` is metadata within files, not a path component. This was corrected from an earlier design where `company_name` was used as the folder, causing brief files to land in the wrong directory.

---

## Consequences

**What becomes easier:**
- Running Phase 0 alone for quick deal screening (under 30 minutes)
- Adding new agents to Phase 1 without modifying Phase 0
- Generating reports from VDR-only data OR VDR+Agent data
- Resuming Phase 1 from any failed agent (completed agents are skipped)
- Inspecting intermediate state (every stage writes readable JSON)

**What becomes harder:**
- Keeping the signal format compatible across both phases
- Ensuring the state-seeding bridge stays in sync as the brief schema evolves
- Testing end-to-end (must run Phase 0 before Phase 1 tests are meaningful)
- Cross-deal analytics (file-based state doesn't support efficient queries)

**What we'll need to revisit:**
- File locking for concurrent scan/agent execution (currently unsafe)
- Database migration when multi-tenant or cross-deal intelligence becomes a priority
- Agent parallelization within dependency tiers
- Model selection per component (Haiku for low-complexity tasks)
- Streaming progress for long-running agent calls

---

## Action Items

1. [x] Implement Phase 0 pipeline (VDR triage with 4-step processing)
2. [x] Implement Phase 1 pipeline (8-agent sequential chain)
3. [x] Build state-seeding bridge (`seed_deal_state_from_vdr`)
4. [x] Add checkpoint/resume for Phase 0 (scan registry with batch-level checkpointing)
5. [x] Build report generator that merges both phases
6. [ ] Add file locking for concurrent access safety
7. [ ] Centralize Claude API wrapper (eliminate duplicated `_extract_json()`)
8. [ ] Unify "lens" vs "pillar" naming across codebase
9. [ ] Add end-to-end integration test (Phase 0 → seed → Phase 1 → report)
10. [ ] Evaluate agent parallelization for independent dependency tiers
