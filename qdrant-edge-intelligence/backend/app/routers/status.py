from fastapi import APIRouter

from app.services import connectivity
from app.services.edge_store import edge_store

router = APIRouter(prefix="/status", tags=["status"])


@router.get("")
def device_status():
    return {
        "online": connectivity.is_online(),
        "memory_points": edge_store.count(),
        "dirty_points": len(edge_store.dirty_points()),
    }
