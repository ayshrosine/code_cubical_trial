# AI-Powered Edge Memory & Intelligence Platform (PS3)

Offline-first AI application built around **Qdrant Edge**: a local semantic
memory that lives on the device, plus a sync engine that reconciles with a
central Qdrant Server when connectivity returns.

## Architecture

```
┌─────────────────────────┐        (offline capable)        ┌──────────────────────┐
│   Edge Device (agent)   │  ── snapshot / delta sync ──►    │   Qdrant Server        │
│                          │  ◄── pulls updates ──────────    │   (cloud, docker)      │
│  - Qdrant Edge shard     │                                  │  - source of truth for │
│    (on-disk, embedded)   │                                  │    cross-device data   │
│  - FastAPI agent process │                                  │                        │
│  - Sync engine           │                                  │                        │
└──────────┬───────────────┘                                  └──────────┬─────────────┘
           │ REST                                                        │ REST
           └───────────────────────────┬───────────────────────────────-┘
                                        │
                              ┌─────────▼─────────┐
                              │  Dashboard (web)    │
                              │  - memory inspector │
                              │  - search console    │
                              │  - sync/status panel │
                              └────────────────────┘
```

**Edge tier**: In production this maps to `qdrant-edge` (Rust core, with
Flutter/React Native bindings) running fully in-process on the device with no
server. For this scaffold, `backend/app/services/edge_store.py` wraps
`qdrant-client` in **local mode** (on-disk, no server process) as a
stand-in with the same API shape — swap it for the native `qdrant-edge`
shard bindings when targeting a real mobile/embedded device.

**Cloud tier**: a normal Qdrant server (`docker-compose.yml`) is the
central source of truth other devices/the backend sync against.

**Sync engine**: `backend/app/services/sync_engine.py` tracks a `dirty` /
`synced_at` flag per point in the local store, pushes deltas to the server
when `is_online()` is true, pulls down points updated after the device's
`last_synced_at` cursor, and resolves conflicts by last-write-wins on a
`updated_at` payload timestamp (documented as the place to swap in a
smarter policy — e.g. vector-similarity merge, or manual review queue).

## Goal-to-module mapping

| Goal from problem statement | Where it lives |
|---|---|
| Searchable semantic memory on-device | `services/edge_store.py` |
| Low-latency vector/hybrid search, no network | `routers/search.py` (hits edge store only) |
| Decide what stays local vs. syncs | `sync_engine.should_sync()` |
| Intermittent connectivity, keep operating | `services/connectivity.py` + offline toggle in dashboard |
| Sync edge ↔ server when connectivity returns | `sync_engine.run_sync()`, `routers/sync.py` |
| Handle evolving memory / conflicts | `sync_engine.resolve_conflict()` |
| Inspect memory, search, sync status, activity | `frontend/index.html` dashboard |

## Getting started

```bash
# 1. Start the cloud Qdrant server
docker compose up -d

# 2. Backend (edge agent + sync API)
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# 3. Open the dashboard
open ../frontend/index.html   # or serve it with any static server
```

## Environment Variables

Create a `.env` file in the `backend` directory:

```env
EDGE_STORAGE_PATH=./edge_data
CLOUD_QDRANT_URL=http://localhost:6333
COLLECTION_NAME=device_memory
VECTOR_SIZE=384
SYNC_INTERVAL_SECONDS=10
DEVICE_ISOLATED_COLLECTIONS=true
AUTO_RESOLUTION_THRESHOLD_SECONDS=60
CIRCUIT_BREAKER_FAILURE_THRESHOLD=5
CIRCUIT_BREAKER_RECOVERY_TIMEOUT=300
JWT_SECRET_KEY=your-secret-key-change-in-production
JWT_ALGORITHM=HS256
TOKEN_EXPIRY_HOURS=24
DEVICES_FILE=devices.json
OPENAI_API_KEY=your-openai-api-key-optional
```

