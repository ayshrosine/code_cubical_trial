from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends

from app.models.schemas import Conflict, ConflictResolution
from app.services import sync_engine
from app.services.auth_middleware import optional_auth

router = APIRouter(prefix="/conflicts", tags=["conflicts"])


@router.get("", response_model=list[Conflict])
def list_conflicts():
    """List all unresolved conflicts."""
    conflicts = sync_engine.get_unresolved_conflicts()
    return [
        Conflict(
            point_id=c.point_id,
            local_payload=c.local_payload,
            remote_payload=c.remote_payload,
            local_updated_at=c.local_updated_at,
            remote_updated_at=c.remote_updated_at,
            detected_at=c.detected_at,
            resolved=c.resolved,
            resolution=c.resolution
        )
        for c in conflicts
    ]


@router.get("/{point_id}", response_model=Conflict)
def get_conflict(point_id: str):
    """Get a specific conflict by point ID."""
    conflict = next((c for c in sync_engine.conflicts if c.point_id == point_id), None)
    if not conflict:
        raise HTTPException(status_code=404, detail="Conflict not found")

    return Conflict(
        point_id=conflict.point_id,
        local_payload=conflict.local_payload,
        remote_payload=conflict.remote_payload,
        local_updated_at=conflict.local_updated_at,
        remote_updated_at=conflict.remote_updated_at,
        detected_at=conflict.detected_at,
        resolved=conflict.resolved,
        resolution=conflict.resolution
    )


@router.post("/{point_id}/resolve")
def resolve_conflict(point_id: str, resolution: ConflictResolution, device: dict = Depends(optional_auth)):
    """Resolve a specific conflict."""
    device_id = device["device_id"] if device else None
    success = sync_engine.resolve_conflict_manual(
        point_id,
        resolution.resolution_type,
        resolution.merged_payload,
        device_id
    )

    if not success:
        raise HTTPException(status_code=400, detail="Failed to resolve conflict")

    return {"point_id": point_id, "resolution": resolution.resolution_type, "success": True}


@router.post("/resolve-all")
def resolve_all_conflicts(resolution: ConflictResolution, device: dict = Depends(optional_auth)):
    """Resolve all conflicts with the same resolution type."""
    device_id = device["device_id"] if device else None
    conflicts = sync_engine.get_unresolved_conflicts()
    resolved_count = 0

    for conflict in conflicts:
        success = sync_engine.resolve_conflict_manual(
            conflict.point_id,
            resolution.resolution_type,
            resolution.merged_payload,
            device_id
        )
        if success:
            resolved_count += 1

    return {"resolved_count": resolved_count, "total_conflicts": len(conflicts)}


@router.get("/count")
def conflict_count():
    """Get count of unresolved conflicts."""
    return {"count": len(sync_engine.get_unresolved_conflicts())}


@router.get("/history")
def conflict_history():
    """Get all conflicts including resolved ones (history)."""
    return [
        Conflict(
            point_id=c.point_id,
            local_payload=c.local_payload,
            remote_payload=c.remote_payload,
            local_updated_at=c.local_updated_at,
            remote_updated_at=c.remote_updated_at,
            detected_at=c.detected_at,
            resolved=c.resolved,
            resolution=c.resolution
        )
        for c in sync_engine.conflicts
    ]
