import secrets
import logging
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

logger = logging.getLogger("auth.key_rotation")


# --- Pydantic Data Boundaries ---

class ApiKeyRecord(BaseModel):
    """Internal database representation of a physical API Key node."""
    id: str
    tenant_id: str
    name: str
    key_hash: str
    scopes: List[str] = []
    created_at: datetime
    expires_at: Optional[datetime] = None
    is_active: bool = True
    rotated_from_id: Optional[str] = None
    next_rotation_at: Optional[datetime] = None

class CreateKeyRequest(BaseModel):
    tenant_id: str
    name: str
    scopes: List[str] = []
    ttl_days: Optional[int] = 90

class RotateKeyRequest(BaseModel):
    ttl_days: Optional[int] = 90

class ScheduleRotationRequest(BaseModel):
    days_from_now: int


# --- Memory State Mocks ---
# Simulated database persistence layer (ordinarily bound to asyncpg via Postgres tables)
MOCK_KEY_DB: Dict[str, ApiKeyRecord] = {}


# --- Business Logic Service Engine ---

class KeyRotationService:
    """
    Robust cryptographic engine managing API Key lifecycles, automated 
    temporal TTL rotations, and secure payload hashing pipelines.
    """
    def __init__(self):
        # Sub-system injection points (Database Pools, Redis Caches, Mailers) go here
        pass

    def _generate_secret(self) -> tuple[str, str, str]:
        """
        Cryptographically secures key generation natively avoiding timing attacks.
        Returns mapped tuple: (key_id, raw_secret, hashed_secret)
        """
        key_id = f"key_{secrets.token_hex(8)}"
        raw_secret = f"aop_{secrets.token_urlsafe(32)}"
        
        # Simulated one-way cryptographic hashing (Standard implementation utilizes Argon2 or bcrypt)
        # Storing raw keys is strictly forbidden in AOP compliance bounds
        key_hash = f"hashed_digest_{raw_secret[-12:]}"
        
        return key_id, raw_secret, key_hash

    async def generate_new_key(self, tenant_id: str, name: str, scopes: List[str], ttl_days: Optional[int] = 90) -> dict:
        """Constructs and safely stores a brand new API Key boundary."""
        key_id, raw_secret, key_hash = self._generate_secret()
        
        expires_at = datetime.utcnow() + timedelta(days=ttl_days) if ttl_days else None
        
        record = ApiKeyRecord(
            id=key_id,
            tenant_id=tenant_id,
            name=name,
            key_hash=key_hash,
            scopes=scopes,
            created_at=datetime.utcnow(),
            expires_at=expires_at
        )
        MOCK_KEY_DB[key_id] = record
        
        logger.info(f"Cryptographic sequence completed. Key {key_id} bound to tenant {tenant_id}.")
        
        # Raw secret is returned STRICTLY ONCE during this payload. Never again.
        return {
            "key_id": key_id,
            "secret_key": raw_secret,
            "expires_at": expires_at.isoformat() if expires_at else None
        }

    async def list_keys(self, tenant_id: str) -> List[ApiKeyRecord]:
        """Iterates stored hash maps fetching all logical keys mapped to a tenant."""
        return [k for k in MOCK_KEY_DB.values() if k.tenant_id == tenant_id]

    async def revoke_key(self, key_id: str):
        """Structurally terminates a key's functional state natively blocking all future execution."""
        if key_id not in MOCK_KEY_DB:
            raise ValueError(f"Key reference {key_id} missing from registry.")
            
        record = MOCK_KEY_DB[key_id]
        record.is_active = False
        record.expires_at = datetime.utcnow() # Terminate TTL immediately
        
        logger.info(f"API Key {key_id} permanently revoked.")
        await self._notify_rotation(record, "revoked via admin override")
        return True

    async def rotate_key(self, key_id: str, ttl_days: Optional[int] = 90) -> dict:
        """
        Synchronously forces a cryptographic rotation. 
        Spins up a new clone inheriting the original scopes and instantly deprecates the old node.
        """
        if key_id not in MOCK_KEY_DB:
            raise ValueError(f"Key reference {key_id} missing from registry.")
            
        old_record = MOCK_KEY_DB[key_id]
        
        # 1. Spawn cloned replacement mapped structurally
        new_id, raw_secret, new_hash = self._generate_secret()
        expires_at = datetime.utcnow() + timedelta(days=ttl_days) if ttl_days else None
        
        new_record = ApiKeyRecord(
            id=new_id,
            tenant_id=old_record.tenant_id,
            name=f"{old_record.name} (Rotated)",
            key_hash=new_hash,
            scopes=old_record.scopes,
            created_at=datetime.utcnow(),
            expires_at=expires_at,
            rotated_from_id=old_record.id
        )
        MOCK_KEY_DB[new_id] = new_record
        
        # 2. Hard deprecate the origin key (Zero grace-period architecture)
        old_record.is_active = False
        old_record.expires_at = datetime.utcnow()
        
        logger.info(f"API Key rotated successfully: {old_record.id} -> {new_record.id}")
        await self._notify_rotation(old_record, f"rotated to replacement hash {new_record.id}")
        
        return {
            "key_id": new_id,
            "secret_key": raw_secret,
            "expires_at": expires_at.isoformat() if expires_at else None,
            "previous_key_id": old_record.id
        }

    async def schedule_rotation(self, key_id: str, days: int) -> dict:
        """Triggers a temporal marker allowing background Crons to auto-rotate this boundary silently."""
        if key_id not in MOCK_KEY_DB:
            raise ValueError(f"Key reference {key_id} missing from registry.")
            
        record = MOCK_KEY_DB[key_id]
        rotation_date = datetime.utcnow() + timedelta(days=days)
        record.next_rotation_at = rotation_date
        
        logger.info(f"Cron scheduled rotation mapped to key {key_id} at temporal edge {rotation_date.isoformat()}")
        return {"scheduled_for": rotation_date.isoformat()}

    async def get_key_usage_stats(self, key_id: str) -> dict:
        """Locates and extracts analytical usage arrays natively tied to this exact key signature."""
        if key_id not in MOCK_KEY_DB:
            raise ValueError(f"Key reference {key_id} missing from registry.")
            
        # Simulating SQL log extraction
        return {
            "key_id": key_id,
            "total_invocations": 14205,
            "last_used_at": (datetime.utcnow() - timedelta(minutes=5)).isoformat(),
            "rate_limit_hits": 12
        }

    async def _notify_rotation(self, record: ApiKeyRecord, action: str):
        """Internal router pipeline simulating email/slack pushes hitting Tenant Owners upon security changes."""
        logger.warning(f"[SECURITY NOTIFICATION DISPATCHED] Tenant API Key '{record.name}' ({record.id}) was {action}.")


