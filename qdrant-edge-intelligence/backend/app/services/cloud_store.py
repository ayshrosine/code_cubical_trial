"""Thin wrapper around the central Qdrant Server (the 'cloud' tier)."""
from typing import Any, Dict, List

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from app.config import CLOUD_QDRANT_URL, COLLECTION_NAME, VECTOR_SIZE, DEVICE_ISOLATED_COLLECTIONS


class CloudStore:
    def __init__(self, url: str = CLOUD_QDRANT_URL):
        self.client = QdrantClient(url=url, timeout=2.0)
        # Try to ensure default collection exists, but don't fail if cloud is unreachable
        try:
            self.ensure_collection(None)
        except Exception:
            # Cloud not available - will be handled at runtime
            pass

    def is_reachable(self) -> bool:
        try:
            self.client.get_collections()
            return True
        except Exception:
            return False

    def _get_collection_name(self, device_id: str = None) -> str:
        """Get collection name based on device_id and isolation mode."""
        if DEVICE_ISOLATED_COLLECTIONS and device_id:
            return f"{COLLECTION_NAME}_{device_id}"
        return COLLECTION_NAME

    def ensure_collection(self, device_id: str = None):
        collection_name = self._get_collection_name(device_id)
        existing = [c.name for c in self.client.get_collections().collections]
        if collection_name not in existing:
            self.client.create_collection(
                collection_name=collection_name,
                vectors_config=qmodels.VectorParams(
                    size=VECTOR_SIZE, distance=qmodels.Distance.COSINE
                ),
            )

    def upsert_many(self, points: List[qmodels.PointStruct], device_id: str = None):
        collection_name = self._get_collection_name(device_id)
        self.ensure_collection(device_id)
        self.client.upsert(collection_name=collection_name, points=points)

    def get_updated_since(self, timestamp: float, device_id: str = None):
        """Points whose payload.updated_at is newer than the device's cursor."""
        collection_name = self._get_collection_name(device_id)
        self.ensure_collection(device_id)
        points, _ = self.client.scroll(
            collection_name=collection_name,
            scroll_filter=qmodels.Filter(
                must=[qmodels.FieldCondition(key="updated_at", range=qmodels.Range(gt=timestamp))]
            ),
            limit=1000,
            with_vectors=True,
        )
        return points

    def get_point(self, point_id: str, device_id: str = None):
        collection_name = self._get_collection_name(device_id)
        self.ensure_collection(device_id)
        res = self.client.retrieve(collection_name=collection_name, ids=[point_id], with_vectors=True)
        return res[0] if res else None


cloud_store = CloudStore()
