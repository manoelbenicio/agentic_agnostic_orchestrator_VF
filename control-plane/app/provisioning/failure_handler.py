"""Activation failure persistence, retry, and API helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from psycopg.types.json import Jsonb

from .activation import ActivationResult, ActivationStepResult

DEFAULT_MAX_RETRIES = 3
DEFAULT_BASE_BACKOFF_SECONDS = 30


class ActivationFailure(BaseModel):
    """Persisted failed activation with retry metadata and partial step state."""

    model_config = ConfigDict(extra="forbid")

    record_id: str
    target: str
    step_results: list[ActivationStepResult] = Field(default_factory=list)
    failed_step: str
    error: str
    retry_eligible: bool
    retry_count: int = 0
    max_retries: int = DEFAULT_MAX_RETRIES
    next_retry_at: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


def save_activation_failure(
    *,
    record_id: str,
    target: str,
    error: Exception | str,
    failed_step: str,
    step_results: list[ActivationStepResult],
    data: dict[str, Any],
    state: Any,
    max_retries: int = DEFAULT_MAX_RETRIES,
    base_backoff_seconds: int = DEFAULT_BASE_BACKOFF_SECONDS,
) -> ActivationFailure:
    """Persist partial activation state after a failed orchestration attempt."""

    conn = _connection(state)
    error_text = str(error)
    now = datetime.now(timezone.utc)
    metadata = dict(data)
    retry_count = 0

    if conn is not None:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT metadata FROM provisioning_records WHERE record_id = %s",
                (record_id,),
            )
            row = cur.fetchone()
            if row:
                metadata = _metadata(_row_get(row, "metadata"))
                retry_count = _int_value(metadata.get("retry_count"), default=0)

            retry_eligible = retry_count < max_retries
            next_retry_at = _next_retry_time(now, retry_count, base_backoff_seconds) if retry_eligible else None
            updated_metadata = {
                **metadata,
                **dict(data),
                "failed_step": failed_step,
                "failed_error": error_text,
                "failed_at": now.isoformat(),
                "retry_count": retry_count,
                "max_retries": max_retries,
                "retry_eligible": retry_eligible,
                "next_retry_at": next_retry_at.isoformat() if next_retry_at else None,
                "step_results": [step.model_dump() for step in step_results],
            }

            if row:
                cur.execute(
                    """
                    UPDATE provisioning_records
                    SET status = %s, metadata = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE record_id = %s
                    """,
                    ("failed", Jsonb(updated_metadata), record_id),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO provisioning_records (record_id, target, status, metadata)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (record_id, target, "failed", Jsonb(updated_metadata)),
                )
        conn.commit()
        return ActivationFailure(
            record_id=record_id,
            target=target,
            step_results=step_results,
            failed_step=failed_step,
            error=error_text,
            retry_eligible=retry_eligible,
            retry_count=retry_count,
            max_retries=max_retries,
            next_retry_at=next_retry_at.isoformat() if next_retry_at else None,
            metadata=updated_metadata,
        )

    return ActivationFailure(
        record_id=record_id,
        target=target,
        step_results=step_results,
        failed_step=failed_step,
        error=error_text,
        retry_eligible=False,
        retry_count=0,
        max_retries=max_retries,
        metadata=metadata,
    )


def retry_activation(
    record_id: str,
    state: Any,
    *,
    max_retries: int = DEFAULT_MAX_RETRIES,
    base_backoff_seconds: int = DEFAULT_BASE_BACKOFF_SECONDS,
    force: bool = False,
) -> ActivationResult:
    """Retry a failed activation, resuming after the last successful step."""

    conn = _required_connection(state)
    now = datetime.now(timezone.utc)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT record_id, target, status, metadata FROM provisioning_records WHERE record_id = %s",
            (record_id,),
        )
        row = cur.fetchone()
        if not row:
            raise ValueError(f"Activation record '{record_id}' not found.")
        if _row_get(row, "status") != "failed":
            raise ValueError(f"Activation record '{record_id}' is not failed.")

        metadata = _metadata(_row_get(row, "metadata"))
        retry_count = _int_value(metadata.get("retry_count"), default=0)
        configured_max_retries = _int_value(metadata.get("max_retries"), default=max_retries)
        if retry_count >= configured_max_retries:
            raise ValueError(f"Activation record '{record_id}' exceeded retry limit.")

        next_retry_at = _parse_datetime(metadata.get("next_retry_at"))
        if next_retry_at is not None and next_retry_at > now and not force:
            raise ValueError(
                f"Activation record '{record_id}' is not retryable until {next_retry_at.isoformat()}."
            )

        updated_metadata = {
            **metadata,
            "retry_count": retry_count + 1,
            "max_retries": configured_max_retries,
            "last_retry_at": now.isoformat(),
            "retry_eligible": retry_count + 1 < configured_max_retries,
            "next_retry_at": _next_retry_time(now, retry_count + 1, base_backoff_seconds).isoformat()
            if retry_count + 1 < configured_max_retries
            else None,
        }
        cur.execute(
            """
            UPDATE provisioning_records
            SET metadata = %s, updated_at = CURRENT_TIMESTAMP
            WHERE record_id = %s
            """,
            (Jsonb(updated_metadata), record_id),
        )
    conn.commit()

    request_data = {
        key: value
        for key, value in updated_metadata.items()
        if key
        not in {
            "failed_step",
            "failed_error",
            "failed_at",
            "retry_eligible",
            "next_retry_at",
            "last_retry_at",
            "step_results",
        }
    }
    request_data["record_id"] = record_id

    from .activation import orchestrate_activation

    return orchestrate_activation(request_data, state)


def list_activation_failures(state: Any, *, limit: int = 100) -> list[ActivationFailure]:
    """List failed activation records with their persisted step results."""

    conn = _required_connection(state)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT record_id, target, metadata
            FROM provisioning_records
            WHERE status = 'failed'
            ORDER BY updated_at DESC, created_at DESC
            LIMIT %s
            """,
            (limit,),
        )
        rows = cur.fetchall()

        failures: list[ActivationFailure] = []
        for row in rows:
            record_id = _row_get(row, "record_id")
            metadata = _metadata(_row_get(row, "metadata"))
            cur.execute(
                """
                SELECT step_name, status, output, error, duration_seconds
                FROM step_results
                WHERE record_id = %s
                ORDER BY started_at ASC
                """,
                (record_id,),
            )
            step_results = [_step_result(step_row) for step_row in cur.fetchall()]
            if not step_results:
                step_results = [_step_result(step) for step in metadata.get("step_results", [])]
            failures.append(
                ActivationFailure(
                    record_id=record_id,
                    target=str(_row_get(row, "target") or "unknown"),
                    step_results=step_results,
                    failed_step=str(metadata.get("failed_step") or "unknown"),
                    error=str(metadata.get("failed_error") or ""),
                    retry_eligible=bool(metadata.get("retry_eligible", False)),
                    retry_count=_int_value(metadata.get("retry_count"), default=0),
                    max_retries=_int_value(metadata.get("max_retries"), default=DEFAULT_MAX_RETRIES),
                    next_retry_at=metadata.get("next_retry_at"),
                    metadata=metadata,
                )
            )
    return failures


