from fastapi import APIRouter

from app.services.sync_logger import sync_logger

router = APIRouter(prefix="/sync/logs", tags=["sync_logs"])


@router.get("/recent")
def get_recent_logs(limit: int = 50):
    """Get recent sync operation logs."""
    return sync_logger.get_recent_events(limit=limit)


@router.get("/metrics")
def get_performance_metrics():
    """Get sync performance metrics."""
    return sync_logger.get_performance_metrics()


@router.get("/errors")
def get_error_summary():
    """Get error summary by category."""
    return sync_logger.get_error_summary()
