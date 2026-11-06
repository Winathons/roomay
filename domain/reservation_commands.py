"""Reservation command preparation for the *real* Roomay operating system.

These are pure, deterministic business rules. Plans are NEVER persisted by this
module and MUST NOT be interpreted as booked rooms. Workpeg authorization,
fresh state, atomicity/serialization and row read-back are separate mandatory
gates for a production write.

See docs/reservation-operations.md and WOR-9.
"""
from dataclasses import dataclass
from re import fullmatch
from uuid import NAMESPACE_URL, UUID, uuid5

from .hotel import interval, room_eligibility, validate_snapshot


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
    index = validate_snapshot(snapshot)
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
    index = validate_snapshot(snapshot)
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
