"""Reservation command preparation for the *real* Roomay operating system.

These are pure, deterministic business rules. Plans are NEVER persisted by this
module and MUST NOT be interpreted as booked rooms. Workpeg authorization,
fresh state, atomicity/serialization and row read-back are separate mandatory
gates for a production write.

See docs/reservation-operations.md and WOR-9.
"""
from dataclasses import dataclass
from datetime import datetime
from re import fullmatch
from uuid import NAMESPACE_URL, UUID, uuid5
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .hotel import interval, parse_day, room_eligibility, validate_snapshot


class ReservationRejected(ValueError):
    """Typed refusal that UI/server adapters may render without exposing PII."""

    def __init__(self, *reasons):
        self.reasons = tuple(reasons)
        super().__init__(", ".join(reasons))


@dataclass(frozen=True)
class ReservationPlan:
    """Uncommitted write intent. Never proof that a booking exists in Workpeg."""

    action: str
    reservation_id: str
    expected_status: str | None
    record: dict
    # This is a *requirement*, not a capability the current Workpeg UI provides.
    requires_authoritative_guard: bool = True
    persisted: bool = False


@dataclass(frozen=True)
class WriteContext:
    """Claims a future trusted writer must verify outside this pure module.

    Constructing this value is not authentication or a lock. Production code
    must derive it from the authenticated server-side business session and hold
    the serialization guard through authoritative re-read and write.
    """

    business_id: str
    snapshot_business_id: str
    actor_id: str
    actor_role: str
    authorization_verified: bool
    snapshot_fresh: bool
    serialization_guard_held: bool
    authoritative_now: str | None = None


@dataclass(frozen=True)
class CheckInPlan:
    """Separate, uncommitted intent for physical occupancy and occupants."""

    action: str
    reservation_id: str
    stay_record: dict
    occupant_records: tuple
    requires_authoritative_guard: bool = True
    persisted: bool = False


def _write_gate(context, *, require_serialization=True):
    if not isinstance(context, WriteContext):
        raise ReservationRejected("trusted_write_context_required")
    _uuid(context.business_id, "business_id")
    _uuid(context.snapshot_business_id, "snapshot_business_id")
    _uuid(context.actor_id, "actor_id")
    if context.business_id != context.snapshot_business_id:
        raise ReservationRejected("wrong_business")
    if context.authorization_verified is not True or context.actor_role not in {
        "owner", "manager", "receptionist"
    }:
        raise ReservationRejected("authorized_staff_required")
    if context.snapshot_fresh is not True:
        raise ReservationRejected("stale_snapshot")
    if require_serialization and context.serialization_guard_held is not True:
        raise ReservationRejected("authoritative_serialization_unavailable")


def _idempotency_key(value):
    if not isinstance(value, str) or not fullmatch(r"[A-Za-z0-9_-]{12,128}", value):
        raise ReservationRejected("invalid_idempotency_key")
    return value


def _uuid(value, label):
    if not isinstance(value, str):
        raise ReservationRejected("invalid_" + label)
    try:
        if str(UUID(value)) != value:
            raise ValueError("noncanonical")
    except (ValueError, AttributeError):
        raise ReservationRejected("invalid_" + label) from None
    return value


def prepare_booking_request(
    snapshot, *, idempotency_key, guest_id, room_type_id,
    arrival, departure, party_size, source,
):
    """Plan a PENDING request. Requests never reserve inventory or create stays.

    The deterministic UUID allows retries to identify the same logical request
    after refreshing a complete business snapshot. It does NOT make a Workpeg
    row write unique/atomic; the adapter must enforce that separately.
    """
    try:
        index = validate_snapshot(snapshot)
    except (ValueError, TypeError):
        raise ReservationRejected("invalid_or_stale_snapshot") from None
    if not isinstance(idempotency_key, str) or not fullmatch(
        r"[A-Za-z0-9_-]{12,128}", idempotency_key
    ):
        raise ReservationRejected("invalid_idempotency_key")
    guest_id = _uuid(guest_id, "guest_id")
    room_type_id = _uuid(room_type_id, "room_type_id")
    if guest_id not in index["guests"]:
        raise ReservationRejected("unknown_guest")
    if room_type_id not in index["room_types"]:
        raise ReservationRejected("unknown_room_type")
    try:
        interval(arrival, departure)
    except (ValueError, TypeError):
        raise ReservationRejected("invalid_date_range") from None
    if type(party_size) is not int or not (
        1 <= party_size <= index["room_types"][room_type_id]["capacity"]
    ):
        raise ReservationRejected("invalid_party_size")
    if source not in ("advance", "walk_in"):
        raise ReservationRejected("invalid_source")

    reservation_id = str(uuid5(NAMESPACE_URL, "roomay:booking:v1:" + idempotency_key))
    proposed = {
        "entity_id": reservation_id,
        "guest_id": guest_id,
        "room_type_id": room_type_id,
        "arrival": arrival,
        "departure": departure,
        "party_size": party_size,
        "source": source,
        "status": "pending_confirmation",
    }
    existing = index["reservations"].get(reservation_id)
    if existing:
        # Later confirmation/cancellation must not change the immutable request.
        immutable = ("guest_id", "room_type_id", "arrival", "departure", "party_size", "source")
        if any(existing.get(key) != proposed[key] for key in immutable):
            raise ReservationRejected("idempotency_key_reused_for_different_request")
        return ReservationPlan("already_requested", reservation_id, existing["status"], dict(existing))
    return ReservationPlan("create_pending_request", reservation_id, None, proposed)


