import jwt
from typing import Optional
from fastapi import Request, HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, APIKeyHeader
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

# Import KeyScope to integrate with the rate limiter
from .rate_limiter import KeyScope

# --- Mock Constants ---
# In a real environment, load these from environment variables or a key vault.
JWT_SECRET = "mock_signature"  # Matches the mock from auth_router
JWT_ALGORITHM = "HS256"

# Mock database of API keys for demonstration
VALID_API_KEYS = {
    "sk-test-123": {
        "tenant_id": "tenant_1",
        "user_id": "service_account",
        "role": "admin",
        "rpm_limit": 60,
        "tpm_limit": 100000
    }
}

class AuthMiddleware(BaseHTTPMiddleware):
    """
    Middleware that performs dual authentication (JWT Bearer or X-API-Key).
    Enriches the request context (request.state) with user, tenant, role, and rate limit scopes.
    """
    async def dispatch(self, request: Request, call_next):
        # Skip auth for public infrastructure endpoints
        if request.url.path in ["/health", "/docs", "/openapi.json", "/auth/token"]:
            return await call_next(request)

        # Retrieve headers
        api_key = request.headers.get("X-API-Key")
        auth_header = request.headers.get("Authorization")
        
        is_authenticated = False
        
        # 1. Try X-API-Key Authentication
        if api_key:
            key_info = VALID_API_KEYS.get(api_key)
            if key_info:
                # Enrich context
                request.state.user_id = key_info["user_id"]
                request.state.tenant_id = key_info["tenant_id"]
                request.state.role = key_info["role"]
                
                # Setup KeyScope for rate_limiter.py integration
                request.state.key_scope = KeyScope(
                    tenant_id=key_info["tenant_id"],
                    api_key=api_key,
                    rpm_limit=key_info["rpm_limit"],
                    tpm_limit=key_info["tpm_limit"]
                )
                is_authenticated = True
            else:
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={"detail": "Invalid API Key"}
                )
                
        # 2. Try JWT Bearer Authentication
        elif auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
            try:
                # In production, audience and issuer validations should be added
                payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
                
                # Enrich context from JWT claims
                request.state.user_id = payload.get("sub")
                request.state.tenant_id = payload.get("tenant_id", "default_tenant")
                request.state.role = payload.get("role", "viewer")
                
                # Setup KeyScope for rate_limiter.py integration
                request.state.key_scope = KeyScope(
                    tenant_id=request.state.tenant_id,
                    api_key=f"jwt_{request.state.user_id}",
                    rpm_limit=30,     # Default JWT limits
                    tpm_limit=50000
                )
                is_authenticated = True
                
            except jwt.ExpiredSignatureError:
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={"detail": "Token has expired"}
                )
            except jwt.InvalidTokenError:
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={"detail": "Invalid token"}
                )
                
        if not is_authenticated:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Not authenticated. Provide Bearer JWT or X-API-Key."}
            )

        # Proceed to next middleware (e.g., RateLimitingMiddleware)
        return await call_next(request)


# --- FastAPI Dependency for Protected Routes ---

bearer_scheme = HTTPBearer(auto_error=False)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

async def require_auth(
    request: Request,
    token: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    api_key: Optional[str] = Depends(api_key_header)
):
    """
    FastAPI dependency injection for protected routes.
    
    Since the AuthMiddleware runs globally and enriches `request.state`, 
    this dependency simply ensures that the state was successfully enriched.
    It can be injected into any route (e.g., `Depends(require_auth)`) to guarantee
    the route only executes for authenticated contexts.
    """
    if not hasattr(request.state, "user_id") or not request.state.user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    return request.state
