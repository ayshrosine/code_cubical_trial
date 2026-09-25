"""
Authentication middleware for protecting routes.

Provides FastAPI dependencies for JWT token verification.
"""
from typing import Optional

from fastapi import Header, HTTPException

from app.services.auth import auth_service


async def get_current_device(authorization: Optional[str] = Header(None)):
    """
    Dependency to verify JWT token and extract device info.

    Usage:
        @router.get("/protected")
        def protected_route(device: dict = Depends(get_current_device)):
            return {"message": f"Hello {device['device_name']}"}
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header missing")

    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization format")

    token = authorization.split(" ")[1]
    device_info = auth_service.verify_token(token)

    if not device_info:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return device_info


async def optional_auth(authorization: Optional[str] = Header(None)):
    """
    Optional authentication - returns device info if token valid, None otherwise.

    Usage:
        @router.get("/public")
        def public_route(device: Optional[dict] = Depends(optional_auth)):
            if device:
                return {"message": f"Hello {device['device_name']}"}
            return {"message": "Hello anonymous"}
    """
    if not authorization or not authorization.startswith("Bearer "):
        return None

    token = authorization.split(" ")[1]
    return auth_service.verify_token(token)
