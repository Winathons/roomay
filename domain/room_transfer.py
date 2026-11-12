"""WOR-12: guarded, unpersisted plans for moving an active hotel stay.

No module caller gains Workpeg authorization or persistence. A future trusted
adapter must hold the authoritative guard through all writes and readback.
"""
from copy import deepcopy
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from .checkout_commands import (
    OperationRejected, _authoritative_instant, _context_gate, _operation_identity,
    _operation_key, _operation_matches, _reject_prior_operation, _snapshot, _uuid,
)
from .hotel import parse_day, parse_instant, overlaps, validate_snapshot
from .service_requests import validate_request

_OPEN_REQUESTS = {
    "received", "assigned", "acknowledged", "in_progress", "reopened", "escalated",
}


@dataclass(frozen=True)
class RoomTransferPlan:
    action: str
    operation_id: str
    idempotency_key: str
    operation_signature: str
    stay_id: str
    reservation_id: str
    from_room_id: str
    to_room_id: str
    moved_at: str
    reason: str
    stay_before: dict
    stay_after: dict
    reservation_before: dict
    reservation_after: dict
    old_room_before: dict
    old_room_after: dict
    new_room_before: dict
    new_room_after: dict
    # Existing service-request records remain unchanged. Open tickets tied to
    # the original room require an explicit human disposition.
    historical_request_ids: tuple
    open_old_room_request_ids: tuple
    audit_intent: dict
    requires_authoritative_guard: bool = True
    requires_durable_idempotency: bool = True
    requires_complete_readback: bool = True
    persisted: bool = False


def _verified_request_history(service_requests, context, stay, snapshot, old_room_id):
    if not isinstance(service_requests, list):
        raise OperationRejected("complete_request_history_required")
    known_rooms = {room["entity_id"] for room in snapshot["rooms"]}
    ids, unresolved = [], []
    seen = set()
    for request in service_requests:
        try:
            validate_request(request)
        except (ValueError, TypeError, KeyError):
            raise OperationRejected("invalid_request_history") from None
        if request["hotel_id"] != context.hotel_id:
            raise OperationRejected("wrong_hotel_request_history")
        if request["request_id"] in seen:
            raise OperationRejected("duplicate_request_history")
        seen.add(request["request_id"])
        if request["stay_id"] == stay["entity_id"]:
            if request["room_id"] not in known_rooms:
                raise OperationRejected("unknown_request_room")
            ids.append(request["request_id"])
            if request["room_id"] == old_room_id and request["status"] in _OPEN_REQUESTS:
                unresolved.append(request["request_id"])
    return tuple(sorted(ids)), tuple(sorted(unresolved))


