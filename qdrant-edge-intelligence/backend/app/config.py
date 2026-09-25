import os

# Where the edge shard is persisted on-disk (simulates on-device storage).
EDGE_STORAGE_PATH = os.getenv("EDGE_STORAGE_PATH", "./edge_data")

# Cloud Qdrant server location.
CLOUD_QDRANT_URL = os.getenv("CLOUD_QDRANT_URL", "http://localhost:6333")

COLLECTION_NAME = os.getenv("COLLECTION_NAME", "device_memory")
VECTOR_SIZE = int(os.getenv("VECTOR_SIZE", "384"))

# How often the background sync loop checks connectivity + pushes/pulls, in seconds.
SYNC_INTERVAL_SECONDS = int(os.getenv("SYNC_INTERVAL_SECONDS", "10"))

# JWT Authentication configuration
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-secret-key-change-in-production")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
TOKEN_EXPIRY_HOURS = int(os.getenv("TOKEN_EXPIRY_HOURS", "24"))

# Device registry file
DEVICES_FILE = os.getenv("DEVICES_FILE", "devices.json")

# OpenAI API key for embedding fallback
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# Device-isolated collections mode
DEVICE_ISOLATED_COLLECTIONS = os.getenv("DEVICE_ISOLATED_COLLECTIONS", "true").lower() == "true"

# Auto-resolution threshold (seconds) - auto-resolve conflicts if time diff below this
AUTO_RESOLUTION_THRESHOLD_SECONDS = float(os.getenv("AUTO_RESOLUTION_THRESHOLD_SECONDS", "60"))

# Circuit breaker configuration
CIRCUIT_BREAKER_FAILURE_THRESHOLD = int(os.getenv("CIRCUIT_BREAKER_FAILURE_THRESHOLD", "5"))
CIRCUIT_BREAKER_RECOVERY_TIMEOUT = int(os.getenv("CIRCUIT_BREAKER_RECOVERY_TIMEOUT", "300"))
