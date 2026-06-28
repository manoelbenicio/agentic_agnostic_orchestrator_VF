"""
Orchestration engine for the AOP control plane.

This module owns the *executable* layer of the orchestration framework
defined in :mod:`app.orchestration.workflow`:

    * :class:`OrchestrationEngine`  - the executor: dispatches steps to
      handlers, applies retry + fallback policies, runs ``parallel``
      sub-steps concurrently, and tracks :class:`WorkflowStatus` /
      :class:`StepStatus` across the run.
    * Built-in step handlers for the five supported ``StepType`` values
      (``llm_call``, ``api_call``, ``transform``, ``condition``,
      ``parallel``).
    * A FastAPI :class:`APIRouter` mounted at ``/orchestration/workflows``
      exposing ``POST /execute`` and ``POST /validate`` endpoints.

Concurrency model
-----------------
Top-level steps execute in dependency-respecting order. Within a step, the
``parallel`` handler launches its sub-steps via ``asyncio.gather`` and
returns once all sub-steps complete (or one fails, unless the sub-step
defines its own fallback). LLM and HTTP calls are awaited directly.
"""

from __future__ import annotations

import asyncio
import builtins as _builtins
import json
import logging
import math
import re
from datetime import datetime, timezone
from typing import (
    Any,
    Awaitable,
    Callable,
    Dict,
    Iterable,
    List,
    Mapping,
    Optional,
    Sequence,
)

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from .workflow import (
    ExecutionContext,
    RetryPolicy,
    StepDefinition,
    StepResult,
    StepStatus,
    StepType,
    WorkflowDefinition,
    WorkflowResult,
    WorkflowStatus,
)

logger = logging.getLogger("orchestration.engine")


# ---------------------------------------------------------------------------
# Adapter resolver type
# ---------------------------------------------------------------------------

