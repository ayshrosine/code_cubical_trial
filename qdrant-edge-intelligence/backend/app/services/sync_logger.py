"""
Sync operation logging service.

Provides detailed logging for sync operations, conflict resolution,
performance metrics, and error categorization for debugging and monitoring.
"""
import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional


class SyncEventType(Enum):
    SYNC_START = "sync_start"
    SYNC_COMPLETE = "sync_complete"
    SYNC_ERROR = "sync_error"
    PUSH_START = "push_start"
    PUSH_COMPLETE = "push_complete"
    PUSH_ERROR = "push_error"
    PULL_START = "pull_start"
    PULL_COMPLETE = "pull_complete"
    PULL_ERROR = "pull_error"
    CONFLICT_DETECTED = "conflict_detected"
    CONFLICT_RESOLVED = "conflict_resolved"
    CONNECTIVITY_CHANGE = "connectivity_change"


class ErrorCategory(Enum):
    NETWORK = "network"
    TIMEOUT = "timeout"
    AUTHENTICATION = "authentication"
    VALIDATION = "validation"
    STORAGE = "storage"
    UNKNOWN = "unknown"


@dataclass
class SyncEvent:
    event_type: SyncEventType
    timestamp: float
    details: dict = field(default_factory=dict)
    error_category: Optional[ErrorCategory] = None
    duration_ms: Optional[float] = None


