"""
JWT authentication service for multi-device support.

Provides device registration, JWT token generation/verification,
and device identity management for multi-device scenarios.
"""
import json
import os
import time
from datetime import datetime, timedelta
from typing import Optional

from jose import jwt, JWTError
from passlib.context import CryptContext

from app.config import (
    JWT_SECRET_KEY,
    JWT_ALGORITHM,
    TOKEN_EXPIRY_HOURS,
    DEVICES_FILE
)

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AuthService:
    def __init__(self):
        self.devices = {}  # device_id -> device_info
        self._load_devices()

    def _load_devices(self):
        """Load registered devices from disk."""
        if os.path.exists(DEVICES_FILE):
            try:
                with open(DEVICES_FILE, 'r') as f:
                    self.devices = json.load(f)
                print(f"Loaded {len(self.devices)} registered devices")
            except Exception as e:
                print(f"Failed to load devices: {e}, starting with empty registry")
                self.devices = {}

    def _save_devices(self):
        """Persist registered devices to disk."""
        try:
            with open(DEVICES_FILE, 'w') as f:
                json.dump(self.devices, f, indent=2)
        except Exception as e:
            print(f"Failed to save devices: {e}")

    def register_device(self, device_id: str, device_name: str) -> dict:
        """
        Register a new device and return JWT token.

        Args:
            device_id: Unique identifier for the device
            device_name: Human-readable name for the device

        Returns:
            Dictionary with access_token, token_type, and device_info
        """
        if device_id in self.devices:
            # Device already registered, just issue new token
            device_info = self.devices[device_id]
            return self._create_token(device_id, device_info["device_name"])

        # Register new device
        device_info = {
            "device_id": device_id,
            "device_name": device_name,
            "registered_at": time.time(),
            "last_seen": time.time()
        }
        self.devices[device_id] = device_info
        self._save_devices()

        return self._create_token(device_id, device_name)

    def login_device(self, device_id: str) -> Optional[dict]:
        """
        Login an existing device and return JWT token.

        Args:
            device_id: Device identifier

        Returns:
            Dictionary with access_token, token_type, and device_info, or None if not found
        """
        if device_id not in self.devices:
            return None

        device_info = self.devices[device_id]
        device_info["last_seen"] = time.time()
        self._save_devices()

        return self._create_token(device_id, device_info["device_name"])

    def _create_token(self, device_id: str, device_name: str) -> dict:
        """Create JWT token for a device."""
        expiry = datetime.utcnow() + timedelta(hours=TOKEN_EXPIRY_HOURS)
        payload = {
            "device_id": device_id,
            "device_name": device_name,
            "exp": expiry,
            "iat": datetime.utcnow()
        }

        token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

        return {
            "access_token": token,
            "token_type": "bearer",
            "device_info": {
                "device_id": device_id,
                "device_name": device_name,
                "registered_at": self.devices[device_id]["registered_at"]
            }
        }

    def verify_token(self, token: str) -> Optional[dict]:
        """
        Verify JWT token and return device info.

        Args:
            token: JWT token string

        Returns:
            Device info dict if valid, None otherwise
        """
        try:
            payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
            device_id = payload.get("device_id")

            if device_id not in self.devices:
                return None

            # Update last seen
            self.devices[device_id]["last_seen"] = time.time()
            self._save_devices()

            return {
                "device_id": device_id,
                "device_name": payload.get("device_name"),
                "registered_at": self.devices[device_id]["registered_at"]
            }

        except jwt.ExpiredSignatureError:
            print("Token expired")
            return None
        except JWTError as e:
            print(f"Invalid token: {e}")
            return None

    def get_device_info(self, device_id: str) -> Optional[dict]:
        """Get device information without authentication."""
        if device_id not in self.devices:
            return None
        return self.devices[device_id]

    def list_devices(self) -> list:
        """List all registered devices (admin function)."""
        return list(self.devices.values())

    def unregister_device(self, device_id: str) -> bool:
        """Unregister a device."""
        if device_id not in self.devices:
            return False

        del self.devices[device_id]
        self._save_devices()
        return True


# Global instance
auth_service = AuthService()
