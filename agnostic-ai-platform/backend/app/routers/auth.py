from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
import hashlib
import hmac
import json
import os
import secrets
import string
from typing import Any, Literal

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field


router = APIRouter(prefix="/auth", tags=["Auth"])

DEVICE_CODE_EXPIRES_IN_SECONDS = 600
DEVICE_CODE_INTERVAL_SECONDS = 5
ACCESS_TOKEN_EXPIRES_IN_SECONDS = 3600
USER_CODE_ALPHABET = string.ascii_uppercase + string.digits
DEVICE_GRANT_TYPE = "urn:ietf:params:oauth:grant-type:device_code"


class DeviceAuthorizeRequest(BaseModel):
    client_id: str = Field(min_length=1, max_length=255)
    scope: str | None = Field(default=None, max_length=2048)
    audience: str | None = Field(default=None, max_length=255)


class DeviceAuthorizeResponse(BaseModel):
    device_code: str
    user_code: str
    verification_uri: str
    verification_uri_complete: str
    expires_in: int
    interval: int


class DeviceTokenRequest(BaseModel):
    device_code: str = Field(min_length=1)
    client_id: str = Field(min_length=1, max_length=255)
    grant_type: Literal["urn:ietf:params:oauth:grant-type:device_code"] = DEVICE_GRANT_TYPE


class DeviceTokenResponse(BaseModel):
    access_token: str
    token_type: Literal["Bearer"] = "Bearer"
    expires_in: int
    scope: str | None = None


class GoogleDeviceAuthorizeRequest(BaseModel):
    user_code: str = Field(min_length=1, max_length=32)
    id_token: str = Field(min_length=1)


class LocalUser(BaseModel):
    user_id: str
    provider: Literal["google"] = "google"
    provider_subject: str
    email: str | None = None
    name: str | None = None
    picture: str | None = None
    hosted_domain: str | None = None
    created_at: datetime
    updated_at: datetime


class GoogleDeviceAuthorizeResponse(BaseModel):
    status: Literal["approved"]
    user: LocalUser
    client_id: str
    scope: str | None = None


class DeviceAuthorizationRecord(BaseModel):
    client_id: str
    scope: str | None = None
    audience: str | None = None
    device_code: str
    user_code: str
    status: Literal["pending", "approved", "denied", "expired"] = "pending"
    subject: str | None = None
    identity_provider: str | None = None
    email: str | None = None
    created_at: datetime
    expires_at: datetime


DEVICE_AUTHORIZATIONS_BY_DEVICE_CODE: dict[str, DeviceAuthorizationRecord] = {}
DEVICE_AUTHORIZATIONS_BY_USER_CODE: dict[str, str] = {}
LOCAL_USERS_BY_ID: dict[str, LocalUser] = {}
LOCAL_USERS_BY_GOOGLE_SUB: dict[str, str] = {}


@router.post("/device/authorize", response_model=DeviceAuthorizeResponse)
async def authorize_device(request: DeviceAuthorizeRequest) -> DeviceAuthorizeResponse:
    _prune_expired_authorizations()

    device_code = _new_device_code()
    user_code = _new_user_code()
    now = datetime.now(UTC)
    expires_at = now + timedelta(seconds=DEVICE_CODE_EXPIRES_IN_SECONDS)

    record = DeviceAuthorizationRecord(
        client_id=request.client_id,
        scope=request.scope,
        audience=request.audience,
        device_code=device_code,
        user_code=user_code,
        created_at=now,
        expires_at=expires_at,
    )
    DEVICE_AUTHORIZATIONS_BY_DEVICE_CODE[device_code] = record
    DEVICE_AUTHORIZATIONS_BY_USER_CODE[user_code] = device_code

    verification_uri = _verification_uri()
    separator = "&" if "?" in verification_uri else "?"
    return DeviceAuthorizeResponse(
        device_code=device_code,
        user_code=user_code,
        verification_uri=verification_uri,
        verification_uri_complete=f"{verification_uri}{separator}user_code={user_code}",
        expires_in=DEVICE_CODE_EXPIRES_IN_SECONDS,
        interval=DEVICE_CODE_INTERVAL_SECONDS,
    )


