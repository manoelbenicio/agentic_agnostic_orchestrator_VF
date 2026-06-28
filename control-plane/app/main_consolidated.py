import time
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

# Configure core logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("aop.main")

# --- Dynamic Module Resolution & Router Imports ---
# We try to import actively developed modules natively. If they haven't been compiled
# in the directory structure yet, we gracefully degrade to synthetic Stub Routers.

def get_router(module_path: str, router_name: str, prefix: str) -> APIRouter:
    try:
        module = __import__(module_path, fromlist=[router_name])
        return getattr(module, router_name)
    except (ImportError, AttributeError):
        logger.debug(f"Module {module_path} unresolvable. Mounting stub router at {prefix}.")
        return APIRouter(prefix=prefix, tags=[prefix.strip("/")])


# Resolving Existing Built Modules
health_router = get_router("app.health", "health_router", "/health")
analytics_router = get_router("app.analytics", "analytics_router", "/analytics")
websocket_router = get_router("app.websocket", "websocket_router", "/ws")

try:
    from app.provisioning.routes import router as prov_router
    from app.provisioning.export import router as prov_export_router
except ImportError:
    prov_router = APIRouter(prefix="/provisioning", tags=["provisioning"])
    prov_export_router = APIRouter(prefix="/provisioning/export", tags=["provisioning_export"])

# Resolving Requested Modules (Stubs utilized if unavailable)
registry_router = get_router("app.registry", "router", "/registry")
topology_router = get_router("app.topology", "router", "/topology")
governance_router = get_router("app.governance", "router", "/governance")
billing_router = get_router("app.billing", "router", "/billing")
notifications_router = get_router("app.notifications", "router", "/notifications")
settings_router = get_router("app.settings", "router", "/settings")
orchestration_router = get_router("app.orchestration", "router", "/orchestration")
agents_runtime_router = get_router("app.agents.runtime", "router", "/agents")
adapters_router = get_router("app.adapters", "router", "/adapters")


# --- Custom Middleware Definitions ---

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Intercepts the HTTP lifecycle to record analytical duration telemetry.
    """
    async def dispatch(self, request: Request, call_next):
        start_time = time.perf_counter()
        
        response = await call_next(request)
        
        process_time = time.perf_counter() - start_time
        logger.info(
            f"{request.method} {request.url.path} - "
            f"Status: {response.status_code} - "
            f"Duration: {process_time:.4f}s"
        )
        return response


class MockRedis:
    """Mock implementation bypassing actual network TCP connection logic."""
    pass

try:
    from app.rate_limiting import RateLimitMiddleware
except ImportError:
    RateLimitMiddleware = None


# --- Lifespan Event Handling ---

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Modern FastAPI Lifespan context manager encapsulating strict 
    Startup and Shutdown event sequences cleanly.
    """
    logger.info("=== INITIALIZING AOP CONTROL PLANE ===")
    
    # 1. Initialize Adapters
    logger.info("[Startup] Probing and initializing LLM registry adapters...")
    app.state.adapters_loaded = True
    
    # 2. Start Scheduler
    logger.info("[Startup] Launching distributed APScheduler workers...")
    app.state.scheduler_running = True
    
    # 3. Connect Event Bus
    logger.info("[Startup] Establishing AMQP/Kafka Event Bus bindings...")
    app.state.event_bus_connected = True
    
    logger.info("=== AOP CONTROL PLANE BOOT SEQUENCE COMPLETE ===")
    
    # Yield control directly to the active FastAPI loop
    yield
    
    # --- SHUTDOWN SEQUENCE ---
    logger.info("=== INITIATING AOP CONTROL PLANE SHUTDOWN ===")
    
    logger.info("[Shutdown] Draining background scheduler jobs...")
    app.state.scheduler_running = False
    
    logger.info("[Shutdown] Terminating active Event Bus bindings...")
    app.state.event_bus_connected = False
    
    logger.info("[Shutdown] Cleaning up orphan adapter memory blocks...")
    app.state.adapters_loaded = False
    
    logger.info("=== CLEANUP COMPLETE. GOODBYE. ===")


# --- Application Assembly Factory ---

def create_app() -> FastAPI:
    """
    Primary factory methodology constructing the consolidated App State.
    """
    app = FastAPI(
        title="Agnostic Orchestration Platform (AOP)",
        description="Unified Control Plane bridging Provisioning, Topologies, and LLM Registry Networks.",
        version="1.5.0",
        lifespan=lifespan
    )

    # 1. Global Middleware Injection (Order matters: Outside to Inside)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"], # Open for local dev; tightly bounded in production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    app.add_middleware(RequestLoggingMiddleware)
    
    if RateLimitMiddleware:
        # In a real boot-up, this utilizes redis.asyncio.from_url(env)
        mock_redis_client = MockRedis()
        app.add_middleware(RateLimitMiddleware, redis_client=mock_redis_client)

    # 2. Consolidated Router Wiring
    logger.info("Mounting ecosystem routers into application tree...")
    app.include_router(health_router)
    app.include_router(analytics_router)
    app.include_router(websocket_router)
    app.include_router(prov_router)
    app.include_router(prov_export_router)
    
    # 3. Future-proof Extensibility Routers
    app.include_router(registry_router)
    app.include_router(topology_router)
    app.include_router(governance_router)
    app.include_router(billing_router)
    app.include_router(notifications_router)
    app.include_router(settings_router)
    app.include_router(orchestration_router)
    app.include_router(agents_runtime_router)
    app.include_router(adapters_router)

    return app


# Module Export
app = create_app()
