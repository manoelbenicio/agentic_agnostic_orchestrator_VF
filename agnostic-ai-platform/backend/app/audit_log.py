import logging
import json
from datetime import datetime
from typing import Optional, List, Any
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, Query

# Configure structured logger for audit logs
audit_logger = logging.getLogger("audit")
audit_logger.setLevel(logging.INFO)

# Router for the audit endpoints
router = APIRouter(prefix="/audit", tags=["audit"])

# --- Models ---
class AuditEntry(BaseModel):
    """
    Represents an audit log entry for LLM API calls and actions.
    """
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    user_id: str
    tenant_id: str
    action: str
    model: Optional[str] = None
    tokens: Optional[int] = 0
    cost: Optional[float] = 0.0
    ip: Optional[str] = None
    status: str

# --- Mock DB Layer ---
# In a production app, this would interact with SQLAlchemy, Tortoise ORM, or similar.
class AuditDatabaseMock:
    async def insert(self, entry: AuditEntry):
        # Mock database insertion
        pass
        
    async def fetch(self, tenant_id: Optional[str], skip: int, limit: int) -> List[AuditEntry]:
        # Mock database fetch with filtering and pagination
        return []

async def get_db():
    return AuditDatabaseMock()

# --- Functions ---
async def log_audit(entry: AuditEntry, db: Any = None):
    """
    Writes the audit entry to both a structured log (JSON) and the database table.
    """
    # 1. Write to structured log
    log_dict = entry.model_dump(mode='json')
    audit_logger.info(json.dumps(log_dict))
    
    # 2. Write to database table
    # Typically you would inject the DB session into the function,
    # but falling back to a new DB instance if not provided for convenience.
    if db is None:
        db = AuditDatabaseMock()
    await db.insert(entry)

# --- Endpoints ---
@router.get("/logs", response_model=List[AuditEntry])
async def get_audit_logs(
    tenant_id: Optional[str] = Query(None, description="Filter audit logs by tenant ID"),
    skip: int = Query(0, ge=0, description="Pagination skip (offset)"),
    limit: int = Query(50, ge=1, le=1000, description="Pagination limit"),
    db: Any = Depends(get_db)
):
    """
    Retrieve audit logs with optional tenant filtering and pagination.
    In a real implementation, you would also use the `require_permission` 
    dependency here to restrict access.
    """
    logs = await db.fetch(tenant_id=tenant_id, skip=skip, limit=limit)
    return logs
