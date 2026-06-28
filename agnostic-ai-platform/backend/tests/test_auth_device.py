from __future__ import annotations

import base64
import json
import re
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.routers import auth as auth_router
from app.main import create_app
from app.routers.auth import (
    DEVICE_AUTHORIZATIONS_BY_DEVICE_CODE,
    DEVICE_AUTHORIZATIONS_BY_USER_CODE,
    LOCAL_USERS_BY_GOOGLE_SUB,
    LOCAL_USERS_BY_ID,
)


def setup_function() -> None:
    DEVICE_AUTHORIZATIONS_BY_DEVICE_CODE.clear()
    DEVICE_AUTHORIZATIONS_BY_USER_CODE.clear()
    LOCAL_USERS_BY_GOOGLE_SUB.clear()
    LOCAL_USERS_BY_ID.clear()


def test_device_authorize_generates_device_and_user_codes(monkeypatch) -> None:
    monkeypatch.setenv("AOP_DEVICE_VERIFICATION_URI", "https://auth.example.test/device")
    client = TestClient(create_app())

    response = client.post(
        "/auth/device/authorize",
        json={"client_id": "desktop-cli", "scope": "openid profile", "audience": "aop-api"},
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["device_code"]) >= 32
    assert re.fullmatch(r"[A-Z0-9]{4}-[A-Z0-9]{4}", body["user_code"])
    assert body["verification_uri"] == "https://auth.example.test/device"
    assert body["verification_uri_complete"] == f"https://auth.example.test/device?user_code={body['user_code']}"
    assert body["expires_in"] == 600
    assert body["interval"] == 5

    stored = DEVICE_AUTHORIZATIONS_BY_DEVICE_CODE[body["device_code"]]
    assert stored.client_id == "desktop-cli"
    assert stored.scope == "openid profile"
    assert stored.audience == "aop-api"
    assert stored.status == "pending"
    assert DEVICE_AUTHORIZATIONS_BY_USER_CODE[body["user_code"]] == body["device_code"]


def test_device_authorize_rejects_missing_client_id() -> None:
    client = TestClient(create_app())

    response = client.post("/auth/device/authorize", json={"scope": "openid"})

    assert response.status_code == 422


def test_device_token_returns_authorization_pending_before_approval() -> None:
    client = TestClient(create_app())
    authorized = client.post("/auth/device/authorize", json={"client_id": "desktop-cli"})

    response = client.post(
        "/auth/device/token",
        json={"client_id": "desktop-cli", "device_code": authorized.json()["device_code"]},
    )

    assert response.status_code == 400
    assert response.json()["error"] == "authorization_pending"


