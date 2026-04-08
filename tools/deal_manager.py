"""
Deal Manager: multi-deal lifecycle management.

Provides CRUD operations and state persistence for technology due diligence deals.
Each deal gets a folder at outputs/<deal_id>/ with:
  - deal_meta.json (metadata: company, sector, deal_type, created_at, status, agent_progress)
  - deal_state.json (cumulative state across all agents)
  - agents/ (per-agent output JSONs)
  - vdr/ (VDR scan outputs)
  - questionnaire/ (DRL tracking)

Why: PE TDD platform needs to manage multiple concurrent deals with persistent state
across agent runs. This module is the source of truth for all deal metadata and state.
"""

import json
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Deal status constants
DEAL_STATUSES = ["intake", "scanning", "analyzing", "review", "complete", "archived"]

# Path to outputs directory
OUTPUTS_DIR = Path(__file__).parent.parent / "outputs"


def _ensure_outputs_dir() -> Path:
    """Ensure outputs directory exists."""
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    return OUTPUTS_DIR


def create_deal(
    deal_id: str,
    company_name: str,
    sector: str,
    deal_type: str,
    vdr_path: str = "",
    intake_data: Optional[dict] = None,
) -> dict:
    """
    Create a new deal with initial metadata.

    Creates the folder structure at outputs/<deal_id>/ and initializes
    deal_meta.json and deal_state.json files.

    Args:
        deal_id: Unique identifier for this deal (e.g., "acme-2025-q1").
        company_name: Name of the target company.
        sector: Industry sector (e.g., "Life Sciences").
        deal_type: Deal type (e.g., "acquisition", "carve-out").
        vdr_path: Optional path to virtual data room.
        intake_data: Optional dict of intake data to seed the deal state.

    Returns:
        dict: The created deal_meta object.

    Raises:
        ValueError: If deal_id already exists.
    """
    _ensure_outputs_dir()
    deal_folder = OUTPUTS_DIR / deal_id

    if deal_folder.exists():
        raise ValueError(f"Deal {deal_id} already exists at {deal_folder}")

    # Create folder structure
    deal_folder.mkdir(parents=True, exist_ok=True)
    (deal_folder / "agents").mkdir(exist_ok=True)
    (deal_folder / "vdr").mkdir(exist_ok=True)
    (deal_folder / "questionnaire").mkdir(exist_ok=True)

    # Initialize deal_meta.json
    now = datetime.utcnow().isoformat() + "Z"
    deal_meta = {
        "deal_id": deal_id,
        "company_name": company_name,
        "sector": sector,
        "deal_type": deal_type,
        "vdr_path": vdr_path,
        "status": "intake",
        "created_at": now,
        "updated_at": now,
        "agent_progress": {},
    }

    meta_file = deal_folder / "deal_meta.json"
    with open(meta_file, "w") as f:
        json.dump(deal_meta, f, indent=2)

    # Initialize deal_state.json
    deal_state = {
        "deal_id": deal_id,
        "company_name": company_name,
        "status": "intake",
        "intake_data": intake_data or {},
        "agents": {},
    }

    state_file = deal_folder / "deal_state.json"
    with open(state_file, "w") as f:
        json.dump(deal_state, f, indent=2)

    logger.info(f"Created deal {deal_id} at {deal_folder}")
    return deal_meta


def get_deal(deal_id: str) -> Optional[dict]:
    """
    Retrieve deal metadata by ID.

    Args:
        deal_id: Deal identifier.

    Returns:
        dict: The deal_meta object, or None if not found.
    """
    meta_file = OUTPUTS_DIR / deal_id / "deal_meta.json"
    if not meta_file.exists():
        return None

    with open(meta_file, "r") as f:
        return json.load(f)


def list_deals() -> list[dict]:
    """
    List all deals in the outputs directory.

    Returns:
        list: Deal metadata objects, sorted by created_at (newest first).
    """
    _ensure_outputs_dir()
    deals = []

    for deal_folder in sorted(OUTPUTS_DIR.iterdir()):
        if not deal_folder.is_dir():
            continue

        meta_file = deal_folder / "deal_meta.json"
        if meta_file.exists():
            with open(meta_file, "r") as f:
                deals.append(json.load(f))

    # Sort by created_at descending
    deals.sort(key=lambda d: d.get("created_at", ""), reverse=True)
    return deals


def update_deal(deal_id: str, **kwargs) -> dict:
    """
    Update deal metadata fields.

    Only updates top-level fields in deal_meta.json. To update agent_progress,
    use update_agent_progress() instead.

    Args:
        deal_id: Deal identifier.
        **kwargs: Fields to update (e.g., status="scanning", vdr_path="/path").

    Returns:
        dict: The updated deal_meta object.

    Raises:
        ValueError: If deal does not exist.
    """
    meta = get_deal(deal_id)
    if meta is None:
        raise ValueError(f"Deal {deal_id} not found")

    # Update fields
    for key, value in kwargs.items():
        if key != "agent_progress":  # agent_progress is updated separately
            meta[key] = value

    # Update timestamp
    meta["updated_at"] = datetime.utcnow().isoformat() + "Z"

    # Persist
    meta_file = OUTPUTS_DIR / deal_id / "deal_meta.json"
    with open(meta_file, "w") as f:
        json.dump(meta, f, indent=2)

    logger.info(f"Updated deal {deal_id}: {list(kwargs.keys())}")
    return meta


def get_deal_state(deal_id: str) -> dict:
    """
    Get the cumulative deal state (all agent outputs merged).

    Args:
        deal_id: Deal identifier.

    Returns:
        dict: The deal_state object.

    Raises:
        ValueError: If deal does not exist.
    """
    state_file = OUTPUTS_DIR / deal_id / "deal_state.json"
    if not state_file.exists():
        raise ValueError(f"Deal {deal_id} not found")

    with open(state_file, "r") as f:
        return json.load(f)


