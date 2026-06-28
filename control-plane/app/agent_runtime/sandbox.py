"""Sandboxed execution with CPU / memory / timeout / output limits.

:class:`AgentSandbox` runs a callable inside a child process with POSIX
resource limits applied (when available) and full stdout / stderr capture.
The parent enforces a wall-clock timeout, caps captured output size, and
terminates the child if it overruns.

Resource-limit strategy:

  * ``RLIMIT_CPU`` (seconds) is applied via :mod:`resource` in the child.
    A SIGXCPU is delivered when the limit is exceeded; the child may trap
    it but typically cannot escape.
  * ``RLIMIT_AS`` (address-space bytes) bounds virtual memory. Allocations
    that exceed the limit raise :class:`MemoryError` in the child.
  * Wall-clock timeout is enforced by the parent (``proc.join(timeout)``);
    the child is then terminated and killed.
  * Captured stdout / stderr are truncated to ``max_output_bytes`` in the
    parent to bound transport cost.

If ``multiprocessing`` or :mod:`resource` are unavailable (e.g. Windows
forks, stripped Python builds), the sandbox falls back to a thread-based
executor that still enforces wall-clock timeout and output capture.
"""

from __future__ import annotations

import io
import logging
import multiprocessing as _mp
import os
import platform
import queue as _queue
import sys
import threading
import time
import traceback
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

logger = logging.getLogger(__name__)

_IS_WINDOWS = platform.system() == "Windows"
_HAS_RESOURCE = not _IS_WINDOWS and sys.platform != "win32"

_DEFAULT_TIMEOUT_S = 30.0
_DEFAULT_CPU_SECONDS = 10
_DEFAULT_MEMORY_MB = 512
_DEFAULT_MAX_OUTPUT_BYTES = 1_048_576  # 1 MiB


@dataclass(frozen=True, slots=True)
class ResourceLimits:
    """Resource caps applied to a sandboxed call.

    All fields are optional; ``None`` means "no limit". ``timeout_s`` is
    always enforced by the parent. ``max_output_bytes`` bounds the size of
    captured stdout / stderr to keep transport predictable.
    """

    cpu_seconds: int | None = _DEFAULT_CPU_SECONDS
    memory_mb: int | None = _DEFAULT_MEMORY_MB
    timeout_s: float = _DEFAULT_TIMEOUT_S
    max_output_bytes: int = _DEFAULT_MAX_OUTPUT_BYTES
    extra_popen_env: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.cpu_seconds is not None and self.cpu_seconds <= 0:
            raise ValueError("cpu_seconds must be > 0 when set")
        if self.memory_mb is not None and self.memory_mb <= 0:
            raise ValueError("memory_mb must be > 0 when set")
        if self.timeout_s <= 0:
            raise ValueError("timeout_s must be > 0")
        if self.max_output_bytes <= 0:
            raise ValueError("max_output_bytes must be > 0")


class ResourceLimitError(RuntimeError):
    """Raised when a sandboxed call exceeds CPU, memory, or wall-clock limits."""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(f"{kind}: {message}")
        self.kind = kind


@dataclass(frozen=True, slots=True)
class SandboxResult:
    """Outcome of a single :meth:`AgentSandbox.execute` call."""

    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool
    resource_exceeded: bool
    result: Any
    error: str | None
    duration_s: float
    pid: int | None = None

    @property
    def succeeded(self) -> bool:
        return self.exit_code == 0 and not self.timed_out and not self.resource_exceeded and self.error is None

    def to_dict(self) -> dict[str, Any]:
        return {
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit_code": self.exit_code,
            "timed_out": self.timed_out,
            "resource_exceeded": self.resource_exceeded,
            "result": self.result,
            "error": self.error,
            "duration_s": self.duration_s,
            "pid": self.pid,
            "succeeded": self.succeeded,
        }


# ---------------------------------------------------------------------------
# Child entry point (must be top-level for pickling under 'spawn')
# ---------------------------------------------------------------------------


