from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class MemoryPoint(BaseModel):
    id: Optional[str] = None
    vector: List[float]
    payload: Dict[str, Any] = Field(default_factory=dict)


class TextMemoryPoint(BaseModel):
    id: Optional[str] = None
    text: str
    payload: Dict[str, Any] = Field(default_factory=dict)


class SearchRequest(BaseModel):
    vector: List[float]
    limit: int = 5
    filter: Optional[Dict[str, Any]] = None


class TextSearchRequest(BaseModel):
    text: str
    limit: int = 5
    filter: Optional[Dict[str, Any]] = None


class SearchResult(BaseModel):
    id: str
    score: float
    payload: Dict[str, Any]


class SyncStatus(BaseModel):
    online: bool
    connection_state: str
    pending_points: int
    last_synced_at: Optional[str]
    last_sync_result: Optional[str]
    network_quality: Optional[Dict[str, Any]] = None
    sync_stats: Optional[Dict[str, Any]] = None
    sync_paused: Optional[bool] = None
    circuit_breaker_open: Optional[bool] = None


class ConnectivityToggle(BaseModel):
    online: bool


class Conflict(BaseModel):
    point_id: str
    local_payload: Dict[str, Any]
    remote_payload: Dict[str, Any]
    local_updated_at: float
    remote_updated_at: float
    detected_at: float
    resolved: bool = False
    resolution: Optional[str] = None


class ConflictResolution(BaseModel):
    resolution_type: str  # "local", "remote", "merge"
    merged_payload: Optional[Dict[str, Any]] = None


class DeviceRegistration(BaseModel):
    device_id: str
    device_name: str


class DeviceLogin(BaseModel):
    device_id: str


class DeviceInfo(BaseModel):
    device_id: str
    device_name: str
    registered_at: float


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    device_info: DeviceInfo
