import json
from datetime import datetime, timezone
from typing import List, Optional, Any, Dict

import asyncpg
from pydantic import BaseModel, Field

class ProvisioningRecord(BaseModel):
    """
    Pydantic model representing a provisioning request.
    """
    id: str = Field(..., description="Unique ID for the provisioning request")
    tenant_id: str = Field(..., description="ID of the tenant requesting provisioning")
    status: str = Field(..., description="Current status (e.g., PENDING, IN_PROGRESS, SUCCESS, FAILED)")
    resource_type: str = Field(..., description="Type of resource (e.g., 'database', 'llm_endpoint')")
    resource_config: Dict[str, Any] = Field(default_factory=dict, description="Configuration parameters for the resource")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class ProvisioningRepository:
    """
    Repository for managing ProvisioningRecord persistence using asyncpg connection pooling.
    """
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    def _parse_row(self, row: asyncpg.Record) -> ProvisioningRecord:
        """
        Helper method to deserialize an asyncpg Record into a Pydantic model.
        """
        resource_config = row['resource_config']
        # asyncpg returns JSON/JSONB as strings unless custom type codecs are configured on the pool
        if isinstance(resource_config, str):
            resource_config = json.loads(resource_config)
            
        return ProvisioningRecord(
            id=row['id'],
            tenant_id=row['tenant_id'],
            status=row['status'],
            resource_type=row['resource_type'],
            resource_config=resource_config,
            created_at=row['created_at'],
            updated_at=row['updated_at']
        )

    async def create_provisioning_request(self, record: ProvisioningRecord) -> ProvisioningRecord:
        """
        Create a new provisioning request in the database.
        """
        query = """
            INSERT INTO provisioning_requests (
                id, tenant_id, status, resource_type, resource_config, created_at, updated_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING id, tenant_id, status, resource_type, resource_config, created_at, updated_at
        """
        async with self.pool.acquire() as conn:
            # Serialize the configuration dictionary to a JSON string
            config_json = json.dumps(record.resource_config)
            row = await conn.fetchrow(
                query,
                record.id,
                record.tenant_id,
                record.status,
                record.resource_type,
                config_json,
                record.created_at,
                record.updated_at
            )
            return self._parse_row(row)

    async def get_provisioning_request(self, request_id: str) -> Optional[ProvisioningRecord]:
        """
        Retrieve a single provisioning request by its ID.
        """
        query = """
            SELECT id, tenant_id, status, resource_type, resource_config, created_at, updated_at
            FROM provisioning_requests
            WHERE id = $1
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, request_id)
            if row:
                return self._parse_row(row)
            return None

    async def list_provisioning_requests(
        self, tenant_id: Optional[str] = None, limit: int = 50, offset: int = 0
    ) -> List[ProvisioningRecord]:
        """
        List provisioning requests with pagination and optional tenant filtering.
        """
        if tenant_id:
            query = """
                SELECT id, tenant_id, status, resource_type, resource_config, created_at, updated_at
                FROM provisioning_requests
                WHERE tenant_id = $1
                ORDER BY created_at DESC
                LIMIT $2 OFFSET $3
            """
            args = (tenant_id, limit, offset)
        else:
            query = """
                SELECT id, tenant_id, status, resource_type, resource_config, created_at, updated_at
                FROM provisioning_requests
                ORDER BY created_at DESC
                LIMIT $1 OFFSET $2
            """
            args = (limit, offset)

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, *args)
            return [self._parse_row(row) for row in rows]

    async def update_provisioning_status(self, request_id: str, new_status: str) -> Optional[ProvisioningRecord]:
        """
        Update the status of an existing provisioning request.
        """
        query = """
            UPDATE provisioning_requests
            SET status = $2, updated_at = $3
            WHERE id = $1
            RETURNING id, tenant_id, status, resource_type, resource_config, created_at, updated_at
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, request_id, new_status, datetime.now(timezone.utc))
            if row:
                return self._parse_row(row)
            return None

    async def delete_provisioning_request(self, request_id: str) -> bool:
        """
        Delete a provisioning request. Returns True if a record was actually deleted.
        """
        query = "DELETE FROM provisioning_requests WHERE id = $1"
        async with self.pool.acquire() as conn:
            result = await conn.execute(query, request_id)
            # asyncpg execute returns a status tag like "DELETE 1" or "DELETE 0"
            if result.startswith("DELETE "):
                try:
                    count = int(result.split(" ")[1])
                    return count > 0
                except ValueError:
                    return False
            return False
