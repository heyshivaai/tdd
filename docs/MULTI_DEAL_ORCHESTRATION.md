# Multi-Deal Management Layer and Agent Orchestrator

## Overview

This document describes the multi-deal management layer (deal_manager.py) and agent orchestrator (orchestrator.py) that form the control plane for the TDD Platform's Phase 1 agent chain.

## Architecture

### Two Core Modules

#### 1. tools/deal_manager.py
Central deal lifecycle management with persistent state across agent runs.

**Responsibilities:**
- CRUD operations on deals (create, read, update, delete)
- Deal folder structure: `outputs/<deal_id>/`
  - `deal_meta.json` — metadata, status, agent_progress
  - `deal_state.json` — cumulative state (grows as agents run)
  - `agents/` — per-agent output JSONs
  - `vdr/` — VDR scan outputs
  - `questionnaire/` — DRL tracking

**Key Functions:**
```python
create_deal(deal_id, company_name, sector, deal_type, vdr_path="", intake_data=None) -> dict
get_deal(deal_id) -> Optional[dict]
list_deals() -> list[dict]
update_deal(deal_id, **kwargs) -> dict
get_deal_state(deal_id) -> dict
update_deal_state(deal_id, agent_name, agent_output) -> dict
get_agent_progress(deal_id) -> dict
update_agent_progress(deal_id, agent_name, status, output_file="") -> dict
save_agent_output(deal_id, agent_name, output) -> str
get_next_pending_agent(deal_id, agent_chain) -> Optional[str]
```

#### 2. agents/orchestrator.py
Chains the 8 Phase 1 agents sequentially with progress tracking and error resilience.

**Agent Chain (in execution order):**
1. **Alex** — Intake & Profile — Transforms intake data into structured company profile
2. **Morgan** — Public Signals — Collects and synthesizes public intelligence
3. **Jordan** — Repo Analysis — Analyzes source repositories for engineering health
4. **Riley** — Security — Assesses security posture and vulnerability management
5. **Casey** — Code Quality — Evaluates maintainability, technical debt, test coverage
6. **Taylor** — Infrastructure — Reviews cloud architecture, cost efficiency, compliance
7. **Drew** — Benchmarking — Contextualizes findings and builds deal scenarios
8. **Sam** — Report Synthesis — Produces PE-ready final assessment report

**Key Functions:**
```python
run_agent(deal_id, agent_name, client, rate_limiter=None) -> dict
run_chain(deal_id, client, start_from="alex", stop_after="sam", on_progress=None, rate_limiter=None) -> dict
get_next_agent(deal_id) -> Optional[str]
run_single_agent_by_index(deal_id, agent_index, client, rate_limiter=None) -> dict
```

## Data Flow

### Deal Lifecycle

```
1. CREATE DEAL
   └─> outputs/<deal_id>/
       ├─ deal_meta.json (status=intake)
       ├─ deal_state.json (empty agents dict)
       ├─ agents/
       ├─ vdr/
       └─ questionnaire/

2. RUN AGENT (Alex)
   └─> Load prompt from prompts/agents/alex.txt
   └─> Get current deal_state
   └─> Call Claude API (system=prompt, user=state JSON)
   └─> Parse JSON response
   └─> Save output to agents/alex.json
   └─> Merge into deal_state.json
   └─> Update agent_progress[alex] = {status: completed, completed_at, output_file}

3. RUN NEXT AGENT (Morgan)
   └─> get_deal_state() returns cumulative state (including alex's output)
   └─> Load prompt from prompts/agents/morgan.txt
   └─> Call Claude with full state
   └─> Morgan's response builds on Alex's findings
   └─> Repeat save/merge/track process

4. COMPLETE CHAIN
   └─> All 8 agents run sequentially
   └─> Each agent sees all prior agent outputs
   └─> Final deal_state contains all agent outputs
   └─> agent_progress shows completed timeline
```

### State Structure

**deal_meta.json:**
```json
{
  "deal_id": "acme-2025-q1",
  "company_name": "Acme Corp",
  "sector": "Life Sciences",
  "deal_type": "acquisition",
  "vdr_path": "/path/to/vdr",
  "status": "analyzing",
  "created_at": "2026-04-07T23:30:00Z",
  "updated_at": "2026-04-07T23:45:00Z",
  "agent_progress": {
    "alex": {
      "status": "completed",
      "completed_at": "2026-04-07T23:32:00Z",
      "output_file": "/absolute/path/to/agents/alex.json"
    },
    "morgan": {
      "status": "running",
      "completed_at": null,
      "output_file": ""
    }
  }
}
```

