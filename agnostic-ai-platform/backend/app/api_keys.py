"""
AI Platform — API Key Management
Task: ai-platform-4.2
Manages API keys for tenant/project-scoped access to LLM endpoints.
Supports key creation, rotation, revocation, and usage tracking.
"""
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, List, Dict, Any

from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════
# MODELS
# ═══════════════════════════════════════════════════════════

class KeyStatus(str, Enum):
    ACTIVE = "active"
    REVOKED = "revoked"
    EXPIRED = "expired"
    ROTATED = "rotated"


class KeyScope(BaseModel):
    """Defines what an API key can access."""
    tenant_id: str
    project_id: Optional[str] = None
    allowed_models: List[str] = Field(default_factory=list)  # empty = all models
    allowed_endpoints: List[str] = Field(default_factory=list)  # empty = all endpoints
    rate_limit_rpm: int = 60  # requests per minute
    rate_limit_tpm: int = 100_000  # tokens per minute
    max_tokens_per_request: int = 4096
    budget_limit_usd: Optional[float] = None  # monthly budget cap


class APIKeyRecord(BaseModel):
    """Full API key record stored in the database."""
    key_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    key_prefix: str  # first 8 chars for identification (e.g. "aop_sk_xxxxxxxx")
    key_hash: str  # SHA-256 hash of the full key
    name: str  # human-readable name
    description: Optional[str] = None
    scope: KeyScope
    status: KeyStatus = KeyStatus.ACTIVE
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None
    rotated_from: Optional[str] = None  # key_id of predecessor
    usage_count: int = 0
    total_tokens_used: int = 0
    total_cost_usd: float = 0.0
    created_by: str = "system"
    metadata: Dict[str, Any] = Field(default_factory=dict)


class APIKeyCreateRequest(BaseModel):
    """Request to create a new API key."""
    name: str
    description: Optional[str] = None
    tenant_id: str
    project_id: Optional[str] = None
    allowed_models: List[str] = Field(default_factory=list)
    rate_limit_rpm: int = 60
    rate_limit_tpm: int = 100_000
    max_tokens_per_request: int = 4096
    budget_limit_usd: Optional[float] = None
    expires_in_days: Optional[int] = 90  # None = never expires


class APIKeyCreateResponse(BaseModel):
    """Response after creating a key — the ONLY time the full key is returned."""
    key_id: str
    api_key: str  # full key, shown only once
    key_prefix: str
    name: str
    scope: KeyScope
    expires_at: Optional[datetime]
    message: str = "Store this key securely. It will not be shown again."


class APIKeyInfo(BaseModel):
    """Safe key info (never includes the full key or hash)."""
    key_id: str
    key_prefix: str
    name: str
    description: Optional[str]
    scope: KeyScope
    status: KeyStatus
    created_at: datetime
    expires_at: Optional[datetime]
    last_used_at: Optional[datetime]
    usage_count: int
    total_tokens_used: int
    total_cost_usd: float


# ═══════════════════════════════════════════════════════════
# KEY MANAGER
# ═══════════════════════════════════════════════════════════

