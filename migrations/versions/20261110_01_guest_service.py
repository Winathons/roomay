"""Create Roomay guest access, service request, and audit tables."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261110_01"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("hotel_bindings",
        sa.Column("business_id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("hotel_id", postgresql.UUID(as_uuid=False), nullable=False, unique=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.create_table("staff_bindings",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("business_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("hotel_bindings.business_id"), nullable=False),
        sa.Column("hotel_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("workpeg_subject", sa.String(255), nullable=False),
        sa.Column("actor_id", sa.String(255), nullable=False, unique=True),
        sa.Column("department", sa.String(40), nullable=False),
        sa.Column("roles", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("business_id", "workpeg_subject", name="uq_staff_business_subject"))
    op.create_index("ix_staff_bindings_business_id", "staff_bindings", ["business_id"])
    op.create_index("ix_staff_bindings_hotel_id", "staff_bindings", ["hotel_id"])
    op.create_table("oidc_states",
        sa.Column("state_hash", sa.String(64), primary_key=True),
        sa.Column("nonce", sa.Text(), nullable=False),
        sa.Column("verifier", sa.Text(), nullable=False),
        sa.Column("browser_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.create_table("staff_sessions",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("workpeg_subject", sa.String(255), nullable=False),
        sa.Column("business_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("workpeg_role", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)))
    op.create_index("ix_staff_sessions_business_id", "staff_sessions", ["business_id"])
    op.create_index("ix_staff_sessions_expires_at", "staff_sessions", ["expires_at"])
    op.create_table("guest_invitations",
        sa.Column("invitation_id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("business_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("hotel_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("guest_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("stay_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("room_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("issued_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("redeemed_at", sa.DateTime(timezone=True)))
    op.create_index("ix_guest_invitations_business_id", "guest_invitations", ["business_id"])
    op.create_index("ix_guest_invitations_hotel_id", "guest_invitations", ["hotel_id"])
    op.create_index("ix_guest_invitations_expires_at", "guest_invitations", ["expires_at"])
    op.create_index("ix_guest_invitations_issued_by", "guest_invitations", ["issued_by"])
    op.create_table("guest_sessions",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("business_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("hotel_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("guest_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("stay_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("room_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)))
    op.create_index("ix_guest_sessions_business_id", "guest_sessions", ["business_id"])
    op.create_index("ix_guest_sessions_hotel_id", "guest_sessions", ["hotel_id"])
    op.create_index("ix_guest_sessions_expires_at", "guest_sessions", ["expires_at"])
    op.create_table("pending_requests",
        sa.UniqueConstraint("session_hash", "operation_key", name="uq_pending_session_operation"),
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("session_hash", sa.String(64), sa.ForeignKey("guest_sessions.token_hash"), nullable=False),
        sa.Column("operation_key", sa.String(64), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)))
    op.create_index("ix_pending_requests_session_hash", "pending_requests", ["session_hash"])
    op.create_index("ix_pending_requests_expires_at", "pending_requests", ["expires_at"])
    op.create_table("operational_requests",
        sa.Column("request_id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("business_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("hotel_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("request_data", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("hotel_id", "idempotency_key", name="uq_request_hotel_idempotency"),
        sa.UniqueConstraint("business_id", "request_id", name="uq_request_business_id"))
    op.create_index("ix_operational_requests_business_id", "operational_requests", ["business_id"])
    op.create_index("ix_operational_requests_hotel_id", "operational_requests", ["hotel_id"])
    op.create_table("operational_request_audit",
        sa.Column("event_id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("business_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("hotel_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("request_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("operational_requests.request_id", ondelete="CASCADE"), nullable=False),
        sa.Column("operation_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_data", postgresql.JSONB(), nullable=False),
        sa.Column("commit_state", sa.String(16), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("request_id", "sequence", name="uq_audit_request_sequence"),
        sa.UniqueConstraint("business_id", "operation_id", name="uq_audit_business_operation"))
    op.create_index("ix_operational_request_audit_business_id", "operational_request_audit", ["business_id"])
    op.create_index("ix_operational_request_audit_hotel_id", "operational_request_audit", ["hotel_id"])
    op.create_index("ix_operational_request_audit_request_id", "operational_request_audit", ["request_id"])

def downgrade():
    op.drop_table("operational_request_audit")
    op.drop_table("operational_requests")
    op.drop_table("pending_requests")
    op.drop_table("guest_sessions")
    op.drop_table("guest_invitations")
    op.drop_table("staff_sessions")
    op.drop_table("oidc_states")
    op.drop_table("staff_bindings")
    op.drop_table("hotel_bindings")
