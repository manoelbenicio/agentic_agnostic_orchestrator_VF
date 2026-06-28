"""Prometheus text export for tracing metrics."""

from __future__ import annotations

from .repository import TraceRepository


class TracingMetricsExporter:
    """Expose tracing/burn metrics through the existing Prometheus stack."""

    def __init__(self, repository: TraceRepository) -> None:
        self.repository = repository

    def burn_metrics(self) -> str:
        """Return per-agent and per-runtime burn metrics."""
        lines = [
            "# HELP aop_trace_token_burn_total Token burn by agent and runtime",
            "# TYPE aop_trace_token_burn_total counter",
        ]
        rows = self.repository.burn_by_agent_runtime()
        for row in rows:
            labels = f'agent_id="{row["agent_id"]}",runtime_id="{row["runtime_id"]}"'
            lines.append(f'aop_trace_token_burn_total{{{labels}}} {int(row["token_burn"] or 0)}')
        lines.extend(
            [
                "# HELP aop_trace_seat_seconds_total Seat seconds by agent and runtime",
                "# TYPE aop_trace_seat_seconds_total counter",
            ]
        )
        for row in rows:
            labels = f'agent_id="{row["agent_id"]}",runtime_id="{row["runtime_id"]}"'
            lines.append(f'aop_trace_seat_seconds_total{{{labels}}} {int(row["seat_seconds"] or 0)}')
        return "\n".join(lines) + "\n"