class SyncLogger:
    def __init__(self, log_file: str = "sync_operations.log"):
        self.log_file = log_file
        self.events: List[SyncEvent] = []
        self._operation_start_times = {}
        self._max_events = 1000  # Keep last 1000 events in memory
        self._ensure_log_file()

    def _ensure_log_file(self):
        """Create log file if it doesn't exist."""
        if not os.path.exists(self.log_file):
            with open(self.log_file, 'w') as f:
                f.write("")  # Create empty file

    def log_event(self, event_type: SyncEventType, details: dict = None,
                  error_category: ErrorCategory = None, duration_ms: float = None):
        """Log a sync event."""
        event = SyncEvent(
            event_type=event_type,
            timestamp=time.time(),
            details=details or {},
            error_category=error_category,
            duration_ms=duration_ms
        )
        self.events.append(event)

        # Keep only recent events in memory
        if len(self.events) > self._max_events:
            self.events.pop(0)

        # Write to file
        self._write_to_file(event)

    def start_operation(self, operation_name: str):
        """Mark the start of an operation for timing."""
        self._operation_start_times[operation_name] = time.time()
        self.log_event(
            SyncEventType.SYNC_START,
            details={"operation": operation_name}
        )

    def end_operation(self, operation_name: str, success: bool = True,
                      details: dict = None, error_category: ErrorCategory = None):
        """Mark the end of an operation with timing."""
        start_time = self._operation_start_times.get(operation_name)
        duration_ms = None
        if start_time:
            duration_ms = (time.time() - start_time) * 1000
            del self._operation_start_times[operation_name]

        event_type = SyncEventType.SYNC_COMPLETE if success else SyncEventType.SYNC_ERROR
        final_details = details or {}
        final_details["operation"] = operation_name

        self.log_event(
            event_type,
            details=final_details,
            error_category=error_category,
            duration_ms=duration_ms
        )

    def log_push(self, points_count: int, success: bool = True, error: str = None):
        """Log a push operation."""
        if success:
            self.log_event(
                SyncEventType.PUSH_COMPLETE,
                details={"points_pushed": points_count}
            )
        else:
            self.log_event(
                SyncEventType.PUSH_ERROR,
                details={"points_attempted": points_count, "error": error},
                error_category=self._categorize_error(error)
            )

    def log_pull(self, points_count: int, success: bool = True, error: str = None):
        """Log a pull operation."""
        if success:
            self.log_event(
                SyncEventType.PULL_COMPLETE,
                details={"points_pulled": points_count}
            )
        else:
            self.log_event(
                SyncEventType.PULL_ERROR,
                details={"error": error},
                error_category=self._categorize_error(error)
            )

    def log_conflict(self, point_id: str, local_updated_at: float,
                     remote_updated_at: float, resolution: str = None):
        """Log a conflict detection and resolution."""
        if resolution:
            self.log_event(
                SyncEventType.CONFLICT_RESOLVED,
                details={
                    "point_id": point_id,
                    "local_updated_at": local_updated_at,
                    "remote_updated_at": remote_updated_at,
                    "resolution": resolution
                }
            )
        else:
            self.log_event(
                SyncEventType.CONFLICT_DETECTED,
                details={
                    "point_id": point_id,
                    "local_updated_at": local_updated_at,
                    "remote_updated_at": remote_updated_at
                }
            )

    def log_connectivity_change(self, online: bool, state: str):
        """Log connectivity state changes."""
        self.log_event(
            SyncEventType.CONNECTIVITY_CHANGE,
            details={"online": online, "state": state}
        )

    def _categorize_error(self, error: str) -> ErrorCategory:
        """Categorize an error based on the error message."""
        if not error:
            return ErrorCategory.UNKNOWN

        error_lower = error.lower()
        if "timeout" in error_lower or "timed out" in error_lower:
            return ErrorCategory.TIMEOUT
        elif "network" in error_lower or "connection" in error_lower:
            return ErrorCategory.NETWORK
        elif "auth" in error_lower or "unauthorized" in error_lower:
            return ErrorCategory.AUTHENTICATION
        elif "storage" in error_lower or "disk" in error_lower:
            return ErrorCategory.STORAGE
        elif "validation" in error_lower or "invalid" in error_lower:
            return ErrorCategory.VALIDATION
        else:
            return ErrorCategory.UNKNOWN

    def _write_to_file(self, event: SyncEvent):
        """Write event to log file."""
        try:
            with open(self.log_file, 'a') as f:
                log_entry = {
                    "timestamp": datetime.fromtimestamp(event.timestamp).isoformat(),
                    "event_type": event.event_type.value,
                    "details": event.details,
                    "error_category": event.error_category.value if event.error_category else None,
                    "duration_ms": event.duration_ms
                }
                f.write(json.dumps(log_entry) + "\n")
        except Exception as e:
            print(f"Failed to write to sync log: {e}")

    def get_recent_events(self, limit: int = 50) -> List[dict]:
        """Get recent events for display."""
        recent = self.events[-limit:] if len(self.events) > limit else self.events
        return [
            {
                "timestamp": datetime.fromtimestamp(e.timestamp).isoformat(),
                "event_type": e.event_type.value,
                "details": e.details,
                "error_category": e.error_category.value if e.error_category else None,
                "duration_ms": e.duration_ms
            }
            for e in recent
        ]

    def get_performance_metrics(self) -> dict:
        """Calculate performance metrics from logged events."""
        sync_events = [e for e in self.events if e.event_type == SyncEventType.SYNC_COMPLETE]
        if not sync_events:
            return {}

        durations = [e.duration_ms for e in sync_events if e.duration_ms]
        return {
            "total_syncs": len(sync_events),
            "avg_sync_duration_ms": sum(durations) / len(durations) if durations else None,
            "min_sync_duration_ms": min(durations) if durations else None,
            "max_sync_duration_ms": max(durations) if durations else None,
        }

    def get_error_summary(self) -> dict:
        """Get summary of errors by category."""
        error_events = [e for e in self.events if e.event_type == SyncEventType.SYNC_ERROR]
        if not error_events:
            return {}

        by_category = {}
        for event in error_events:
            category = event.error_category.value if event.error_category else "unknown"
            by_category[category] = by_category.get(category, 0) + 1

        return {
            "total_errors": len(error_events),
            "by_category": by_category
        }


# Global instance
sync_logger = SyncLogger()
