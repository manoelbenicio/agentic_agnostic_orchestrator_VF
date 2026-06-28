"""Initial provisioning schema.

Revision ID: 001_initial_provisioning
Revises:
Create Date: 2026-06-28
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "001_initial_provisioning"
down_revision = None
branch_labels = None
depends_on = None

SCHEMA = "aop_provisioning"


def upgrade() -> None:
    op.execute(sa.text(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}"))

    op.create_table(
        "provisioning_requests",
        sa.Column("request_id", sa.Text(), primary_key=True),
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("target", sa.Text(), nullable=False),
        sa.Column("stable_key", sa.Text(), nullable=True),
        sa.Column("requested_by", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        schema=SCHEMA,
    )
    op.create_index(
        "provisioning_requests_tenant_project_idx",
        "provisioning_requests",
        ["tenant_id", "project_id"],
        schema=SCHEMA,
    )
    op.create_index(
        "provisioning_requests_status_idx",
        "provisioning_requests",
        ["status"],
        schema=SCHEMA,
    )
    op.create_index(
        "provisioning_requests_stable_key_idx",
        "provisioning_requests",
        ["stable_key"],
        schema=SCHEMA,
    )

    op.create_table(
        "activation_results",
        sa.Column("activation_id", sa.Text(), primary_key=True),
        sa.Column(
            "request_id",
            sa.Text(),
            sa.ForeignKey(f"{SCHEMA}.provisioning_requests.request_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("target", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        schema=SCHEMA,
    )
    op.create_index(
        "activation_results_request_id_idx",
        "activation_results",
        ["request_id"],
        schema=SCHEMA,
    )
    op.create_index(
        "activation_results_status_idx",
        "activation_results",
        ["status"],
        schema=SCHEMA,
    )

    op.create_table(
        "activation_steps",
        sa.Column("step_id", sa.Text(), primary_key=True),
        sa.Column(
            "activation_id",
            sa.Text(),
            sa.ForeignKey(f"{SCHEMA}.activation_results.activation_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("step_name", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        schema=SCHEMA,
    )
    op.create_index(
        "activation_steps_activation_id_idx",
        "activation_steps",
        ["activation_id"],
        schema=SCHEMA,
    )
    op.create_index(
        "activation_steps_status_idx",
        "activation_steps",
        ["status"],
        schema=SCHEMA,
    )
    op.create_index(
        "activation_steps_name_idx",
        "activation_steps",
        ["step_name"],
        schema=SCHEMA,
    )

    op.create_table(
        "failed_activations",
        sa.Column("failure_id", sa.Text(), primary_key=True),
        sa.Column(
            "activation_id",
            sa.Text(),
            sa.ForeignKey(f"{SCHEMA}.activation_results.activation_id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "request_id",
            sa.Text(),
            sa.ForeignKey(f"{SCHEMA}.provisioning_requests.request_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("failed_step", sa.Text(), nullable=True),
        sa.Column("error_type", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=False),
        sa.Column("retryable", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        schema=SCHEMA,
    )
    op.create_index(
        "failed_activations_activation_id_idx",
        "failed_activations",
        ["activation_id"],
        schema=SCHEMA,
    )
    op.create_index(
        "failed_activations_request_id_idx",
        "failed_activations",
        ["request_id"],
        schema=SCHEMA,
    )
    op.create_index(
        "failed_activations_retryable_idx",
        "failed_activations",
        ["retryable"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_index("failed_activations_retryable_idx", table_name="failed_activations", schema=SCHEMA)
    op.drop_index("failed_activations_request_id_idx", table_name="failed_activations", schema=SCHEMA)
    op.drop_index("failed_activations_activation_id_idx", table_name="failed_activations", schema=SCHEMA)
    op.drop_table("failed_activations", schema=SCHEMA)

    op.drop_index("activation_steps_name_idx", table_name="activation_steps", schema=SCHEMA)
    op.drop_index("activation_steps_status_idx", table_name="activation_steps", schema=SCHEMA)
    op.drop_index("activation_steps_activation_id_idx", table_name="activation_steps", schema=SCHEMA)
    op.drop_table("activation_steps", schema=SCHEMA)

    op.drop_index("activation_results_status_idx", table_name="activation_results", schema=SCHEMA)
    op.drop_index("activation_results_request_id_idx", table_name="activation_results", schema=SCHEMA)
    op.drop_table("activation_results", schema=SCHEMA)

    op.drop_index("provisioning_requests_stable_key_idx", table_name="provisioning_requests", schema=SCHEMA)
    op.drop_index("provisioning_requests_status_idx", table_name="provisioning_requests", schema=SCHEMA)
    op.drop_index("provisioning_requests_tenant_project_idx", table_name="provisioning_requests", schema=SCHEMA)
    op.drop_table("provisioning_requests", schema=SCHEMA)