# An adapter resolver is anything that, given a provider key, returns an
# object exposing ``async complete(model=..., messages=...)`` - i.e. the
# :class:`BaseAdapter` contract from :mod:`app.registry.adapters`.
AdapterResolver = Callable[[str], Any]


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class OrchestrationEngine:
    """Executes :class:`WorkflowDefinition` instances.

    Parameters
    ----------
    adapters:
        Optional mapping of ``provider_key`` -> pre-initialized
        :class:`BaseAdapter` (or any object with the same ``complete`` /
        ``stream`` shape). Used directly when an ``llm_call`` step references
        one of these keys.
    adapter_resolver:
        Optional callable invoked when ``llm_call`` step's provider is not
        in ``adapters``. Receives the provider key and must return an
        adapter instance (e.g. a factory that looks up ``app.registry``).
        Either ``adapters`` or ``adapter_resolver`` is required for
        ``llm_call`` steps to succeed.
    http_client:
        Optional ``httpx.AsyncClient`` to use for ``api_call`` steps. When
        ``None``, a default client with sensible timeouts is created and
        re-used across calls (closed only when the engine itself is closed).
    max_parallelism:
        Upper bound on how many sub-steps inside a ``parallel`` step may
        execute concurrently. Defaults to ``10``.
    request_timeout_s:
        Default per-request timeout for ``api_call`` steps when the step
        config does not specify one.
    """

    def __init__(
        self,
        *,
        adapters: Optional[Mapping[str, Any]] = None,
        adapter_resolver: Optional[AdapterResolver] = None,
        http_client: Optional[httpx.AsyncClient] = None,
        max_parallelism: int = 10,
        request_timeout_s: float = 30.0,
    ) -> None:
        self._adapters: Dict[str, Any] = dict(adapters or {})
        self._adapter_resolver = adapter_resolver
        self._http_client = http_client
        self._http_client_owned = http_client is None
        self._max_parallelism = max(1, int(max_parallelism))
        self._request_timeout_s = float(request_timeout_s)
        # Dispatch table populated after method definitions below.
        self._handlers: Dict[StepType, Callable[[StepDefinition, ExecutionContext], Awaitable[Any]]] = {}

    # --------------------------------------------------------------- lifecycle

    async def aclose(self) -> None:
        """Close any owned HTTP client. Call when the engine is no longer needed."""
        if self._http_client_owned and self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

    async def __aenter__(self) -> "OrchestrationEngine":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.aclose()

    # --------------------------------------------------------------- public

    async def execute_workflow(
        self,
        workflow_def: WorkflowDefinition,
        context: Optional[ExecutionContext] = None,
    ) -> WorkflowResult:
        """Execute ``workflow_def`` end-to-end and return a :class:`WorkflowResult`.

        Top-level steps run in topological order (Kahn's algorithm over
        ``depends_on`` edges). Each step's output is stored in
        :attr:`ExecutionContext.outputs` under the step's ``output_key``
        (defaulting to its ``id``) and becomes available to subsequent
        steps via expressions and template strings.

        The workflow halts at the first step that ends in ``FAILED``
        status without a successful fallback; remaining steps are
        recorded as :attr:`StepStatus.SKIPPED`.
        """
        workflow_def.validate_dependencies()
        ctx = context or ExecutionContext()
        result = WorkflowResult(
            workflow_id=workflow_def.id,
            status=WorkflowStatus.RUNNING,
        )

        try:
            ordered = self._topological_sort(workflow_def.steps)
        except ValueError as e:
            result.status = WorkflowStatus.FAILED
            result.error = f"Invalid workflow: {e}"
            result.completed_at = datetime.now(timezone.utc)
            return result

        for step in ordered:
            step_result = await self._execute_step(step, ctx)
            result.step_results[step.id] = step_result

            # Always record step output for downstream steps, even on
            # failure (so a follow-up conditional can inspect the error).
            ctx.set_output(step.resolve_output_key(), _output_for_chain(step_result))

            if step_result.status == StepStatus.FAILED:
                # Mark downstream steps as skipped.
                downstream = _downstream_of(step.id, workflow_def.steps)
                skipped_ids = {s.id for s in downstream if s.id not in result.step_results}
                for sid in skipped_ids:
                    result.step_results[sid] = StepResult(
                        step_id=sid,
                        status=StepStatus.SKIPPED,
                        error=f"upstream step {step.id!r} failed",
                    )
                result.status = WorkflowStatus.FAILED
                result.error = f"Step {step.id!r} failed: {step_result.error}"
                result.completed_at = datetime.now(timezone.utc)
                return result

        result.status = WorkflowStatus.COMPLETED
        result.final_context = ctx.as_mapping()
        result.completed_at = datetime.now(timezone.utc)
        return result

    async def _execute_step(
        self,
        step: StepDefinition,
        context: ExecutionContext,
    ) -> StepResult:
        """Execute a single step with retry and fallback policy applied."""
        result = StepResult(step_id=step.id, status=StepStatus.PENDING)
        result.mark_running()

        policy: RetryPolicy = step.retry or RetryPolicy(max_attempts=1)
        last_exc: Optional[BaseException] = None
        attempts = 0

        while True:
            attempts += 1
            result.attempts = attempts
            try:
                output = await self._dispatch(step, context)
                result.mark_completed(output)
                return result
            except Exception as exc:  # noqa: BLE001 - engine catches everything
                last_exc = exc
                if policy.should_retry(attempts, exc):
                    result.status = StepStatus.RETRYING
                    delay = policy.backoff_for(attempts + 1)
                    logger.info(
                        "step %r attempt %d failed (%s); retrying in %.2fs",
                        step.id, attempts, exc, delay,
                    )
                    if delay > 0:
                        await asyncio.sleep(delay)
                    continue
                break

        # All retries exhausted - try fallback if present.
        if step.fallback is not None:
            try:
                fallback_output = await self._dispatch(step.fallback, context)
                result.status = StepStatus.FALLBACK
                result.used_fallback = True
                result.output = fallback_output
                result.error = (
                    f"primary failed after {attempts} attempt(s): {last_exc}; "
                    f"fallback succeeded"
                )
                result.completed_at = datetime.now(timezone.utc)
                result.duration_ms = (
                    (result.completed_at - result.started_at).total_seconds() * 1000.0
                )
                return result
            except Exception as fexc:  # noqa: BLE001
                result.mark_failed(fexc)
                result.error = (
                    f"primary failed: {last_exc}; "
                    f"fallback also failed: {fexc}"
                )
                return result

        result.mark_failed(last_exc or RuntimeError("step failed without exception"))
        return result

    # --------------------------------------------------------------- dispatch

    async def _dispatch(
        self,
        step: StepDefinition,
        context: ExecutionContext,
    ) -> Any:
        handler = self._handlers.get(step.type)
        if handler is None:
            raise ValueError(f"No handler registered for step type {step.type!r}")
        return await handler(step, context)

    # --------------------------------------------------------------- handlers

    async def _handle_llm_call(
        self,
        step: StepDefinition,
        context: ExecutionContext,
    ) -> Any:
        cfg = step.config
        provider = cfg.get("provider")
        if not provider:
            raise ValueError(
                f"llm_call step {step.id!r} requires 'provider' in config"
            )
        adapter = self._resolve_adapter(provider)

        model = cfg.get("model")
        if not model:
            raise ValueError(
                f"llm_call step {step.id!r} requires 'model' in config"
            )

        raw_messages = cfg.get("messages") or []
        messages = self._render_messages(raw_messages, context)

        completion_kwargs: Dict[str, Any] = {}
        for key in ("temperature", "max_tokens", "top_p", "stop"):
            if key in cfg and cfg[key] is not None:
                completion_kwargs[key] = cfg[key]

        completion = await adapter.complete(
            model=str(model),
            messages=messages,
            **completion_kwargs,
        )
        # Normalize to a plain dict so it serializes cleanly.
        if hasattr(completion, "model_dump"):
            try:
                return completion.model_dump()
            except Exception:  # pragma: no cover - defensive
                pass
        if isinstance(completion, Mapping):
            return dict(completion)
        return {"result": str(completion)}

    async def _handle_api_call(
        self,
        step: StepDefinition,
        context: ExecutionContext,
    ) -> Any:
        cfg = step.config
        url = self._render_string(cfg.get("url", ""), context)
        if not url:
            raise ValueError(f"api_call step {step.id!r} requires non-empty 'url'")
        method = str(cfg.get("method", "GET")).upper()
        headers = {
            str(k): self._render_string(str(v), context)
            for k, v in (cfg.get("headers") or {}).items()
        }
        body = cfg.get("body")
        if isinstance(body, str):
            body = self._render_string(body, context)
        timeout = float(cfg.get("timeout", self._request_timeout_s))
        follow_redirects = bool(cfg.get("follow_redirects", True))

        client = self._get_http_client()
        response = await client.request(
            method=method,
            url=url,
            headers=headers,
            json=body if body is not None and method != "GET" else None,
            timeout=timeout,
            follow_redirects=follow_redirects,
        )

        result: Dict[str, Any] = {
            "status_code": response.status_code,
            "headers": dict(response.headers),
        }
        try:
            result["body"] = response.json()
        except Exception:
            result["text"] = response.text

        if response.status_code >= 400:
            # Surface HTTP errors as step failures so retry/fallback can kick in.
            raise RuntimeError(
                f"api_call {method} {url} -> {response.status_code}: "
                f"{result.get('text') or result.get('body')}"
            )
        return result

    async def _handle_transform(
        self,
        step: StepDefinition,
        context: ExecutionContext,
    ) -> Any:
        expression = step.config.get("expression")
        if not expression or not isinstance(expression, str):
            raise ValueError(
                f"transform step {step.id!r} requires string 'expression' in config"
            )
        return _safe_eval(expression, context)

    async def _handle_condition(
        self,
        step: StepDefinition,
        context: ExecutionContext,
    ) -> Any:
        cfg = step.config
        expression = cfg.get("expression")
        if not expression or not isinstance(expression, str):
            raise ValueError(
                f"condition step {step.id!r} requires string 'expression' in config"
            )
        branches = cfg.get("branches") or {}
        if not isinstance(branches, Mapping):
            raise ValueError(
                f"condition step {step.id!r} requires 'branches' mapping"
            )

        cond_result = bool(_safe_eval(expression, context))
        branch_key = "true" if cond_result else "false"
        branch_step = branches.get(branch_key)

        output: Dict[str, Any] = {
            "branch": branch_key,
            "expression_result": cond_result,
        }

        if branch_step is None:
            output["output"] = None
            return output

        if not isinstance(branch_step, StepDefinition):
            raise ValueError(
                f"condition step {step.id!r}: branch {branch_key!r} must be a "
                f"StepDefinition, got {type(branch_step).__name__}"
            )
        # Execute the branch as a self-contained step (no retry/fallback
        # wrapping - the branch can declare its own).
        branch_result = await self._execute_step(branch_step, context)
        output["output"] = _output_for_chain(branch_result)
        output["status"] = branch_result.status.value
        return output

    async def _handle_parallel(
        self,
        step: StepDefinition,
        context: ExecutionContext,
    ) -> Any:
        sub_steps: Sequence[Any] = step.config.get("steps") or []
        if not sub_steps:
            return []
        if not all(isinstance(s, StepDefinition) for s in sub_steps):
            raise ValueError(
                f"parallel step {step.id!r}: all 'steps' entries must be StepDefinitions"
            )
        sub_steps = list(sub_steps)  # type: ignore[assignment]

        semaphore = asyncio.Semaphore(self._max_parallelism)

        async def _run_with_cap(sub: StepDefinition) -> StepResult:
            async with semaphore:
                return await self._execute_step(sub, context)

        gathered = await asyncio.gather(
            *(_run_with_cap(s) for s in sub_steps),
            return_exceptions=False,
        )

        # Write each sub-step output back to the context using its declared key.
        for sub, sub_result in zip(sub_steps, gathered):
            context.set_output(sub.resolve_output_key(), _output_for_chain(sub_result))

        return [
            {
                "step_id": r.step_id,
                "status": r.status.value,
                "output": r.output,
                "error": r.error,
                "attempts": r.attempts,
                "used_fallback": r.used_fallback,
            }
            for r in gathered
        ]

    # --------------------------------------------------------------- helpers

    def _resolve_adapter(self, provider: str) -> Any:
        adapter = self._adapters.get(provider)
        if adapter is not None:
            return adapter
        if self._adapter_resolver is not None:
            adapter = self._adapter_resolver(provider)
            if adapter is None:
                raise RuntimeError(
                    f"adapter_resolver returned None for provider {provider!r}"
                )
            return adapter
        raise RuntimeError(
            f"No adapter registered for provider {provider!r}. "
            f"Construct the OrchestrationEngine with `adapters=` or "
            f"`adapter_resolver=`."
        )

    def _get_http_client(self) -> httpx.AsyncClient:
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=self._request_timeout_s,
                follow_redirects=True,
            )
        return self._http_client

    @staticmethod
    def _render_string(template: Any, context: ExecutionContext) -> Any:
        """Substitute ``${...}`` placeholders in ``template`` against ``context``.

        Supports simple paths like ``${ctx.outputs.foo}`` or
        ``${outputs.foo}``. Unknown placeholders are left intact so callers
        can see what failed to resolve.
        """
        if not isinstance(template, str):
            return template
        if "${" not in template:
            return template

        def _replace(match: "re.Match[str]") -> str:
            path = match.group(1).strip()
            try:
                value = _resolve_context_path(path, context)
            except Exception:
                return match.group(0)
            if value is None:
                return "null"
            if isinstance(value, bool):
                return "true" if value else "false"
            if isinstance(value, (dict, list)):
                return json.dumps(value, default=str)
            return str(value)

        return re.sub(r"\$\{([^}]+)\}", _replace, template)

    @staticmethod
    def _render_messages(
        messages: Iterable[Mapping[str, Any]],
        context: ExecutionContext,
    ) -> List[Dict[str, Any]]:
        rendered: List[Dict[str, Any]] = []
        for msg in messages:
            if not isinstance(msg, Mapping):
                raise ValueError(f"messages entry must be a mapping, got {type(msg).__name__}")
            new_msg: Dict[str, Any] = {}
            for key, value in msg.items():
                if isinstance(value, str):
                    new_msg[key] = OrchestrationEngine._render_string(value, context)
                elif isinstance(value, list):
                    # Common case: list of {"type": "text", "text": "..."} parts.
                    new_msg[key] = [
                        {k: OrchestrationEngine._render_string(v, context) if isinstance(v, str) else v
                         for k, v in (part.items() if isinstance(part, Mapping) else [])}
                        if isinstance(part, Mapping)
                        else part
                        for part in value
                    ]
                else:
                    new_msg[key] = value
            rendered.append(new_msg)
        return rendered

    @staticmethod
    def _topological_sort(steps: Sequence[StepDefinition]) -> List[StepDefinition]:
        """Kahn-style topological sort. Raises ``ValueError`` on cycles."""
        by_id = {s.id: s for s in steps}
        in_degree: Dict[str, int] = {s.id: 0 for s in steps}
        graph: Dict[str, List[str]] = {s.id: [] for s in steps}
        for step in steps:
            for dep in step.depends_on:
                if dep not in by_id:
                    raise ValueError(
                        f"Step {step.id!r} depends on unknown step {dep!r}"
                    )
                graph[dep].append(step.id)
                in_degree[step.id] += 1

        queue: List[str] = [sid for sid, deg in in_degree.items() if deg == 0]
        # Preserve original declaration order for ties.
        queue.sort(key=lambda sid: next(i for i, s in enumerate(steps) if s.id == sid))

        ordered: List[StepDefinition] = []
        while queue:
            sid = queue.pop(0)
            ordered.append(by_id[sid])
            for nxt in graph[sid]:
                in_degree[nxt] -= 1
                if in_degree[nxt] == 0:
                    # Insert preserving original declaration order.
                    insert_at = next(
                        (i for i, s in enumerate(queue) if s == nxt),
                        len(queue),
                    )
                    queue.insert(insert_at, nxt)

        if len(ordered) != len(steps):
            cycle = [sid for sid, d in in_degree.items() if d > 0]
            raise ValueError(f"Cycle detected in workflow dependencies: {cycle}")
        return ordered


