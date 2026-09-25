import asyncio
import contextlib

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import SYNC_INTERVAL_SECONDS
from app.routers import memory, search, sync, status, sync_logs, conflicts, auth
from app.services import sync_engine


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_background_sync_loop())
    yield
    task.cancel()


async def _background_sync_loop():
    """Periodically attempts a sync; no-ops (fast) whenever offline."""
    while True:
        await asyncio.sleep(SYNC_INTERVAL_SECONDS)
        try:
            sync_engine.run_sync()
        except Exception as e:
            sync_engine.sync_state.last_result = f"error: {e}"


app = FastAPI(title="Edge Memory & Intelligence Platform", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(memory.router)
app.include_router(search.router)
app.include_router(sync.router)
app.include_router(status.router)
app.include_router(sync_logs.router)
app.include_router(conflicts.router)
app.include_router(auth.router)


@app.get("/")
def root():
    return {"service": "edge-memory-platform", "status": "running"}