# --- FastAPI REST Router Interface ---

router = APIRouter(prefix="/auth/keys", tags=["auth", "api_keys", "security"])
service = KeyRotationService()

@router.post("")
async def create_key(req: CreateKeyRequest):
    """POST /auth/keys -> Generates a new secure API Key bound to a tenant constraints."""
    return await service.generate_new_key(
        tenant_id=req.tenant_id, 
        name=req.name, 
        scopes=req.scopes, 
        ttl_days=req.ttl_days
    )

@router.get("")
async def list_keys(tenant_id: str = Query(..., description="Target structural tenant map")):
    """GET /auth/keys -> Extracts all known active and revoked API keys structurally tied to a tenant."""
    keys = await service.list_keys(tenant_id)
    return {"tenant_id": tenant_id, "keys": keys}

@router.post("/{key_id}/rotate")
async def rotate_key(key_id: str, req: RotateKeyRequest):
    """POST /auth/keys/{id}/rotate -> Immediately destroys target key and clones a secure replacement natively."""
    try:
        return await service.rotate_key(key_id, req.ttl_days)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.post("/{key_id}/revoke")
async def revoke_key(key_id: str):
    """POST /auth/keys/{id}/revoke -> Instantly shuts down capabilities mapped to this target string."""
    try:
        await service.revoke_key(key_id)
        return {"status": "revoked", "key_id": key_id}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.post("/{key_id}/schedule")
async def schedule_key_rotation(key_id: str, req: ScheduleRotationRequest):
    """POST /auth/keys/{id}/schedule -> Queues a background Cron routine to eventually silently clone this key."""
    try:
        return await service.schedule_rotation(key_id, req.days_from_now)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/{key_id}/stats")
async def get_key_stats(key_id: str):
    """GET /auth/keys/{id}/stats -> Dumps statistical utilization data mapped entirely to this token."""
    try:
        return await service.get_key_usage_stats(key_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
