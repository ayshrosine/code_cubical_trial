"""
On-device semantic memory.

This wraps qdrant-client's *local mode* (on-disk, in-process, no server) to
stand in for the real `qdrant-edge` embedded shard during the hackathon.
The API shape (upsert / search / retrieve) is deliberately close to the
real qdrant-edge shard API (`shard.upsert`, `shard.search`, `shard.flush`)
so swapping in native bindings later is mostly a matter of changing this
one module.
"""
import time
import uuid
from typing import Any, Dict, List, Optional

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from app.config import EDGE_STORAGE_PATH, COLLECTION_NAME, VECTOR_SIZE, DEVICE_ISOLATED_COLLECTIONS


class EdgeStore:
    def __init__(self, path: str = EDGE_STORAGE_PATH):
        # path=... puts qdrant-client into local/embedded mode: no server process.
        self.client = QdrantClient(path=path)
        self._ensure_collection(None)  # Ensure default collection exists for backward compatibility

    def _get_collection_name(self, device_id: Optional[str] = None) -> str:
        """Get collection name based on device_id and isolation mode."""
        if DEVICE_ISOLATED_COLLECTIONS and device_id:
            return f"{COLLECTION_NAME}_{device_id}"
        return COLLECTION_NAME

    def _ensure_collection(self, device_id: Optional[str] = None):
        collection_name = self._get_collection_name(device_id)
        existing = [c.name for c in self.client.get_collections().collections]
        if collection_name not in existing:
            self.client.create_collection(
                collection_name=collection_name,
                vectors_config=qmodels.VectorParams(
                    size=VECTOR_SIZE, distance=qmodels.Distance.COSINE
                ),
            )

    def upsert(self, vector: List[float], payload: Dict[str, Any], point_id: Optional[str] = None, device_id: Optional[str] = None) -> str:
        collection_name = self._get_collection_name(device_id)
        self._ensure_collection(device_id)
        pid = point_id or str(uuid.uuid4())
        payload = {
            **payload,
            "updated_at": payload.get("updated_at") or time.time(),
            "dirty": True,          # not yet pushed to cloud
            "synced_at": None,
        }
        self.client.upsert(
            collection_name=collection_name,
            points=[qmodels.PointStruct(id=pid, vector=vector, payload=payload)],
        )
        return pid

    def search(self, vector: List[float], limit: int = 5, query_filter: Optional[dict] = None, device_id: Optional[str] = None):
        collection_name = self._get_collection_name(device_id)
        self._ensure_collection(device_id)
        result = self.client.query_points(
            collection_name=collection_name,
            query=vector,
            limit=limit,
            query_filter=qmodels.Filter(**query_filter) if query_filter else None,
        )
        return result.points

    def all_points(self, limit: int = 1000, device_id: Optional[str] = None):
        collection_name = self._get_collection_name(device_id)
        self._ensure_collection(device_id)
        points, _ = self.client.scroll(collection_name=collection_name, limit=limit, with_vectors=True)
        return points

    def dirty_points(self, device_id: Optional[str] = None):
        collection_name = self._get_collection_name(device_id)
        self._ensure_collection(device_id)
        points, _ = self.client.scroll(
            collection_name=collection_name,
            scroll_filter=qmodels.Filter(
                must=[qmodels.FieldCondition(key="dirty", match=qmodels.MatchValue(value=True))]
            ),
            limit=1000,
            with_vectors=True,
        )
        return points

    def mark_synced(self, point_ids: List[str], device_id: Optional[str] = None):
        collection_name = self._get_collection_name(device_id)
        for pid in point_ids:
            self.client.set_payload(
                collection_name=collection_name,
                payload={"dirty": False, "synced_at": time.time()},
                points=[pid],
            )

    def upsert_from_cloud(self, point_id: str, vector: List[float], payload: Dict[str, Any], device_id: Optional[str] = None):
        """Apply an incoming point from the cloud without marking it dirty again."""
        collection_name = self._get_collection_name(device_id)
        self._ensure_collection(device_id)
        payload = {**payload, "dirty": False, "synced_at": time.time()}
        self.client.upsert(
            collection_name=collection_name,
            points=[qmodels.PointStruct(id=point_id, vector=vector, payload=payload)],
        )

    def count(self, device_id: Optional[str] = None) -> int:
        collection_name = self._get_collection_name(device_id)
        self._ensure_collection(device_id)
        return self.client.count(collection_name=collection_name).count


edge_store = EdgeStore()
