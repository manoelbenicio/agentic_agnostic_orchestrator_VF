import jwt
from datetime import datetime, timedelta
from typing import Any, Tuple
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

SECRET_KEY = "super_secret_agnostic_key"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

def create_access_token(user_id: str, role: str, tenant_id: str) -> str:
    """Generate a JWT with stateless session claims."""
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = {
        "sub": user_id,
        "role": role,
        "tenant_id": tenant_id,
        "exp": expire
    }
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

class JWTAuthMiddleware(BaseHTTPMiddleware):
    """Middleware that validates JWT on every request for stateless session handling."""
    
    async def dispatch(self, request: Request, call_next: Any) -> Response:
        exempt_paths = ["/health", "/metrics", "/docs", "/openapi.json", "/auth/token"]
        if request.url.path in exempt_paths or request.url.path.startswith("/auth/device/") or request.method == "OPTIONS":
            return await call_next(request)

        if getattr(request.state, "tenant_context", None) is not None and request.headers.get("X-API-Key"):
            return await call_next(request)

        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401, 
                content={"detail": "Missing or invalid Authorization header"}
            )

        token = auth_header.split(" ")[1]
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            # Attach stateless session info to request.state
            request.state.user_id = payload.get("sub")
            request.state.role = payload.get("role")
            request.state.tenant_id = payload.get("tenant_id")
        except jwt.ExpiredSignatureError:
            return JSONResponse(
                status_code=401,
                content={"detail": "Token expired"}
            )
        except jwt.PyJWTError:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid token"}
            )

        return await call_next(request)
