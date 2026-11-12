"""WOR-13: authorization-gated reservation desk *plans*, never Workpeg writes.

The standalone pure model cannot verify a Workpeg staff session, acquire a real
serialization guard, or persist a committed audit. Only a future trusted
provider adapter may supply those capabilities; do not expose these plans as
successful confirmed or cancelled reservations.
"""
from dataclasses import dataclass
from datetime import timedelta
from hashlib import sha256
import json
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .hotel import parse_day, parse_instant, validate_snapshot
from .reservation_commands import (
    ReservationRejected, WriteContext, _idempotency_key, _uuid, _write_gate,
    prepare_authorized_room_confirmation, prepare_cancellation,
)


@dataclass(frozen=True)
class StaffReservationReview:
    """Assertions that only a trusted staff adapter may derive and issue.

    Boolean values supplied by a browser/AI do not establish actual proof.
    Avoid guest PII, rates, contact details and payment evidence in this object.
    """

    reservation_id: str
    reviewed_by_actor_id: str
    reviewed_at: str
    inventory_reviewed: bool
    booking_terms_reviewed: bool


@dataclass(frozen=True)
class ReservationDecisionPlan:
    """Unpersisted reservation row transition plus future audit requirements."""

    action: str
    operation_id: str
    idempotency_key: str
    operation_signature: str
    reservation_id: str
    reservation_before: dict
    reservation_after: dict
    audit_intent: dict
    requires_authoritative_guard: bool = True
    requires_durable_idempotency: bool = True
    requires_committed_audit: bool = True
    requires_complete_readback: bool = True
    persisted: bool = False


def _authoritative_instant(context):
    _write_gate(context)
    try:
        return parse_instant(context.authoritative_now)
    except (TypeError, ValueError, OverflowError):
        raise ReservationRejected("authoritative_clock_unavailable") from None


def _text(value, reason, *, limit=500):
    if not isinstance(value, str) or not 3 <= len(value.strip()) <= limit:
        raise ReservationRejected(reason)
    return value.strip()


def _snapshot(snapshot):
    try:
        return validate_snapshot(snapshot)
    except (ValueError, TypeError, KeyError):
        raise ReservationRejected("invalid_or_incomplete_snapshot") from None


def _operation(action, context, idempotency_key, before, after, details,
               prior_operation):
    key = _idempotency_key(idempotency_key)
    scope = f"roomay:reservation-desk:v1:{context.business_id}:{key}"
    operation_id = str(uuid5(NAMESPACE_URL, scope))
    payload = {
        "action": action, "actor_id": context.actor_id,
        "reservation_before": before, "reservation_after": after,
        "details": details,
    }
    signature = sha256(json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode("utf-8")).hexdigest()
    if prior_operation is not None:
        if not isinstance(prior_operation, dict) or prior_operation.get(
                "idempotency_key") != key:
            raise ReservationRejected("invalid_prior_operation")
        if (prior_operation.get("operation_id") != operation_id
                or prior_operation.get("operation_signature") != signature):
            raise ReservationRejected("idempotency_key_reused_for_different_operation")
        raise ReservationRejected("operation_already_attempted_readback_required")
    return operation_id, key, signature


def _decision(action, reservation_id, before, after, context, now, key, details,
              prior_operation):
    operation_id, key, signature = _operation(
        action, context, key, before, after, details, prior_operation,
    )
    audit = {
        "action": action, "operation_id": operation_id,
        "business_id": context.business_id, "actor_id": context.actor_id,
        "reservation_id": reservation_id, "occurred_at": now.isoformat(),
        "from_status": before["status"], "to_status": after["status"],
        "from_room_id": before.get("room_id"),
        "to_room_id": after.get("room_id"),
        **details,
    }
    return ReservationDecisionPlan(
        action=action, operation_id=operation_id,
        idempotency_key=key, operation_signature=signature,
        reservation_id=reservation_id,
        reservation_before=dict(before), reservation_after=dict(after),
        audit_intent=audit,
    )


