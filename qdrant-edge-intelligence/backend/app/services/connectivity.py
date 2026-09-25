"""
Tracks whether the device is allowed to talk to the cloud.

Two layers:
  - `_forced_offline`: a manual toggle so the dashboard can demo "airplane
    mode" deterministically, regardless of whether the Qdrant server is
    actually reachable.
  - real reachability: falls back to actually pinging the cloud store.

Enhanced with network quality detection, heartbeat mechanism, and
connection state management for improved reliability.
"""
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from app.services.cloud_store import cloud_store
from app.services.sync_logger import sync_logger


class ConnectionState(Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    DEGRADED = "degraded"
    RECONNECTING = "reconnecting"


@dataclass
class NetworkQuality:
    latency_ms: float
    success_rate: float
    last_check: float
    consecutive_failures: int


_forced_offline = False
_connection_state = ConnectionState.OFFLINE
_network_quality: Optional[NetworkQuality] = None
_latency_history = []
_max_latency_samples = 10
_latency_threshold_ms = 500  # Consider degraded if latency > 500ms
_consecutive_success_threshold = 3  # Need 3 successes to mark online
_consecutive_failure_threshold = 2  # Mark offline after 2 failures


def set_forced_offline(offline: bool):
    global _forced_offline, _connection_state
    old_state = _connection_state
    _forced_offline = offline
    if offline:
        _connection_state = ConnectionState.OFFLINE
    else:
        _connection_state = ConnectionState.RECONNECTING

    # Log state change
    if old_state != _connection_state:
        sync_logger.log_connectivity_change(not offline, _connection_state.value)


def is_online() -> bool:
    if _forced_offline:
        return False
    return _check_connectivity()


def get_connection_state() -> ConnectionState:
    """Get current detailed connection state."""
    return _connection_state


def get_network_quality() -> Optional[NetworkQuality]:
    """Get current network quality metrics."""
    return _network_quality


def _check_connectivity() -> bool:
    """Check connectivity with quality assessment."""
    start_time = time.time()
    success = cloud_store.is_reachable()
    latency_ms = (time.time() - start_time) * 1000

    _update_quality_metrics(success, latency_ms)
    _update_connection_state()

    return success


def _update_quality_metrics(success: bool, latency_ms: float):
    """Update network quality metrics."""
    global _network_quality, _latency_history

    if _network_quality is None:
        _network_quality = NetworkQuality(
            latency_ms=latency_ms,
            success_rate=1.0 if success else 0.0,
            last_check=time.time(),
            consecutive_failures=0 if success else 1
        )
    else:
        # Update latency history
        _latency_history.append(latency_ms)
        if len(_latency_history) > _max_latency_samples:
            _latency_history.pop(0)

        # Calculate average latency
        avg_latency = sum(_latency_history) / len(_latency_history)

        # Update success rate (exponential moving average)
        alpha = 0.3  # Smoothing factor
        current_rate = 1.0 if success else 0.0
        new_rate = alpha * current_rate + (1 - alpha) * _network_quality.success_rate

        # Update consecutive failures
        new_failures = 0 if success else _network_quality.consecutive_failures + 1

        _network_quality = NetworkQuality(
            latency_ms=avg_latency,
            success_rate=new_rate,
            last_check=time.time(),
            consecutive_failures=new_failures
        )


def _update_connection_state():
    """Update connection state based on quality metrics."""
    global _connection_state

    if _forced_offline:
        _connection_state = ConnectionState.OFFLINE
        return

    if _network_quality is None:
        _connection_state = ConnectionState.OFFLINE
        return

    quality = _network_quality

    # Check for consecutive failures
    if quality.consecutive_failures >= _consecutive_failure_threshold:
        _connection_state = ConnectionState.OFFLINE
        return

    # Check for consecutive successes to mark online
    if quality.consecutive_failures == 0 and quality.success_rate > 0.8:
        if quality.latency_ms > _latency_threshold_ms:
            _connection_state = ConnectionState.DEGRADED
        else:
            _connection_state = ConnectionState.ONLINE
        return

    # Intermediate states
    if quality.success_rate > 0.5:
        _connection_state = ConnectionState.RECONNECTING
    else:
        _connection_state = ConnectionState.OFFLINE


def reset_connectivity_state():
    """Reset connectivity state (useful for testing or manual recovery)."""
    global _network_quality, _latency_history, _connection_state
    _network_quality = None
    _latency_history = []
    _connection_state = ConnectionState.RECONNECTING