**deal_state.json:**
```json
{
  "deal_id": "acme-2025-q1",
  "company_name": "Acme Corp",
  "status": "analyzing",
  "intake_data": { /* intake form responses */ },
  "agents": {
    "alex": { /* alex's full structured output */ },
    "morgan": { /* morgan's full structured output */ }
  }
}
```

## Agent Prompts

All agent prompts are stored in `prompts/agents/<name>.txt`:

- `alex.txt` — 5.9 KB — Intake profile and risk framing
- `morgan.txt` — 3.8 KB — Public signal synthesis
- `jordan.txt` — 6.0 KB — Repository and team analysis
- `riley.txt` — 5.5 KB — Security posture assessment
- `casey.txt` — 5.4 KB — Code quality and technical debt
- `taylor.txt` — 5.5 KB — Infrastructure and cost efficiency
- `drew.txt` — 4.6 KB — Benchmarking and deal scenarios
- `sam.txt` — 6.0 KB — Final PE-ready report synthesis

Each prompt is self-contained and includes:
- Analyst role and context
- Specific tasks to complete (numbered)
- Input data expectations
- Output JSON schema (required fields, no field may be empty)
- GxP compliance and deal-specific considerations

## Integration Points

### With CLI/Dashboard
```python
# Dashboard wants to start a new deal
from tools.deal_manager import create_deal
deal = create_deal("veeva-2025", "Veeva Systems", "Life Sciences", "acquisition")

# Dashboard wants to run next agent
from agents.orchestrator import get_next_agent, run_agent
next_agent = get_next_agent("veeva-2025")  # returns "alex"
output = run_agent("veeva-2025", "alex", client)

# Dashboard wants to track progress
from tools.deal_manager import get_agent_progress
progress = get_agent_progress("veeva-2025")  # returns {agent_name: {status, completed_at, ...}}
```

### With Streaming/Real-time Updates
```python
# Dashboard can pass callback for live updates
def on_agent_complete(agent_name: str, deal_state: dict):
    # Send WebSocket message to client with progress
    websocket.send({
        "type": "agent_complete",
        "agent": agent_name,
        "progress": get_agent_progress(deal_id)
    })

run_chain(deal_id, client, on_progress=on_agent_complete)
```

### With Rate Limiting
```python
from tools.rate_limiter import RateLimiter

limiter = RateLimiter(max_tokens_per_minute=400_000)

# Rate limiter is passed through orchestrator to track API usage
run_chain(deal_id, client, rate_limiter=limiter)

# Check stats
print(limiter.stats())  # {total_tokens, total_calls, total_wait_seconds, current_window_tokens}
```

## Error Handling and Resilience

### Agent Failure
If an agent fails:
1. `update_agent_progress()` sets status="failed"
2. Exception is raised and propagated
3. Caller can retry or move to next agent
4. State is preserved for recovery

### Resume-from-Failure
If a deal was interrupted mid-chain:
```python
# Get next pending agent
next_agent = get_next_agent("veeva-2025")  # returns agent after last completed one

# Run from that point
run_chain("veeva-2025", client, start_from=next_agent, stop_after="sam")
```

### State Persistence
- Each agent's output is saved immediately to disk
- deal_meta.json is updated after each agent completes
- If process crashes, state is fully recoverable from disk

## Production Considerations

### Concurrency
The current implementation is single-threaded per deal. Multiple deals can run in parallel by invoking separate processes:

```python
# Process 1: veeva-2025
run_chain("veeva-2025", client)

# Process 2: acme-2025 (runs in parallel)
run_chain("acme-2025", client)
```

### Storage
Deal folders can grow to 50-100 MB per deal (depending on VDR and output sizes).
Use `delete_deal()` to archive old deals or implement retention policies.

### Logging
All operations log to `logger` (module-level logger in both modules).
Configure logging in application startup:

```python
import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
```

## Testing

All core functions have unit tests that use temporary directories:

```python
# Test assumes deal exists
deal = create_deal("test-1", "Test Corp", "Tech", "acq")
state = get_deal_state("test-1")
assert state["deal_id"] == "test-1"
```

## Future Extensions

### Checkpointing
- Save snapshots at each agent completion for audit trail
- Enable time-travel debugging (replay deal analysis at specific point)

### Partial Scans
- Run subset of agents (e.g., security + code quality only)
- Weighted scoring across domains

### Multi-Phase Support
- Phase 1: 8 agents (current)
- Phase 2: Report generation, value creation planning
- Phase 3: Post-acquisition monitoring

### Customization
- Agent chain reordering per deal type
- Custom prompts per vertical (pharma vs. fintech)
- Conditional agent execution (skip agents based on priors)
