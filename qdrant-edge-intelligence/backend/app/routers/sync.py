from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from app.models.schemas import SyncStatus, ConnectivityToggle
from app.services import connectivity, sync_engine
from app.services.edge_store import edge_store
from app.services.auth_middleware import optional_auth

router = APIRouter(prefix="/sync", tags=["sync"])


@router.post("/run")
def trigger_sync(device: dict = Depends(optional_auth)):
    device_id = device["device_id"] if device else None
    result = sync_engine.run_sync(device_id)
    return {"result": result}


@router.get("/status")
def status(device: dict = Depends(optional_auth)):
    device_id = device["device_id"] if device else None
    ts = sync_engine.sync_state.last_synced_at
    quality = connectivity.get_network_quality()

    dirty = edge_store.dirty_points(device_id)

    return SyncStatus(
        online=connectivity.is_online(),
        connection_state=connectivity.get_connection_state().value,
        pending_points=len(dirty),
        last_synced_at=datetime.fromtimestamp(ts, tz=timezone.utc).isoformat() if ts else None,
        last_sync_result=sync_engine.sync_state.last_result,
        network_quality={
            "latency_ms": quality.latency_ms if quality else None,
            "success_rate": quality.success_rate if quality else None,
            "consecutive_failures": quality.consecutive_failures if quality else None,
        } if quality else None,
        sync_stats={
            "total_pushed": sync_engine.sync_state.total_pushed,
            "total_pulled": sync_engine.sync_state.total_pulled,
            "consecutive_failures": sync_engine.sync_state.consecutive_failures,
        },
        sync_paused=sync_engine.sync_state.sync_paused,
        circuit_breaker_open=sync_engine.sync_state.circuit_breaker_open
    )


@router.post("/pause")
def pause_sync():
    """Pause automatic sync."""
    sync_engine.sync_state.sync_paused = True
    sync_engine.save_sync_state()
    return {"sync_paused": True}


@router.post("/resume")
def resume_sync():
    """Resume automatic sync."""
    sync_engine.sync_state.sync_paused = False
    sync_engine.save_sync_state()
    return {"sync_paused": False}


@router.post("/connectivity")
def set_connectivity(toggle: ConnectivityToggle, device: dict = Depends(optional_auth)):
    """Simulate going offline/online — e.g. 'airplane mode' for the demo."""
    connectivity.set_forced_offline(offline=not toggle.online)
    return {"online": connectivity.is_online(), "state": connectivity.get_connection_state().value}