class APIKeyManager:
    """
    Manages API key lifecycle: create, validate, rotate, revoke, track usage.
    
    In production, this would be backed by PostgreSQL.
    Current implementation uses in-memory store for development.
    """

    def __init__(self):
        self._keys: Dict[str, APIKeyRecord] = {}  # key_id -> record
        self._hash_index: Dict[str, str] = {}  # key_hash -> key_id (for fast lookup)

    @staticmethod
    def _generate_key() -> str:
        """Generate a cryptographically secure API key."""
        random_bytes = secrets.token_hex(32)  # 64 hex chars
        return f"aop_sk_{random_bytes}"

    @staticmethod
    def _hash_key(api_key: str) -> str:
        """Hash an API key using SHA-256."""
        return hashlib.sha256(api_key.encode("utf-8")).hexdigest()

    @staticmethod
    def _extract_prefix(api_key: str) -> str:
        """Extract the prefix for key identification."""
        return api_key[:15]  # "aop_sk_" + first 8 hex chars

    # ── Create ──────────────────────────────────────────────

    def create_key(self, request: APIKeyCreateRequest) -> APIKeyCreateResponse:
        """Create a new API key. Returns the full key only once."""
        api_key = self._generate_key()
        key_hash = self._hash_key(api_key)
        key_prefix = self._extract_prefix(api_key)

        expires_at = None
        if request.expires_in_days is not None:
            expires_at = datetime.utcnow() + timedelta(days=request.expires_in_days)

        scope = KeyScope(
            tenant_id=request.tenant_id,
            project_id=request.project_id,
            allowed_models=request.allowed_models,
            rate_limit_rpm=request.rate_limit_rpm,
            rate_limit_tpm=request.rate_limit_tpm,
            max_tokens_per_request=request.max_tokens_per_request,
            budget_limit_usd=request.budget_limit_usd,
        )

        record = APIKeyRecord(
            key_prefix=key_prefix,
            key_hash=key_hash,
            name=request.name,
            description=request.description,
            scope=scope,
            expires_at=expires_at,
        )

        self._keys[record.key_id] = record
        self._hash_index[key_hash] = record.key_id

        return APIKeyCreateResponse(
            key_id=record.key_id,
            api_key=api_key,
            key_prefix=key_prefix,
            name=request.name,
            scope=scope,
            expires_at=expires_at,
        )

    # ── Validate ────────────────────────────────────────────

    def validate_key(self, api_key: str) -> Optional[APIKeyRecord]:
        """
        Validate an API key and return its record if valid.
        Returns None if invalid, expired, or revoked.
        """
        key_hash = self._hash_key(api_key)
        key_id = self._hash_index.get(key_hash)
        if key_id is None:
            return None

        record = self._keys.get(key_id)
        if record is None:
            return None

        # Check status
        if record.status != KeyStatus.ACTIVE:
            return None

        # Check expiration
        if record.expires_at and datetime.utcnow() > record.expires_at:
            record.status = KeyStatus.EXPIRED
            return None

        # Check budget
        if record.scope.budget_limit_usd is not None:
            if record.total_cost_usd >= record.scope.budget_limit_usd:
                return None

        # Update last_used_at
        record.last_used_at = datetime.utcnow()
        record.usage_count += 1

        return record

    # ── Rotate ──────────────────────────────────────────────

    def rotate_key(self, key_id: str, expires_in_days: Optional[int] = 90) -> Optional[APIKeyCreateResponse]:
        """
        Rotate a key: revoke old, create new with same scope.
        Returns the new key response, or None if key_id not found.
        """
        old_record = self._keys.get(key_id)
        if old_record is None:
            return None

        # Revoke old key
        old_record.status = KeyStatus.ROTATED
        old_record.revoked_at = datetime.utcnow()

        # Remove from hash index
        if old_record.key_hash in self._hash_index:
            del self._hash_index[old_record.key_hash]

        # Create new key with same scope
        create_request = APIKeyCreateRequest(
            name=f"{old_record.name} (rotated)",
            description=old_record.description,
            tenant_id=old_record.scope.tenant_id,
            project_id=old_record.scope.project_id,
            allowed_models=old_record.scope.allowed_models,
            rate_limit_rpm=old_record.scope.rate_limit_rpm,
            rate_limit_tpm=old_record.scope.rate_limit_tpm,
            max_tokens_per_request=old_record.scope.max_tokens_per_request,
            budget_limit_usd=old_record.scope.budget_limit_usd,
            expires_in_days=expires_in_days,
        )

        response = self.create_key(create_request)

        # Link new key to old
        new_record = self._keys[response.key_id]
        new_record.rotated_from = key_id

        return response

    # ── Revoke ──────────────────────────────────────────────

    def revoke_key(self, key_id: str) -> bool:
        """Revoke an API key. Returns True if found and revoked."""
        record = self._keys.get(key_id)
        if record is None:
            return False

        record.status = KeyStatus.REVOKED
        record.revoked_at = datetime.utcnow()

        # Remove from hash index
        if record.key_hash in self._hash_index:
            del self._hash_index[record.key_hash]

        return True

    # ── Usage Tracking ──────────────────────────────────────

    def record_usage(self, key_id: str, tokens_used: int, cost_usd: float) -> bool:
        """Record token usage and cost for a key."""
        record = self._keys.get(key_id)
        if record is None:
            return False

        record.total_tokens_used += tokens_used
        record.total_cost_usd += cost_usd
        return True

    # ── List / Get ──────────────────────────────────────────

    def list_keys(self, tenant_id: str, include_revoked: bool = False) -> List[APIKeyInfo]:
        """List all keys for a tenant (never returns the full key)."""
        results = []
        for record in self._keys.values():
            if record.scope.tenant_id != tenant_id:
                continue
            if not include_revoked and record.status in (KeyStatus.REVOKED, KeyStatus.ROTATED):
                continue
            results.append(APIKeyInfo(
                key_id=record.key_id,
                key_prefix=record.key_prefix,
                name=record.name,
                description=record.description,
                scope=record.scope,
                status=record.status,
                created_at=record.created_at,
                expires_at=record.expires_at,
                last_used_at=record.last_used_at,
                usage_count=record.usage_count,
                total_tokens_used=record.total_tokens_used,
                total_cost_usd=record.total_cost_usd,
            ))
        return results

    def get_key_info(self, key_id: str) -> Optional[APIKeyInfo]:
        """Get safe info for a single key."""
        record = self._keys.get(key_id)
        if record is None:
            return None
        return APIKeyInfo(
            key_id=record.key_id,
            key_prefix=record.key_prefix,
            name=record.name,
            description=record.description,
            scope=record.scope,
            status=record.status,
            created_at=record.created_at,
            expires_at=record.expires_at,
            last_used_at=record.last_used_at,
            usage_count=record.usage_count,
            total_tokens_used=record.total_tokens_used,
            total_cost_usd=record.total_cost_usd,
        )


# ═══════════════════════════════════════════════════════════
# SINGLETON
# ═══════════════════════════════════════════════════════════
api_key_manager = APIKeyManager()