# Wire up the handler dispatch table now that the methods exist.
OrchestrationEngine._handlers = {  # type: ignore[attr-defined]
    StepType.LLM_CALL: OrchestrationEngine._handle_llm_call,
    StepType.API_CALL: OrchestrationEngine._handle_api_call,
    StepType.TRANSFORM: OrchestrationEngine._handle_transform,
    StepType.CONDITION: OrchestrationEngine._handle_condition,
    StepType.PARALLEL: OrchestrationEngine._handle_parallel,
}


# ---------------------------------------------------------------------------
# Module-level helpers (pure functions; no engine instance required)
# ---------------------------------------------------------------------------


# A small whitelist of safe builtins for transform / condition expressions.
_SAFE_BUILTINS: Dict[str, Any] = {
    name: getattr(_builtins, name)
    for name in (
        "abs", "all", "any", "bool", "dict", "enumerate", "filter",
        "float", "frozenset", "int", "isinstance", "issubclass",
        "len", "list", "map", "max", "min", "print", "range", "repr",
        "reversed", "round", "set", "slice", "sorted", "str", "sum",
        "tuple", "type", "zip",
    )
    if hasattr(_builtins, name)
}


def _safe_eval(expression: str, context: ExecutionContext) -> Any:
    """Evaluate a Python expression with a sandboxed globals dict.

    The expression can reference ``ctx`` (the :class:`ExecutionContext`
    mapping), plus a small whitelist of pure builtins and the ``json`` and
    ``math`` modules. Attribute access on arbitrary objects is NOT
    restricted; callers should treat this as "trusted-author sandbox", not
    "untrusted-user sandbox".
    """
    safe_globals: Dict[str, Any] = {
        "__builtins__": _SAFE_BUILTINS,
        "json": json,
        "math": math,
    }
    safe_locals: Dict[str, Any] = {"ctx": context.as_mapping()}
    return eval(expression, safe_globals, safe_locals)