def prepare_room_confirmation(snapshot, *, reservation_id, room_id, staff_authorized):
    """Propose a staff-reviewed room confirmation; NEVER commit from stale reads.

    A secure adapter must check actual staff permissions server-side and serialize
    competing confirmations for a room/date interval, then verify the saved row.
    """
    try:
        index = validate_snapshot(snapshot)
    except (ValueError, TypeError):
        raise ReservationRejected("invalid_or_stale_snapshot") from None
    reservation_id = _uuid(reservation_id, "reservation_id")
    room_id = _uuid(room_id, "room_id")
    if staff_authorized is not True:
        raise ReservationRejected("authorized_staff_required")
    booking = index["reservations"].get(reservation_id)
    if booking is None:
        raise ReservationRejected("unknown_reservation")
    if booking["status"] != "pending_confirmation":
        raise ReservationRejected("reservation_not_pending")
    if room_id not in index["rooms"]:
        raise ReservationRejected("unknown_room")
    reasons = room_eligibility(snapshot, reservation_id, room_id)
    if reasons:
        raise ReservationRejected(*reasons)

    proposed = dict(booking)
    proposed.update(room_id=room_id, status="confirmed")
    return ReservationPlan("confirm_reservation", reservation_id, "pending_confirmation", proposed)


def prepare_cancellation(snapshot, *, reservation_id, staff_authorized):
    """Plan cancellation only when an actual stay has not used this booking."""
    index = validate_snapshot(snapshot)
    reservation_id = _uuid(reservation_id, "reservation_id")
    if staff_authorized is not True:
        raise ReservationRejected("authorized_staff_required")
    booking = index["reservations"].get(reservation_id)
    if booking is None:
        raise ReservationRejected("unknown_reservation")
    if any(stay["reservation_id"] == reservation_id for stay in snapshot["stays"]):
        raise ReservationRejected("reservation_already_used")
    if booking["status"] == "cancelled":
        return ReservationPlan("already_cancelled", reservation_id, "cancelled", dict(booking))
    proposed = dict(booking)
    proposed["status"] = "cancelled"
    return ReservationPlan("cancel_reservation", reservation_id, booking["status"], proposed)


def prepare_walk_in_request(
    snapshot, *, idempotency_key, guest_id, room_type_id, arrival, departure,
    party_size, context,
):
    """Prepare an unconfirmed walk-in request; it claims no room or occupancy.

    Business identity and authenticated actor context are required. A durable
    create still needs a server-side idempotency/uniqueness gate; the returned
    plan is not evidence that the request was saved.
    """
    _write_gate(context)
    return prepare_booking_request(
        snapshot, idempotency_key=_idempotency_key(idempotency_key),
        guest_id=guest_id, room_type_id=room_type_id, arrival=arrival,
        departure=departure, party_size=party_size, source="walk_in",
    )


def prepare_authorized_room_confirmation(
    snapshot, *, reservation_id, room_id, context,
):
    """Prepare confirmation only with fresh, same-business, serialized authority.

    ``serialization_guard_held`` must represent a real server-side guard held
    through the authoritative re-read and write. The Workpeg SDK currently has
    no documented CAS/transaction primitive, so this gate is unavailable to
    the current UI adapter and confirmation must fail closed there.
    """
    _write_gate(context)
    plan = prepare_room_confirmation(
        snapshot, reservation_id=reservation_id, room_id=room_id,
        staff_authorized=True,
    )
    return plan