The dashboard talks to `http://localhost:8000`. Use the **"Go offline /
Go online"** toggle to simulate intermittent connectivity — while
"offline", search and writes keep working against the local shard only;
sync is disabled and queues up dirty points until you go back online.

## Multi-Device Demo

1. Register multiple devices using the dashboard:
   - Device 1: ID `device-1`, Name `Laptop`
   - Device 2: ID `device-2`, Name `Phone`
2. Each device gets its own isolated collection
3. Add memory points from each device
4. Toggle connectivity to see sync behavior
5. Create conflicts by editing the same point from both devices while offline
6. Use the conflict resolution UI to resolve conflicts

## API Endpoints

### Authentication
- `POST /auth/register` - Register a new device
- `POST /auth/login` - Login with existing device
- `GET /auth/me` - Get current device info
- `GET /auth/devices` - List all devices (admin)

### Memory
- `POST /memory` - Add vector memory point
- `POST /memory/text` - Add text memory point (auto-embedded)
- `GET /memory` - List memory points
- `GET /memory/count` - Get memory count

### Search
- `POST /search` - Vector search
- `POST /search/text` - Text search (auto-embedded)

### Sync
- `POST /sync/run` - Trigger manual sync
- `GET /sync/status` - Get sync status
- `POST /sync/connectivity` - Toggle connectivity
- `POST /sync/pause` - Pause automatic sync
- `POST /sync/resume` - Resume automatic sync

### Conflicts
- `GET /conflicts` - List unresolved conflicts
- `GET /conflicts/history` - Get conflict history
- `GET /conflicts/count` - Get conflict count
- `POST /conflicts/{point_id}/resolve` - Resolve specific conflict
- `POST /conflicts/resolve-all` - Resolve all conflicts

## Next steps / hackathon TODO

- [x] ~~Swap `edge_store.py`'s qdrant-client local-mode shim for real
      `qdrant-edge` bindings (React Native or Flutter) once a device target
      is picked.~~ (Deferred - requires specific platform target)
- [x] ~~Add an embedding step (e.g. sentence-transformers or an API) so raw
      text/notes can be ingested, not just raw vectors.~~ (Implemented)
- [x] ~~Build out the conflict-resolution UI (currently last-write-wins only).~~ (Implemented with manual resolution, merge editor, and bulk actions)
- [x] ~~Add auth/device identity so multiple simulated edge devices can sync
      to the same server and you can demo multi-device merge.~~ (Implemented with JWT auth and device-isolated collections)

## New Features Implemented

### Device-Isolated Collections
- Each device now gets its own collection (e.g., `device_memory_device-1`, `device_memory_device-2`)
- Configurable via `DEVICE_ISOLATED_COLLECTIONS` environment variable (default: true)
- Backward compatible with single-collection mode when disabled

### Enhanced Conflict Resolution
- **Auto-resolution**: Conflicts with time diff < 60s (configurable) are auto-resolved
- **Manual resolution UI**: Side-by-side diff view with timestamps
- **Custom merge**: JSON merge editor for creating custom resolutions
- **Bulk actions**: Resolve all conflicts as local or remote at once
- **Conflict history**: View all conflicts including resolved ones

### Sync Reliability Enhancements
- **Pause/Resume**: Control automatic sync via API and UI
- **Circuit breaker**: Automatically pauses sync after 5 consecutive failures
- **Exponential backoff**: Retry logic with increasing delays
- **State persistence**: Sync state and conflicts saved to disk for crash recovery
- **Batch management**: Points synced in batches of 100 (configurable)

### Multi-Device Authentication
- **JWT tokens**: Device registration and login with JWT authentication
- **Device registry**: Persistent device registry with last_seen tracking
- **Device filtering**: All operations automatically scoped to authenticated device

### Text Embedding Service
- **Hybrid approach**: Local sentence-transformers with OpenAI API fallback
- **Offline capable**: Works fully offline with local model
- **Batch support**: Efficient batch embedding for multiple texts
