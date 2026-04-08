"""
Agent Orchestrator: runs the Phase 1 agent chain for a deal.

Chains the 8 Phase 1 agents sequentially (Alex -> Sam).
Each agent:
1. Gets its system prompt from prompts/agents/<name>.txt
2. Receives the cumulative deal state as user message
3. Returns structured JSON that gets merged into deal state
4. Output saved to outputs/<deal_id>/agents/<name>.json

Why: PE TDD platform needs to chain multiple AI agents while:
- Maintaining state across agent calls
- Tracking progress and failures
- Supporting resume-from-failure scenarios
- Providing real-time progress callbacks for dashboards
"""

import json
import logging
import os
from pathlib import Path
from typing import Callable, Optional

from anthropic import Anthropic

from tools.deal_manager import (
    get_agent_progress,
    get_deal,
    get_deal_state,
    get_next_pending_agent,
    save_agent_output,
    update_agent_progress,
    update_deal_state,
)
from tools.json_utils import extract_json
from tools.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

# Agent chain definition: order matters, dependencies are all prior agents
AGENT_CHAIN = [
    {"name": "alex", "label": "Alex — Intake & Profile", "depends_on": []},
    {"name": "morgan", "label": "Morgan — Public Signals", "depends_on": ["alex"]},
    {"name": "jordan", "label": "Jordan — Repo Analysis", "depends_on": ["alex", "morgan"]},
    {"name": "riley", "label": "Riley — Security", "depends_on": ["alex", "morgan", "jordan"]},
    {"name": "casey", "label": "Casey — Code Quality", "depends_on": ["alex", "morgan", "jordan", "riley"]},
    {"name": "taylor", "label": "Taylor — Infrastructure", "depends_on": ["alex", "morgan", "jordan", "riley", "casey"]},
    {"name": "drew", "label": "Drew — Benchmarking", "depends_on": ["alex", "morgan", "jordan", "riley", "casey", "taylor"]},
    {"name": "sam", "label": "Sam — Report Synthesis", "depends_on": ["alex", "morgan", "jordan", "riley", "casey", "taylor", "drew"]},
]

# Get the agent names as a list
AGENT_NAMES = [agent["name"] for agent in AGENT_CHAIN]


def get_agent_by_name(name: str) -> Optional[dict]:
    """
    Look up an agent definition by name.

    Args:
        name: Agent name (e.g. "alex", "morgan").

    Returns:
        Agent dict from AGENT_CHAIN, or None if not found.
    """
    for agent in AGENT_CHAIN:
        if agent["name"] == name:
            return agent
    return None


def _load_agent_prompt(agent_name: str) -> str:
    """
    Load agent prompt from prompts/agents/<name>.txt.

    Args:
        agent_name: Name of the agent (e.g., "alex").

    Returns:
        str: The prompt text.

    Raises:
        FileNotFoundError: If prompt file does not exist.
    """
    prompt_file = Path(__file__).parent.parent / "prompts" / "agents" / f"{agent_name}.txt"

    if not prompt_file.exists():
        raise FileNotFoundError(f"Agent prompt not found: {prompt_file}")

    with open(prompt_file, "r") as f:
        return f.read()


def run_agent(
    deal_id: str,
    agent_name: str,
    client: Anthropic,
    rate_limiter: Optional[RateLimiter] = None,
) -> dict:
    """
    Run a single agent for a deal.

    1. Loads the agent prompt from prompts/agents/<name>.txt
    2. Gets the current deal state
    3. Calls Claude API with the prompt and state
    4. Parses the JSON response
    5. Saves output to disk
    6. Updates deal state with the agent's output
    7. Updates agent_progress in deal metadata

    Args:
        deal_id: Deal identifier.
        agent_name: Name of the agent to run (e.g., "alex").
        client: Anthropic API client.
        rate_limiter: Optional rate limiter to pace API calls.

    Returns:
        dict: The agent's output (the structured analysis).

    Raises:
        FileNotFoundError: If agent prompt not found.
        ValueError: If deal not found or agent name invalid.
        json.JSONDecodeError: If Claude response is not valid JSON.
    """
    # Validate agent name
    if agent_name not in AGENT_NAMES:
        raise ValueError(f"Invalid agent name: {agent_name}. Valid: {AGENT_NAMES}")

    # Load prompt
    logger.info(f"Loading prompt for {agent_name}...")
    prompt = _load_agent_prompt(agent_name)

    # Get deal state
    logger.info(f"Loading deal state for {deal_id}...")
    state = get_deal_state(deal_id)

    # Update agent progress: running
    update_agent_progress(deal_id, agent_name, "running")

    # Rate limit if needed
    if rate_limiter:
        rate_limiter.wait_if_needed(next_estimated_tokens=20000)

    # Call Claude API
    logger.info(f"Calling Claude API for agent {agent_name}...")
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=8000,
        system=prompt,
        messages=[
            {
                "role": "user",
                "content": f"Deal state:\n\n{json.dumps(state, indent=2)}",
            }
        ],
    )

    # Record token usage
    if rate_limiter:
        usage_tokens = response.usage.input_tokens + response.usage.output_tokens
        rate_limiter.record_usage(usage_tokens)
        logger.info(f"Used {usage_tokens} tokens. Rate limiter stats: {rate_limiter.stats()}")

    # Extract response text
    response_text = response.content[0].text

    # Parse JSON
    logger.info(f"Parsing JSON response from {agent_name}...")
    agent_output = extract_json(response_text)

    if agent_output is None:
        logger.error(f"Failed to extract JSON from {agent_name} response")
        logger.error(f"Raw response: {response_text[:500]}")
        raise json.JSONDecodeError("Could not extract JSON from agent response", response_text, 0)

    # Save output to disk
    output_file = save_agent_output(deal_id, agent_name, agent_output)

    # Update deal state
    logger.info(f"Updating deal state with {agent_name} output...")
    update_deal_state(deal_id, agent_name, agent_output)

    # Update agent progress: completed
    update_agent_progress(deal_id, agent_name, "completed", output_file)

    logger.info(f"Agent {agent_name} completed successfully")
    return agent_output