def build_provisioning_failure_router(get_state, *, prefix: str = "/provisioning") -> APIRouter:
    """Build provisioning failure API routes."""

    router = APIRouter(prefix=prefix, tags=["provisioning"])

    @router.get("/failures", response_model=list[ActivationFailure])
    def get_activation_failures(
        limit: int = Query(100, ge=1, le=500),
        state: Any = Depends(get_state),
    ) -> list[ActivationFailure]:
        try:
            return list_activation_failures(state, limit=limit)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    return router


def _connection(state: Any) -> Any | None:
    if hasattr(state, "postgres_connections") and state.postgres_connections:
        return state.postgres_connections[-1]
    return None


def _required_connection(state: Any) -> Any:
    conn = _connection(state)
    if conn is None:
        raise RuntimeError("No database connection available for activation failures.")
    return conn


def _metadata(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    return {}


def _row_get(row: Any, key: str, default: Any = None) -> Any:
    if isinstance(row, dict):
        return row.get(key, default)
    try:
        return row[key]
    except (KeyError, TypeError):
        return default


def _step_result(row: Any) -> ActivationStepResult:
    if isinstance(row, ActivationStepResult):
        return row
    return ActivationStepResult(
        step_name=str(_row_get(row, "step_name") or ""),
        status=str(_row_get(row, "status") or ""),
        output=_row_get(row, "output"),
        error=_row_get(row, "error"),
        duration_seconds=float(_row_get(row, "duration_seconds") or 0.0),
    )


def _int_value(value: Any, *, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _next_retry_time(now: datetime, retry_count: int, base_backoff_seconds: int) -> datetime:
    return now + timedelta(seconds=base_backoff_seconds * (2**retry_count))
