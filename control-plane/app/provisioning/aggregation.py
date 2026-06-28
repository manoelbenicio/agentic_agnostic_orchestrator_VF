import asyncpg
from typing import Dict, List, Any

class DashboardAggregator:
    """
    Service for executing analytical and aggregation queries on provisioning data.
    All methods return native Python dictionaries or lists of dictionaries suitable 
    for JSON serialization and immediate frontend chart rendering.
    """
    
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def count_by_status(self) -> List[Dict[str, Any]]:
        """
        Groups provisioning requests by their current status.
        Chart Target: Pie Chart, Donut Chart
        """
        query = """
            SELECT status, COUNT(*) as count
            FROM provisioning_requests
            GROUP BY status
            ORDER BY count DESC
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query)
            return [{"status": row["status"], "count": row["count"]} for row in rows]

    async def count_by_tenant(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Groups provisioning requests by tenant ID, returning the top N tenants by volume.
        Chart Target: Bar Chart, Leaderboard
        """
        query = """
            SELECT tenant_id, COUNT(*) as count
            FROM provisioning_requests
            GROUP BY tenant_id
            ORDER BY count DESC
            LIMIT $1
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, limit)
            return [{"tenant_id": row["tenant_id"], "count": row["count"]} for row in rows]

    async def daily_activation_trend(self, days: int = 30) -> List[Dict[str, Any]]:
        """
        Daily trend of provisioning activations over the last N days.
        Chart Target: Line Chart, Area Chart
        """
        query = """
            SELECT DATE(created_at) as date, COUNT(*) as count
            FROM provisioning_requests
            WHERE created_at >= CURRENT_DATE - ($1::int * INTERVAL '1 day')
            GROUP BY DATE(created_at)
            ORDER BY date ASC
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, days)
            return [
                {
                    "date": row["date"].isoformat() if row["date"] else None,
                    "count": row["count"]
                }
                for row in rows
            ]

    async def average_activation_duration(self) -> Dict[str, Any]:
        """
        Calculates the average duration from creation to success for provisioned resources.
        Chart Target: KPI Scorecard / Big Number Chart
        """
        query = """
            SELECT AVG(EXTRACT(EPOCH FROM (updated_at - created_at))) as avg_seconds
            FROM provisioning_requests
            WHERE status = 'SUCCESS'
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query)
            avg_seconds = row["avg_seconds"] if row["avg_seconds"] is not None else 0.0
            return {
                "average_duration_seconds": float(avg_seconds),
                "formatted": f"{float(avg_seconds):.2f}s"
            }

    async def failure_rate_by_step(self) -> List[Dict[str, Any]]:
        """
        Aggregates failures grouped by the specific orchestration step they failed on.
        Assumes `failed_step` is stored dynamically in the `resource_config` JSONB column.
        Chart Target: Funnel Chart, Horizontal Bar Chart
        """
        query = """
            SELECT resource_config->>'failed_step' as step, COUNT(*) as count
            FROM provisioning_requests
            WHERE status = 'FAILED' AND resource_config->>'failed_step' IS NOT NULL
            GROUP BY step
            ORDER BY count DESC
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query)
            return [{"step": row["step"], "count": row["count"]} for row in rows]

    async def top_errors(self, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Identifies the most common error reasons causing provisioning failures.
        Assumes `error_message` is stored dynamically in the `resource_config` JSONB column.
        Chart Target: Data Table, Bar Chart
        """
        query = """
            SELECT resource_config->>'error_message' as error, COUNT(*) as count
            FROM provisioning_requests
            WHERE status = 'FAILED' AND resource_config->>'error_message' IS NOT NULL
            GROUP BY error
            ORDER BY count DESC
            LIMIT $1
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, limit)
            return [{"error": row["error"], "count": row["count"]} for row in rows]