def _resolve_context_path(path: str, context: ExecutionContext) -> Any:
    """Resolve a dotted path like ``ctx.outputs.foo`` against the context.

    The leading ``ctx.`` segment is optional; ``outputs.foo`` is treated
    identically to ``ctx.outputs.foo``.
    """
    mapping = context.as_mapping()
    parts = [p for p in path.split(".") if p]
    if parts and parts[0] == "ctx":
        parts = parts[1:]
    cur: Any = mapping
    for part in parts:
        if isinstance(cur, Mapping):
            if part in cur:
                cur = cur[part]
            else:
                try:
                    idx = int(part)
                    cur = cur[idx]  # type: ignore[index]
                except (ValueError, KeyError, IndexError, TypeError):
                    raise KeyError(f"path {path!r} not found in context")
        elif isinstance(cur, list):
            try:
                idx = int(part)
                cur = cur[idx]
            except (ValueError, IndexError):
                raise KeyError(f"path {path!r} not found in context")
        else:
            raise KeyError(f"path {path!r} not found in context")
    return cur


def _downstream_of(
    step_id: str,
    steps: Sequence[StepDefinition],
) -> List[StepDefinition]:
    """Return steps that (directly or transitively) depend on ``step_id``."""
    downstream_ids: set = set()
    frontier: List[str] = [step_id]
    by_dep: Dict[str, List[str]] = {}
    for step in steps:
        for dep in step.depends_on:
            by_dep.setdefault(dep, []).append(step.id)

    while frontier:
        current = frontier.pop()
        for child_id in by_dep.get(current, []):
            if child_id not in downstream_ids:
                downstream_ids.add(child_id)
                frontier.append(child_id)

    return [s for s in steps if s.id in downstream_ids]