def run_chain(
    deal_id: str,
    client: Anthropic,
    start_from: str = "alex",
    stop_after: str = "sam",
    on_progress: Optional[Callable[[str, dict], None]] = None,
    rate_limiter: Optional[RateLimiter] = None,
) -> dict:
    """
    Run the full agent chain (or a subset).

    Iterates through AGENT_CHAIN from start_from to stop_after.
    Skips agents that are already completed (unless they appear after the range).
    Calls on_progress callback after each agent completes.

    Args:
        deal_id: Deal identifier.
        client: Anthropic API client.
        start_from: First agent to run (e.g., "alex"). Default: "alex".
        stop_after: Last agent to run (e.g., "sam"). Default: "sam".
        on_progress: Optional callback(agent_name, deal_state) called after each agent.
        rate_limiter: Optional rate limiter.

    Returns:
        dict: The final deal state after all agents complete.

    Raises:
        ValueError: If deal not found, invalid agent names, or agent fails.
    """
    # Validate agent names
    if start_from not in AGENT_NAMES or stop_after not in AGENT_NAMES:
        raise ValueError(f"Invalid agent names. Valid: {AGENT_NAMES}")

    start_idx = AGENT_NAMES.index(start_from)
    stop_idx = AGENT_NAMES.index(stop_after)

    if start_idx > stop_idx:
        raise ValueError(f"start_from ({start_from}) must come before stop_after ({stop_after})")

    # Get deal to validate it exists
    deal = get_deal(deal_id)
    if deal is None:
        raise ValueError(f"Deal {deal_id} not found")

    logger.info(f"Starting agent chain for deal {deal_id}")
    logger.info(f"Range: {start_from} -> {stop_after}")

    # Run agents in sequence
    for i in range(start_idx, stop_idx + 1):
        agent_name = AGENT_NAMES[i]
        progress = get_agent_progress(deal_id)
        agent_progress = progress.get(agent_name, {})
        status = agent_progress.get("status", "pending")

        # Skip if already completed
        if status == "completed":
            logger.info(f"Skipping {agent_name} (already completed)")
            if on_progress:
                state = get_deal_state(deal_id)
                on_progress(agent_name, state)
            continue

        # Run agent
        logger.info(f"Running {agent_name}...")
        try:
            run_agent(deal_id, agent_name, client, rate_limiter)

            # Call progress callback
            if on_progress:
                state = get_deal_state(deal_id)
                on_progress(agent_name, state)

        except Exception as e:
            logger.error(f"Agent {agent_name} failed: {e}")
            update_agent_progress(deal_id, agent_name, "failed")
            raise

    # Return final deal state
    final_state = get_deal_state(deal_id)
    logger.info(f"Agent chain completed for deal {deal_id}")
    return final_state


def get_next_agent(deal_id: str) -> Optional[str]:
    """
    Returns the name of the next agent to run, or None if chain is complete.

    Args:
        deal_id: Deal identifier.

    Returns:
        str: Agent name, or None if all agents are complete.

    Raises:
        ValueError: If deal not found.
    """
    return get_next_pending_agent(deal_id, AGENT_NAMES)


def run_single_agent_by_index(
    deal_id: str,
    agent_index: int,
    client: Anthropic,
    rate_limiter: Optional[RateLimiter] = None,
) -> dict:
    """
    Run a single agent by its index in the chain.

    Helper function for dashboard/CLI that may refer to agents by index.

    Args:
        deal_id: Deal identifier.
        agent_index: Index in AGENT_NAMES (0-based).
        client: Anthropic API client.
        rate_limiter: Optional rate limiter.

    Returns:
        dict: Agent output.

    Raises:
        ValueError: If index out of range.
    """
    if agent_index < 0 or agent_index >= len(AGENT_NAMES):
        raise ValueError(f"Agent index {agent_index} out of range (0-{len(AGENT_NAMES) - 1})")

    agent_name = AGENT_NAMES[agent_index]
    return run_agent(deal_id, agent_name, client, rate_limiter)
