"""
Edge <-> Cloud sync.

Policy (deliberately simple for the hackathon, called out so it's easy to
upgrade during judging Q&A):

  - Push: every point locally marked `dirty=True` is upserted to the cloud
    collection, then marked clean with a `synced_at` timestamp.
  - Pull: the device keeps a `last_synced_at` cursor. On each sync, it asks
    the cloud for every point with `payload.updated_at > last_synced_at`
    and applies them locally.
  - Conflict resolution: if a point exists both locally (dirty) and in the
    cloud's "updated since" set, last-write-wins by comparing
    `payload.updated_at`. This is the seam to replace with something
    smarter (vector merge, manual review queue, CRDT-style merge) later.

Enhanced with retry logic, state persistence, and batch management for reliability.
"""
import json
import os
import time
from dataclasses import dataclass, field
from typing import Optional

from qdrant_client.http import models as qmodels

from app.services.edge_store import edge_store
from app.services.cloud_store import cloud_store
from app.services.connectivity import is_online
from app.services.sync_logger import sync_logger
from app.config import AUTO_RESOLUTION_THRESHOLD_SECONDS, CIRCUIT_BREAKER_FAILURE_THRESHOLD, CIRCUIT_BREAKER_RECOVERY_TIMEOUT

# Sync state persistence file
SYNC_STATE_FILE = "sync_state.json"
CONFLICTS_FILE = "conflicts.json"

# Retry configuration
MAX_RETRIES = 3
RETRY_DELAY_BASE = 1.0  # seconds
BATCH_SIZE = 100  # max points per batch


@dataclass
class SyncState:
    last_synced_at: float = 0.0
    last_result: Optional[str] = None
    last_run_at: Optional[float] = None
    retry_count: int = 0
    consecutive_failures: int = 0
    total_pushed: int = 0
    total_pulled: int = 0
    sync_paused: bool = False
    circuit_breaker_open: bool = False
    circuit_breaker_opened_at: Optional[float] = None


@dataclass
class Conflict:
    point_id: str
    local_payload: dict
    remote_payload: dict
    local_updated_at: float
    remote_updated_at: float
    detected_at: float
    resolved: bool = False
    resolution: Optional[str] = None


sync_state = SyncState()
conflicts: list[Conflict] = []


def load_sync_state():
    """Load sync state from disk for crash recovery."""
    global sync_state
    if os.path.exists(SYNC_STATE_FILE):
        try:
            with open(SYNC_STATE_FILE, 'r') as f:
                data = json.load(f)
                sync_state = SyncState(**data)
                print(f"Sync state loaded: last_synced_at={sync_state.last_synced_at}")
        except Exception as e:
            print(f"Failed to load sync state: {e}, using defaults")


def load_conflicts():
    """Load conflicts from disk for persistence."""
    global conflicts
    if os.path.exists(CONFLICTS_FILE):
        try:
            with open(CONFLICTS_FILE, 'r') as f:
                data = json.load(f)
                conflicts = [Conflict(**c) for c in data]
                print(f"Loaded {len(conflicts)} conflicts from disk")
        except Exception as e:
            print(f"Failed to load conflicts: {e}, starting with empty list")
            conflicts = []


def save_sync_state():
    """Persist sync state to disk for crash recovery."""
    try:
        with open(SYNC_STATE_FILE, 'w') as f:
            json.dump({
                'last_synced_at': sync_state.last_synced_at,
                'last_result': sync_state.last_result,
                'last_run_at': sync_state.last_run_at,
                'retry_count': sync_state.retry_count,
                'consecutive_failures': sync_state.consecutive_failures,
                'total_pushed': sync_state.total_pushed,
                'total_pulled': sync_state.total_pulled,
            }, f)
    except Exception as e:
        print(f"Failed to save sync state: {e}")


