"""initial

Revision ID: 001
Revises: 
Create Date: 2026-06-28 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# Revision Identifiers used natively by Alembic diff checks
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Generates exact physical DDL logic resolving Foreign Key dependencies 
    seamlessly constructing the monolithic database core natively.
    """
    # ----------------------------------------------------
    # Phase 1: Constructing Independent Root Tables
    # ----------------------------------------------------
    
    # 1. Platform Settings (Key-Value Singleton Store)
    op.create_table('platform_settings',
        sa.Column('category', sa.String(length=100), nullable=False),
        sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('updated_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_platform_settings_category'), 'platform_settings', ['category'], unique=True)
    op.create_index(op.f('ix_platform_settings_id'), 'platform_settings', ['id'], unique=False)

    # 2. Adapters (Global AI Network Definitions)
    op.create_table('adapters',
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('provider_type', sa.String(length=100), nullable=False),
        sa.Column('endpoint_url', sa.String(length=500), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('metadata_config', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_adapters_id'), 'adapters', ['id'], unique=False)
    op.create_index(op.f('ix_adapters_name'), 'adapters', ['name'], unique=True)
    op.create_index(op.f('ix_adapters_provider_type'), 'adapters', ['provider_type'], unique=False)
    op.create_index(op.f('ix_adapters_status'), 'adapters', ['status'], unique=False)

    # 3. Tenants (Core Access Governance Boundary)
    op.create_table('tenants',
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('domain', sa.String(length=255), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('monthly_budget_usd', sa.Float(), nullable=False),
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_tenants_domain'), 'tenants', ['domain'], unique=True)
    op.create_index(op.f('ix_tenants_id'), 'tenants', ['id'], unique=False)
    op.create_index(op.f('ix_tenants_name'), 'tenants', ['name'], unique=True)
    op.create_index(op.f('ix_tenants_status'), 'tenants', ['status'], unique=False)

    # ----------------------------------------------------
    # Phase 2: Constructing Dependent Relational Tables
    # ----------------------------------------------------
    
    # 4. Roles (RBAC Logic)
    op.create_table('roles',
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('permissions', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_roles_id'), 'roles', ['id'], unique=False)
    op.create_index(op.f('ix_roles_tenant_id'), 'roles', ['tenant_id'], unique=False)

    # 5. Users (IAM Logic)
    op.create_table('users',
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('role_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('last_login', sa.DateTime(timezone=True), nullable=True),
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['role_id'], ['roles.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_index(op.f('ix_users_id'), 'users', ['id'], unique=False)
    op.create_index(op.f('ix_users_role_id'), 'users', ['role_id'], unique=False)
    op.create_index(op.f('ix_users_tenant_id'), 'users', ['tenant_id'], unique=False)

    # 6. Agents (Active Network Nodes)
    op.create_table('agents',
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('adapter_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('model_identifier', sa.String(length=255), nullable=False),
        sa.Column('system_prompt', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('config', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['adapter_id'], ['adapters.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_agents_adapter_id'), 'agents', ['adapter_id'], unique=False)
    op.create_index(op.f('ix_agents_id'), 'agents', ['id'], unique=False)
    op.create_index(op.f('ix_agents_name'), 'agents', ['name'], unique=False)
    op.create_index(op.f('ix_agents_status'), 'agents', ['status'], unique=False)
    op.create_index(op.f('ix_agents_tenant_id'), 'agents', ['tenant_id'], unique=False)

    # 7. Provisioning Requests (IaC Execution States)
    op.create_table('provisioning_requests',
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('resource_type', sa.String(length=100), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('infrastructure_payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_provisioning_requests_id'), 'provisioning_requests', ['id'], unique=False)
    op.create_index(op.f('ix_provisioning_requests_resource_type'), 'provisioning_requests', ['resource_type'], unique=False)
    op.create_index(op.f('ix_provisioning_requests_status'), 'provisioning_requests', ['status'], unique=False)
    op.create_index(op.f('ix_provisioning_requests_tenant_id'), 'provisioning_requests', ['tenant_id'], unique=False)

    # 8. Audit Logs (Immutable Traceability)
    op.create_table('audit_logs',
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('action', sa.String(length=255), nullable=False),
        sa.Column('resource', sa.String(length=255), nullable=False),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    # Advanced compound index explicitly designed to radically accelerate multi-tenant time-series filtering
    op.create_index('ix_audit_tenant_time', 'audit_logs', ['tenant_id', 'created_at'], unique=False)
    op.create_index(op.f('ix_audit_logs_action'), 'audit_logs', ['action'], unique=False)
    op.create_index(op.f('ix_audit_logs_id'), 'audit_logs', ['id'], unique=False)
    op.create_index(op.f('ix_audit_logs_resource'), 'audit_logs', ['resource'], unique=False)
    op.create_index(op.f('ix_audit_logs_tenant_id'), 'audit_logs', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_audit_logs_user_id'), 'audit_logs', ['user_id'], unique=False)

    # 9. Cost Records (Dense Financial Traceability)
    op.create_table('cost_records',
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('resource_type', sa.String(length=100), nullable=False),
        sa.Column('resource_id', sa.String(length=255), nullable=True),
        sa.Column('amount_usd', sa.Float(), nullable=False),
        sa.Column('metadata_context', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_cost_tenant_time', 'cost_records', ['tenant_id', 'created_at'], unique=False)
    op.create_index(op.f('ix_cost_records_id'), 'cost_records', ['id'], unique=False)
    op.create_index(op.f('ix_cost_records_resource_id'), 'cost_records', ['resource_id'], unique=False)
    op.create_index(op.f('ix_cost_records_resource_type'), 'cost_records', ['resource_type'], unique=False)
    op.create_index(op.f('ix_cost_records_tenant_id'), 'cost_records', ['tenant_id'], unique=False)

    # 10. Notifications (Asynchronous Messaging Acknowledgments)
    op.create_table('notifications',
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('delivery_type', sa.String(length=50), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('is_read', sa.Boolean(), nullable=False),
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_notifications_delivery_type'), 'notifications', ['delivery_type'], unique=False)
    op.create_index(op.f('ix_notifications_id'), 'notifications', ['id'], unique=False)
    op.create_index(op.f('ix_notifications_is_read'), 'notifications', ['is_read'], unique=False)
    op.create_index(op.f('ix_notifications_status'), 'notifications', ['status'], unique=False)
    op.create_index(op.f('ix_notifications_tenant_id'), 'notifications', ['tenant_id'], unique=False)


def downgrade() -> None:
    """Executes a clean cascade obliterating logical structures recursively."""
    # Drop Dependent Layers (Cascade Safety)
    op.drop_index(op.f('ix_notifications_tenant_id'), table_name='notifications')
    op.drop_index(op.f('ix_notifications_status'), table_name='notifications')
    op.drop_index(op.f('ix_notifications_is_read'), table_name='notifications')
    op.drop_index(op.f('ix_notifications_id'), table_name='notifications')
    op.drop_index(op.f('ix_notifications_delivery_type'), table_name='notifications')
    op.drop_table('notifications')
    
    op.drop_index(op.f('ix_cost_records_tenant_id'), table_name='cost_records')
    op.drop_index(op.f('ix_cost_records_resource_type'), table_name='cost_records')
    op.drop_index(op.f('ix_cost_records_resource_id'), table_name='cost_records')
    op.drop_index(op.f('ix_cost_records_id'), table_name='cost_records')
    op.drop_index('ix_cost_tenant_time', table_name='cost_records')
    op.drop_table('cost_records')
    
    op.drop_index(op.f('ix_audit_logs_user_id'), table_name='audit_logs')
    op.drop_index(op.f('ix_audit_logs_tenant_id'), table_name='audit_logs')
    op.drop_index(op.f('ix_audit_logs_resource'), table_name='audit_logs')
    op.drop_index(op.f('ix_audit_logs_id'), table_name='audit_logs')
    op.drop_index(op.f('ix_audit_logs_action'), table_name='audit_logs')
    op.drop_index('ix_audit_tenant_time', table_name='audit_logs')
    op.drop_table('audit_logs')
    
    op.drop_index(op.f('ix_provisioning_requests_tenant_id'), table_name='provisioning_requests')
    op.drop_index(op.f('ix_provisioning_requests_status'), table_name='provisioning_requests')
    op.drop_index(op.f('ix_provisioning_requests_resource_type'), table_name='provisioning_requests')
    op.drop_index(op.f('ix_provisioning_requests_id'), table_name='provisioning_requests')
    op.drop_table('provisioning_requests')
    
    op.drop_index(op.f('ix_agents_tenant_id'), table_name='agents')
    op.drop_index(op.f('ix_agents_status'), table_name='agents')
    op.drop_index(op.f('ix_agents_name'), table_name='agents')
    op.drop_index(op.f('ix_agents_id'), table_name='agents')
    op.drop_index(op.f('ix_agents_adapter_id'), table_name='agents')
    op.drop_table('agents')
    
    op.drop_index(op.f('ix_users_tenant_id'), table_name='users')
    op.drop_index(op.f('ix_users_role_id'), table_name='users')
    op.drop_index(op.f('ix_users_id'), table_name='users')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')
    
    op.drop_index(op.f('ix_roles_tenant_id'), table_name='roles')
    op.drop_index(op.f('ix_roles_id'), table_name='roles')
    op.drop_table('roles')

    # Drop Parent Domains (Root Level)
    op.drop_index(op.f('ix_tenants_status'), table_name='tenants')
    op.drop_index(op.f('ix_tenants_name'), table_name='tenants')
    op.drop_index(op.f('ix_tenants_id'), table_name='tenants')
    op.drop_index(op.f('ix_tenants_domain'), table_name='tenants')
    op.drop_table('tenants')
    
    op.drop_index(op.f('ix_adapters_status'), table_name='adapters')
    op.drop_index(op.f('ix_adapters_provider_type'), table_name='adapters')
    op.drop_index(op.f('ix_adapters_name'), table_name='adapters')
    op.drop_index(op.f('ix_adapters_id'), table_name='adapters')
    op.drop_table('adapters')
    
    op.drop_index(op.f('ix_platform_settings_id'), table_name='platform_settings')
    op.drop_index(op.f('ix_platform_settings_category'), table_name='platform_settings')
    op.drop_table('platform_settings')