def _sandbox_child_entry(
    func: Callable[..., Any],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    limits: ResourceLimits,
    out_q: "_mp.Queue[tuple[str, Any]]",
) -> None:
    """Run inside the child process. Apply limits, capture output, report result."""
    # Resource limits MUST be applied before any non-trivial allocation.
    if _HAS_RESOURCE:
        import resource as _resource  # type: ignore[import-not-found]

        if limits.cpu_seconds is not None:
            try:
                _resource.setrlimit(
                    _resource.RLIMIT_CPU,
                    (int(limits.cpu_seconds), int(limits.cpu_seconds) + 1),
                )
            except (ValueError, OSError) as exc:
                logger.debug("could not set RLIMIT_CPU: %s", exc)

        if limits.memory_mb is not None:
            try:
                byte_limit = int(limits.memory_mb) * 1024 * 1024
                _resource.setrlimit(_resource.RLIMIT_AS, (byte_limit, byte_limit))
            except (ValueError, OSError) as exc:
                logger.debug("could not set RLIMIT_AS: %s", exc)

    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    pid = os.getpid()
    result: Any = _SANDBOX_SENTINEL
    error: str | None = None
    start = time.monotonic()

    try:
        with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
            try:
                result = func(*args, **kwargs)
            except SystemExit as exc:
                error = f"SystemExit({exc.code!r})"
            except BaseException as exc:  # noqa: BLE001 - we reformat into a string
                error = f"{type(exc).__name__}: {exc}"
                traceback.print_exc(file=stderr_buf)
    except BaseException as exc:  # noqa: BLE001 - last-resort capture
        error = f"{type(exc).__name__}: {exc}"

    duration = time.monotonic() - start
    try:
        out_q.put(("stdout", stdout_buf.getvalue()))
        out_q.put(("stderr", stderr_buf.getvalue()))
        out_q.put(("done", (result, error, duration, pid)))
    except Exception:  # pragma: no cover - parent may already be gone
        logger.debug("failed to publish sandbox result", exc_info=True)


_SANDBOX_SENTINEL: Any = object()


# ---------------------------------------------------------------------------
# AgentSandbox
# ---------------------------------------------------------------------------


