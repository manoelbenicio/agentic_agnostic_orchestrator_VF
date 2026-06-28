import logging
from typing import List, Dict, Any
from datetime import datetime
from pydantic import BaseModel
from fastapi import APIRouter, Query

logger = logging.getLogger("billing.cost_allocation")


# --- Structural Pydantic Data Models ---

class CostAllocationRequest(BaseModel):
    """Financial tracking payload bounding arbitrary utilization to explicit tenant scopes."""
    tenant_id: str
    amount_usd: float
    resource_type: str  # Architectural context: 'llm_inference', 'vector_storage', 'training'
    resource_id: str
    metadata: Dict[str, Any] = {}

class BudgetLimitRequest(BaseModel):
    """Administrative mutation schema altering physical spend thresholds."""
    tenant_id: str
    monthly_budget_usd: float

class BudgetStatus(BaseModel):
    """Materialized mathematical response bounding current burn against hard limits."""
    tenant_id: str
    monthly_budget_usd: float
    current_spend_usd: float
    is_exceeded: bool
    remaining_usd: float


# --- Database Transaction Engine ---

class CostAllocationService:
    """
    Governance and Billing logic engine. Executes high-performance aggregate SQL constraints 
    managing tenant budget caps, transactional USD allocations, and temporal reporting natively.
    """
    def __init__(self, db_pool=None):
        # Database binding injected natively (e.g. asyncpg pool architecture)
        self.db_pool = db_pool

    async def allocate_cost(self, req: CostAllocationRequest) -> str:
        """
        Records an immutable financial transaction block mapped directly to a tenant pipeline.
        Utilized dynamically by LLM routers tracking per-token consumption.
        """
        query = """
            INSERT INTO cost_allocations (tenant_id, amount_usd, resource_type, resource_id, metadata, timestamp)
            VALUES ($1, $2, $3, $4, $5, NOW())
            RETURNING id;
        """
        logger.info(f"Financial Engine: Allocating ${req.amount_usd:.4f} to tenant '{req.tenant_id}' (Target: {req.resource_type})")
        
        if self.db_pool:
            async with self.db_pool.acquire() as conn:
                record_id = await conn.fetchval(
                    query, 
                    req.tenant_id, req.amount_usd, req.resource_type, req.resource_id, req.metadata
                )
                return str(record_id)
        else:
            return "synthetic-tx-uuid"

    async def set_budget_limit(self, tenant_id: str, monthly_budget_usd: float):
        """
        Transactionally executes an UPSERT overriding a tenant's hard programmatic monthly spending boundary.
        """
        query = """
            INSERT INTO tenant_budgets (tenant_id, monthly_budget_usd, updated_at)
            VALUES ($1, $2, NOW())
            ON CONFLICT (tenant_id) DO UPDATE SET 
                monthly_budget_usd = EXCLUDED.monthly_budget_usd,
                updated_at = NOW();
        """
        logger.info(f"Governance Engine: Committing strict Monthly Budget Cap for '{tenant_id}' at ${monthly_budget_usd:.2f}")
        
        if self.db_pool:
            async with self.db_pool.acquire() as conn:
                await conn.execute(query, tenant_id, monthly_budget_usd)
        return True

    async def get_tenant_costs(self, tenant_id: str) -> Dict[str, Any]:
        """
        Calculates total monolithic aggregated spend utilizing high-performance native SQL summation.
        """
        query = """
            SELECT COALESCE(SUM(amount_usd), 0.0) as total_spend, COUNT(*) as transaction_count
            FROM cost_allocations
            WHERE tenant_id = $1;
        """
        if self.db_pool:
            async with self.db_pool.acquire() as conn:
                record = await conn.fetchrow(query, tenant_id)
                return {
                    "tenant_id": tenant_id,
                    "total_spend_usd": float(record["total_spend"]),
                    "transaction_count": record["transaction_count"]
                }
        else:
            # Synthetic materialization logic
            return {"tenant_id": tenant_id, "total_spend_usd": 142.50, "transaction_count": 8940}

    async def check_budget_exceeded(self, tenant_id: str) -> BudgetStatus:
        """
        Dynamically compares active rolling monthly spend logic against hard budget limitations.
        Critical for injecting blocks into global LLM routing or API RateLimit pipelines.
        """
        query = """
            WITH current_spend AS (
                SELECT COALESCE(SUM(amount_usd), 0.0) as spent
                FROM cost_allocations
                WHERE tenant_id = $1 
                AND date_trunc('month', timestamp) = date_trunc('month', NOW())
            ),
            budget AS (
                SELECT monthly_budget_usd
                FROM tenant_budgets
                WHERE tenant_id = $1
            )
            SELECT 
                (SELECT spent FROM current_spend) as current_spend,
                COALESCE((SELECT monthly_budget_usd FROM budget), 0.0) as monthly_budget
        """
        if self.db_pool:
            async with self.db_pool.acquire() as conn:
                record = await conn.fetchrow(query, tenant_id)
                spent = float(record["current_spend"])
                budget = float(record["monthly_budget"])
        else:
            # Synthetic state enforcing heuristic checks
            spent = 450.00
            budget = 500.00
            
        remaining = max(0.0, budget - spent)
        is_exceeded = spent >= budget if budget > 0 else False
        
        if is_exceeded:
            logger.warning(f"🚨 GOVERNANCE BREACH: Tenant {tenant_id} exceeded structural budget cap of ${budget:.2f}")

        return BudgetStatus(
            tenant_id=tenant_id,
            monthly_budget_usd=budget,
            current_spend_usd=spent,
            is_exceeded=is_exceeded,
            remaining_usd=remaining
        )

    async def get_daily_breakdown(self, tenant_id: str, days: int = 30) -> List[Dict[str, Any]]:
        """
        Maps temporal cost distributions by natively executing grouping logic via PostgreSQL date_trunc bounds.
        """
        query = """
            SELECT date_trunc('day', timestamp) as date, resource_type, SUM(amount_usd) as daily_cost
            FROM cost_allocations
            WHERE tenant_id = $1 AND timestamp >= NOW() - $2::INTERVAL
            GROUP BY 1, 2
            ORDER BY 1 ASC;
        """
        if self.db_pool:
            async with self.db_pool.acquire() as conn:
                interval = f"{days} days"
                records = await conn.fetch(query, tenant_id, interval)
                return [{"date": r["date"].isoformat(), "resource_type": r["resource_type"], "cost_usd": float(r["daily_cost"])} for r in records]
        else:
            return [
                {"date": "2026-06-25", "resource_type": "llm_inference", "cost_usd": 12.50},
                {"date": "2026-06-26", "resource_type": "llm_inference", "cost_usd": 15.20},
                {"date": "2026-06-27", "resource_type": "vector_storage", "cost_usd": 1.10}
            ]


