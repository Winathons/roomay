"""WOR-11: offline front-desk verification before planning physical check-in.

Attestations are requirements for a future authenticated staff writer, not
credentials. No guest IDs, payment state, QR token or booking row is written.
Never construct an attestation directly from browser-supplied booleans.
"""
from dataclasses import dataclass
from datetime import timedelta
from hashlib import sha256
import json
from uuid import NAMESPACE_URL, uuid5

from .hotel import parse_instant, validate_snapshot
from .reservation_commands import (
    CheckInPlan, ReservationRejected, WriteContext, _idempotency_key,
    _uuid, _write_gate, prepare_check_in, reconcile_check_in_readback,
)


@dataclass(frozen=True)
class FrontDeskVerification:
    """A trusted adapter must derive these fields from verified staff evidence.

    Store no ID photos/numbers, contact details, payment screenshots or raw
    QR bearer codes here. A hotel may choose a supported payment disposition,
    but 'provider_paid' is reserved for server-verified provider events.
    """

    reservation_id: str
    primary_guest_id: str
    occupant_guest_ids: tuple[str, ...]
    reviewed_by_actor_id: str
    reviewed_at: str
    identity_verified_in_person: bool
    contact_confirmed: bool
    rate_reviewed: bool
    payment_disposition: str
    payment_evidence_source: str


@dataclass(frozen=True)
class VerifiedCheckInPlan:
    """Contains an unpersisted CheckInPlan plus a separate audit intent."""

    check_in: CheckInPlan
    operation_id: str
    idempotency_key: str
    operation_signature: str
    audit_intent: dict
    requires_authoritative_guard: bool = True
    requires_durable_idempotency: bool = True
    requires_committed_audit: bool = True
    requires_complete_readback: bool = True
    persisted: bool = False


_ALLOWED_PAYMENT_EVIDENCE = {
    "provider_paid": "verified_provider_callback",
    "payment_deferred": "authorized_hotel_payment_policy",
    "no_payment_due": "authorized_hotel_payment_policy",
}
_REVIEW_MAX_AGE = timedelta(minutes=30)


def _trusted_review(review, *, reservation_id, occupant_guest_ids, context,
                    checked_in_at):
    if not isinstance(review, FrontDeskVerification):
        raise ReservationRejected("trusted_front_desk_review_required")
    if not isinstance(context, WriteContext):
        raise ReservationRejected("trusted_write_context_required")
    if review.reviewed_by_actor_id != context.actor_id:
        raise ReservationRejected("review_actor_mismatch")
    if review.reservation_id != reservation_id:
        raise ReservationRejected("review_reservation_mismatch")
    _uuid(review.primary_guest_id, "primary_guest_id")
    if (not isinstance(review.occupant_guest_ids, tuple)
            or not review.occupant_guest_ids
            or any(not isinstance(guest, str) for guest in review.occupant_guest_ids)):
        raise ReservationRejected("verified_occupants_required")
    verified_ids = tuple(_uuid(guest, "verified_guest_id")
                         for guest in review.occupant_guest_ids)
    if (review.primary_guest_id not in verified_ids
            or len(set(verified_ids)) != len(verified_ids)
            or not isinstance(occupant_guest_ids, (list, tuple))
            or set(verified_ids) != set(occupant_guest_ids)
            or len(verified_ids) != len(occupant_guest_ids)):
        raise ReservationRejected("occupant_verification_mismatch")
    if review.identity_verified_in_person is not True:
        raise ReservationRejected("identity_verification_required")
    if review.contact_confirmed is not True:
        raise ReservationRejected("contact_confirmation_required")
    if review.rate_reviewed is not True:
        raise ReservationRejected("agreed_rate_review_required")
    if _ALLOWED_PAYMENT_EVIDENCE.get(review.payment_disposition) != review.payment_evidence_source:
        raise ReservationRejected("trusted_payment_evidence_required")
    try:
        reviewed_at = parse_instant(review.reviewed_at)
        now = parse_instant(context.authoritative_now)
        checked_in = parse_instant(checked_in_at)
    except (ValueError, TypeError, OverflowError):
        raise ReservationRejected("valid_front_desk_review_time_required") from None
    if (reviewed_at > checked_in or reviewed_at > now
            or checked_in - reviewed_at > _REVIEW_MAX_AGE):
        raise ReservationRejected("front_desk_review_stale_or_future")