@router.post("/device/google/authorize", response_model=GoogleDeviceAuthorizeResponse)
async def authorize_device_with_google(request: GoogleDeviceAuthorizeRequest) -> GoogleDeviceAuthorizeResponse | JSONResponse:
    user_code = _normalize_user_code(request.user_code)
    device_code = DEVICE_AUTHORIZATIONS_BY_USER_CODE.get(user_code)
    if device_code is None:
        return _oauth_error("invalid_grant", "Unknown user_code")
    record = DEVICE_AUTHORIZATIONS_BY_DEVICE_CODE.get(device_code)
    if record is None:
        DEVICE_AUTHORIZATIONS_BY_USER_CODE.pop(user_code, None)
        return _oauth_error("invalid_grant", "Unknown user_code")
    if record.expires_at <= datetime.now(UTC):
        record.status = "expired"
        _remove_authorization(record)
        return _oauth_error("expired_token", "Device code expired")
    if record.status == "denied":
        _remove_authorization(record)
        return _oauth_error("access_denied", "Device authorization was denied")
    if record.status == "approved":
        user = LOCAL_USERS_BY_ID.get(record.subject or "")
        if user is None:
            return _oauth_error("invalid_grant", "Device authorization is not valid")
        return GoogleDeviceAuthorizeResponse(status="approved", user=user, client_id=record.client_id, scope=record.scope)

    claims = _verify_google_id_token(request.id_token)
    if isinstance(claims, JSONResponse):
        return claims
    user = _map_google_claims_to_local_user(claims)
    record.status = "approved"
    record.subject = user.user_id
    record.identity_provider = "google"
    record.email = user.email
    return GoogleDeviceAuthorizeResponse(status="approved", user=user, client_id=record.client_id, scope=record.scope)


@router.post("/device/token", response_model=DeviceTokenResponse)
async def device_token(request: DeviceTokenRequest) -> DeviceTokenResponse | JSONResponse:
    record = DEVICE_AUTHORIZATIONS_BY_DEVICE_CODE.get(request.device_code)
    if record is None:
        return _oauth_error("invalid_grant", "Unknown device_code")
    if record.client_id != request.client_id:
        return _oauth_error("invalid_grant", "device_code was not issued to this client_id")
    if record.expires_at <= datetime.now(UTC):
        record.status = "expired"
        _remove_authorization(record)
        return _oauth_error("expired_token", "Device code expired")
    if record.status == "pending":
        return _oauth_error("authorization_pending", "Authorization is still pending")
    if record.status == "denied":
        _remove_authorization(record)
        return _oauth_error("access_denied", "Device authorization was denied")
    if record.status != "approved":
        return _oauth_error("invalid_grant", "Device authorization is not valid")

    token = _encode_jwt(
        {
            "sub": record.subject or record.client_id,
            "client_id": record.client_id,
            "scope": record.scope,
            "aud": record.audience,
            "idp": record.identity_provider,
            "email": record.email,
            "device_code_hash": hashlib.sha256(record.device_code.encode("utf-8")).hexdigest(),
        },
        expires_in=ACCESS_TOKEN_EXPIRES_IN_SECONDS,
    )
    _remove_authorization(record)
    return DeviceTokenResponse(
        access_token=token,
        expires_in=ACCESS_TOKEN_EXPIRES_IN_SECONDS,
        scope=record.scope,
    )


def _verification_uri() -> str:
    return os.environ.get("AOP_DEVICE_VERIFICATION_URI", "http://localhost:3000/device")


def _normalize_user_code(user_code: str) -> str:
    return user_code.strip().upper().replace(" ", "-")


def _new_device_code() -> str:
    while True:
        code = secrets.token_urlsafe(32)
        if code not in DEVICE_AUTHORIZATIONS_BY_DEVICE_CODE:
            return code


def _new_user_code() -> str:
    while True:
        code = "-".join(
            "".join(secrets.choice(USER_CODE_ALPHABET) for _ in range(4))
            for _ in range(2)
        )
        if code not in DEVICE_AUTHORIZATIONS_BY_USER_CODE:
            return code


def _prune_expired_authorizations() -> None:
    now = datetime.now(UTC)
    expired = [
        device_code
        for device_code, record in DEVICE_AUTHORIZATIONS_BY_DEVICE_CODE.items()
        if record.expires_at <= now
    ]
    for device_code in expired:
        record = DEVICE_AUTHORIZATIONS_BY_DEVICE_CODE[device_code]
        record.status = "expired"
        _remove_authorization(record)