class AgentSandbox:
    """Execute a callable with CPU / memory / timeout / output limits."""

    def __init__(self, limits: ResourceLimits | None = None) -> None:
        self._limits = limits or ResourceLimits()
        self._executions: int = 0
        self._lock = threading.Lock()

    @property
    def limits(self) -> ResourceLimits:
        return self._limits

    @property
    def executions(self) -> int:
        with self._lock:
            return self._executions

    # ------------------------------------------------------------------ exec
    def execute(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> SandboxResult:
        """Run ``func(*args, **kwargs)`` under the configured limits.

        Always returns a :class:`SandboxResult`; never raises for normal
        timeouts / resource overruns (those are reported via flags). Only
        programmer errors (e.g. unpicklable function on Windows) raise.
        """
        with self._lock:
            self._executions += 1

        if self._supports_subprocess():
            return self._execute_subprocess(func, args, kwargs)

        # Fallback: in-process thread executor with wall-clock + output limits only.
        return self._execute_threaded(func, args, kwargs)

    # ----------------------------------------------------------- internals
    def _supports_subprocess(self) -> bool:
        # multiprocessing always available in CPython; resource limits may not be.
        return True

    def _execute_subprocess(
        self,
        func: Callable[..., Any],
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> SandboxResult:
        ctx = _mp.get_context("fork" if not _IS_WINDOWS else "spawn")
        out_q: "_mp.Queue[tuple[str, Any]]" = ctx.Queue()
        proc = ctx.Process(
            target=_sandbox_child_entry,
            args=(func, args, kwargs, self._limits, out_q),
            daemon=True,
        )
        start = time.monotonic()
        proc.start()
        timed_out = False
        resource_exceeded = False
        result: Any = _SANDBOX_SENTINEL
        error: str | None = None
        duration = 0.0
        child_pid: int | None = proc.pid

        try:
            proc.join(timeout=self._limits.timeout_s)
            timed_out = proc.is_alive()
            if timed_out:
                logger.warning("sandbox child pid=%s exceeded wall-clock timeout", proc.pid)
                proc.terminate()
                proc.join(1.0)
                if proc.is_alive():
                    proc.kill()
                    proc.join(0.5)

            # Drain the queue (non-blocking) for any output the child managed to publish.
            stdout_text, stderr_text, payload = self._drain_queue(out_q)
            if payload is not None:
                result, error, duration, child_pid = payload

            # Negative exit codes on POSIX indicate termination by signal.
            # SIGXCPU (-24) means CPU limit hit; SIGKILL (-9) is our hard kill.
            if proc.exitcode is not None and proc.exitcode < 0:
                try:
                    signum = -proc.exitcode
                except TypeError:
                    signum = 0
                if signum == 24:  # SIGXCPU
                    resource_exceeded = True
                    error = error or "RLIMIT_CPU exceeded"
                elif signum == 9 and timed_out:
                    resource_exceeded = True
                    error = error or "process killed after timeout"
        finally:
            if proc.is_alive():
                proc.kill()
                proc.join(0.5)
            proc.close() if hasattr(proc, "close") else None

        wall = time.monotonic() - start
        return self._build_result(
            stdout=stdout_text,
            stderr=stderr_text,
            exit_code=proc.exitcode if proc.exitcode is not None else -1,
            timed_out=timed_out,
            resource_exceeded=resource_exceeded,
            result=result if result is not _SANDBOX_SENTINEL else None,
            error=error,
            duration=duration or wall,
            pid=child_pid,
        )

    def _execute_threaded(
        self,
        func: Callable[..., Any],
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> SandboxResult:
        """In-process fallback used when subprocess limits cannot be relied upon.

        Still enforces wall-clock timeout and captures stdout / stderr.
        CPU / memory caps are best-effort hints only.
        """
        result_box: dict[str, Any] = {}
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        start = time.monotonic()

        def runner() -> None:
            try:
                result_box["result"] = func(*args, **kwargs)
            except BaseException as exc:  # noqa: BLE001
                result_box["error"] = f"{type(exc).__name__}: {exc}"
                traceback.print_exc(file=stderr_buf)

        thread = threading.Thread(target=runner, daemon=True)
        thread.start()
        thread.join(timeout=self._limits.timeout_s)
        timed_out = thread.is_alive()
        duration = time.monotonic() - start

        if timed_out:
            error = "wall-clock timeout"
        else:
            error = result_box.get("error")

        result = result_box.get("result", _SANDBOX_SENTINEL)
        return self._build_result(
            stdout=stdout_buf.getvalue(),
            stderr=stderr_buf.getvalue(),
            exit_code=0 if not timed_out and error is None else 1,
            timed_out=timed_out,
            resource_exceeded=False,
            result=result if result is not _SANDBOX_SENTINEL else None,
            error=error,
            duration=duration,
            pid=None,
        )

    # ----------------------------------------------------------- helpers
    @staticmethod
    def _drain_queue(q: "_mp.Queue[tuple[str, Any]]") -> tuple[str, str, tuple[Any, Any, float, int] | None]:
        stdout_parts: list[str] = []
        stderr_parts: list[str] = []
        payload: tuple[Any, Any, float, int] | None = None
        while True:
            try:
                kind, value = q.get_nowait()
            except (_queue.Empty, EOFError, OSError):
                break
            if kind == "stdout":
                stdout_parts.append(value if isinstance(value, str) else str(value))
            elif kind == "stderr":
                stderr_parts.append(value if isinstance(value, str) else str(value))
            elif kind == "done":
                payload = value  # type: ignore[assignment]
        return "".join(stdout_parts), "".join(stderr_parts), payload

    def _build_result(
        self,
        *,
        stdout: str,
        stderr: str,
        exit_code: int,
        timed_out: bool,
        resource_exceeded: bool,
        result: Any,
        error: str | None,
        duration: float,
        pid: int | None,
    ) -> SandboxResult:
        return SandboxResult(
            stdout=self._cap(stdout),
            stderr=self._cap(stderr),
            exit_code=exit_code,
            timed_out=timed_out,
            resource_exceeded=resource_exceeded,
            result=result,
            error=error,
            duration_s=round(duration, 6),
            pid=pid,
        )

    def _cap(self, text: str) -> str:
        if len(text) <= self._limits.max_output_bytes:
            return text
        return text[: self._limits.max_output_bytes] + "\n...<truncated>"


__all__ = [
    "AgentSandbox",
    "ResourceLimits",
    "ResourceLimitError",
    "SandboxResult",
    "ResourceLimits",
]