def prepare_verified_walk_in_check_in(
    snapshot, *, review, checked_in_at, today, hotel_timezone, idempotency_key,
    context,
):
    """Gate physical walk-in check-in behind fresh in-person staff verification.

    Does not validate payment provider signatures or hotel membership itself.
    The future trusted adapter must obtain review and WriteContext from
    independently authenticated sources, not a QR, AI or browser assertion.
    """
    _write_gate(context)
    try:
        index = validate_snapshot(snapshot)
    except (ValueError, TypeError, KeyError):
        raise ReservationRejected("invalid_or_stale_snapshot") from None
    if not isinstance(review, FrontDeskVerification):
        raise ReservationRejected("trusted_front_desk_review_required")
    reservation_id = _uuid(review.reservation_id, "reservation_id")
    reservation = index["reservations"].get(reservation_id)
    if reservation is None:
        raise ReservationRejected("unknown_reservation")
    if reservation["source"] != "walk_in":
        raise ReservationRejected("walk_in_reservation_required")
    if reservation["guest_id"] != review.primary_guest_id:
        raise ReservationRejected("review_primary_guest_mismatch")
    _trusted_review(
        review, reservation_id=reservation_id,
        occupant_guest_ids=review.occupant_guest_ids,
        context=context, checked_in_at=checked_in_at,
    )
    key = _idempotency_key(idempotency_key)
    check_in = prepare_check_in(
        snapshot, reservation_id=reservation_id,
        occupant_guest_ids=review.occupant_guest_ids,
        checked_in_at=checked_in_at, today=today, hotel_timezone=hotel_timezone,
        idempotency_key=key, context=context,
    )
    payload = {
        "reservation_id": reservation_id, "stay_id": check_in.stay_record["entity_id"],
        "occupant_guest_ids": sorted(review.occupant_guest_ids),
        "reviewed_by_actor_id": review.reviewed_by_actor_id,
        "reviewed_at": review.reviewed_at,
        "checked_in_at": check_in.stay_record["checked_in_at"],
        "payment_disposition": review.payment_disposition,
        "payment_evidence_source": review.payment_evidence_source,
    }
    operation_id = str(uuid5(
        NAMESPACE_URL, f"roomay:verified-walkin-checkin:v1:{context.business_id}:{key}",
    ))
    signature = sha256(json.dumps(
        payload, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()
    audit = {
        "action": "verified_walk_in_check_in_planned",
        "operation_id": operation_id, "business_id": context.business_id,
        "actor_id": context.actor_id, "reservation_id": reservation_id,
        "stay_id": check_in.stay_record["entity_id"],
        "reviewed_at": review.reviewed_at,
        "payment_disposition": review.payment_disposition,
        "payment_evidence_source": review.payment_evidence_source,
        "identity_verified_in_person": True,
    }
    return VerifiedCheckInPlan(
        check_in=check_in, operation_id=operation_id, idempotency_key=key,
        operation_signature=signature, audit_intent=audit,
    )


def reconcile_verified_check_in_readback(
    plan, snapshot, *, context, operation_record=None,
):
    """Fail closed without matching *durable* operation and audit evidence.

    Rows alone do not prove who verified the guest, agreed to the rate, or
    authorized payment terms. Never retry uncertain multi-row writes blindly.
    """
    _write_gate(context)
    if not isinstance(plan, VerifiedCheckInPlan):
        raise ReservationRejected("invalid_verified_check_in_plan")
    if (not isinstance(operation_record, dict)
            or operation_record.get("operation_id") != plan.operation_id
            or operation_record.get("idempotency_key") != plan.idempotency_key
            or operation_record.get("operation_signature") != plan.operation_signature
            or operation_record.get("audit_committed") is not True):
        return "operation_or_audit_evidence_missing_manual_reconciliation"
    state = reconcile_check_in_readback(plan.check_in, snapshot, context=context)
    if state != "expected_rows_observed_do_not_repeat":
        return "committed_audit_and_rows_disagree_manual_reconciliation"
    return "verified_check_in_observed_do_not_repeat"
