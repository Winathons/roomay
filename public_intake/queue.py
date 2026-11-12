"""Formnow-style temporary public inquiry queue; never the hotel source of truth.

Only a separately Workpeg-authenticated Peg can copy a queued item into
canonical Workpeg Tables. This code never calls Workpeg or issues a token.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import hashlib
import hmac
import json
import secrets
from uuid import UUID, uuid4

from sqlalchemy import Boolean, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, and_, delete, or_, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


QUEUE_TTL_SECONDS = 72 * 3600
ACKED_TTL_SECONDS = 24 * 3600
LEASE_SECONDS = 120
RATE_PER_MINUTE = 20


class Base(DeclarativeBase):
    pass


class IntakePortal(Base):
    """Opaque business-bound public link set up by an owner, never by a guest."""

    __tablename__ = "roomay_intake_portals"
    portal_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    business_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    hotel_id: Mapped[str] = mapped_column(String(36), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class QueuedInquiry(Base):
    """Temporary unverified booking interest; NOT a reservation or staff ticket."""

    __tablename__ = "roomay_intake_queued_inquiries"
    __table_args__ = (
        UniqueConstraint("portal_id", "idempotency_key", name="uq_roomay_intake_portal_key"),
    )
    inquiry_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    portal_id: Mapped[str] = mapped_column(String(36), ForeignKey(IntakePortal.portal_id), index=True)
    business_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    hotel_id: Mapped[str] = mapped_column(String(36), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(36), nullable=False)
    content_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    # PII is held temporarily and must be purged; never log or return publicly.
    data: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[int] = mapped_column(Integer, nullable=False)
    expires_at: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    lease_token_digest: Mapped[str | None] = mapped_column(String(64))
    lease_owner_digest: Mapped[str | None] = mapped_column(String(64))
    leased_until: Mapped[int | None] = mapped_column(Integer)
    acknowledged_at: Mapped[int | None] = mapped_column(Integer)
    workpeg_table_uuid: Mapped[str | None] = mapped_column(String(36))
    workpeg_row_id: Mapped[int | None] = mapped_column(Integer)


class RateWindow(Base):
    __tablename__ = "roomay_intake_rate_windows"
    portal_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    address_digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    window: Mapped[int] = mapped_column(Integer, primary_key=True)
    hits: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class IntakeError(ValueError):
    def __init__(self, code: str, status: int = 400):
        super().__init__(code)
        self.code, self.status = code, status


def canonical_uuid(value: str) -> str:
    try:
        parsed = UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        raise IntakeError("invalid_identifier", 422) from None
    if str(parsed) != value:
        raise IntakeError("invalid_identifier", 422)
    return str(parsed)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def normalized_inquiry(data: dict, today: date) -> dict:
    """Validate public data before it is staged; not availability/identity proof."""
    if not isinstance(data, dict) or set(data) != {
        "arrival", "departure", "party_size", "email", "room_type", "note", "consent"
    }:
        raise IntakeError("invalid_inquiry", 422)
    if data["consent"] is not True:
        raise IntakeError("consent_required", 422)
    try:
        arrival = date.fromisoformat(data["arrival"])
        departure = date.fromisoformat(data["departure"])
    except (TypeError, ValueError, AttributeError):
        raise IntakeError("invalid_stay_dates", 422) from None
    if (arrival < today or arrival > today + timedelta(days=365)
            or not 1 <= (departure - arrival).days <= 30):
        raise IntakeError("invalid_stay_dates", 422)
    party = data["party_size"]
    if type(party) is not int or not 1 <= party <= 12:
        raise IntakeError("invalid_party_size", 422)
    email = data["email"]
    if not isinstance(email, str):
        raise IntakeError("invalid_contact_email", 422)
    email = email.strip().lower()
    if (len(email) > 254 or len(email) < 6 or any(c.isspace() for c in email)
            or any(ord(c) < 32 or ord(c) >= 127 for c in email)
            or email.count("@") != 1):
        raise IntakeError("invalid_contact_email", 422)
    left, host = email.rsplit("@", 1)
    if not left or not host or "." not in host or host.startswith(".") or host.endswith("."):
        raise IntakeError("invalid_contact_email", 422)
    fields = {}
    for name, limit in (("room_type", 80), ("note", 500)):
        val = data[name]
        if not isinstance(val, str):
            raise IntakeError("invalid_inquiry", 422)
        val = val.strip()
        if len(val) > limit or any(ord(c) < 32 and c not in "\n\t" for c in val):
            raise IntakeError("invalid_inquiry", 422)
        fields[name] = val
    return {
        "arrival": arrival.isoformat(), "departure": departure.isoformat(),
        "party_size": party, "email": email, **fields,
    }


def content_digest(data: dict) -> str:
    # Stable canonical representation; does not put personal data in logs.
    return _digest(json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True))


def check_rate_limit(db, portal_id: str, address: str, secret: bytes, now: int) -> None:
    if len(secret) < 32:
        raise RuntimeError("intake_rate_limit_key_missing")
    key = hmac.new(secret, (portal_id + "\x00" + address).encode(), hashlib.sha256).hexdigest()
    window = now // 60
    existing = db.scalar(select(RateWindow).where(
        RateWindow.portal_id == portal_id, RateWindow.address_digest == key,
        RateWindow.window == window).with_for_update())
    if existing is None:
        db.add(RateWindow(portal_id=portal_id, address_digest=key, window=window, hits=1))
    elif existing.hits >= RATE_PER_MINUTE:
        raise IntakeError("rate_limited", 429)
    else:
        existing.hits += 1
    # A competing creation of the rate row fails closed and may be retried.


def enqueue(db, *, portal_id: str, idempotency_key: str, data: dict,
            address: str, secret: bytes, now: int) -> QueuedInquiry:
    portal_id = canonical_uuid(portal_id)
    idempotency_key = canonical_uuid(idempotency_key)
    portal = db.get(IntakePortal, portal_id)
    if portal is None or not portal.active:
        raise IntakeError("portal_unavailable", 404)
    today = datetime.fromtimestamp(now, timezone.utc).date()
    body = normalized_inquiry(data, today)
    hash_value = content_digest(body)
    check_rate_limit(db, portal_id, address, secret, now)
    existing = db.scalar(select(QueuedInquiry).where(
        QueuedInquiry.portal_id == portal_id,
        QueuedInquiry.idempotency_key == idempotency_key).with_for_update())
    if existing is not None:
        if existing.content_digest != hash_value:
            raise IntakeError("idempotency_conflict", 409)
        if existing.expires_at <= now and existing.acknowledged_at is None:
            raise IntakeError("inquiry_expired", 410)
        return existing
    item = QueuedInquiry(
        inquiry_id=str(uuid4()), portal_id=portal_id,
        business_id=portal.business_id, hotel_id=portal.hotel_id,
        idempotency_key=idempotency_key, content_digest=hash_value,
        data=body, created_at=now, expires_at=now + QUEUE_TTL_SECONDS)
    db.add(item)
    db.flush()  # Commit before the public HTTP response; duplicates fail closed.
    return item


def lease(db, *, business_id: str, hotel_id: str, subject: str, now: int, limit: int = 20) -> list[dict]:
    if not 1 <= limit <= 20:
        raise IntakeError("invalid_lease_limit", 422)
    business_id = canonical_uuid(business_id)
    hotel_id = canonical_uuid(hotel_id)
    if not isinstance(subject, str) or not subject:
        raise IntakeError("staff_authentication_required", 401)
    query = (select(QueuedInquiry).join(IntakePortal)
             .where(QueuedInquiry.business_id == business_id,
                    QueuedInquiry.hotel_id == hotel_id,
                    IntakePortal.active.is_(True),
                    QueuedInquiry.acknowledged_at.is_(None),
                    QueuedInquiry.expires_at > now,
                    or_(QueuedInquiry.leased_until.is_(None),
                        QueuedInquiry.leased_until <= now))
             .order_by(QueuedInquiry.created_at, QueuedInquiry.inquiry_id)
             .limit(limit).with_for_update(skip_locked=True))
    out = []
    for item in db.scalars(query).all():
        lease_token = secrets.token_urlsafe(32)
        item.lease_token_digest = _digest(lease_token)
        item.lease_owner_digest = _digest(business_id + ":" + subject)
        item.leased_until = now + LEASE_SECONDS
        out.append({
            "id": item.inquiry_id,
            "business_id": item.business_id,
            "hotel_id": item.hotel_id,
            "payload_digest": item.content_digest,
            "data": dict(item.data),
            "lease_token": lease_token,
            "expires_at": item.expires_at,
        })
    db.flush()
    return out


def acknowledge(db, *, business_id: str, hotel_id: str, subject: str, inquiry_id: str,
                lease_token: str, readback: dict, now: int) -> bool:
    """Acknowledge only a still-owned lease with a matching readback receipt.

    The *staff Peg* must obtain readback from Workpeg itself; this external
    server has no Workpeg credential and cannot independently attest the row.
    """
    business_id = canonical_uuid(business_id)
    hotel_id = canonical_uuid(hotel_id)
    inquiry_id = canonical_uuid(inquiry_id)
    item = db.scalar(select(QueuedInquiry).where(
        QueuedInquiry.inquiry_id == inquiry_id,
        QueuedInquiry.business_id == business_id,
        QueuedInquiry.hotel_id == hotel_id).with_for_update())
    if item is None:
        raise IntakeError("inquiry_unavailable", 404)
    if item.acknowledged_at is not None:
        return False
    if (not isinstance(lease_token, str) or not item.lease_token_digest
            or not secrets.compare_digest(item.lease_token_digest, _digest(lease_token))
            or item.lease_owner_digest != _digest(business_id + ":" + subject)
            or item.leased_until is None or item.leased_until <= now
            or item.expires_at <= now):
        raise IntakeError("lease_invalid", 409)
    if not isinstance(readback, dict) or set(readback) != {
        "source_id", "business_id", "hotel_id", "payload_digest", "table_uuid", "row_id"
    }:
        raise IntakeError("workpeg_readback_required", 409)
    if not (readback["source_id"] == item.inquiry_id
            and readback["business_id"] == item.business_id
            and readback["hotel_id"] == item.hotel_id
            and readback["payload_digest"] == item.content_digest
            and type(readback["row_id"]) is int and readback["row_id"] > 0):
        raise IntakeError("workpeg_readback_mismatch", 409)
    table_uuid = canonical_uuid(readback["table_uuid"])
    item.workpeg_row_id = readback["row_id"]
    item.workpeg_table_uuid = table_uuid
    item.acknowledged_at = now
    # Keep only the minimal receipt after successful acknowledgement; remove PII.
    item.data = {}
    item.lease_token_digest = None
    item.lease_owner_digest = None
    item.leased_until = None
    db.flush()
    return True


def purge_expired(db, *, now: int) -> int:
    """Run from an owner-managed retention job; not an exposed HTTP route."""
    count = db.execute(delete(QueuedInquiry).where(or_(
        and_(QueuedInquiry.acknowledged_at.is_(None), QueuedInquiry.expires_at <= now),
        and_(QueuedInquiry.acknowledged_at.is_not(None),
             QueuedInquiry.acknowledged_at <= now - ACKED_TTL_SECONDS)
    ))).rowcount
    db.execute(delete(RateWindow).where(RateWindow.window < (now // 60) - 2))
    return count