def _remove_authorization(record: DeviceAuthorizationRecord) -> None:
    DEVICE_AUTHORIZATIONS_BY_DEVICE_CODE.pop(record.device_code, None)
    DEVICE_AUTHORIZATIONS_BY_USER_CODE.pop(record.user_code, None)


def _verify_google_id_token(raw_id_token: str) -> dict[str, Any] | JSONResponse:
    client_id = os.environ.get("GOOGLE_OAUTH_CLIENT_ID")
    if not client_id:
        return _oauth_error("server_error", "GOOGLE_OAUTH_CLIENT_ID is not configured", status_code=503)
    try:
        from google.auth.transport import requests
        from google.oauth2 import id_token

        claims = id_token.verify_oauth2_token(raw_id_token, requests.Request(), client_id)
    except ImportError:
        return _oauth_error("server_error", "google-auth is not installed", status_code=503)
    except ValueError:
        return _oauth_error("invalid_grant", "Invalid Google ID token")

    return _validate_google_claims(claims)


def _validate_google_claims(claims: dict[str, Any]) -> dict[str, Any] | JSONResponse:
    if not isinstance(claims, dict) or not claims.get("sub"):
        return _oauth_error("invalid_grant", "Google ID token is missing subject")
    if claims.get("email") and claims.get("email_verified") is False:
        return _oauth_error("invalid_grant", "Google account email is not verified")
    allowed_domains = _allowed_google_domains()
    if allowed_domains:
        hosted_domain = claims.get("hd")
        if hosted_domain not in allowed_domains:
            return _oauth_error("access_denied", "Google account domain is not allowed")
    return claims


def _allowed_google_domains() -> set[str]:
    raw = os.environ.get("GOOGLE_OAUTH_ALLOWED_DOMAINS") or os.environ.get("GOOGLE_ALLOWED_DOMAINS") or ""
    return {domain.strip() for domain in raw.split(",") if domain.strip()}


def _map_google_claims_to_local_user(claims: dict[str, Any]) -> LocalUser:
    google_sub = str(claims["sub"])
    existing_user_id = LOCAL_USERS_BY_GOOGLE_SUB.get(google_sub)
    now = datetime.now(UTC)
    if existing_user_id and existing_user_id in LOCAL_USERS_BY_ID:
        user = LOCAL_USERS_BY_ID[existing_user_id]
        updated = user.model_copy(
            update={
                "email": claims.get("email"),
                "name": claims.get("name"),
                "picture": claims.get("picture"),
                "hosted_domain": claims.get("hd"),
                "updated_at": now,
            }
        )
        LOCAL_USERS_BY_ID[existing_user_id] = updated
        return updated

    user = LocalUser(
        user_id=f"user_{secrets.token_urlsafe(18)}",
        provider_subject=google_sub,
        email=claims.get("email"),
        name=claims.get("name"),
        picture=claims.get("picture"),
        hosted_domain=claims.get("hd"),
        created_at=now,
        updated_at=now,
    )
    LOCAL_USERS_BY_ID[user.user_id] = user
    LOCAL_USERS_BY_GOOGLE_SUB[google_sub] = user.user_id
    return user


def _oauth_error(error: str, description: str, *, status_code: int = 400) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": error, "error_description": description},
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )


def _encode_jwt(claims: dict[str, Any], *, expires_in: int) -> str:
    now = int(datetime.now(UTC).timestamp())
    payload = {
        **{key: value for key, value in claims.items() if value is not None},
        "iat": now,
        "exp": now + expires_in,
    }
    header = {"alg": "HS256", "typ": "JWT"}
    signing_input = ".".join(
        [
            _base64url_json(header),
            _base64url_json(payload),
        ]
    )
    signature = hmac.new(_jwt_secret().encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256).digest()
    return f"{signing_input}.{_base64url(signature)}"


def _jwt_secret() -> str:
    return os.environ.get("JWT_SECRET") or os.environ.get("AOP_JWT_SECRET") or "change-me-dev-jwt-secret"


def _base64url_json(value: dict[str, Any]) -> str:
    return _base64url(json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8"))


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")

class LoginRequest(BaseModel):
    user_id: str
    role: str
    tenant_id: str

class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"

@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    """
    Issue a new JWT access token with user_id, role, and tenant_id claims.
    """
    from app.auth import create_access_token
    token = create_access_token(
        user_id=request.user_id,
        role=request.role,
        tenant_id=request.tenant_id
    )
    return LoginResponse(access_token=token)
