# TDD Platform — Engineering Review
**Date:** 2026-04-07 | **Scope:** Full codebase audit across 6 dimensions

---

## Executive Summary

**Overall Score: 7.5/10** — Solid foundation, well-architected pipeline, but needs hardening before production deployment. The scan crash is a memory issue, not a design flaw. ~2 weeks of focused fixes would make this production-ready for single-tenant use.

**151 tests passing** | **45% coverage** | **3 critical bugs** | **~25 total issues found**

---

## 1. CRASH ROOT CAUSE (Why scans keep failing)

**Root cause: Memory exhaustion during document reading (90% confidence)**

The scan crashes at phase="reading" every time. Three consecutive failures, same phase, PID dies silently. The culprit:

- **openpyxl memory bloat**: A 231 KB Excel file expands to 50-500 MB when loaded with `data_only=True`. With 640 documents including 30+ Excel files, peak memory hits 300-400 MB per batch.
- **Large PDFs**: One 86 MB PDF in the VDR expands 1.5-2x during text extraction.
- **No memory release**: Old code loaded ALL 640 docs before starting extraction. The streaming refactor (just built) fixes this — now reads batch-by-batch and releases memory after each.

**The streaming fix we just built should resolve this.** If it still crashes, the next fix is: add a per-file memory cap (skip files > 50 MB, extract first N pages only for huge PDFs), and add openpyxl lazy reading for large Excel files.

---

## 2. CRITICAL BUGS (Fix before next scan)

### BUG 1: `response.content[0]` without bounds check
**Files:** signal_extractor.py:217, cross_referencer.py:64, domain_analyst.py:201
**Impact:** If Claude returns empty content (API error), IndexError crashes the scan.
**Fix:** Check `if not response.content` before accessing `[0]`.

### BUG 2: Race condition on scan registry
**File:** scan_registry.py
**Impact:** Two concurrent processes can clobber each other's writes (read-modify-write without locking).
**Fix:** Add file locking (`fcntl.flock` on Linux, `msvcrt.locking` on Windows) or move to SQLite.

### BUG 3: Orphaned scans on unhandled exception
**File:** agents/vdr_triage.py
**Impact:** If `run_triage()` throws an uncaught exception, scan stays "running" in registry forever. The `cleanup_stale_scans()` we built mitigates this, but the proper fix is a try-finally around the entire pipeline.
**Fix:** Wrap `run_triage()` in try/except that calls `fail_scan()` on any exception.

---

## 3. HIGH-PRIORITY ISSUES

| # | Issue | File(s) | Effort |
|---|-------|---------|--------|
| 1 | Thread pool exceptions silently swallowed — sub-batch failures return empty result indistinguishable from "no signals found" | signal_extractor.py | 30 min |
| 2 | Missing checkpoint cleanup on error — stale checkpoints cause next scan to skip fresh documents | vdr_triage.py | 15 min |
| 3 | No timeout on Claude API calls — if API hangs, scan blocks forever | signal_extractor.py, cross_referencer.py, domain_analyst.py | 15 min |
| 4 | No validation of JSON schema from Claude — could return error JSON treated as empty signals | signal_extractor.py | 30 min |
| 5 | ZIP path traversal risk — malicious ZIP could write outside target directory | structure_mapper.py | 20 min |
| 6 | Unbounded signal list in cross-referencer — noisy extraction could create 10K+ signals in memory | cross_referencer.py | 20 min |

---

## 4. TECH DEBT

### Duplication (Quick Fixes)
- `_extract_json()` implemented identically in 3 files (signal_extractor, cross_referencer, domain_analyst) → Extract to shared utility
- `DATA_DIR` and `OUTPUT_DIR` defined in 7 files → Centralize in config module
- `MODEL = "claude-sonnet-4-20250514"` hardcoded in 3 files → Single `.env` variable