def prepare_staff_confirmation(
    snapshot, *, reservation_id, room_id, review, idempotency_key,
    context, hotel_timezone, prior_operation=None,
):
    """Recheck pending inventory and propose a staff confirmation + audit.

    A dirty room can be reserved for a *future* arrival but is not check-in
    eligible until housekeeping signs off. No room is occupied by this plan.
    """
    now = _authoritative_instant(context)
    index = _snapshot(snapshot)
    reservation_id = _uuid(reservation_id, "reservation_id")
    booking = index["reservations"].get(reservation_id)
    if booking is None:
        raise ReservationRejected("unknown_reservation")
    if not isinstance(review, StaffReservationReview):
        raise ReservationRejected("trusted_staff_review_required")
    if review.reservation_id != reservation_id:
        raise ReservationRejected("review_reservation_mismatch")
    if review.reviewed_by_actor_id != context.actor_id:
        raise ReservationRejected("review_actor_mismatch")
    if review.inventory_reviewed is not True:
        raise ReservationRejected("inventory_review_required")
    if review.booking_terms_reviewed is not True:
        raise ReservationRejected("booking_terms_review_required")
    try:
        reviewed_at = parse_instant(review.reviewed_at)
    except (TypeError, ValueError, OverflowError):
        raise ReservationRejected("valid_review_timestamp_required") from None
    if reviewed_at > now or now - reviewed_at > timedelta(minutes=30):
        raise ReservationRejected("staff_review_stale_or_future")
    if not isinstance(hotel_timezone, str) or not hotel_timezone.strip():
        raise ReservationRejected("authoritative_hotel_timezone_required")
    try:
        hotel_day = now.astimezone(ZoneInfo(hotel_timezone)).date()
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        raise ReservationRejected("authoritative_hotel_timezone_unavailable") from None
    if parse_day(booking["departure"]) <= hotel_day:
        raise ReservationRejected("booking_departure_already_passed")
    plan = prepare_authorized_room_confirmation(
        snapshot, reservation_id=reservation_id, room_id=room_id, context=context,
    )
    return _decision(
        "confirm_reservation", reservation_id, booking, plan.record,
        context, now, idempotency_key,
        {"reviewed_at": reviewed_at.isoformat(),
         "inventory_reviewed": True, "booking_terms_reviewed": True},
        prior_operation,
    )


def prepare_staff_cancellation(
    snapshot, *, reservation_id, reason, idempotency_key,
    context, prior_operation=None,
):
    """Cancel only a reservation with no linked stay; never free real occupancy."""
    now = _authoritative_instant(context)
    index = _snapshot(snapshot)
    reservation_id = _uuid(reservation_id, "reservation_id")
    booking = index["reservations"].get(reservation_id)
    if booking is None:
        raise ReservationRejected("unknown_reservation")
    reason = _text(reason, "cancellation_reason_required")
    plan = prepare_cancellation(
        snapshot, reservation_id=reservation_id, staff_authorized=True,
    )
    if plan.action == "already_cancelled":
        raise ReservationRejected("operation_already_attempted_readback_required")
    return _decision(
        "cancel_reservation", reservation_id, booking, plan.record, context,
        now, idempotency_key, {"cancellation_reason": reason}, prior_operation,
    )


def reconcile_reservation_decision(
    plan, snapshot, *, context, operation_record=None,
):
    """Classify an observed row with matching *committed* audit evidence.

    A matching row alone does NOT prove server authorization or completed
    audit. Both the operation identity and audit proof must come from a trusted
    durable store. Failed/uncertain writes require manual reconciliation.
    """
    _write_gate(context)
    if not isinstance(plan, ReservationDecisionPlan):
        raise ReservationRejected("invalid_reservation_decision_plan")
    if (not isinstance(operation_record, dict)
            or operation_record.get("operation_id") != plan.operation_id
            or operation_record.get("idempotency_key") != plan.idempotency_key
            or operation_record.get("operation_signature") != plan.operation_signature
            or operation_record.get("audit_committed") is not True):
        return "operation_or_audit_evidence_missing_manual_reconciliation"
    try:
        index = validate_snapshot(snapshot)
    except (ValueError, TypeError, KeyError):
        return "invalid_readback_manual_reconciliation"
    observed = index["reservations"].get(plan.reservation_id)
    if observed == plan.reservation_after:
        return "reservation_decision_observed_do_not_repeat"
    if observed == plan.reservation_before:
        return "source_state_observed_manual_reconciliation"
    return "partial_or_conflicting_state_manual_reconciliation"
