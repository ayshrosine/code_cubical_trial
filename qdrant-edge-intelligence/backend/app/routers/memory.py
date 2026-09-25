from fastapi import APIRouter, Depends

from app.models.schemas import MemoryPoint, TextMemoryPoint
from app.services.edge_store import edge_store
from app.services.embedding import embedding_service
from app.services.auth_middleware import optional_auth

router = APIRouter(prefix="/memory", tags=["memory"])


@router.post("")
def add_memory(point: MemoryPoint, device: dict = Depends(optional_auth)):
    """Write a new point directly to the on-device shard (works fully offline)."""
    device_id = device["device_id"] if device else None
    # Add device_id to payload if authenticated
    if device:
        point.payload["device_id"] = device_id

    pid = edge_store.upsert(vector=point.vector, payload=point.payload, point_id=point.id, device_id=device_id)
    return {"id": pid}


@router.post("/text")
def add_text_memory(point: TextMemoryPoint, device: dict = Depends(optional_auth)):
    """Write a new text-based memory point with automatic embedding."""
    device_id = device["device_id"] if device else None
    vector = embedding_service.embed(point.text)
    enhanced_payload = {
        **point.payload,
        "text": point.text,
        "embedding_method": "local" if embedding_service.is_local_available() else "api",
    }

    # Add device_id to payload if authenticated
    if device:
        enhanced_payload["device_id"] = device_id

    pid = edge_store.upsert(vector=vector, payload=enhanced_payload, point_id=point.id, device_id=device_id)
    return {"id": pid}


@router.get("")
def list_memory(limit: int = 100, device: dict = Depends(optional_auth)):
    device_id = device["device_id"] if device else None
    points = edge_store.all_points(limit=limit, device_id=device_id)

    return [{"id": p.id, "payload": p.payload} for p in points]


@router.get("/count")
def memory_count(device: dict = Depends(optional_auth)):
    device_id = device["device_id"] if device else None
    return {"count": edge_store.count(device_id=device_id)}