def save_conflicts():
    """Persist conflicts to disk."""
    try:
        with open(CONFLICTS_FILE, 'w') as f:
            json.dump([
                {
                    'point_id': c.point_id,
                    'local_payload': c.local_payload,
                    'remote_payload': c.remote_payload,
                    'local_updated_at': c.local_updated_at,
                    'remote_updated_at': c.remote_updated_at,
                    'detected_at': c.detected_at,
                    'resolved': c.resolved,
                    'resolution': c.resolution,
                }
                for c in conflicts
            ], f)
    except Exception as e:
        print(f"Failed to save conflicts: {e}")


def should_sync(device_id: Optional[str] = None) -> bool:
    """Only sync when online AND there's something to do."""
    if not is_online():
        return False
    if sync_state.sync_paused:
        return False
    # Check circuit breaker
    if sync_state.circuit_breaker_open:
        if sync_state.circuit_breaker_opened_at:
            elapsed = time.time() - sync_state.circuit_breaker_opened_at
            if elapsed < CIRCUIT_BREAKER_RECOVERY_TIMEOUT:
                return False
            else:
                # Recovery timeout elapsed, try to close circuit breaker
                sync_state.circuit_breaker_open = False
                sync_state.circuit_breaker_opened_at = None
                print("Circuit breaker recovery timeout elapsed, attempting to close")
    return len(edge_store.dirty_points(device_id)) > 0 or True  # always worth checking for pulls


def resolve_conflict(local_updated_at: float, remote_updated_at: float) -> str:
    """Returns 'local' or 'remote' — whichever should win."""
    time_diff = abs(remote_updated_at - local_updated_at)
    # Auto-resolve if time difference is below threshold
    if time_diff < AUTO_RESOLUTION_THRESHOLD_SECONDS:
        return "remote" if remote_updated_at > local_updated_at else "local"
    # Otherwise, queue for manual resolution
    return "manual"


def run_sync(device_id: Optional[str] = None) -> str:
    """Run sync with retry logic and state persistence."""
    sync_logger.start_operation("sync")

    if not is_online():
        sync_state.last_result = "skipped: offline"
        sync_state.last_run_at = time.time()
        save_sync_state()
        sync_logger.end_operation("sync", success=True, details={"result": "skipped: offline"})
        return sync_state.last_result

    if sync_state.sync_paused:
        sync_state.last_result = "skipped: paused"
        sync_state.last_run_at = time.time()
        save_sync_state()
        sync_logger.end_operation("sync", success=True, details={"result": "skipped: paused"})
        return sync_state.last_result

    # Reset retry count on successful connectivity
    sync_state.retry_count = 0

    try:
        pushed = _push_dirty_with_retry(device_id)
        pulled = _pull_updates_with_retry(device_id)

        # Success - reset failure counter and close circuit breaker
        sync_state.consecutive_failures = 0
        sync_state.circuit_breaker_open = False
        sync_state.circuit_breaker_opened_at = None
        sync_state.total_pushed += pushed
        sync_state.total_pulled += pulled
        sync_state.last_synced_at = time.time()
        sync_state.last_run_at = sync_state.last_synced_at
        sync_state.last_result = f"ok: pushed {pushed}, pulled {pulled}"
        save_sync_state()
        sync_logger.end_operation("sync", success=True, details={"pushed": pushed, "pulled": pulled})
        return sync_state.last_result

    except Exception as e:
        sync_state.consecutive_failures += 1
        sync_state.last_result = f"error: {str(e)}"
        sync_state.last_run_at = time.time()
        
        # Open circuit breaker if threshold exceeded
        if sync_state.consecutive_failures >= CIRCUIT_BREAKER_FAILURE_THRESHOLD:
            sync_state.circuit_breaker_open = True
            sync_state.circuit_breaker_opened_at = time.time()
            print(f"Circuit breaker opened after {CIRCUIT_BREAKER_FAILURE_THRESHOLD} consecutive failures")
        
        save_sync_state()
        sync_logger.end_operation("sync", success=False, details={"error": str(e)})
        raise


