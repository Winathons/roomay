"""Offline checkout and housekeeping command contracts.

Every result is an unpersisted proposal. A future trusted Workpeg adapter must
derive these context claims from authenticated server state, hold a real
serialization guard, durably deduplicate the operation, and reconcile every
affected row before reporting success.
"""
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json
from re import fullmatch
from uuid import NAMESPACE_URL, UUID, uuid5
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .hotel import parse_day, parse_instant, validate_snapshot
from .service_requests import validate_request


class OperationRejected(ValueError):
    """Stable, non-sensitive reason for refusing a proposed operation."""

    def __init__(self, *reasons):
        self.reasons = tuple(reasons)
        super().__init__(", ".join(reasons))


@dataclass(frozen=True)
class OperationContext:
    """Untrusted-at-this-layer claims expected from a future trusted adapter."""

    business_id: str
    snapshot_business_id: str
    hotel_id: str
    snapshot_hotel_id: str
    actor_id: str
    actor_role: str
    authorization_verified: bool
    snapshot_fresh: bool
    serialization_guard_held: bool
    authoritative_now: str | None
    actor_department: str | None = None
    safety_snapshot_complete: bool = False


@dataclass(frozen=True)
class CheckoutPlan:
    """Unpersisted, multi-row checkout intent with before/after snapshots."""

    action: str
    operation_id: str
    idempotency_key: str
    operation_signature: str
    stay_id: str
    room_id: str
    stay_before: dict
    stay_after: dict
    occupants_before: tuple
    occupants_after: tuple
    room_before: dict
    room_after: dict
    requires_authoritative_guard: bool = True
    requires_durable_idempotency: bool = True
    requires_complete_readback: bool = True
    persisted: bool = False


@dataclass(frozen=True)
class HousekeepingPlan:
    """Unpersisted room-readiness transition proposal."""

    action: str
    operation_id: str
    idempotency_key: str
    operation_signature: str
    room_id: str
    expected_status: str
    target_status: str
    room_before: dict
    room_after: dict
    requires_authoritative_guard: bool = True
    requires_durable_idempotency: bool = True
    requires_readback: bool = True
    persisted: bool = False


_CHECKOUT_ROLES = {"owner", "owner_operator", "manager", "receptionist"}
_HOUSEKEEPING = {"dirty", "cleaning", "inspection", "ready"}
_TRANSITIONS = {
    ("dirty", "cleaning"): "cleaner",
    ("cleaning", "inspection"): "cleaner",
    ("inspection", "cleaning"): "cleaner",  # inspection failed; re-clean
    ("inspection", "ready"): "supervisor",
}
_OPERATION_KEY = r"[A-Za-z0-9_-]{12,128}"


def _uuid(value, label):
    if not isinstance(value, str):
        raise OperationRejected("invalid_" + label)
    try:
        if str(UUID(value)) != value:
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise OperationRejected("invalid_" + label) from None
    return value


def _context_base(context):
    if not isinstance(context, OperationContext):
        raise OperationRejected("trusted_operation_context_required")
    _uuid(context.business_id, "business_id")
    _uuid(context.snapshot_business_id, "snapshot_business_id")
    _uuid(context.hotel_id, "hotel_id")
    _uuid(context.snapshot_hotel_id, "snapshot_hotel_id")
    if not isinstance(context.actor_id, str) or not context.actor_id.strip():
        raise OperationRejected("invalid_actor")
    if not isinstance(context.actor_role, str):
        raise OperationRejected("authorization_context_invalid")
    if context.business_id != context.snapshot_business_id:
        raise OperationRejected("wrong_business")
    if context.hotel_id != context.snapshot_hotel_id:
        raise OperationRejected("wrong_hotel")
    if context.authorization_verified is not True:
        raise OperationRejected("authorized_staff_required")
    if context.snapshot_fresh is not True:
        raise OperationRejected("stale_snapshot")
    if context.serialization_guard_held is not True:
        raise OperationRejected("authoritative_serialization_unavailable")


