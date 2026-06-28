from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from .failure_handler import ActivationFailure, list_activation_failures, retry_activation
from .repository import ProvisioningRecord, ProvisioningRepository
from .websocket import broadcast_provisioning_event

router = APIRouter(prefix="/provisioning", tags=["provisioning"])

# Dummy dependency to get the repository 
# In a real app this would likely come from app state or a broader dependency tree
async def get_provisioning_repository() -> ProvisioningRepository:
    raise NotImplementedError("Dependency not wired to an actual DB pool yet")

class ProvisioningRequestCreate(BaseModel):
    id: str
    tenant_id: str
    resource_type: str
    resource_config: dict

@router.post("/requests", response_model=ProvisioningRecord)
async def create_provisioning_request(
    request: ProvisioningRequestCreate,
    repo: ProvisioningRepository = Depends(get_provisioning_repository)
):
    record = ProvisioningRecord(
        id=request.id,
        tenant_id=request.tenant_id,
        status="PENDING",
        resource_type=request.resource_type,
        resource_config=request.resource_config
    )
    created = await repo.create_provisioning_request(record)
    await broadcast_provisioning_event(
        "new_request",
        {"request_id": created.id, "tenant_id": created.tenant_id, "status": created.status},
    )
    return created

@router.get("/requests", response_model=List[ProvisioningRecord])
async def list_provisioning_requests(
    tenant_id: Optional[str] = Query(None, description="Filter by tenant ID"),
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    repo: ProvisioningRepository = Depends(get_provisioning_repository)
):
    # Retrieve base records
    records = await repo.list_provisioning_requests(tenant_id=tenant_id, limit=limit, offset=offset)
    
    # Filter by status if provided (in production this would be pushed down to the DB query)
    if status:
        records = [r for r in records if r.status == status]
        
    return records

@router.get("/requests/{id}", response_model=ProvisioningRecord)
async def get_provisioning_request(
    id: str,
    repo: ProvisioningRepository = Depends(get_provisioning_repository)
):
    record = await repo.get_provisioning_request(id)
    if not record:
        raise HTTPException(status_code=404, detail="Provisioning request not found")
    return record

@router.post("/requests/{id}/activate")
async def activate_provisioning_request(
    id: str,
    repo: ProvisioningRepository = Depends(get_provisioning_repository)
):
    """
    Triggers the activation orchestration for a pending provisioning request.
    """
    record = await repo.update_provisioning_status(id, "ACTIVATING")
    if not record:
        raise HTTPException(status_code=404, detail="Provisioning request not found")
    await broadcast_provisioning_event(
        "activation_started",
        {"request_id": record.id, "tenant_id": record.tenant_id, "status": record.status},
    )
    
    # Placeholder for actual activation orchestration logic
    return {"status": "activation_triggered", "record": record}

@router.get("/failures", response_model=List[ActivationFailure])
async def list_provisioning_failures(
    request: Request,
    tenant_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """
    List failed activations.
    """
    state = getattr(request.app.state, "container", None)
    if state is None:
        raise HTTPException(status_code=503, detail="Application state is not available.")
    try:
        failures = list_activation_failures(state, limit=limit + offset)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if tenant_id:
        failures = [failure for failure in failures if failure.metadata.get("tenant_id") == tenant_id]
    return failures[offset : offset + limit]

@router.post("/failures/{id}/retry")
async def retry_provisioning_failure(
    id: str,
    request: Request,
):
    """
    Retry a failed activation from its last successful step.
    """
    state = getattr(request.app.state, "container", None)
    if state is None:
        raise HTTPException(status_code=503, detail="Application state is not available.")
    try:
        result = retry_activation(id, state)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "retry_triggered", "record": result}
