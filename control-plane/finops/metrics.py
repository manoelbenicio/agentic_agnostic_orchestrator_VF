"""Prometheus text export for FinOps metrics."""

from __future__ import annotations

from .repository import FinOpsRepository


class FinOpsMetricsExporter:
    """Expose FinOps metrics for the existing Prometheus stack to scrape."""

    def __init__(self, repository: FinOpsRepository) -> None:
        self.repository = repository

    def project_metrics(self, *, tenant_id: str, project_id: str) -> str:
        """Return Prometheus text for one tenant/project rollup."""
        rollup = self.repository.rollup_project(tenant_id, project_id)
        labels = f'tenant_id="{tenant_id}",project_id="{project_id}"'
        lines = [
            "# HELP aop_finops_project_cost_usd Project cost by engine",
            "# TYPE aop_finops_project_cost_usd gauge",
            f'aop_finops_project_cost_usd{{{labels},engine="total"}} {rollup.total_cost_usd}',
            f'aop_finops_project_cost_usd{{{labels},engine="token"}} {rollup.token_cost_usd}',
            f'aop_finops_project_cost_usd{{{labels},engine="seat"}} {rollup.seat_cost_usd}',
            "# HELP aop_finops_project_cost_records Cost record count",
            "# TYPE aop_finops_project_cost_records gauge",
            f"aop_finops_project_cost_records{{{labels}}} {rollup.record_count}",
        ]
        return "\n".join(lines) + "\n"

    @staticmethod
    def _escape(value: str) -> str:
        """Escape a Prometheus label value."""
        return value.replace("\\", "\\\\").replace('"', '\\"')

    def all_project_metrics(self) -> str:
        """Return Prometheus text for EVERY tenant/project plus per-model breakdown.

        Replaces the previously hard-coded ``tenant-a``/``project-a`` export with
        a dynamic scan of all tenants/projects that have cost records, and emits
        a ``aop_finops_model_cost_usd`` series labelled by model so Grafana can
        break cost down by model (OpenAI/Gemini/...). When there is no cost data
        the metric families are still declared (with HELP/TYPE) so the scrape is
        always well-formed.
        """
        cost_lines = [
            "# HELP aop_finops_project_cost_usd Project cost by engine",
            "# TYPE aop_finops_project_cost_usd gauge",
        ]
        record_lines = [
            "# HELP aop_finops_project_cost_records Cost record count",
            "# TYPE aop_finops_project_cost_records gauge",
        ]
        model_lines = [
            "# HELP aop_finops_model_cost_usd Project cost broken down by model",
            "# TYPE aop_finops_model_cost_usd gauge",
        ]
        vendor_lines = [
            "# HELP aop_finops_vendor_cost_usd Project cost broken down by vendor",
            "# TYPE aop_finops_vendor_cost_usd gauge",
        ]
        for tenant_id, project_id in self.repository.list_projects():
            t = self._escape(tenant_id)
            p = self._escape(project_id)
            labels = f'tenant_id="{t}",project_id="{p}"'
            rollup = self.repository.rollup_project(tenant_id, project_id)
            cost_lines.append(f'aop_finops_project_cost_usd{{{labels},engine="total"}} {rollup.total_cost_usd}')
            cost_lines.append(f'aop_finops_project_cost_usd{{{labels},engine="token"}} {rollup.token_cost_usd}')
            cost_lines.append(f'aop_finops_project_cost_usd{{{labels},engine="seat"}} {rollup.seat_cost_usd}')
            record_lines.append(f"aop_finops_project_cost_records{{{labels}}} {rollup.record_count}")
            for bucket in self.repository.rollup_by_dimension(tenant_id, project_id, "model"):
                model = self._escape(bucket.key)
                model_lines.append(
                    f'aop_finops_model_cost_usd{{{labels},model="{model}"}} {bucket.total_cost_usd}'
                )
            for bucket in self.repository.rollup_by_dimension(tenant_id, project_id, "vendor"):
                vendor = self._escape(bucket.key)
                vendor_lines.append(
                    f'aop_finops_vendor_cost_usd{{{labels},vendor="{vendor}"}} {bucket.total_cost_usd}'
                )
        return "\n".join(cost_lines + record_lines + model_lines + vendor_lines) + "\n"