def _context_gate(context, *, operation):
    _context_base(context)
    if operation == "checkout":
        if context.actor_role not in _CHECKOUT_ROLES:
            raise OperationRejected("authorized_checkout_staff_required")
    elif operation == "cleaner":
        if (context.actor_role != "department_staff"
                or context.actor_department != "housekeeping"):
            raise OperationRejected("housekeeping_staff_required")
    elif operation == "supervisor":
        if context.actor_role not in {"owner", "owner_operator", "manager"}:
            raise OperationRejected("housekeeping_supervisor_required")
    else:
        raise OperationRejected("invalid_operation")


def _snapshot(snapshot):
    try:
        return validate_snapshot(snapshot)
    except (ValueError, TypeError, KeyError):
        raise OperationRejected("invalid_or_incomplete_snapshot") from None


def _operation_key(value):
    if not isinstance(value, str) or not fullmatch(_OPERATION_KEY, value):
        raise OperationRejected("invalid_idempotency_key")
    return value


def _operation_identity(kind, scope, key, payload):
    operation_id = str(uuid5(NAMESPACE_URL, f"roomay:{kind}:v1:{scope}:{key}"))
    signature = sha256(json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode("utf-8")).hexdigest()
    return operation_id, signature


def _reject_prior_operation(prior_operation, *, operation_id, key, signature):
    """Require a future durable operation ledger to stop replay/changed input."""
    if prior_operation is None:
        return
    if not isinstance(prior_operation, dict):
        raise OperationRejected("invalid_prior_operation")
    if prior_operation.get("idempotency_key") != key:
        raise OperationRejected("invalid_prior_operation")
    if (prior_operation.get("operation_id") != operation_id
            or prior_operation.get("operation_signature") != signature):
        raise OperationRejected("idempotency_key_reused_for_different_operation")
    raise OperationRejected("operation_already_attempted_readback_required")


def _authoritative_instant(context, *, occurred_at, today, hotel_timezone):
    try:
        event = parse_instant(occurred_at)
    except (ValueError, TypeError, OverflowError):
        raise OperationRejected("invalid_operation_timestamp") from None
    try:
        supplied_date = parse_day(today)
    except (ValueError, TypeError):
        raise OperationRejected("invalid_operational_date") from None
    try:
        now = parse_instant(context.authoritative_now)
    except (ValueError, TypeError, OverflowError):
        raise OperationRejected("authoritative_clock_unavailable") from None
    if not isinstance(hotel_timezone, str) or not hotel_timezone.strip():
        raise OperationRejected("invalid_authoritative_hotel_timezone")
    try:
        zone = ZoneInfo(hotel_timezone)
    except ZoneInfoNotFoundError:
        raise OperationRejected("authoritative_hotel_timezone_unavailable") from None
    except (ValueError, TypeError):
        raise OperationRejected("invalid_authoritative_hotel_timezone") from None
    local_today = now.astimezone(zone).date()
    if supplied_date != local_today:
        raise OperationRejected("operational_date_not_authoritative")
    if event.astimezone(zone).date() != local_today:
        raise OperationRejected("operation_timestamp_operational_date_mismatch")
    if event > now:
        raise OperationRejected("operation_timestamp_in_future")
    return event


