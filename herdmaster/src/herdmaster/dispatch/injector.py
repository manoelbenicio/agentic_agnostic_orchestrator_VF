"""Reliable task prompt injection into Herdr agent panes."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
import shlex

from herdmaster.config import HerdMasterConfig
from herdmaster.db.repositories import AgentRepo, utc_now
from herdmaster.dispatch.queue import TERMINAL_STATES, TaskQueue
from herdmaster.herdr.adapter import HerdrAdapter, HerdrError


MAX_PROMPT_BYTES = 1_000_000  # 1 MB hard limit


@dataclass(frozen=True, slots=True)
class DispatchInjectorConfig:
    """Runtime knobs for raw keystroke injection and file fallback."""

    idle_timeout_s: int = 60
    max_chunk_chars: int = 700
    file_fallback_threshold_chars: int = 4000
    chunk_pace_s: float = 0.08
    retry_attempts: int = 3
    base_backoff_s: float = 1.0
    max_backoff_s: float = 30.0
    fallback_dir: Path = Path("~/.config/herdmaster/prompts").expanduser()

    @classmethod
    def from_herdmaster_config(
        cls,
        config: HerdMasterConfig,
        **overrides: object,
    ) -> "DispatchInjectorConfig":
        values = {"fallback_dir": config.paths.config_dir / "prompts"}
        values.update(overrides)
        return cls(**values)


@dataclass(frozen=True, slots=True)
class DispatchResult:
    """Outcome of a dispatch attempt."""

    task_id: str
    status: str
    attempts: int
    pane_id: str | None = None
    prompt_file: Path | None = None
    error: str | None = None


class DispatchError(RuntimeError):
    """Raised when dispatch cannot proceed safely."""


class AgentNotIdle(HerdrError):
    """Raised when Herdr cannot confirm that an agent is idle."""


class DispatchInjector:
    """Inject assigned tasks into Herdr panes only after the agent is idle."""

    def __init__(
        self,
        adapter: HerdrAdapter,
        queue: TaskQueue,
        agent_repo: AgentRepo,
        config: DispatchInjectorConfig | HerdMasterConfig | None = None,
    ) -> None:
        self.adapter = adapter
        self.queue = queue
        self.agent_repo = agent_repo
        if isinstance(config, HerdMasterConfig):
            self.config = DispatchInjectorConfig.from_herdmaster_config(config)
        else:
            self.config = config or DispatchInjectorConfig()

    async def dispatch(self, task: dict[str, object]) -> DispatchResult:
        """Dispatch one already-assigned task with idle gating and retries."""

        task_id = _required_text(task, "id")
        current = self.queue.task_repo.get(task_id)
        if current is None:
            raise KeyError(task_id)

        state = str(current.get("state") or "")
        if state in {"dispatched", "in_progress"} | TERMINAL_STATES:
            return DispatchResult(task_id=task_id, status="skipped", attempts=0)
        if state != "assigned":
            raise DispatchError(f"task {task_id!r} must be assigned before dispatch; got {state!r}")

        agent_id = _required_text(current, "assigned_to")
        prompt = _required_text(current, "prompt")
        pane_id: str | None = None

        for attempt in range(1, self.config.retry_attempts + 1):
            try:
                pane_id = pane_id or await self._resolve_pane_id(agent_id)
                await self._wait_idle(pane_id)
                prompt_file = await self._send_prompt(pane_id, task_id, prompt)
                self.queue.mark_dispatched(task_id)
                self.queue.mark_in_progress(task_id)
                return DispatchResult(
                    task_id=task_id,
                    status="in_progress",
                    attempts=attempt,
                    pane_id=pane_id,
                    prompt_file=prompt_file,
                )
            except AgentNotIdle as exc:
                if self._retry_count(task_id) >= self._max_retries(task_id):
                    self._mark_failed_from_current_state(task_id, str(exc))
                    return DispatchResult(
                        task_id=task_id,
                        status="failed",
                        attempts=attempt,
                        pane_id=pane_id,
                        error=str(exc),
                    )
                await self._backoff(attempt)
                self._requeue_for_later(task_id)
                return DispatchResult(
                    task_id=task_id,
                    status="requeued",
                    attempts=attempt,
                    pane_id=pane_id,
                    error=str(exc),
                )
            except HerdrError as exc:
                if attempt >= self.config.retry_attempts:
                    self._mark_failed_from_current_state(task_id, str(exc))
                    return DispatchResult(
                        task_id=task_id,
                        status="failed",
                        attempts=attempt,
                        pane_id=pane_id,
                        error=str(exc),
                    )
                await self._backoff(attempt)

        raise DispatchError(f"dispatch retry loop exited unexpectedly for task {task_id!r}")

    async def _resolve_pane_id(self, agent_id: str) -> str:
        stored = self.agent_repo.get(agent_id)
        pane_id = ""
        if stored is not None:
            pane_id = str(stored.get("herdr_pane") or "")
        if pane_id:
            return pane_id

        for agent in await self.adapter.agent_list():
            if agent.id == agent_id and agent.pane_id:
                return agent.pane_id
        raise HerdrError(f"agent {agent_id!r} has no resolvable Herdr pane")

    async def _wait_idle(self, pane_id: str) -> None:
        try:
            await self.adapter.agent_wait(
                pane_id,
                state="idle",
                timeout=self.config.idle_timeout_s,
            )
        except HerdrError as exc:
            raise AgentNotIdle(f"pane {pane_id!r} did not become idle: {exc}") from exc

    async def _send_prompt(self, pane_id: str, task_id: str, prompt: str) -> Path | None:
        if len(prompt) > self.config.file_fallback_threshold_chars:
            prompt_file = self._write_prompt_file(task_id, prompt)
            await self._send_file_fallback(pane_id, prompt_file)
            return prompt_file

        try:
            for chunk in _chunks(prompt, self.config.max_chunk_chars):
                await self.adapter.pane_send(pane_id, chunk)
                await asyncio.sleep(self.config.chunk_pace_s)
            await self.adapter.pane_send(pane_id, "\r")
            return None
        except HerdrError:
            prompt_file = self._write_prompt_file(task_id, prompt)
            await self._clear_current_input(pane_id)
            await self._send_file_fallback(pane_id, prompt_file)
            return prompt_file

    async def _send_file_fallback(self, pane_id: str, prompt_file: Path) -> None:
        command = (
            "Read and execute this HerdMaster task prompt: "
            f"{shlex.quote(str(prompt_file))}"
        )
        await self.adapter.pane_send(pane_id, command)
        await asyncio.sleep(self.config.chunk_pace_s)
        await self.adapter.pane_send(pane_id, "\r")

    async def _clear_current_input(self, pane_id: str) -> None:
        try:
            await self.adapter.pane_send(pane_id, "\x15")
            await asyncio.sleep(self.config.chunk_pace_s)
        except HerdrError:
            pass

    def _write_prompt_file(self, task_id: str, prompt: str) -> Path:
        prompt_size = len(prompt.encode())
        if prompt_size > MAX_PROMPT_BYTES:
            raise DispatchError(
                f"prompt exceeds {MAX_PROMPT_BYTES} bytes limit "
                f"({prompt_size} bytes)"
            )
        self.config.fallback_dir.mkdir(parents=True, exist_ok=True)
        prompt_file = self.config.fallback_dir / f"{_safe_filename(task_id)}.md"
        prompt_file.write_text(prompt, encoding="utf-8")
        return prompt_file

    def _mark_failed_from_current_state(self, task_id: str, error_message: str) -> None:
        task = self.queue.task_repo.get(task_id)
        if task is None:
            raise KeyError(task_id)
        state = str(task.get("state") or "")
        if state == "in_progress":
            self.queue.mark_failed(task_id, error_message)
            return
        if state == "dispatched":
            self.queue.mark_in_progress(task_id)
            self.queue.mark_failed(task_id, error_message)
            return
        if state == "assigned":
            self.queue.task_repo.conn.execute(
                """
                UPDATE tasks
                SET state = 'failed',
                    error_message = ?,
                    completed_at = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (error_message, utc_now(), task_id),
            )
            self.queue.task_repo.conn.commit()
            return
        if state not in TERMINAL_STATES:
            self.queue.task_repo.fail(task_id, error_message, state="failed")

    def _requeue_for_later(self, task_id: str) -> None:
        if not self.queue.task_repo.increment_retry(task_id):
            raise KeyError(task_id)
        self.queue.task_repo.conn.execute(
            """
            UPDATE tasks
            SET state = 'queued',
                assigned_to = NULL,
                dispatched_at = NULL,
                completed_at = NULL,
                error_message = NULL,
                version = version + 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (task_id,),
        )
        self.queue.task_repo.conn.commit()

    def _retry_count(self, task_id: str) -> int:
        task = self.queue.task_repo.get(task_id)
        if task is None:
            raise KeyError(task_id)
        return int(task.get("retry_count") or 0)

    def _max_retries(self, task_id: str) -> int:
        task = self.queue.task_repo.get(task_id)
        if task is None:
            raise KeyError(task_id)
        return int(task.get("max_retries") or 0)

    async def _backoff(self, attempt: int) -> None:
        delay = min(
            self.config.max_backoff_s,
            self.config.base_backoff_s * (2 ** (attempt - 1)),
        )
        await asyncio.sleep(delay)


def _chunks(value: str, max_chars: int) -> list[str]:
    if max_chars <= 0:
        raise ValueError("max_chunk_chars must be > 0")
    return [value[index:index + max_chars] for index in range(0, len(value), max_chars)] or [""]


def _required_text(task: dict[str, object], key: str) -> str:
    value = task.get(key)
    if value is None or value == "":
        raise DispatchError(f"task is missing required field {key!r}")
    return str(value)


def _safe_filename(value: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in value)
    return safe.strip("._") or "task"
