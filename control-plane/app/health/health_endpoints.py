import time
import asyncio
from typing import Dict, Any, Tuple
from fastapi import APIRouter, Response, status

class HealthService:
    """
    Service responsible for orchestrating platform-wide health checks 
    across all critical downstream dependencies.
    """
    
    async def check_database(self) -> Tuple[bool, float]:
        """Check PostgreSQL database connection viability and latency."""
        start = time.perf_counter()
        # Mocking an async DB ping
        await asyncio.sleep(0.01)
        latency = (time.perf_counter() - start) * 1000
        return True, latency

    async def check_redis(self) -> Tuple[bool, float]:
        """Check Redis caching connection viability and latency."""
        start = time.perf_counter()
        # Mocking an async Redis ping
        await asyncio.sleep(0.005)
        latency = (time.perf_counter() - start) * 1000
        return True, latency

    async def check_message_bus(self) -> Tuple[bool, float]:
        """Check Message Bus (Kafka/RabbitMQ) connection viability and latency."""
        start = time.perf_counter()
        # Mocking an async Message Bus ping
        await asyncio.sleep(0.015)
        latency = (time.perf_counter() - start) * 1000
        return True, latency

    async def check_adapters(self) -> Tuple[bool, float]:
        """Check aggregate LLM registry adapters health."""
        start = time.perf_counter()
        # Mocking adapter pool check
        await asyncio.sleep(0.02)
        latency = (time.perf_counter() - start) * 1000
        return True, latency

    async def run_all_checks(self) -> Dict[str, Any]:
        """
        Executes all component checks concurrently and aggregates the 
        results into a standardized report payload.
        """
        # Execute network bounds concurrently for fast resolution
        results = await asyncio.gather(
            self.check_database(),
            self.check_redis(),
            self.check_message_bus(),
            self.check_adapters(),
            return_exceptions=True
        )

        components = ["database", "redis", "message_bus", "adapters"]
        report: Dict[str, Any] = {}
        all_healthy = True

        for comp, res in zip(components, results):
            if isinstance(res, Exception):
                all_healthy = False
                report[comp] = {
                    "status": "unhealthy", 
                    "error": str(res), 
                    "latency_ms": None
                }
            else:
                is_healthy, latency = res
                if not is_healthy:
                    all_healthy = False
                report[comp] = {
                    "status": "healthy" if is_healthy else "unhealthy",
                    "latency_ms": round(latency, 2)
                }

        return {
            "status": "healthy" if all_healthy else "degraded",
            "components": report
        }


# --- API Routes ---

router = APIRouter(prefix="/health", tags=["health"])
health_service = HealthService()

@router.get("")
async def get_health(response: Response):
    """
    GET /health
    Provides a simple high-level boolean status of the platform.
    """
    report = await health_service.run_all_checks()
    if report["status"] != "healthy":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    
    return {"status": report["status"]}


@router.get("/detailed")
async def get_health_detailed(response: Response):
    """
    GET /health/detailed
    Provides granular component-level statuses equipped with connection latencies.
    """
    report = await health_service.run_all_checks()
    if report["status"] != "healthy":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        
    return report


@router.get("/ready")
async def get_health_ready(response: Response):
    """
    GET /health/ready
    Kubernetes Readiness Probe target. Dictates whether this pod should 
    receive traffic from the Service load balancer.
    """
    report = await health_service.run_all_checks()
    if report["status"] != "healthy":
        # Returning 503 drops the pod from the k8s load balancer pool safely
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"ready": False, "reason": "dependencies_unhealthy"}
        
    return {"ready": True}


@router.get("/live")
async def get_health_live():
    """
    GET /health/live
    Kubernetes Liveness Probe target. Dictates whether the pod's container 
    has fundamentally crashed/deadlocked and needs a hard restart.
    """
    # Liveness is intrinsically less strict; responding to HTTP means the event loop is alive.
    return {"live": True}