def update_deal_state(deal_id: str, agent_name: str, agent_output: dict) -> dict:
    """
    Merge an agent's output into the cumulative deal state and save to disk.

    Args:
        deal_id: Deal identifier.
        agent_name: Name of the agent producing the output (e.g., "alex").
        agent_output: The structured agent output dict.

    Returns:
        dict: The updated deal_state object.

    Raises:
        ValueError: If deal does not exist.
    """
    state = get_deal_state(deal_id)

    # Store agent output in the state
    state["agents"][agent_name] = agent_output

    # Persist to disk
    state_file = OUTPUTS_DIR / deal_id / "deal_state.json"
    with open(state_file, "w") as f:
        json.dump(state, f, indent=2)

    logger.info(f"Updated deal state {deal_id} with output from {agent_name}")
    return state


def get_agent_progress(deal_id: str) -> dict:
    """
    Get the progress of all agents for a deal.

    Returns dict mapping agent_name -> {status, completed_at, output_file}.

    Args:
        deal_id: Deal identifier.

    Returns:
        dict: Agent progress mapping.

    Raises:
        ValueError: If deal does not exist.
    """
    meta = get_deal(deal_id)
    if meta is None:
        raise ValueError(f"Deal {deal_id} not found")

    return meta.get("agent_progress", {})


def update_agent_progress(
    deal_id: str,
    agent_name: str,
    status: str,
    output_file: str = "",
) -> dict:
    """
    Update the progress of a single agent.

    Args:
        deal_id: Deal identifier.
        agent_name: Name of the agent.
        status: Status string ("pending", "running", "completed", "failed").
        output_file: Path to the agent's output file (relative to deal folder).

    Returns:
        dict: Updated deal_meta object.

    Raises:
        ValueError: If deal does not exist.
    """
    meta = get_deal(deal_id)
    if meta is None:
        raise ValueError(f"Deal {deal_id} not found")

    now = datetime.utcnow().isoformat() + "Z"

    meta["agent_progress"][agent_name] = {
        "status": status,
        "completed_at": now if status == "completed" else None,
        "output_file": output_file,
    }

    # Persist
    meta_file = OUTPUTS_DIR / deal_id / "deal_meta.json"
    with open(meta_file, "w") as f:
        json.dump(meta, f, indent=2)

    return meta


def save_agent_output(deal_id: str, agent_name: str, output: dict) -> str:
    """
    Save agent output to outputs/<deal_id>/agents/<agent_name>.json.

    Args:
        deal_id: Deal identifier.
        agent_name: Name of the agent.
        output: Agent output dict.

    Returns:
        str: Path to the saved file (absolute).

    Raises:
        ValueError: If deal does not exist.
    """
    deal_folder = OUTPUTS_DIR / deal_id
    if not deal_folder.exists():
        raise ValueError(f"Deal {deal_id} not found")

    output_file = deal_folder / "agents" / f"{agent_name}.json"
    with open(output_file, "w") as f:
        json.dump(output, f, indent=2)

    logger.info(f"Saved agent output for {agent_name} at {output_file}")
    return str(output_file.absolute())


def get_agent_output(deal_id: str, agent_name: str) -> Optional[dict]:
    """
    Load a specific agent's output from disk.

    Args:
        deal_id: Deal identifier.
        agent_name: Name of the agent.

    Returns:
        Agent output dict, or None if not found.
    """
    output_file = OUTPUTS_DIR / deal_id / "agents" / f"{agent_name}.json"
    if not output_file.exists():
        return None
    try:
        with open(output_file, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as exc:
        logger.warning(f"Failed to load agent output for {agent_name}: {exc}")
        return None


def update_agent_status(deal_id: str, agent_name: str, status: str, **kwargs) -> dict:
    """
    Convenience wrapper around update_agent_progress for dashboard use.

    Args:
        deal_id: Deal identifier.
        agent_name: Name of the agent.
        status: New status ("pending", "running", "completed", "failed").
        **kwargs: Additional fields (completed_at, error, etc.)

    Returns:
        Updated agent progress dict.
    """
    return update_agent_progress(deal_id, agent_name, status, **kwargs)


def get_next_pending_agent(deal_id: str, agent_chain: list[str]) -> Optional[str]:
    """
    Get the next agent to run based on the chain order.

    An agent is ready to run if:
    1. Its status is not "completed" in agent_progress
    2. All agents it depends on (all prior agents in chain) are "completed"

    Args:
        deal_id: Deal identifier.
        agent_chain: Ordered list of agent names in the chain.

    Returns:
        str: Name of next agent to run, or None if chain is complete.

    Raises:
        ValueError: If deal does not exist.
    """
    progress = get_agent_progress(deal_id)

    for agent_name in agent_chain:
        agent_progress = progress.get(agent_name, {})
        status = agent_progress.get("status", "pending")

        if status != "completed":
            return agent_name

    return None


def archive_deal(deal_id: str) -> dict:
    """
    Archive a deal (set status to "archived").

    Args:
        deal_id: Deal identifier.

    Returns:
        dict: Updated deal_meta object.

    Raises:
        ValueError: If deal does not exist.
    """
    return update_deal(deal_id, status="archived")


def delete_deal(deal_id: str) -> bool:
    """
    Delete a deal folder and all its contents.

    Args:
        deal_id: Deal identifier.

    Returns:
        bool: True if deleted, False if deal did not exist.
    """
    deal_folder = OUTPUTS_DIR / deal_id
    if not deal_folder.exists():
        return False

    shutil.rmtree(deal_folder)
    logger.info(f"Deleted deal {deal_id}")
    return True
