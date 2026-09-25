from fastapi import APIRouter, Depends

from app.models.schemas import SearchRequest, TextSearchRequest, SearchResult
from app.services.edge_store import edge_store
from app.services.embedding import embedding_service
from app.services.auth_middleware import optional_auth

router = APIRouter(prefix="/search", tags=["search"])


@router.post("", response_model=list[SearchResult])
def search(req: SearchRequest, device: dict = Depends(optional_auth)):
    """
    Always queries the local edge shard only — this endpoint never touches
    the network, so it works identically online or offline.
    """
    device_id = device["device_id"] if device else None
    hits = edge_store.search(vector=req.vector, limit=req.limit, query_filter=req.filter, device_id=device_id)
    return [SearchResult(id=str(h.id), score=h.score, payload=h.payload or {}) for h in hits]


@router.post("/text", response_model=list[SearchResult])
def search_text(req: TextSearchRequest, device: dict = Depends(optional_auth)):
    """
    Search using text query with automatic embedding.
    Works offline if local embedding model is available.
    """
    device_id = device["device_id"] if device else None
    vector = embedding_service.embed(req.text)
    hits = edge_store.search(vector=vector, limit=req.limit, query_filter=req.filter, device_id=device_id)
    return [SearchResult(id=str(h.id), score=h.score, payload=h.payload or {}) for h in hits]