def prepare_checkout(
    snapshot, *, stay_id, checked_out_at, today, hotel_timezone,
    idempotency_key, context, prior_operation=None,
):
    """Prepare checked-out stay, remaining occupant departures, and Dirty room.

    A late checkout remains allowed: scheduled departure is not physical
    checkout. A held guard is only a claim at this offline boundary; this plan
    cannot itself authenticate, serialize, write, or establish persistence.
    """
    _context_gate(context, operation="checkout")
    index = _snapshot(snapshot)
    stay_id = _uuid(stay_id, "stay_id")
    key = _operation_key(idempotency_key)
    event = _authoritative_instant(
        context, occurred_at=checked_out_at, today=today,
        hotel_timezone=hotel_timezone,
    )
    stay = index["stays"].get(stay_id)
    if stay is None:
        raise OperationRejected("unknown_stay")
    if stay["status"] != "checked_in":
        raise OperationRejected("stay_not_checked_in")
    booking = index["reservations"].get(stay["reservation_id"])
    room = index["rooms"].get(stay["room_id"])
    if (booking is None or booking["status"] != "confirmed"
            or booking.get("room_id") != stay["room_id"] or room is None):
        raise OperationRejected("stay_assignment_inconsistent")
    checked_in = parse_instant(stay["checked_in_at"])
    if event < checked_in:
        raise OperationRejected("checkout_before_check_in")
    zone = ZoneInfo(hotel_timezone)
    arrival = parse_day(booking["arrival"])
    departure = parse_day(booking["departure"])
    check_in_date = checked_in.astimezone(zone).date()
    if not arrival <= check_in_date < departure:
        raise OperationRejected("stay_check_in_outside_reservation")
    if event.astimezone(zone).date() < arrival:
        raise OperationRejected("checkout_before_reservation_start")

    occupants = sorted(
        (row for row in snapshot["stay_guests"] if row["stay_id"] == stay_id),
        key=lambda row: row["entity_id"],
    )
    if not occupants:
        raise OperationRejected("registered_occupants_required")
    remaining = [row for row in occupants if not row.get("left_at")]
    for occupant in occupants:
        joined_at = parse_instant(occupant["joined_at"])
        if joined_at > event:
            raise OperationRejected("occupant_arrival_after_checkout")
        if joined_at > parse_instant(context.authoritative_now):
            raise OperationRejected("occupant_arrival_in_future")
        if occupant.get("left_at"):
            left_at = parse_instant(occupant["left_at"])
            if left_at > event:
                raise OperationRejected("occupant_departure_after_checkout")
            if left_at > parse_instant(context.authoritative_now):
                raise OperationRejected("occupant_departure_in_future")

    stay_after = dict(stay, status="checked_out", checked_out_at=event.isoformat())
    occupants_after = tuple(
        dict(row, left_at=event.isoformat()) if not row.get("left_at") else dict(row)
        for row in occupants
    )
    room_after = dict(room, housekeeping="dirty")
    payload = {
        "stay_id": stay_id, "checked_out_at": event.isoformat(),
        "occupant_ids": [row["entity_id"] for row in remaining],
        "room_id": room["entity_id"], "room_housekeeping": "dirty",
        "before": {
            "stay": stay, "occupants": occupants, "room": room,
        },
    }
    operation_id, signature = _operation_identity(
        "checkout", f"{context.business_id}:{context.hotel_id}:{stay_id}", key, payload,
    )
    _reject_prior_operation(
        prior_operation, operation_id=operation_id, key=key, signature=signature,
    )
    return CheckoutPlan(
        action="prepare_checkout", operation_id=operation_id,
        idempotency_key=key, operation_signature=signature, stay_id=stay_id,
        room_id=room["entity_id"], stay_before=deepcopy(stay),
        stay_after=stay_after, occupants_before=tuple(deepcopy(occupants)),
        occupants_after=occupants_after, room_before=deepcopy(room),
        room_after=room_after,
    )


