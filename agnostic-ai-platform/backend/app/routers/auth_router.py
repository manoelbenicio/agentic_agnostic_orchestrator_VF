import json
import base64
import secrets
from datetime import datetime
from typing import Optional, Dict, Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

router = APIRouter(prefix="/auth", tags=["auth"])

# --- Request/Response Models ---

class TokenRequest(BaseModel):
    client_id: str
    client_secret: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int

class DeviceRegisterRequest(BaseModel):
    client_id: str
    scope: Optional[str] = None

class DeviceRegisterResponse(BaseModel):
    device_code: str
    user_code: str
    verification_uri: str
    expires_in: int
    interval: int

class DeviceCallbackRequest(BaseModel):
    device_code: str

# --- Mock Implementations ---

def issue_mock_jwt(payload: Dict[str, Any]) -> str:
    """
    Issues a mock JWT.
    In a production application, replace this with python-jose or pyjwt.
    """
    header_json = json.dumps({"alg": "HS256", "typ": "JWT"}).encode()
    payload_json = json.dumps(payload).encode()
    
    header = base64.urlsafe_b64encode(header_json).decode().rstrip("=")
    body = base64.urlsafe_b64encode(payload_json).decode().rstrip("=")
    signature = "mock_signature"
    
    return f"{header}.{body}.{signature}"

# --- Endpoints ---

@router.post("/token", response_model=TokenResponse)
async def issue_token(request: TokenRequest):
    """
    Endpoint to issue JWT based on client credentials or standard credentials.
    """
    # Placeholder authentication check
    if not request.client_id or not request.client_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect client_id or client_secret",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    expires_in = 3600
    token_payload = {
        "sub": request.client_id,
        "role": "developer", # Defaulting to 'developer' role for demonstration
        "exp": int(datetime.utcnow().timestamp()) + expires_in
    }
    
    access_token = issue_mock_jwt(token_payload)
    
    return TokenResponse(
        access_token=access_token,
        expires_in=expires_in
    )


@router.post("/device/register", response_model=DeviceRegisterResponse)
async def auth_device_register(request: DeviceRegisterRequest):
    """
    Initiates the OAuth 2.0 Device Authorization Grant flow.
    Returns device and user codes for out-of-band authorization.
    """
    device_code = secrets.token_urlsafe(32)
    # Generate an 8-character user code with unambiguous characters
    user_code = "".join(secrets.choice("BCDFGHJKLMNPQRSTVWXZ23456789") for _ in range(8))
    
    return DeviceRegisterResponse(
        device_code=device_code,
        user_code=user_code,
        verification_uri="https://api.yourplatform.com/device",
        expires_in=1800,  # 30 minutes
        interval=5        # Recommended polling interval in seconds
    )


@router.post("/device/callback", response_model=TokenResponse)
async def auth_device_callback(request: DeviceCallbackRequest):
    """
    Callback/Polling endpoint for the device flow.
    Devices poll this endpoint with their `device_code` to receive an access token.
    """
    if not request.device_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing device_code"
        )
        
    # Simulate a successful user authorization
    expires_in = 3600
    token_payload = {
        "sub": f"device_{request.device_code[:8]}",
        "role": "viewer", # Devices might default to lower permissions
        "exp": int(datetime.utcnow().timestamp()) + expires_in
    }
    
    access_token = issue_mock_jwt(token_payload)
    
    return TokenResponse(
        access_token=access_token,
        expires_in=expires_in
    )
