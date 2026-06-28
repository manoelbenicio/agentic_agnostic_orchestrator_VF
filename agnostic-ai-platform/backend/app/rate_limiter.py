import time
import asyncio
from typing import Optional, Dict, Tuple
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel

# --- Models ---
class KeyScope(BaseModel):
    """
    Represents the scope, limits, and identifiers tied to an API key.
    Typically loaded by the auth middleware and attached to request.state.
    """
    tenant_id: str
    api_key: str
    rpm_limit: int
    tpm_limit: int

# --- Redis-Ready Store Interface ---
class RateLimitStore:
    """
    Interface for the rate limiter state. 
    Currently uses an in-memory sliding window/token bucket approach, 
    but provides async methods designed to be easily swappable with aioredis.
    """
    def __init__(self):
        # Maps key -> (tokens, last_update_timestamp)
        self._store: Dict[str, Tuple[float, float]] = {}
        self._lock = asyncio.Lock()

    async def get_or_set(self, key: str, default_tokens: float, default_timestamp: float) -> Tuple[float, float]:
        async with self._lock:
            if key not in self._store:
                self._store[key] = (default_tokens, default_timestamp)
            return self._store[key]

    async def update(self, key: str, tokens: float, timestamp: float):
        async with self._lock:
            self._store[key] = (tokens, timestamp)

# Global in-memory instance
store = RateLimitStore()

# --- Rate Limiter Logic ---
async def check_rate_limit(
    identifier: str, 
    limit_per_minute: int, 
    cost: int = 1,
    limit_type: str = "RPM"
) -> Tuple[bool, int]:
    """
    Enforces a rate limit using an async-compatible token bucket algorithm.
    Returns a tuple of (is_allowed, retry_after_seconds).
    """
    now = time.time()
    key = f"ratelimit:{limit_type}:{identifier}"
    
    # Maximum capacity is the limit per minute
    capacity = float(limit_per_minute)
    
    # Refill rate is tokens per second
    refill_rate = capacity / 60.0
    
    # Retrieve current bucket state
    tokens, last_update = await store.get_or_set(key, capacity, now)
    
    # Refill tokens based on elapsed time
    elapsed = now - last_update
    new_tokens = min(capacity, tokens + (elapsed * refill_rate))
    
    if new_tokens >= cost:
        # Under limit: consume cost and update bucket
        await store.update(key, new_tokens - cost, now)
        return True, 0
    else:
        # Over limit: calculate seconds until enough tokens are available
        tokens_needed = cost - new_tokens
        retry_after = int(tokens_needed / refill_rate) if refill_rate > 0 else 60
        return False, max(1, retry_after)


# --- FastAPI Middleware ---
class RateLimitingMiddleware(BaseHTTPMiddleware):
    """
    Middleware that enforces sliding window RPM and TPM limits per API key and per Tenant.
    It expects `request.state.key_scope` to be populated by an earlier authentication step.
    """
    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting for infrastructure endpoints
        if request.url.path in ["/health", "/metrics", "/docs", "/openapi.json"]:
            return await call_next(request)

        key_scope: Optional[KeyScope] = getattr(request.state, "key_scope", None)
        
        if key_scope:
            # 1. Enforce RPM limit per API Key
            key_rpm_allowed, key_rpm_retry = await check_rate_limit(
                identifier=f"api_key:{key_scope.api_key}",
                limit_per_minute=key_scope.rpm_limit,
                cost=1,
                limit_type="RPM"
            )
            
            if not key_rpm_allowed:
                return self._rate_limit_response("RPM limit exceeded for API Key", key_rpm_retry)
                
            # 2. Enforce RPM limit per Tenant (Example logic: combined tenant limit could be defined elsewhere)
            # Using the same limit as the key for demonstration, but typically this would be a broader pool
            tenant_rpm_allowed, tenant_rpm_retry = await check_rate_limit(
                identifier=f"tenant:{key_scope.tenant_id}",
                limit_per_minute=key_scope.rpm_limit * 10,
                cost=1,
                limit_type="RPM"
            )
            
            if not tenant_rpm_allowed:
                return self._rate_limit_response("RPM limit exceeded for Tenant", tenant_rpm_retry)

            # 3. Basic TPM pre-flight check
            # For TPM, we often deduct exact tokens *after* the generation is complete, 
            # but we perform a pre-flight check of cost=1 just to ensure the bucket isn't totally exhausted.
            tpm_allowed, tpm_retry = await check_rate_limit(
                identifier=f"api_key:{key_scope.api_key}",
                limit_per_minute=key_scope.tpm_limit,
                cost=1,
                limit_type="TPM"
            )
            
            if not tpm_allowed:
                return self._rate_limit_response("TPM limit exhausted for API Key", tpm_retry)

        # Process the request
        response = await call_next(request)
        return response

    def _rate_limit_response(self, message: str, retry_after: int) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={"error": "Too Many Requests", "message": message},
            headers={"Retry-After": str(retry_after)}
        )
