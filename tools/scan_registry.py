"""
Scan registry: tracks the state and progress of VDR scans.

Why: A full VDR scan takes 30-60 minutes. The registry persists scan state
to disk so the dashboard can show live progress, the checkpoint system can
resume crashed scans, and practitioners can see which scans are running,
completed, or failed.

Storage: JSON file at outputs/_scan_registry.json. Each key is a company name.
"""
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

OUTPUTS_DIR = Path(__file__).parent.parent / "outputs"
REGISTRY_PATH = OUTPUTS_DIR / "_scan_registry.json"


def _load_registry() -> dict:
    """Load the scan registry from disk."""
    if not REGISTRY_PATH.exists():
        return {}
    try:
        with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as exc:
        logger.warning("Failed to load scan registry: %s", exc)
        return {}


def _save_registry(data: dict) -> None:
    """Save the scan registry to disk."""
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)


def register_scan(
    company_name: str,
    deal_id: str = "",
    sector: str = "",
    deal_type: str = "",
    scan_mode: str = "full",
    total_vdr_docs: int = 0,
    selected_batches: Optional[list] = None,
) -> dict:
    """
    Register a new scan or update an existing one to 'running' state.

    Args:
        company_name: Company being scanned.
        deal_id: Deal identifier.
        sector: Sector/vertical.
        deal_type: Deal type.
        scan_mode: "full" or "selective".
        total_vdr_docs: Total documents in VDR.
        selected_batches: Batches selected for selective scan.

    Returns:
        The scan record dict.
    """
    registry = _load_registry()
    now = datetime.now(timezone.utc).isoformat()

    record = {
        "status": "running",
        "phase": "starting",
        "deal_id": deal_id,
        "sector": sector,
        "deal_type": deal_type,
        "scan_mode": scan_mode,
        "total_vdr_docs": total_vdr_docs,
        "selected_batches": selected_batches or [],
        "pending_batches": [],
        "progress": {
            "batches_done": 0,
            "batches_total": 0,
            "signals_found": 0,
            "doc_count": 0,
            "batches_resumed": 0,
        },
        "timing": {
            "batch_times": [],        # seconds per completed batch
            "current_batch_start": None,
            "avg_batch_seconds": None,
            "eta_seconds": None,      # estimated seconds remaining
            "eta_iso": None,          # estimated completion time (ISO string)
            "elapsed_seconds": 0,
        },
        "started_at": now,
        "updated_at": now,
        "version": 1,
        "rating": None,
        "error": None,
    }

    # Preserve version number if re-scanning
    if company_name in registry:
        prev = registry[company_name]
        record["version"] = prev.get("version", 0) + 1

    registry[company_name] = record
    _save_registry(registry)
    return record


def update_scan(company_name: str, **kwargs) -> Optional[dict]:
    """
    Update fields on an existing scan record.

    Args:
        company_name: Company name.
        **kwargs: Fields to update (status, phase, progress, rating, error, etc.)

    Returns:
        Updated record, or None if company not found.
    """
    registry = _load_registry()
    if company_name not in registry:
        return None

    record = registry[company_name]
    for key, value in kwargs.items():
        if key == "progress" and isinstance(value, dict):
            record.setdefault("progress", {}).update(value)
        else:
            record[key] = value

    record["updated_at"] = datetime.now(timezone.utc).isoformat()
    registry[company_name] = record
    _save_registry(registry)
    return record


def get_scan(company_name: str) -> Optional[dict]:
    """
    Get scan record for a specific company.

    Args:
        company_name: Company name.

    Returns:
        Scan record dict, or None if not found.
    """
    registry = _load_registry()
    return registry.get(company_name)


def get_all_scans() -> dict:
    """
    Get all scan records.

    Returns:
        Dict of company_name -> scan record.
    """
    return _load_registry()