def prepare_housekeeping_transition(
    snapshot, *, room_id, target_status, occurred_at, today, hotel_timezone,
    idempotency_key, context, prior_operation=None, service_requests=None,
):
    """Prepare a single permitted readiness transition without changing blocks."""
    _context_base(context)
    if not (
        context.actor_role in {"owner", "owner_operator", "manager"}
        or (context.actor_role == "department_staff"
            and context.actor_department == "housekeeping")
    ):
        raise OperationRejected("housekeeping_staff_required")
    if not isinstance(target_status, str) or target_status not in _HOUSEKEEPING:
        raise OperationRejected("invalid_housekeeping_status")
    index = _snapshot(snapshot)
    room_id = _uuid(room_id, "room_id")
    room = index["rooms"].get(room_id)
    if room is None:
        raise OperationRejected("unknown_room")
    current = room["housekeeping"]
    required_role = _TRANSITIONS.get((current, target_status))
    if required_role is None:
        if current == target_status:
            raise OperationRejected("duplicate_housekeeping_transition")
        raise OperationRejected("invalid_housekeeping_transition")
    _context_gate(context, operation=required_role)
    key = _operation_key(idempotency_key)
    event = _authoritative_instant(
        context, occurred_at=occurred_at, today=today,
        hotel_timezone=hotel_timezone,
    )
    current_date = event.astimezone(ZoneInfo(hotel_timezone)).date()
    if target_status == "ready":
        if any(stay["room_id"] == room_id and stay["status"] == "checked_in"
               for stay in snapshot["stays"]):
            raise OperationRejected("room_physically_occupied")
        if not room["enabled"]:
            raise OperationRejected("room_disabled")
        if any(
            block["room_id"] == room_id and block["status"] == "active"
            and parse_day(block["start"]) <= current_date < parse_day(block["end"])
            for block in snapshot["room_blocks"]
        ):
            raise OperationRejected("active_maintenance_block")
        if context.safety_snapshot_complete is not True or not isinstance(service_requests, list):
            raise OperationRejected("maintenance_safety_evidence_required")
        open_statuses = {
            "received", "assigned", "acknowledged", "in_progress", "reopened", "escalated",
        }
        for request in service_requests:
            try:
                validate_request(request)
            except (ValueError, TypeError, KeyError):
                raise OperationRejected("invalid_safety_request_snapshot") from None
            if request["hotel_id"] != context.hotel_id:
                raise OperationRejected("wrong_hotel")
            if (request["room_id"] == room_id
                    and request["department"] == "maintenance"
                    and request["status"] in open_statuses):
                raise OperationRejected("unresolved_maintenance_request")

    room_after = dict(room, housekeeping=target_status)
    payload = {
        "room_id": room_id, "from": current, "to": target_status,
        "occurred_at": event.isoformat(),
        "before": room,
    }
    operation_id, signature = _operation_identity(
        "housekeeping", f"{context.business_id}:{context.hotel_id}:{room_id}",
        key, payload,
    )
    _reject_prior_operation(
        prior_operation, operation_id=operation_id, key=key, signature=signature,
    )
    return HousekeepingPlan(
        action="prepare_housekeeping_transition", operation_id=operation_id,
        idempotency_key=key, operation_signature=signature, room_id=room_id,
        expected_status=current, target_status=target_status,
        room_before=deepcopy(room), room_after=room_after,
    )


def _operation_matches(plan, operation_record):
    return (isinstance(operation_record, dict)
            and operation_record.get("operation_id") == plan.operation_id
            and operation_record.get("idempotency_key") == plan.idempotency_key
            and operation_record.get("operation_signature") == plan.operation_signature)


def reconcile_checkout_readback(plan, snapshot, *, context, operation_record=None):
    """Classify a complete read-back; never retries or claims persistence."""
    _context_gate(context, operation="checkout")
    if not isinstance(plan, CheckoutPlan):
        raise OperationRejected("invalid_checkout_plan")
    if not _operation_matches(plan, operation_record):
        return "operation_evidence_missing_manual_reconciliation"
    try:
        index = validate_snapshot(snapshot)
    except (ValueError, TypeError, KeyError):
        return "invalid_readback_manual_reconciliation"
    stay = index["stays"].get(plan.stay_id)
    room = index["rooms"].get(plan.room_id)
    occupants = tuple(sorted(
        (row for row in snapshot["stay_guests"] if row["stay_id"] == plan.stay_id),
        key=lambda row: row["entity_id"],
    ))
    if (stay == plan.stay_after and occupants == tuple(sorted(
            plan.occupants_after, key=lambda row: row["entity_id"]))
            and room == plan.room_after):
        return "target_rows_observed_do_not_repeat"
    if (stay == plan.stay_before and occupants == tuple(sorted(
            plan.occupants_before, key=lambda row: row["entity_id"]))
            and room == plan.room_before):
        return "source_rows_observed_replan_under_fresh_guard"
    return "partial_or_conflicting_rows_manual_reconciliation"


def reconcile_housekeeping_readback(
    plan, snapshot, *, context, operation_record=None,
):
    """Classify the observed readiness row without automatic retry."""
    if not isinstance(plan, HousekeepingPlan):
        raise OperationRejected("invalid_housekeeping_plan")
    required_role = _TRANSITIONS.get((plan.expected_status, plan.target_status))
    _context_gate(context, operation=required_role)
    if not _operation_matches(plan, operation_record):
        return "operation_evidence_missing_manual_reconciliation"
    try:
        index = validate_snapshot(snapshot)
    except (ValueError, TypeError, KeyError):
        return "invalid_readback_manual_reconciliation"
    room = index["rooms"].get(plan.room_id)
    if room == plan.room_after:
        return "target_state_observed_do_not_repeat"
    if room == plan.room_before:
        return "source_state_observed_replan_under_fresh_guard"
    return "conflicting_state_manual_reconciliation"