def test_device_token_returns_jwt_when_authorized(monkeypatch) -> None:
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    client = TestClient(create_app())
    authorized = client.post(
        "/auth/device/authorize",
        json={"client_id": "desktop-cli", "scope": "openid profile", "audience": "aop-api"},
    )
    device_code = authorized.json()["device_code"]
    record = DEVICE_AUTHORIZATIONS_BY_DEVICE_CODE[device_code]
    record.status = "approved"
    record.subject = "user-123"

    response = client.post(
        "/auth/device/token",
        json={"client_id": "desktop-cli", "device_code": device_code},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "Bearer"
    assert body["expires_in"] == 3600
    assert body["scope"] == "openid profile"
    header, payload, signature = body["access_token"].split(".")
    assert json.loads(_b64decode(header)) == {"alg": "HS256", "typ": "JWT"}
    claims = json.loads(_b64decode(payload))
    assert claims["sub"] == "user-123"
    assert claims["client_id"] == "desktop-cli"
    assert claims["scope"] == "openid profile"
    assert claims["aud"] == "aop-api"
    assert claims["exp"] > claims["iat"]
    assert signature
    assert device_code not in DEVICE_AUTHORIZATIONS_BY_DEVICE_CODE


def test_google_device_authorize_approves_flow_and_maps_local_user(monkeypatch) -> None:
    monkeypatch.setattr(
        auth_router,
        "_verify_google_id_token",
        lambda raw_id_token: {
            "sub": "google-sub-1",
            "email": "user@example.com",
            "email_verified": True,
            "name": "Example User",
            "picture": "https://example.com/avatar.png",
            "hd": "example.com",
        },
    )
    client = TestClient(create_app())
    authorized = client.post("/auth/device/authorize", json={"client_id": "desktop-cli", "scope": "openid email"})
    user_code = authorized.json()["user_code"]

    response = client.post(
        "/auth/device/google/authorize",
        json={"user_code": user_code.lower(), "id_token": "google-id-token"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "approved"
    assert body["client_id"] == "desktop-cli"
    assert body["scope"] == "openid email"
    assert body["user"]["provider"] == "google"
    assert body["user"]["provider_subject"] == "google-sub-1"
    assert body["user"]["email"] == "user@example.com"
    assert LOCAL_USERS_BY_GOOGLE_SUB["google-sub-1"] == body["user"]["user_id"]
    record = DEVICE_AUTHORIZATIONS_BY_DEVICE_CODE[authorized.json()["device_code"]]
    assert record.status == "approved"
    assert record.subject == body["user"]["user_id"]
    assert record.identity_provider == "google"
    assert record.email == "user@example.com"


def test_google_device_authorize_then_token_returns_google_identity_jwt(monkeypatch) -> None:
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    monkeypatch.setattr(
        auth_router,
        "_verify_google_id_token",
        lambda raw_id_token: {
            "sub": "google-sub-2",
            "email": "second@example.com",
            "email_verified": True,
        },
    )
    client = TestClient(create_app())
    authorized = client.post("/auth/device/authorize", json={"client_id": "desktop-cli", "scope": "openid email"})

    approval = client.post(
        "/auth/device/google/authorize",
        json={"user_code": authorized.json()["user_code"], "id_token": "google-id-token"},
    )
    token = client.post(
        "/auth/device/token",
        json={"client_id": "desktop-cli", "device_code": authorized.json()["device_code"]},
    )

    assert approval.status_code == 200
    assert token.status_code == 200
    claims = json.loads(_b64decode(token.json()["access_token"].split(".")[1]))
    assert claims["sub"] == approval.json()["user"]["user_id"]
    assert claims["idp"] == "google"
    assert claims["email"] == "second@example.com"


def test_google_device_authorize_rejects_invalid_user_code() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/auth/device/google/authorize",
        json={"user_code": "BAD-CODE", "id_token": "google-id-token"},
    )

    assert response.status_code == 400
    assert response.json()["error"] == "invalid_grant"


def test_google_id_token_validation_enforces_allowed_domain(monkeypatch) -> None:
    monkeypatch.setenv("GOOGLE_OAUTH_ALLOWED_DOMAINS", "example.com")

    response = auth_router._validate_google_claims(
        {
            "sub": "google-sub-3",
            "email": "user@other.test",
            "email_verified": True,
            "hd": "other.test",
        }
    )

    assert response.status_code == 400
    assert json.loads(response.body)["error"] == "access_denied"


def test_device_token_rejects_unknown_or_mismatched_device_code() -> None:
    client = TestClient(create_app())
    authorized = client.post("/auth/device/authorize", json={"client_id": "desktop-cli"})

    unknown = client.post(
        "/auth/device/token",
        json={"client_id": "desktop-cli", "device_code": "missing"},
    )
    mismatch = client.post(
        "/auth/device/token",
        json={"client_id": "other-client", "device_code": authorized.json()["device_code"]},
    )

    assert unknown.status_code == 400
    assert unknown.json()["error"] == "invalid_grant"
    assert mismatch.status_code == 400
    assert mismatch.json()["error"] == "invalid_grant"


def test_device_token_rejects_expired_device_code() -> None:
    client = TestClient(create_app())
    authorized = client.post("/auth/device/authorize", json={"client_id": "desktop-cli"})
    device_code = authorized.json()["device_code"]
    DEVICE_AUTHORIZATIONS_BY_DEVICE_CODE[device_code].expires_at = datetime.now(UTC) - timedelta(seconds=1)

    response = client.post(
        "/auth/device/token",
        json={"client_id": "desktop-cli", "device_code": device_code},
    )

    assert response.status_code == 400
    assert response.json()["error"] == "expired_token"
    assert device_code not in DEVICE_AUTHORIZATIONS_BY_DEVICE_CODE


def _b64decode(value: str) -> str:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding).decode("utf-8")