def _push_dirty_with_retry(device_id: Optional[str] = None) -> int:
    """Push dirty points with retry logic and batching."""
    for attempt in range(MAX_RETRIES):
        try:
            return _push_dirty_batched(device_id)
        except Exception as e:
            sync_state.retry_count += 1
            if attempt < MAX_RETRIES - 1:
                delay = RETRY_DELAY_BASE * (2 ** attempt)  # exponential backoff
                print(f"Push failed (attempt {attempt + 1}), retrying in {delay}s: {e}")
                time.sleep(delay)
            else:
                print(f"Push failed after {MAX_RETRIES} attempts: {e}")
                raise


def _push_dirty_batched(device_id: Optional[str] = None) -> int:
    """Push dirty points in batches to avoid overwhelming the network."""
    sync_logger.start_operation("push")
    dirty = edge_store.dirty_points(device_id)
    if not dirty:
        sync_logger.end_operation("push", success=True, details={"points_pushed": 0})
        return 0

    total_pushed = 0
    try:
        for i in range(0, len(dirty), BATCH_SIZE):
            batch = dirty[i:i + BATCH_SIZE]
            points = [
                qmodels.PointStruct(id=p.id, vector=p.vector, payload=p.payload)
                for p in batch
            ]
            cloud_store.upsert_many(points, device_id)
            edge_store.mark_synced([p.id for p in batch], device_id)
            total_pushed += len(batch)
            print(f"Pushed batch {i//BATCH_SIZE + 1}: {len(batch)} points")

        sync_logger.log_push(total_pushed, success=True)
        sync_logger.end_operation("push", success=True, details={"points_pushed": total_pushed})
        return total_pushed
    except Exception as e:
        sync_logger.log_push(len(dirty), success=False, error=str(e))
        sync_logger.end_operation("push", success=False, details={"error": str(e)})
        raise


def _pull_updates_with_retry(device_id: Optional[str] = None) -> int:
    """Pull updates with retry logic."""
    for attempt in range(MAX_RETRIES):
        try:
            return _pull_updates(device_id)
        except Exception as e:
            sync_state.retry_count += 1
            if attempt < MAX_RETRIES - 1:
                delay = RETRY_DELAY_BASE * (2 ** attempt)  # exponential backoff
                print(f"Pull failed (attempt {attempt + 1}), retrying in {delay}s: {e}")
                time.sleep(delay)
            else:
                print(f"Pull failed after {MAX_RETRIES} attempts: {e}")
                raise


def _pull_updates(device_id: Optional[str] = None) -> int:
    sync_logger.start_operation("pull")
    remote_points = cloud_store.get_updated_since(sync_state.last_synced_at, device_id)
    applied = 0
    conflicts_detected = 0
    auto_resolved = 0
    try:
        for rp in remote_points:
            remote_updated_at = (rp.payload or {}).get("updated_at", 0)
            local = next((lp for lp in edge_store.all_points(device_id=device_id) if lp.id == rp.id), None)
            local_updated_at = (local.payload or {}).get("updated_at", 0) if local else -1

            # Check if this is a conflict (both sides have data)
            if local_updated_at != -1:
                # Check if local point is dirty (has unsent changes)
                local_dirty = (local.payload or {}).get("dirty", False)
                if local_dirty:
                    resolution = resolve_conflict(local_updated_at, remote_updated_at)
                    if resolution == "manual":
                        # Queue conflict for manual resolution
                        _queue_conflict(rp.id, local.payload, rp.payload, local_updated_at, remote_updated_at)
                        conflicts_detected += 1
                        continue
                    else:
                        # Auto-resolve
                        auto_resolved += 1
                        if resolution == "remote":
                            edge_store.upsert_from_cloud(rp.id, rp.vector, rp.payload, device_id)
                            edge_store.mark_synced([rp.id], device_id)
                            applied += 1
                        else:
                            # Keep local, push to cloud
                            cloud_store.upsert_many([qmodels.PointStruct(
                                id=local.id, vector=local.vector, payload=local.payload
                            )], device_id)
                            edge_store.mark_synced([rp.id], device_id)
                            applied += 1
                        sync_logger.log_conflict(rp.id, local_updated_at, remote_updated_at, resolution)
                        continue

            resolution = resolve_conflict(local_updated_at, remote_updated_at)
            if resolution == "remote":
                edge_store.upsert_from_cloud(rp.id, rp.vector, rp.payload, device_id)
                applied += 1
                # Log conflict resolution if both sides had data
                if local_updated_at != -1:
                    sync_logger.log_conflict(rp.id, local_updated_at, remote_updated_at, resolution)

        if conflicts_detected > 0:
            save_conflicts()

        sync_logger.log_pull(applied, success=True)
        sync_logger.end_operation("pull", success=True, details={"points_pulled": applied, "conflicts_detected": conflicts_detected, "auto_resolved": auto_resolved})
        return applied
    except Exception as e:
        sync_logger.log_pull(len(remote_points), success=False, error=str(e))
        sync_logger.end_operation("pull", success=False, details={"error": str(e)})
        raise


