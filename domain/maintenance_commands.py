"""WOR-20: offline maintenance safety plans; not a Workpeg persistence adapter.

Every plan requires a future trusted actor resolver, held serialization guard,
durable idempotency/audit, and verified readback before reporting success.
"""
from copy import deepcopy
from dataclasses import dataclass
from uuid import NAMESPACE_URL, uuid5

from .checkout_commands import (
    OperationContext, OperationRejected, _context_base, _operation_identity,
    _operation_key, _reject_prior_operation, _snapshot, _uuid,
)
from .hotel import parse_day, parse_instant, room_eligibility


_SAFETY_ROLES = {"owner", "owner_operator", "manager"}
_REASSIGN_ROLES = _SAFETY_ROLES | {"receptionist"}


@dataclass(frozen=True)
class MaintenancePlan:
    action: str
    operation_id: str
    idempotency_key: str
    operation_signature: str
    block_id: str
    block_before: dict | None
    block_after: dict
    room_before: dict
    room_after: dict
    affected_active_stays: tuple
    audit_intent: dict
    resolution_conditions: str | None = None
    requires_authoritative_guard: bool = True
    requires_durable_idempotency: bool = True
    requires_complete_readback: bool = True
    persisted: bool = False


@dataclass(frozen=True)
class ReassignmentPlan:
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
    requires_complete_readback: bool = True
    persisted: bool = False


def _gate(context, *, mode):
    _context_base(context)
    if context.safety_snapshot_complete is not True:
        raise OperationRejected("complete_room_safety_snapshot_required")
    try:
        parse_instant(context.authoritative_now)
    except (ValueError, TypeError, OverflowError):
        raise OperationRejected("authoritative_clock_unavailable") from None
    if mode == "maintenance":
        # A maintenance supervisor is a *proposed* future identity mapping.
        # The adapter must independently verify that membership and department.
        allowed = context.actor_role in _SAFETY_ROLES or (
            context.actor_role == "maintenance_supervisor"
            and context.actor_department == "maintenance"
        )
        if not allowed:
            raise OperationRejected("maintenance_supervisor_required")
    elif mode == "reassignment":
        if context.actor_role not in _REASSIGN_ROLES:
            raise OperationRejected("authorized_reception_staff_required")
    else:
        raise OperationRejected("invalid_operation")


def _text(value, reason, *, limit=500):
    if not isinstance(value, str) or not 3 <= len(value.strip()) <= limit:
        raise OperationRejected(reason)
    return value.strip()


def _audit(action, context, operation_id, **fields):
    return dict(
        action=action, operation_id=operation_id, actor_id=context.actor_id,
        business_id=context.business_id, hotel_id=context.hotel_id,
        occurred_at=context.authoritative_now, **fields,
    )


def _affected_active_stays(snapshot, room_id):
    return tuple(sorted(
        stay["entity_id"] for stay in snapshot["stays"]
        if stay["room_id"] == room_id and stay["status"] == "checked_in"
    ))


def prepare_maintenance_block(
    snapshot, *, room_id, start, end, reason, resolution_conditions,
    idempotency_key, context, prior_operation=None,
):
    """Propose an out-of-service block; an occupied room requires human follow-up."""
    _gate(context, mode="maintenance")
    index = _snapshot(snapshot)
    room_id = _uuid(room_id, "room_id")
    if room_id not in index["rooms"]:
        raise OperationRejected("unknown_room")
    try:
        start_day, end_day = parse_day(start), parse_day(end)
        if start_day >= end_day:
            raise ValueError
    except (ValueError, TypeError):
        raise OperationRejected("invalid_block_interval") from None
    reason = _text(reason, "maintenance_reason_required")
    conditions = _text(resolution_conditions, "resolution_conditions_required")
    key = _operation_key(idempotency_key)
    block_id = str(uuid5(NAMESPACE_URL,
                         f"roomay:maintenance-block:v1:{context.business_id}:{key}"))
    payload = dict(room_id=room_id, start=start, end=end, reason=reason,
                   resolution_conditions=conditions, actor_id=context.actor_id)
    operation_id, signature = _operation_identity(
        "maintenance-block", context.business_id, key, payload,
    )
    _reject_prior_operation(prior_operation, operation_id=operation_id,
                            key=key, signature=signature)
    if block_id in index["room_blocks"]:
        raise OperationRejected("operation_already_attempted_readback_required")
    # Active means unsafe from its start until a human releases it, even
    # after the planned end date; no automatic clearance at expiry.
    if any(b["room_id"] == room_id and b["status"] == "active"
           and parse_day(b["start"]) < end_day
           for b in snapshot["room_blocks"]):
        raise OperationRejected("active_maintenance_block_exists")
    block = dict(entity_id=block_id, room_id=room_id, start=start, end=end,
                 reason=reason, status="active")
    room = dict(index["rooms"][room_id])
    return MaintenancePlan(
        action="create_maintenance_block",
        operation_id=operation_id, idempotency_key=key,
        operation_signature=signature, block_id=block_id,
        block_before=None, block_after=block, room_before=room,
        room_after=dict(room), affected_active_stays=_affected_active_stays(
            snapshot, room_id,
        ), resolution_conditions=conditions,
        audit_intent=_audit("maintenance_block_planned", context, operation_id,
                            room_id=room_id, block_id=block_id),
    )


