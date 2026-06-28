from datetime import datetime
import uuid
from typing import List, Optional, Any, Dict
from sqlalchemy import String, Boolean, Float, DateTime, ForeignKey, Text, func, Index
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB

# --- Core Platform Architectural Baseline ---

class Base(DeclarativeBase):
    """
    Monolithic Base Class injecting absolute structural constraints (UUIDv4 physical boundaries 
    and chronological server-side timestamps) directly into all cascading ORM matrices natively.
    """
    # PostgreSQL native binary UUIDs yield radically faster index trees than string UUIDs
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    
    # Pushed evaluation straight to the database layer (func.now()) preventing Python clock drifts
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now(), 
        onupdate=func.now(), 
        nullable=False
    )


# --- Identity, Tenancy, & IAM Boundaries ---

class TenantModel(Base):
    """Physical representation of isolated logical boundaries holding distinct AI workspaces and billing."""
    __tablename__ = "tenants"
    
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    domain: Mapped[Optional[str]] = mapped_column(String(255), unique=True, index=True, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="active", index=True) # Constraints: active, suspended, deleted
    monthly_budget_usd: Mapped[float] = mapped_column(Float, default=100.0)
    
    # Declarative execution graph bindings
    users: Mapped[List["UserModel"]] = relationship("UserModel", back_populates="tenant", cascade="all, delete-orphan")
    roles: Mapped[List["RoleModel"]] = relationship("RoleModel", back_populates="tenant", cascade="all, delete-orphan")
    agents: Mapped[List["AgentModel"]] = relationship("AgentModel", back_populates="tenant")
    cost_records: Mapped[List["CostRecordModel"]] = relationship("CostRecordModel", back_populates="tenant")
    provisioning_requests: Mapped[List["ProvisioningRequestModel"]] = relationship("ProvisioningRequestModel", back_populates="tenant")
    notifications: Mapped[List["NotificationModel"]] = relationship("NotificationModel", back_populates="tenant")

class RoleModel(Base):
    """Maps strict RBAC boundaries encapsulating JSONB constraint payloads."""
    __tablename__ = "roles"
    
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    permissions: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)
    
    tenant: Mapped["TenantModel"] = relationship("TenantModel", back_populates="roles")
    users: Mapped[List["UserModel"]] = relationship("UserModel", back_populates="role")

class UserModel(Base):
    """Isolated actor constraints mapped natively to active sessions."""
    __tablename__ = "users"
    
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    role_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("roles.id", ondelete="SET NULL"), index=True)
    
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    tenant: Mapped["TenantModel"] = relationship("TenantModel", back_populates="users")
    role: Mapped[Optional["RoleModel"]] = relationship("RoleModel", back_populates="users")


# --- Topology, Inference, & Registry ---

class AdapterModel(Base):
    """Platform-wide integration mappings targeting external network architectures (e.g., OpenAI, Ollama)."""
    __tablename__ = "adapters"
    
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    provider_type: Mapped[str] = mapped_column(String(100), index=True, nullable=False) # e.g., 'openai', 'anthropic'
    endpoint_url: Mapped[Optional[str]] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(50), default="offline", index=True) # online, offline, degraded
    
    # Natively supports deep GIN Indexing for dynamic metadata filters inside Postgres
    metadata_config: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict) 
    
    agents: Mapped[List["AgentModel"]] = relationship("AgentModel", back_populates="adapter")

class AgentModel(Base):
    """Live Neural instantiation targets executing localized system prompts."""
    __tablename__ = "agents"
    
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    adapter_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("adapters.id", ondelete="RESTRICT"), index=True)
    
    name: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    model_identifier: Mapped[str] = mapped_column(String(255), nullable=False) # Physical target (e.g. 'gpt-4o-mini')
    system_prompt: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50), default="active", index=True)
    config: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)
    
    tenant: Mapped["TenantModel"] = relationship("TenantModel", back_populates="agents")
    adapter: Mapped["AdapterModel"] = relationship("AdapterModel", back_populates="agents")


# --- IaC & Provisioning Pipelines ---

class ProvisioningRequestModel(Base):
    """Stateful record executing Terraform/Kubernetes network deployments."""
    __tablename__ = "provisioning_requests"
    
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    resource_type: Mapped[str] = mapped_column(String(100), index=True, nullable=False) # 'vector_db', 'redis_cache'
    status: Mapped[str] = mapped_column(String(50), default="pending", index=True) # pending, running, completed, failed
    infrastructure_payload: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    
    tenant: Mapped["TenantModel"] = relationship("TenantModel", back_populates="provisioning_requests")


# --- Governance, Finance, & Telemetry ---

class AuditLogModel(Base):
    """Write-heavy immutable tracking layer tracing API bounds."""
    __tablename__ = "audit_logs"
    
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    
    action: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    resource: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45))
    payload: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)

    # Complex geometric indexing drastically accelerating time-series dashboard filters natively
    __table_args__ = (
        Index("ix_audit_tenant_time", "tenant_id", "created_at"),
    )

class CostRecordModel(Base):
    """Dense numerical arrays bounding fractional USD burns sequentially to resources."""
    __tablename__ = "cost_records"
    
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    
    resource_type: Mapped[str] = mapped_column(String(100), index=True, nullable=False) # 'llm_inference', 'pgvector_storage'
    resource_id: Mapped[Optional[str]] = mapped_column(String(255), index=True)
    amount_usd: Mapped[float] = mapped_column(Float, nullable=False)
    metadata_context: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)

    # Absolutely critical for PostgreSQL date_trunc('month') algorithmic evaluations executing rapidly
    __table_args__ = (
        Index("ix_cost_tenant_time", "tenant_id", "created_at"),
    )
    
    tenant: Mapped["TenantModel"] = relationship("TenantModel", back_populates="cost_records")


# --- Global Settings & Notifications ---

class SettingModel(Base):
    """Replaces traditional singletons with a structural distributed dictionary layout."""
    __tablename__ = "platform_settings"
    
    category: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    payload: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    updated_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

class NotificationModel(Base):
    """Logical decoupling tracking UI acknowledgements targeting asynchronous dispatches."""
    __tablename__ = "notifications"
    
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    delivery_type: Mapped[str] = mapped_column(String(50), index=True, nullable=False) # 'in_app', 'slack', 'webhook'
    status: Mapped[str] = mapped_column(String(50), default="pending", index=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    
    tenant: Mapped["TenantModel"] = relationship("TenantModel", back_populates="notifications")
