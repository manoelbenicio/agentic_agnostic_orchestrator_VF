from enum import Enum
from typing import List, Callable
from fastapi import Request, HTTPException, status

class Role(str, Enum):
    ADMIN = "admin"
    OWNER = "owner"
    DEVELOPER = "developer"
    VIEWER = "viewer"

class Permission(str, Enum):
    MANAGE_KEYS = "manage_keys"
    USE_LLM = "use_llm"
    VIEW_METRICS = "view_metrics"
    MANAGE_USERS = "manage_users"
    MANAGE_MODELS = "manage_models"

# Map roles to their specific granted permissions
ROLE_PERMISSIONS = {
    Role.ADMIN: [
        Permission.MANAGE_KEYS,
        Permission.USE_LLM,
        Permission.VIEW_METRICS,
        Permission.MANAGE_USERS,
        Permission.MANAGE_MODELS
    ],
    Role.OWNER: [
        Permission.MANAGE_KEYS,
        Permission.USE_LLM,
        Permission.VIEW_METRICS,
        Permission.MANAGE_USERS,
        Permission.MANAGE_MODELS
    ],
    Role.DEVELOPER: [
        Permission.MANAGE_KEYS,
        Permission.USE_LLM,
        Permission.VIEW_METRICS,
        Permission.MANAGE_MODELS
    ],
    Role.VIEWER: [
        Permission.VIEW_METRICS
    ]
}

def require_permission(required_permission: Permission) -> Callable:
    """
    FastAPI dependency factory to enforce RBAC.
    
    Expects `request.state.role` to be populated by an authentication middleware
    or earlier dependency before this is evaluated.
    """
    def permission_dependency(request: Request):
        # Fetch the role from the request state
        user_role = getattr(request.state, "role", None)
        
        if not user_role:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User role not found in request context."
            )
            
        try:
            # Parse the string role into the Role enum
            role_enum = Role(user_role)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Unrecognized role: {user_role}"
            )
            
        # Get permissions for the user's role
        role_permissions = ROLE_PERMISSIONS.get(role_enum, [])
        
        # Guard clause against lacking required permission
        if required_permission not in role_permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{role_enum.value}' lacks required permission: '{required_permission.value}'."
            )
            
        return True
        
    return permission_dependency