def _output_for_chain(step_result: StepResult) -> Any:
    """Return the value a downstream step should see for this step's output."""
    if step_result.status == StepStatus.COMPLETED:
        return step_result.output
    if step_result.status == StepStatus.FALLBACK:
        return step_result.output
    return {"status": step_result.status.value, "error": step_result.error}


# ---------------------------------------------------------------------------
# FastAPI router
# ---------------------------------------------------------------------------


class ExecuteWorkflowRequest(BaseModel):
    """Request body for ``POST /orchestration/workflows/execute``."""

    model_config = ConfigDict(extra="forbid")

    workflow: WorkflowDefinition
    inputs: Dict[str, Any] = Field(default_factory=dict)


class ExecuteWorkflowResponse(BaseModel):
    """Response body for ``POST /orchestration/workflows/execute``."""

    model_config = ConfigDict(extra="allow")

    workflow_id: str
    status: WorkflowStatus
    step_results: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    final_context: Optional[Dict[str, Any]] = None
    started_at: datetime
    completed_at: Optional[datetime] = None
    error: Optional[str] = None


class ValidateWorkflowResponse(BaseModel):
    """Response body for ``POST /orchestration/workflows/validate``."""

    model_config = ConfigDict(extra="forbid")

    valid: bool
    step_count: Optional[int] = None
    error: Optional[str] = None
    errors: List[str] = Field(default_factory=list)