def prepare_maintenance_release(
    snapshot, *, block_id, verified_repair, verification_reference,
    idempotency_key, context, prior_operation=None,
):
    """Release needs independently verified repair and supervisor authorization.

    An explicitly released block NEVER changes the room directly to 'ready'.
    A ready room moves back to inspection, and other statuses stay unchanged.
    """
    _gate(context, mode="maintenance")
    index = _snapshot(snapshot)
    block_id = _uuid(block_id, "block_id")
    block = index["room_blocks"].get(block_id)
    if block is None:
        raise OperationRejected("unknown_maintenance_block")
    if block["status"] != "active":
        raise OperationRejected("block_already_released")
    if verified_repair is not True:
        raise OperationRejected("repair_verification_required")
    evidence = _text(verification_reference, "verification_reference_required",
                     limit=250)
    key = _operation_key(idempotency_key)
    payload = dict(block_id=block_id, verified_repair=True,
                   verification_reference=evidence, actor_id=context.actor_id)
    operation_id, signature = _operation_identity(
        "maintenance-release", context.business_id, key, payload,
    )
    _reject_prior_operation(prior_operation, operation_id=operation_id,
                            key=key, signature=signature)
    room = dict(index["rooms"][block["room_id"]])
    room_after = dict(room)
    if room_after["housekeeping"] == "ready":
        room_after["housekeeping"] = "inspection"
    released = dict(block, status="released")
    return MaintenancePlan(
        action="release_maintenance_block",
        operation_id=operation_id, idempotency_key=key,
        operation_signature=signature, block_id=block_id,
        block_before=dict(block), block_after=released,
        room_before=room, room_after=room_after,
        affected_active_stays=_affected_active_stays(snapshot, block["room_id"]),
        audit_intent=_audit("maintenance_release_planned", context, operation_id,
                            room_id=block["room_id"], block_id=block_id,
                            verification_reference=evidence),
    )


def eligible_reassignment_rooms(snapshot, *, reservation_id, context):
    """Read-only, conservative suggestions; never changes a reservation."""
    _gate(context, mode="reassignment")
    index = _snapshot(snapshot)
    reservation_id = _uuid(reservation_id, "reservation_id")
    booking = index["reservations"].get(reservation_id)
    if booking is None:
        raise OperationRejected("unknown_reservation")
    if booking["status"] != "confirmed" or not booking.get("room_id"):
        raise OperationRejected("confirmed_assignment_required")
    if any(stay["reservation_id"] == reservation_id for stay in snapshot["stays"]):
        raise OperationRejected("in_house_transfer_requires_separate_workflow")
    old_room = booking["room_id"]
    if not any(b["room_id"] == old_room and b["status"] == "active"
               and parse_day(b["start"]) < parse_day(booking["departure"])
               for b in snapshot["room_blocks"]):
        raise OperationRejected("reservation_not_affected_by_maintenance")
    # Only a hypothetical copy is changed to pending. No persisted booking
    # is downgraded or freed until an authorized replacement is committed.
    candidate = deepcopy(snapshot)
    for row in candidate["reservations"]:
        if row["entity_id"] == reservation_id:
            row["status"] = "pending_confirmation"
            row.pop("room_id", None)
            break
    results = []
    for room in sorted(candidate["rooms"], key=lambda item: item["number"]):
        if room["entity_id"] == old_room or room["housekeeping"] != "ready":
            continue
        if not room_eligibility(candidate, reservation_id, room["entity_id"]):
            results.append(dict(room_id=room["entity_id"], number=room["number"]))
    return tuple(results)


def prepare_safe_reassignment(
    snapshot, *, reservation_id, alternative_room_id,
    idempotency_key, context, prior_operation=None,
):
    """Plan staff-reviewed replacement for an affected, not-yet-occupied booking."""
    choices = eligible_reassignment_rooms(
        snapshot, reservation_id=reservation_id, context=context,
    )
    alternative_room_id = _uuid(alternative_room_id, "alternative_room_id")
    if alternative_room_id not in {room["room_id"] for room in choices}:
        raise OperationRejected("alternative_room_not_eligible")
    index = _snapshot(snapshot)
    previous = dict(index["reservations"][reservation_id])
    replacement = dict(previous, room_id=alternative_room_id)
    key = _operation_key(idempotency_key)
    payload = dict(reservation_id=reservation_id,
                   from_room_id=previous["room_id"],
                   to_room_id=alternative_room_id, actor_id=context.actor_id)
    operation_id, signature = _operation_identity(
        "maintenance-reassignment", context.business_id, key, payload,
    )
    _reject_prior_operation(prior_operation, operation_id=operation_id,
                            key=key, signature=signature)
    return ReassignmentPlan(
        action="reassign_maintenance_affected_reservation",
        operation_id=operation_id, idempotency_key=key,
        operation_signature=signature, reservation_id=reservation_id,
        reservation_before=previous, reservation_after=replacement,
        audit_intent=_audit("maintenance_reassignment_planned",
                            context, operation_id,
                            reservation_id=reservation_id,
                            from_room_id=previous["room_id"],
                            to_room_id=alternative_room_id),
    )
