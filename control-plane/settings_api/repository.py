"""Postgres-backed CRUD repository for settings, integrations, and API tokens."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import psycopg

from .models import ApiTokenRecord, IntegrationRecord, SettingRecord


class SettingsRepository:
    """Persist and retrieve settings, integrations, and API tokens from Postgres."""

    def __init__(self, conn: psycopg.Connection[Any]) -> None:
        self.conn = conn

    # ── Settings (key-value) ──────────────────────────────────────────

    def get_settings(self, tenant_id: str) -> list[SettingRecord]:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM settings
                WHERE tenant_id = %s
                  AND key NOT LIKE 'integrations.%%'
                ORDER BY key ASC
                """,
                (tenant_id,),
            )
            rows = cur.fetchall()
        return [self._setting(row) for row in rows]

    def upsert_setting(self, *, tenant_id: str, key: str, value: str) -> SettingRecord:
        setting_id = f"setting-{uuid4()}"
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO settings (setting_id, tenant_id, key, value)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (tenant_id, key)
                DO UPDATE SET value = EXCLUDED.value, updated_at = CURRENT_TIMESTAMP
                RETURNING *
                """,
                (setting_id, tenant_id, key, value),
            )
            row = cur.fetchone()
        self.conn.commit()
        if row is None:
            raise RuntimeError("setting upsert returned no row")
        return self._setting(row)

    def delete_setting(self, *, tenant_id: str, key: str) -> bool:
        with self.conn.cursor() as cur:
            cur.execute(
                "DELETE FROM settings WHERE tenant_id = %s AND key = %s",
                (tenant_id, key),
            )
            deleted = cur.rowcount > 0
        self.conn.commit()
        return deleted

    # ── Profile (stored as settings with 'profile.' prefix) ──────────

    def get_profile(self, tenant_id: str) -> dict[str, str]:
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT key, value FROM settings WHERE tenant_id = %s AND key LIKE 'profile.%%' ORDER BY key",
                (tenant_id,),
            )
            rows = cur.fetchall()
        return {row["key"].removeprefix("profile."): row["value"] for row in rows}

    def upsert_profile(self, tenant_id: str, data: dict[str, str]) -> dict[str, str]:
        for k, v in data.items():
            self.upsert_setting(tenant_id=tenant_id, key=f"profile.{k}", value=str(v))
        return self.get_profile(tenant_id)

    # ── Integrations ─────────────────────────────────────────────────

    def list_integrations(self, tenant_id: str) -> list[IntegrationRecord]:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM settings
                WHERE tenant_id = %s
                  AND key LIKE 'integrations.%%'
                ORDER BY created_at DESC
                """,
                (tenant_id,),
            )
            rows = cur.fetchall()
        return [self._integration_from_setting(row) for row in rows]

    def create_integration(
        self,
        *,
        tenant_id: str,
        name: str,
        provider: str,
        config: dict[str, Any] | None = None,
        enabled: bool = True,
        integration_id: str | None = None,
    ) -> IntegrationRecord:
        integration_id = integration_id or f"intg-{uuid4()}"
        payload = {
            "integration_id": integration_id,
            "tenant_id": tenant_id,
            "name": name,
            "provider": provider,
            "config": config or {},
            "enabled": enabled,
        }
        row = self.upsert_setting(
            tenant_id=tenant_id,
            key=f"integrations.{integration_id}",
            value=json.dumps(payload, sort_keys=True),
        )
        return self._integration_from_setting_row(row)

    # ── API Tokens ───────────────────────────────────────────────────

    def list_tokens(self, tenant_id: str) -> list[ApiTokenRecord]:
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM api_tokens WHERE tenant_id = %s AND revoked_at IS NULL ORDER BY created_at DESC",
                (tenant_id,),
            )
            rows = cur.fetchall()
        return [self._token(row) for row in rows]

    def create_token(
        self,
        *,
        tenant_id: str,
        name: str,
        token_hash: str,
        prefix: str = "",
        expires_at: datetime | None = None,
        token_id: str | None = None,
    ) -> ApiTokenRecord:
        token_id = token_id or f"tok-{uuid4()}"
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO api_tokens (id, tenant_id, name, token_hash, prefix, expires_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (token_id, tenant_id, name, token_hash, prefix, expires_at),
            )
            row = cur.fetchone()
        self.conn.commit()
        if row is None:
            raise RuntimeError("token insert returned no row")
        return self._token(row)

    def revoke_token(self, token_id: str) -> ApiTokenRecord | None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                UPDATE api_tokens
                SET revoked_at = CURRENT_TIMESTAMP
                WHERE id = %s AND revoked_at IS NULL
                RETURNING *
                """,
                (token_id,),
            )
            row = cur.fetchone()
        self.conn.commit()
        return self._token(row) if row else None

    # ── Record mappers ───────────────────────────────────────────────

    def _setting(self, row: dict[str, Any]) -> SettingRecord:
        return SettingRecord(
            setting_id=str(row["setting_id"]),
            tenant_id=str(row["tenant_id"]),
            key=str(row["key"]),
            value=str(row["value"]),
            created_at=self._dt(row.get("created_at")),
            updated_at=self._dt(row.get("updated_at")),
        )

    def _integration_from_setting(self, row: dict[str, Any]) -> IntegrationRecord:
        setting = self._setting(row)
        return self._integration_from_setting_row(setting)

    def _integration_from_setting_row(self, row: SettingRecord) -> IntegrationRecord:
        payload = json.loads(row.value)
        return IntegrationRecord(
            integration_id=str(payload["integration_id"]),
            tenant_id=row.tenant_id,
            name=str(payload["name"]),
            provider=str(payload["provider"]),
            config=dict(payload.get("config") or {}),
            enabled=bool(payload.get("enabled", True)),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def _token(self, row: dict[str, Any]) -> ApiTokenRecord:
        return ApiTokenRecord(
            token_id=str(row["id"]),
            tenant_id=str(row["tenant_id"]),
            name=str(row["name"]),
            token_hash=str(row["token_hash"]),
            prefix=str(row.get("prefix", "")),
            created_at=self._dt(row.get("created_at")),
            expires_at=self._dt(row.get("expires_at")),
            revoked_at=self._dt(row.get("revoked_at")),
        )

    def _dt(self, value: Any) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        raise TypeError(f"expected datetime, got {type(value)!r}")