def prepare_check_in(
    snapshot, *, reservation_id, occupant_guest_ids, checked_in_at, today,
    hotel_timezone, idempotency_key, context,
):
    """Prepare physical check-in and occupant rows, without saving either.

    This requires a confirmed, assigned reservation; a fresh complete snapshot;
    authorized reception/management; and a server serialization guard. The
    guard requirement intentionally makes this unusable as an optimistic UI
    command while Workpeg has no verified atomic write facility.
    """
    _write_gate(context)
    try:
        index = validate_snapshot(snapshot)
    except (ValueError, TypeError):
        raise ReservationRejected("invalid_or_stale_snapshot") from None
    reservation_id = _uuid(reservation_id, "reservation_id")
    key = _idempotency_key(idempotency_key)
    try:
        instant = datetime.fromisoformat(checked_in_at)
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise ValueError
    except (ValueError, TypeError, OverflowError):
        raise ReservationRejected("invalid_check_in_time") from None
    try:
        operational_date = parse_day(today)
    except (ValueError, TypeError):
        raise ReservationRejected("invalid_operational_date") from None
    try:
        authoritative_now = datetime.fromisoformat(context.authoritative_now)
        if authoritative_now.tzinfo is None or authoritative_now.utcoffset() is None:
            raise ValueError
    except (ValueError, TypeError, OverflowError):
        raise ReservationRejected("authoritative_clock_unavailable") from None
    if not isinstance(hotel_timezone, str) or not hotel_timezone.strip():
        raise ReservationRejected("invalid_authoritative_hotel_timezone")
    try:
        hotel_zone = ZoneInfo(hotel_timezone)
        local_date = instant.astimezone(hotel_zone).date()
        authoritative_date = authoritative_now.astimezone(hotel_zone).date()
    except ZoneInfoNotFoundError:
        raise ReservationRejected("authoritative_hotel_timezone_unavailable") from None
    except (ValueError, TypeError, OverflowError):
        raise ReservationRejected("invalid_authoritative_hotel_timezone") from None
    if operational_date != authoritative_date:
        raise ReservationRejected("operational_date_not_authoritative")
    if local_date != authoritative_date:
        raise ReservationRejected("check_in_timestamp_operational_date_mismatch")
    if instant > authoritative_now:
        raise ReservationRejected("check_in_timestamp_in_future")
    booking = index["reservations"].get(reservation_id)
    if booking is None:
        raise ReservationRejected("unknown_reservation")
    if booking["status"] != "confirmed" or not booking.get("room_id"):
        raise ReservationRejected("confirmed_assignment_required")
    if not isinstance(occupant_guest_ids, (list, tuple)) or not occupant_guest_ids:
        raise ReservationRejected("occupants_required")
    guests = []
    for guest_id in occupant_guest_ids:
        guests.append(_uuid(guest_id, "occupant_guest_id"))
    if len(set(guests)) != len(guests):
        raise ReservationRejected("duplicate_occupant")
    if len(guests) > booking["party_size"]:
        raise ReservationRejected("party_size_exceeded")
    if any(guest_id not in index["guests"] for guest_id in guests):
        raise ReservationRejected("unknown_occupant")

    stay_id = str(uuid5(NAMESPACE_URL,
                        "roomay:stay:v1:" + context.business_id + ":" + key))
    stay = {
        "entity_id": stay_id, "reservation_id": reservation_id,
        "room_id": booking["room_id"], "status": "checked_in",
        "checked_in_at": instant.isoformat(),
    }
    occupants = tuple({
        "entity_id": str(uuid5(NAMESPACE_URL,
                               "roomay:stay-guest:v1:" + stay_id + ":" + guest_id)),
        "stay_id": stay_id, "guest_id": guest_id,
        "joined_at": instant.isoformat(),
    } for guest_id in guests)

    existing = next((row for row in snapshot["stays"]
                     if row["reservation_id"] == reservation_id), None)
    if existing:
        existing_occupants = sorted(
            (row for row in snapshot["stay_guests"] if row["stay_id"] == existing["entity_id"]),
            key=lambda row: row["entity_id"],
        )
        if existing != stay or existing_occupants != sorted(occupants, key=lambda row: row["entity_id"]):
            raise ReservationRejected("reservation_already_used_or_idempotency_conflict")
        return CheckInPlan("already_checked_in", reservation_id, dict(existing),
                           tuple(dict(row) for row in existing_occupants))
    if any(row["entity_id"] == stay_id for row in snapshot["stays"]):
        raise ReservationRejected("idempotency_key_reused_for_different_check_in")

    try:
        reasons = room_eligibility(
            snapshot, reservation_id, booking["room_id"], check_in=True,
            today=authoritative_date.isoformat(), staff_approved=True,
        )
    except (ValueError, TypeError):
        raise ReservationRejected("invalid_or_stale_snapshot") from None
    if reasons:
        raise ReservationRejected(*reasons)
    return CheckInPlan("check_in_guest", reservation_id, stay, occupants)


def reconcile_check_in_readback(plan, snapshot, *, context):
    """Classify observed rows after an uncertain multi-row check-in attempt.

    This is a retry decision only. It does not claim that Workpeg committed a
    transaction: stay and occupant rows may have been written independently.
    Partial/mismatched observations require manual reconciliation.
    """
    _write_gate(context)
    if not isinstance(plan, CheckInPlan):
        raise ReservationRejected("invalid_check_in_plan")
    try:
        validate_snapshot(snapshot)
    except (ValueError, TypeError):
        return "invalid_readback_manual_reconciliation"
    stay = next((row for row in snapshot["stays"]
                 if row["entity_id"] == plan.stay_record["entity_id"]), None)
    occupants = {row["entity_id"]: row for row in snapshot["stay_guests"]
                 if row["stay_id"] == plan.stay_record["entity_id"]}
    expected = {row["entity_id"]: row for row in plan.occupant_records}
    same_reservation = [row for row in snapshot["stays"]
                        if row["reservation_id"] == plan.reservation_id]
    if stay == plan.stay_record and occupants == expected and len(same_reservation) == 1:
        return "expected_rows_observed_do_not_repeat"
    if stay is None and not occupants and not same_reservation:
        return "rows_absent_retry_only_under_held_guard"
    return "partial_or_conflicting_rows_manual_reconciliation"
