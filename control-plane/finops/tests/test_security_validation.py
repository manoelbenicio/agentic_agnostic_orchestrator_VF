from __future__ import annotations

from finops.repository import FinOpsRepository


def test_rollup_dimension_rejects_sql_payload_before_db_access():
    repo = FinOpsRepository(conn=None)  # type: ignore[arg-type]

    malicious = "agent_id); DROP TABLE finops_cost_records; --"
    try:
        repo.rollup_by_dimension("tenant-dim", "project-dim", malicious)
    except ValueError as exc:
        assert "unsupported rollup dimension" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError for SQL injection dimension")