def _queue_conflict(point_id: str, local_payload: dict, remote_payload: dict,
                    local_updated_at: float, remote_updated_at: float):
    """Queue a conflict for manual resolution."""
    # Check if conflict already exists
    existing = next((c for c in conflicts if c.point_id == point_id and not c.resolved), None)
    if existing:
        return  # Already queued

    conflict = Conflict(
        point_id=point_id,
        local_payload=local_payload,
        remote_payload=remote_payload,
        local_updated_at=local_updated_at,
        remote_updated_at=remote_updated_at,
        detected_at=time.time()
    )
    conflicts.append(conflict)
    sync_logger.log_conflict(point_id, local_updated_at, remote_updated_at)


def get_unresolved_conflicts() -> list[Conflict]:
    """Get all unresolved conflicts."""
    return [c for c in conflicts if not c.resolved]


def resolve_conflict_manual(point_id: str, resolution: str, merged_payload: dict = None, device_id: Optional[str] = None) -> bool:
    """Manually resolve a conflict."""
    conflict = next((c for c in conflicts if c.point_id == point_id and not c.resolved), None)
    if not conflict:
        return False

    try:
        if resolution == "local":
            # Keep local version, push to cloud
            local = next((lp for lp in edge_store.all_points(device_id=device_id) if lp.id == point_id), None)
            if local:
                cloud_store.upsert_many([qmodels.PointStruct(
                    id=local.id, vector=local.vector, payload=local.payload
                )], device_id)
                edge_store.mark_synced([point_id], device_id)

        elif resolution == "remote":
            # Accept remote version, need to fetch vector from cloud
            remote_point = cloud_store.get_point(point_id, device_id)
            if remote_point:
                edge_store.upsert_from_cloud(point_id, remote_point.vector, conflict.remote_payload, device_id)

        elif resolution == "merge" and merged_payload:
            # Apply merged payload
            local = next((lp for lp in edge_store.all_points(device_id=device_id) if lp.id == point_id), None)
            if local:
                merged = {**local.payload, **merged_payload}
                edge_store.upsert_from_cloud(point_id, local.vector, merged, device_id)
                cloud_store.upsert_many([qmodels.PointStruct(
                    id=point_id, vector=local.vector, payload=merged
                )], device_id)
                edge_store.mark_synced([point_id], device_id)

        conflict.resolved = True
        conflict.resolution = resolution
        save_conflicts()
        sync_logger.log_conflict(point_id, conflict.local_updated_at,
                                 conflict.remote_updated_at, resolution)
        return True

    except Exception as e:
        print(f"Failed to resolve conflict {point_id}: {e}")
        return False


# Load state on module import
load_sync_state()
load_conflicts()
