"""PostgreSQL persistence for guest invitations and service-request operations."""
from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON, Uuid


class Base(DeclarativeBase):
    pass


JSONType = JSON().with_variant(JSONB, "postgresql")
UUIDType = Uuid(as_uuid=False).with_variant(PGUUID(as_uuid=False), "postgresql")


class HotelBinding(Base):
    __tablename__ = "hotel_bindings"
    business_id: Mapped[str] = mapped_column(UUIDType, primary_key=True)
    hotel_id: Mapped[str] = mapped_column(UUIDType, nullable=False, unique=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class StaffBinding(Base):
    __tablename__ = "staff_bindings"
    __table_args__ = (UniqueConstraint("business_id", "workpeg_subject", name="uq_staff_business_subject"),)
    id: Mapped[str] = mapped_column(UUIDType, primary_key=True)
    business_id: Mapped[str] = mapped_column(UUIDType, ForeignKey("hotel_bindings.business_id"), index=True)
    hotel_id: Mapped[str] = mapped_column(UUIDType, index=True)
    workpeg_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    department: Mapped[str] = mapped_column(String(40), nullable=False)
    roles: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class OIDCState(Base):
    __tablename__ = "oidc_states"
    state_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    nonce: Mapped[str] = mapped_column(Text, nullable=False)
    verifier: Mapped[str] = mapped_column(Text, nullable=False)
    browser_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class StaffSession(Base):
    __tablename__ = "staff_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    workpeg_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    business_id: Mapped[str] = mapped_column(UUIDType, nullable=False, index=True)
    workpeg_role: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class GuestInvitation(Base):
    __tablename__ = "guest_invitations"
    invitation_id: Mapped[str] = mapped_column(UUIDType, primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    business_id: Mapped[str] = mapped_column(UUIDType, nullable=False, index=True)
    hotel_id: Mapped[str] = mapped_column(UUIDType, nullable=False, index=True)
    guest_id: Mapped[str] = mapped_column(UUIDType, nullable=False)
    stay_id: Mapped[str] = mapped_column(UUIDType, nullable=False)
    room_id: Mapped[str] = mapped_column(UUIDType, nullable=False)
    issued_by: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    redeemed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class GuestSession(Base):
    __tablename__ = "guest_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    business_id: Mapped[str] = mapped_column(UUIDType, nullable=False, index=True)
    hotel_id: Mapped[str] = mapped_column(UUIDType, nullable=False, index=True)
    guest_id: Mapped[str] = mapped_column(UUIDType, nullable=False)
    stay_id: Mapped[str] = mapped_column(UUIDType, nullable=False)
    room_id: Mapped[str] = mapped_column(UUIDType, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PendingRequest(Base):
    __tablename__ = "pending_requests"
    __table_args__ = (UniqueConstraint("session_hash", "operation_key",
                                       name="uq_pending_session_operation"),)
    id: Mapped[str] = mapped_column(UUIDType, primary_key=True)
    session_hash: Mapped[str] = mapped_column(String(64), ForeignKey("guest_sessions.token_hash"), index=True)
    operation_key: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONType, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OperationalRequest(Base):
    __tablename__ = "operational_requests"
    __table_args__ = (
        UniqueConstraint("hotel_id", "idempotency_key", name="uq_request_hotel_idempotency"),
        UniqueConstraint("business_id", "request_id", name="uq_request_business_id"),
    )
    request_id: Mapped[str] = mapped_column(UUIDType, primary_key=True)
    business_id: Mapped[str] = mapped_column(UUIDType, nullable=False, index=True)
    hotel_id: Mapped[str] = mapped_column(UUIDType, nullable=False, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    request_data: Mapped[dict] = mapped_column(JSONType, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class OperationalAudit(Base):
    __tablename__ = "operational_request_audit"
    __table_args__ = (
        UniqueConstraint("request_id", "sequence", name="uq_audit_request_sequence"),
        UniqueConstraint("business_id", "operation_id", name="uq_audit_business_operation"),
    )
    event_id: Mapped[str] = mapped_column(UUIDType, primary_key=True)
    business_id: Mapped[str] = mapped_column(UUIDType, nullable=False, index=True)
    hotel_id: Mapped[str] = mapped_column(UUIDType, nullable=False, index=True)
    request_id: Mapped[str] = mapped_column(UUIDType, ForeignKey("operational_requests.request_id", ondelete="CASCADE"), index=True)
    operation_id: Mapped[str] = mapped_column(UUIDType, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_data: Mapped[dict] = mapped_column(JSONType, nullable=False)
    commit_state: Mapped[str] = mapped_column(String(16), nullable=False, default="committed")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