# Module-level singleton, lazily constructed on first request. Tests can
# override via :func:`set_engine`.
_engine: Optional[OrchestrationEngine] = None
_engine_lock = asyncio.Lock()


def get_engine() -> OrchestrationEngine:
    """Return the process-wide :class:`OrchestrationEngine` instance."""
    global _engine
    if _engine is None:
        _engine = OrchestrationEngine()
    return _engine


def set_engine(engine: Optional[OrchestrationEngine]) -> None:
    """Replace the process-wide engine (primarily for tests)."""
    global _engine
    _engine = engine


def build_orchestration_router() -> APIRouter:
    """Build the FastAPI router mounted at ``/orchestration/workflows``."""
    router = APIRouter(prefix="/orchestration/workflows", tags=["orchestration"])

    @router.post(
        "/execute",
        response_model=ExecuteWorkflowResponse,
        summary="Execute a workflow end-to-end",
    )
    async def execute_workflow(request: ExecuteWorkflowRequest) -> ExecuteWorkflowResponse:
        try:
            request.workflow.validate_dependencies()
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail={"code": "invalid_workflow", "reason": str(e)},
            ) from e

        engine = get_engine()
        ctx = ExecutionContext(inputs=dict(request.inputs))
        result = await engine.execute_workflow(request.workflow, context=ctx)

        return ExecuteWorkflowResponse(
            workflow_id=result.workflow_id,
            status=result.status,
            step_results={
                sid: sr.model_dump(mode="json")
                for sid, sr in result.step_results.items()
            },
            final_context=result.final_context,
            started_at=result.started_at,
            completed_at=result.completed_at,
            error=result.error,
        )

    @router.post(
        "/validate",
        response_model=ValidateWorkflowResponse,
        summary="Validate a workflow definition without executing it",
    )
    async def validate_workflow(request: ExecuteWorkflowRequest) -> ValidateWorkflowResponse:
        errors: List[str] = []
        try:
            request.workflow.validate_dependencies()
        except ValueError as e:
            errors.append(str(e))
        # Step-level validation pass.
        seen_ids: set = set()
        for idx, step in enumerate(request.workflow.steps):
            if step.id in seen_ids:
                errors.append(f"duplicate step id {step.id!r} at index {idx}")
            seen_ids.add(step.id)
            if step.type == StepType.LLM_CALL and not step.config.get("model"):
                errors.append(f"step {step.id!r}: llm_call requires 'model' in config")
            if step.type == StepType.API_CALL and not step.config.get("url"):
                errors.append(f"step {step.id!r}: api_call requires 'url' in config")
            if step.type == StepType.TRANSFORM and not step.config.get("expression"):
                errors.append(f"step {step.id!r}: transform requires 'expression' in config")
            if step.type == StepType.CONDITION and not step.config.get("expression"):
                errors.append(f"step {step.id!r}: condition requires 'expression' in config")
            if step.type == StepType.PARALLEL and not step.config.get("steps"):
                errors.append(f"step {step.id!r}: parallel requires non-empty 'steps' list")

        return ValidateWorkflowResponse(
            valid=not errors,
            step_count=len(request.workflow.steps),
            error=errors[0] if errors else None,
            errors=errors,
        )

    @router.get(
        "/health",
        summary="Liveness probe for the orchestration module",
    )
    async def health() -> Dict[str, Any]:
        return {"status": "ok", "module": "orchestration"}

    return router


# Default router instance for `app.include_router(...)` callers.
router = build_orchestration_router()