def cleanup_stale_scans(max_age_hours: int = 24) -> int:
    """
    Remove scan records that have been 'running' for too long (likely crashed).

    Args:
        max_age_hours: Consider scans stale after this many hours.

    Returns:
        Number of stale scans cleaned up.
    """
    registry = _load_registry()
    now = datetime.now(timezone.utc)
    stale = []

    for company, record in registry.items():
        if record.get("status") == "running":
            started = record.get("started_at", "")
            try:
                started_dt = datetime.fromisoformat(started.replace("Z", "+00:00"))
                age_hours = (now - started_dt).total_seconds() / 3600
                if age_hours > max_age_hours:
                    stale.append(company)
            except (ValueError, TypeError):
                stale.append(company)

    for company in stale:
        registry[company]["status"] = "stale"
        registry[company]["updated_at"] = now.isoformat()
        logger.warning("Marked scan for %s as stale (running > %dh)", company, max_age_hours)

    if stale:
        _save_registry(registry)

    return len(stale)


def start_batch_timer(company_name: str) -> Optional[dict]:
    """
    Mark the start of a batch extraction so we can measure its duration.

    Args:
        company_name: Company name key.

    Returns:
        Updated record, or None if not found.
    """
    registry = _load_registry()
    if company_name not in registry:
        return None
    record = registry[company_name]
    record.setdefault("timing", {})
    record["timing"]["current_batch_start"] = datetime.now(timezone.utc).isoformat()
    record["updated_at"] = datetime.now(timezone.utc).isoformat()
    registry[company_name] = record
    _save_registry(registry)
    return record


def finish_batch_timer(company_name: str) -> Optional[dict]:
    """
    Record a completed batch duration and recalculate ETA.

    Computes average batch time from all completed batches, then multiplies
    by remaining batches to produce an ETA.

    Args:
        company_name: Company name key.

    Returns:
        Updated record with new ETA, or None if not found.
    """
    registry = _load_registry()
    if company_name not in registry:
        return None

    record = registry[company_name]
    timing = record.setdefault("timing", {})
    now = datetime.now(timezone.utc)

    # Calculate this batch's duration
    batch_start_str = timing.get("current_batch_start")
    if batch_start_str:
        try:
            batch_start = datetime.fromisoformat(batch_start_str.replace("Z", "+00:00"))
            batch_seconds = (now - batch_start).total_seconds()
            batch_times = timing.setdefault("batch_times", [])
            batch_times.append(round(batch_seconds, 1))
        except (ValueError, TypeError):
            pass

    # Calculate elapsed since scan start
    started_str = record.get("started_at", "")
    try:
        started_dt = datetime.fromisoformat(started_str.replace("Z", "+00:00"))
        timing["elapsed_seconds"] = round((now - started_dt).total_seconds(), 1)
    except (ValueError, TypeError):
        pass

    # Recalculate ETA
    batch_times = timing.get("batch_times", [])
    if batch_times:
        avg = sum(batch_times) / len(batch_times)
        timing["avg_batch_seconds"] = round(avg, 1)

        batches_done = record.get("progress", {}).get("batches_done", 0)
        batches_total = record.get("progress", {}).get("batches_total", 0)
        remaining = max(0, batches_total - batches_done)

        eta_seconds = round(avg * remaining)
        timing["eta_seconds"] = eta_seconds
        timing["eta_iso"] = (now + timedelta(seconds=eta_seconds)).isoformat()

    timing["current_batch_start"] = None
    record["updated_at"] = now.isoformat()
    registry[company_name] = record
    _save_registry(registry)
    return record


def remove_scan(company_name: str) -> bool:
    """
    Remove a scan record from the registry.

    Args:
        company_name: Company name key to remove.

    Returns:
        True if removed, False if not found.
    """
    registry = _load_registry()
    if company_name not in registry:
        return False
    del registry[company_name]
    _save_registry(registry)
    logger.info("Removed scan record for %s", company_name)
    return True