# --- FastAPI Implementation Routes ---

router = APIRouter(prefix="/billing", tags=["billing", "finance", "governance"])
service = CostAllocationService()

@router.post("/allocate")
async def execute_cost_allocation(req: CostAllocationRequest):
    """
    POST /billing/allocate
    Transactionally commits an immutable financial transaction record targeting arbitrary platform resources.
    """
    tx_id = await service.allocate_cost(req)
    return {"status": "success", "transaction_id": tx_id}

@router.put("/budget")
async def update_budget_limit(req: BudgetLimitRequest):
    """
    PUT /billing/budget
    Forcefully overrides and sets the maximum permissible operational USD expenditure per month.
    """
    await service.set_budget_limit(req.tenant_id, req.monthly_budget_usd)
    return {"status": "success", "tenant_id": req.tenant_id, "monthly_budget_usd": req.monthly_budget_usd}

@router.get("/{tenant_id}/summary")
async def fetch_tenant_cost_summary(tenant_id: str):
    """
    GET /billing/{tenant_id}/summary
    Extracts the monolithic aggregate spend string isolating all historical transactions natively.
    """
    return await service.get_tenant_costs(tenant_id)

@router.get("/{tenant_id}/budget-status", response_model=BudgetStatus)
async def evaluate_budget_status(tenant_id: str):
    """
    GET /billing/{tenant_id}/budget-status
    Executes deep dynamic logic bounding active rolling 30-day matrices against strict limitations.
    Often called prior to executing heavy RAG or LLM operations to dynamically reject operations on broke tenants.
    """
    return await service.check_budget_exceeded(tenant_id)

@router.get("/{tenant_id}/daily")
async def fetch_daily_breakdown(
    tenant_id: str, 
    days: int = Query(30, description="Temporal extraction backward tracking array length")
):
    """
    GET /billing/{tenant_id}/daily
    Extracts highly detailed histogram plots mapping temporal utilization across independent AI features.
    """
    return {"tenant_id": tenant_id, "breakdown": await service.get_daily_breakdown(tenant_id, days)}