def prepare_room_transfer(
    snapshot, *, stay_id, to_room_id, moved_at, today, hotel_timezone,
    reason, idempotency_key, context, service_requests,
    prior_operation=None,
):
    """Prepare a human-approved move with all source/target rows and audit.

    Both the confirmed reservation's room reference and checked-in stay's room
    reference must change together to satisfy the current canonical schema.
    An old room becomes dirty. The guest remains in the same stay and keeps
    all existing requests; no request is automatically moved/rewritten.
    """
    _context_gate(context, operation="checkout")
    if context.safety_snapshot_complete is not True:
        raise OperationRejected("complete_room_safety_snapshot_required")
    index = _snapshot(snapshot)
    stay_id = _uuid(stay_id, "stay_id")
    to_room_id = _uuid(to_room_id, "to_room_id")
    key = _operation_key(idempotency_key)
    if not isinstance(reason, str) or not 3 <= len(reason.strip()) <= 500:
        raise OperationRejected("room_move_reason_required")
    reason = reason.strip()
    event = _authoritative_instant(
        context, occurred_at=moved_at, today=today, hotel_timezone=hotel_timezone,
    )
    stay = index["stays"].get(stay_id)
    if stay is None:
        raise OperationRejected("unknown_stay")
    if stay["status"] != "checked_in":
        raise OperationRejected("active_stay_required")
    reservation = index["reservations"].get(stay["reservation_id"])
    old_room = index["rooms"].get(stay["room_id"])
    new_room = index["rooms"].get(to_room_id)
    if (reservation is None or reservation["status"] != "confirmed"
            or reservation.get("room_id") != stay["room_id"] or old_room is None):
        raise OperationRejected("stay_assignment_inconsistent")
    if new_room is None:
        raise OperationRejected("unknown_target_room")
    if to_room_id == old_room["entity_id"]:
        raise OperationRejected("same_room_transfer")
    if event < parse_instant(stay["checked_in_at"]):
        raise OperationRejected("transfer_before_check_in")
    occupants = [
        guest for guest in snapshot["stay_guests"]
        if guest["stay_id"] == stay_id and guest.get("left_at") is None
    ]
    if not occupants:
        raise OperationRejected("active_occupants_required")
    if any(parse_instant(guest["joined_at"]) > event for guest in occupants):
        raise OperationRejected("occupant_arrival_after_transfer")
    if not new_room["enabled"]:
        raise OperationRejected("room_disabled")
    if new_room["room_type_id"] != reservation["room_type_id"]:
        raise OperationRejected("wrong_room_type")
    if new_room["housekeeping"] != "ready":
        raise OperationRejected("housekeeping_not_ready")
    if any(item["status"] == "checked_in" and item["room_id"] == to_room_id
           for item in snapshot["stays"]):
        raise OperationRejected("room_physically_occupied")
    if any(item["entity_id"] != reservation["entity_id"]
           and item["status"] == "confirmed" and item.get("room_id") == to_room_id
           and overlaps(item["arrival"], item["departure"],
                        reservation["arrival"], reservation["departure"])
           for item in snapshot["reservations"]):
        raise OperationRejected("reservation_overlap")
    # A maintenance block with status=active remains unsafe past its planned
    # end. A currently active block must block even on an overdue checkout.
    effective_end = max(parse_day(reservation["departure"]),
                        event.astimezone(ZoneInfo(hotel_timezone)).date())
    if any(block["room_id"] == to_room_id and block["status"] == "active"
           and parse_day(block["start"]) <= effective_end
           for block in snapshot["room_blocks"]):
        raise OperationRejected("active_maintenance_block")
    historical, pending = _verified_request_history(
        service_requests, context, stay, snapshot, old_room["entity_id"],
    )
    stay_after = dict(stay, room_id=to_room_id)
    reservation_after = dict(reservation, room_id=to_room_id)
    old_room_after = dict(old_room, housekeeping="dirty")
    proposed = deepcopy(snapshot)
    proposed["stays"] = [stay_after if row["entity_id"] == stay_id else row
                         for row in proposed["stays"]]
    proposed["reservations"] = [
        reservation_after if row["entity_id"] == reservation["entity_id"] else row
        for row in proposed["reservations"]
    ]
    proposed["rooms"] = [old_room_after if row["entity_id"] == old_room["entity_id"]
                         else row for row in proposed["rooms"]]
    try:
        validate_snapshot(proposed)
    except (ValueError, TypeError, KeyError):
        raise OperationRejected("transfer_target_inconsistent") from None

    payload = {
        "stay_id": stay_id, "reservation_id": reservation["entity_id"],
        "from_room_id": old_room["entity_id"], "to_room_id": to_room_id,
        "moved_at": event.isoformat(), "reason": reason,
        "historical_request_ids": historical,
        "open_old_room_request_ids": pending,
        "before": {"stay": stay, "reservation": reservation,
                   "old_room": old_room, "new_room": new_room},
    }
    operation_id, signature = _operation_identity(
        "room-transfer", f"{context.business_id}:{context.hotel_id}:{stay_id}",
        key, payload,
    )
    _reject_prior_operation(
        prior_operation, operation_id=operation_id, key=key, signature=signature,
    )
    audit = {
        "action": "room_transfer_planned", "operation_id": operation_id,
        "business_id": context.business_id, "hotel_id": context.hotel_id,
        "actor_id": context.actor_id, "stay_id": stay_id,
        "reservation_id": reservation["entity_id"],
        "from_room_id": old_room["entity_id"], "to_room_id": to_room_id,
        "occurred_at": event.isoformat(), "reason": reason,
        "open_old_room_request_ids": pending,
    }
    return RoomTransferPlan(
        action="prepare_room_transfer", operation_id=operation_id,
        idempotency_key=key, operation_signature=signature,
        stay_id=stay_id, reservation_id=reservation["entity_id"],
        from_room_id=old_room["entity_id"], to_room_id=to_room_id,
        moved_at=event.isoformat(), reason=reason,
        stay_before=deepcopy(stay), stay_after=stay_after,
        reservation_before=deepcopy(reservation),
        reservation_after=reservation_after,
        old_room_before=deepcopy(old_room), old_room_after=old_room_after,
        new_room_before=deepcopy(new_room), new_room_after=deepcopy(new_room),
        historical_request_ids=historical, open_old_room_request_ids=pending,
        audit_intent=audit,
    )


def reconcile_room_transfer_readback(
    plan, snapshot, *, context, operation_record=None,
):
    """Return reconciliation status; never retry or assert a durable commit."""
    _context_gate(context, operation="checkout")
    if not isinstance(plan, RoomTransferPlan):
        raise OperationRejected("invalid_room_transfer_plan")
    if not _operation_matches(plan, operation_record):
        return "operation_evidence_missing_manual_reconciliation"
    try:
        index = validate_snapshot(snapshot)
    except (ValueError, TypeError, KeyError):
        return "invalid_readback_manual_reconciliation"
    stay = index["stays"].get(plan.stay_id)
    reservation = index["reservations"].get(plan.reservation_id)
    old_room = index["rooms"].get(plan.from_room_id)
    new_room = index["rooms"].get(plan.to_room_id)
    observed = (stay, reservation, old_room, new_room)
    if observed == (plan.stay_after, plan.reservation_after,
                    plan.old_room_after, plan.new_room_after):
        return "target_rows_observed_do_not_repeat"
    if observed == (plan.stay_before, plan.reservation_before,
                    plan.old_room_before, plan.new_room_before):
        return "source_rows_observed_replan_under_fresh_guard"
    return "partial_or_conflicting_rows_manual_reconciliation"