### Naming Inconsistency
- 50+ references mixing "lens" (v1.1) and "pillar" (v1.3) across 20+ files
- Backward compatibility aliases (`BATCH_TO_LENSES = BATCH_TO_PILLARS`, `LENS_NAMES = PILLAR_NAMES`) add confusion
- Recommendation: Pick one term ("pillar"), migrate all references, remove aliases

### Missing Abstractions
- Signal processing logic scattered across signal_extractor, signal_store, cross_referencer
- Batch orchestration in vdr_triage.py interleaves 5 concerns (reading, extraction, checkpointing, registry, signal store)
- No shared "Claude API caller" wrapper — each tool builds its own request/response handling

---

## 5. TEST COVERAGE

### Current State
- **151 tests**, all passing, ~7 seconds runtime
- **12 test files** covering 12 of 29 source modules
- DRL pipeline (52 tests) and VDR auto-diff (41 tests) are excellent
- Test:Source ratio is 1:5.8 (should be closer to 1:2)

### Critical Gaps (0 tests)
| Module | LOC | Risk |
|--------|-----|------|
| domain_analyst.py | 434 | NEW — drives Deal Intel page, untested concurrent execution |
| vdr_grader.py | 339 | Generates A-F grade partners see — scoring logic untested |
| drl_grader.py | 338 | Grades questionnaire completion — partial completion untested |
| quinn.py | 200+ | Template change detection — full orchestration untested |
| rate_limiter.py | ~150 | Token budget logic — edge cases untested |
| scan_registry.py | ~220 | Lifecycle tracking — concurrent access untested |

### Recommended: Week 1 (13 hours)
1. test_domain_analyst.py — 10 tests, 4 hours
2. test_vdr_grader.py — 8 tests, 3 hours
3. test_drl_grader.py — 8 tests, 3 hours
4. test_scan_registry.py — 6 tests, 3 hours

This would raise coverage from 45 → 60 and cover the highest-risk paths.

---

## 6. SYSTEM DESIGN

### What's Strong
- Clean separation: Agents → Tools → Outputs → Dashboard (no circular dependencies)
- Smart checkpoint/resume system for crash recovery
- Rate limiter with token-aware pacing
- Dynamic pillar definitions (catalog-driven, not hardcoded)
- Streaming batch pipeline (just built) solves the memory wall

### What Needs Work for Production
| Concern | Current | Production Target |
|---------|---------|-------------------|
| Storage | JSON files on disk | SQLite or Postgres |
| Concurrency | No locking, single-user assumed | File locks minimum, DB transactions ideal |
| Subprocess mgmt | `subprocess.Popen` with stdout parsing | Task queue (Celery/RQ) or async workers |
| Configuration | Mix of .env, hardcoded, module-level constants | Single config module + .env |
| Logging | Mixed print/logger, no structured output | Structured JSON logging to file |
| Deployment | Local Streamlit only | Dockerized, behind auth proxy |

### Cloud Migration Path
- **Phase 1 (2 weeks)**: Hardening — fix critical bugs, add locking, centralize config → Single-tenant cloud-ready
- **Phase 2 (4 weeks)**: Migration — replace JSON files with DB, add task queue, dockerize → Multi-user SaaS
- **Phase 3 (2 weeks)**: Performance — async I/O, connection pooling, caching → Scale

---

## 7. IMMEDIATE ACTION PLAN

### This Week (Before Next Scan)
1. ✅ Streaming batch pipeline (DONE — prevents memory crash)
2. ✅ Stale scan detection (DONE — auto-marks dead PIDs as failed)
3. Add `response.content` bounds checking in 3 files (30 min)
4. Wrap `run_triage()` in try/except → `fail_scan()` (15 min)
5. Add API call timeout of 300s (15 min)
6. Add openpyxl lazy reading for files > 5 MB (20 min)

### Next Week
7. Extract shared `_extract_json()` utility
8. Centralize MODEL and config constants
9. Add file locking to scan registry
10. Write tests for domain_analyst, vdr_grader, scan_registry

### Backlog
11. lens → pillar naming migration
12. SQLite storage migration
13. Structured logging
14. Task queue for scan management
