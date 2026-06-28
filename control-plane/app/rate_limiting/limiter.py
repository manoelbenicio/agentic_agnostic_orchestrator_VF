import time
from typing import Callable, Tuple
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
import redis.asyncio as redis

class RateLimiter:
    """
    Robust sliding window rate limiter backed by Redis Sorted Sets (ZSET).
    """
    def __init__(self, redis_client: redis.Redis, default_limit: int = 100, window_size_sec: int = 60):
        self.redis = redis_client
        self.default_limit = default_limit
        self.window_size_sec = window_size_sec

    async def check_rate_limit(self, key: str, limit: int, window: int) -> Tuple[bool, int]:
        """
        Executes an atomic Redis sliding window algorithm.
        Returns a tuple mapping: (is_allowed: bool, retry_after_seconds: int)
        """
        now = time.time()
        window_start = now - window
        
        # Utilize a Redis pipeline to batch commands transactionally
        pipe = self.redis.pipeline()
        
        # 1. Prune timestamps older than the trailing window
        pipe.zremrangebyscore(key, 0, window_start)
        
        # 2. Extract the current active request volume in the window
        pipe.zcard(key)
        
        # 3. Add the incoming request timestamp mapped exactly to the current epoch score
        # ZADD signature requires mapping -> {member: score}
        pipe.zadd(key, {str(now): now})
        
        # 4. Set a TTL boundary automatically cleaning up orphaned/inactive keys
        pipe.expire(key, window)
        
        # Execute batch pipeline
        results = await pipe.execute()
        
        # Extract the length recorded prior to insertion (index 1 maps to zcard output)
        current_count = results[1]
        
        if current_count >= limit:
            # Capacity exceeded. Revert the pipeline's insertion atomically.
            await self.redis.zrem(key, str(now))
            
            # Fetch the oldest item in the set to accurately calculate the dropoff queue
            oldest_items = await self.redis.zrange(key, 0, 0, withscores=True)
            if oldest_items:
                # Calculate exactly when the oldest token expires from the window
                oldest_score = oldest_items[0][1]
                retry_after = int(window - (now - oldest_score))
                return False, max(1, retry_after)
            
            # Failsafe logic if empty/corrupted
            return False, window
            
        return True, 0


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware enforcing strict tenant/endpoint boundaries
    using the sliding window RateLimiter engine.
    """
    def __init__(self, app, redis_client: redis.Redis, default_limit: int = 100, window_size_sec: int = 60):
        super().__init__(app)
        self.limiter = RateLimiter(
            redis_client=redis_client, 
            default_limit=default_limit, 
            window_size_sec=window_size_sec
        )

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Intercepts incoming HTTP requests assessing available rate capacity 
        before yielding upstream.
        """
        # Resolve Tenant ID safely. Commonly mapped into `request.state` by upstream AuthMiddleware,
        # otherwise falls back to headers, and finally an anonymous throttle pool.
        tenant_id = getattr(request.state, "tenant_id", None) or request.headers.get("X-Tenant-ID", "anonymous")
        
        endpoint = request.url.path
        
        # Construct isolated capacity bucket key mapping per-tenant + per-endpoint isolation
        key = f"ratelimit:{tenant_id}:{endpoint}"
        
        # Evaluate throughput capacity against the localized sliding window
        is_allowed, retry_after = await self.limiter.check_rate_limit(
            key=key, 
            limit=self.limiter.default_limit, 
            window=self.limiter.window_size_sec
        )
        
        if not is_allowed:
            # Short-circuit execution and return HTTP 429 safely
            return JSONResponse(
                status_code=429,
                content={"detail": "Too Many Requests. Rate limit exceeded for this endpoint."},
                headers={"Retry-After": str(retry_after)}
            )
            
        # Delegate to standard application routing
        response = await call_next(request)
        return response
