from fastapi import APIRouter, HTTPException, Depends

from app.models.schemas import DeviceRegistration, DeviceLogin, TokenResponse, DeviceInfo
from app.services.auth import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse)
def register_device(device: DeviceRegistration):
    """Register a new device and receive JWT token."""
    try:
        result = auth_service.register_device(device.device_id, device.device_name)
        return TokenResponse(
            access_token=result["access_token"],
            token_type=result["token_type"],
            device_info=DeviceInfo(
                device_id=result["device_info"]["device_id"],
                device_name=result["device_info"]["device_name"],
                registered_at=result["device_info"]["registered_at"]
            )
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Registration failed: {str(e)}")


@router.post("/login", response_model=TokenResponse)
def login_device(device: DeviceLogin):
    """Login with existing device ID and receive JWT token."""
    result = auth_service.login_device(device.device_id)
    if not result:
        raise HTTPException(status_code=404, detail="Device not found")

    return TokenResponse(
        access_token=result["access_token"],
        token_type=result["token_type"],
        device_info=DeviceInfo(
            device_id=result["device_info"]["device_id"],
            device_name=result["device_info"]["device_name"],
            registered_at=result["device_info"]["registered_at"]
        )
    )


@router.get("/me", response_model=DeviceInfo)
def get_current_device(token: str):
    """Get current device information from token."""
    device_info = auth_service.verify_token(token)
    if not device_info:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return DeviceInfo(
        device_id=device_info["device_id"],
        device_name=device_info["device_name"],
        registered_at=device_info["registered_at"]
    )


@router.get("/devices")
def list_devices():
    """List all registered devices (admin function)."""
    return {"devices": auth_service.list_devices()}


@router.delete("/devices/{device_id}")
def unregister_device(device_id: str):
    """Unregister a device (admin function)."""
    success = auth_service.unregister_device(device_id)
    if not success:
        raise HTTPException(status_code=404, detail="Device not found")
    return {"message": f"Device {device_id} unregistered"}
