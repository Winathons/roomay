"""Fail-closed hotel service-request lifecycle with no persistence side effects.

Callers must build actors and staff records from authenticated, business-scoped
identity data. Passing these checks does not itself prove a Workpeg permission.
"""
from copy import deepcopy
from datetime import datetime, timedelta
from hashlib import sha256
import json
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from .hotel import parse_instant, validate_snapshot


DEPARTMENTS = ("housekeeping", "maintenance", "food_and_beverage", "reception")
URGENCIES = ("low", "normal", "high", "urgent")
STATUSES = (
    "received", "assigned", "acknowledged", "in_progress", "resolved",
    "reopened", "cancelled", "escalated",
)
ORIGINS = ("guest", "reception_desk", "phone", "staff")

CATEGORY_DEPARTMENTS = {
    "extra_towels": "housekeeping",
    "linen": "housekeeping",
    "room_cleaning": "housekeeping",
    "toiletries": "housekeeping",
    "plumbing": "maintenance",
    "electrical": "maintenance",
    "air_conditioning": "maintenance",
    "room_equipment": "maintenance",
    "room_service": "food_and_beverage",
    "dining": "food_and_beverage",
    "minibar": "food_and_beverage",
    "transport": "reception",
    "wake_up_call": "reception",
    "billing_question": "reception",
    "general_help": "reception",
}

TRANSITIONS = {
    "received": {"assigned", "cancelled", "escalated"},
    "assigned": {"acknowledged", "cancelled", "escalated"},
    "acknowledged": {"in_progress", "cancelled", "escalated"},
    "in_progress": {"resolved", "cancelled", "escalated"},
    "resolved": {"reopened"},
    "reopened": {"assigned", "cancelled", "escalated"},
    "escalated": {"assigned", "cancelled"},
    "cancelled": {"reopened"},
}

TARGET_MINUTES = {
    "low": (60, 480),
    "normal": (30, 240),
    "high": (15, 120),
    "urgent": (5, 30),
}

OPTIONAL_REQUEST_FIELDS = {
    "assigned_staff_id", "assigned_at", "acknowledged_at", "in_progress_at",
    "resolved_at", "reopened_at", "cancelled_at", "escalated_at",
}


class RequestError(ValueError):
    """Stable, non-sensitive domain error for callers and tests."""

    def __init__(self, code):
        self.code = code
        super().__init__(code)


class AuthorizationError(RequestError):
    pass


class ConflictError(RequestError):
    pass


def _uuid(value, code="invalid_uuid"):
    if not isinstance(value, str):
        raise RequestError(code)
    try:
        parsed = UUID(value)
    except (ValueError, TypeError, AttributeError) as error:
        raise RequestError(code) from error
    if str(parsed) != value:
        raise RequestError(code)
    return value


def _text(value, code, limit=1000):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit:
        raise RequestError(code)
    return value.strip()


def _at(value):
    try:
        parsed = parse_instant(value)
    except (ValueError, TypeError) as error:
        raise RequestError("invalid_timestamp") from error
    return parsed


def _operation_id(hotel_id, request_id, operation_key):
    key = _text(operation_key, "invalid_operation_key", 200)
    return str(uuid5(NAMESPACE_URL, f"roomay:request:{hotel_id}:{request_id}:{key}"))


def _event_id(operation_id):
    return str(uuid5(NAMESPACE_URL, "roomay:request-event:" + operation_id))


def _signature(value):
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(encoded).hexdigest()


def route_category(category):
    """Return canonical category, department and explicit triage flag."""
    normalized = category.strip().lower() if isinstance(category, str) else ""
    if normalized in CATEGORY_DEPARTMENTS:
        return normalized, CATEGORY_DEPARTMENTS[normalized], False
    return "unknown", "reception", True


def _staff_index(staff_directory, hotel_id):
    if not isinstance(staff_directory, list):
        raise RequestError("invalid_staff_directory")
    result = {}
    for staff in staff_directory:
        if not isinstance(staff, dict) or set(staff) != {
                "actor_id", "hotel_id", "department", "roles", "active"}:
            raise RequestError("invalid_staff_directory")
        actor_id = _text(staff["actor_id"], "invalid_staff_id", 200)
        if staff["hotel_id"] != hotel_id or staff["department"] not in DEPARTMENTS:
            raise RequestError("invalid_staff_directory")
        if not isinstance(staff["roles"], list) or not all(
                isinstance(role, str) and role for role in staff["roles"]):
            raise RequestError("invalid_staff_directory")
        if type(staff["active"]) is not bool or actor_id in result:
            raise RequestError("invalid_staff_directory")
        result[actor_id] = staff
    return result


def _trusted_actor(actor, hotel_id, staff_directory):
    if not isinstance(actor, dict):
        raise AuthorizationError("invalid_actor")
    if actor.get("hotel_id") != hotel_id:
        raise AuthorizationError("cross_hotel_access")
    kind = actor.get("kind")
    actor_id = _text(actor.get("actor_id"), "invalid_actor", 200)
    if kind == "guest":
        guest_id = _uuid(actor.get("guest_id"), "invalid_guest_actor")
        return {"actor_id": actor_id, "kind": kind, "guest_id": guest_id,
                "department": None, "roles": []}
    if kind != "staff":
        # AI/system input may draft text but cannot become an authority here.
        raise AuthorizationError("untrusted_actor_kind")
    staff = _staff_index(staff_directory, hotel_id).get(actor_id)
    if not staff or not staff["active"]:
        raise AuthorizationError("inactive_or_unknown_staff")
    return {"actor_id": actor_id, "kind": kind,
            "department": staff["department"], "roles": list(staff["roles"])}


def _active_stay(snapshot, stay_id, room_id, guest_id):
    indexes = validate_snapshot(snapshot)
    stay = indexes["stays"].get(stay_id)
    if (not stay or stay["status"] != "checked_in"
            or (room_id is not None and stay["room_id"] != room_id)):
        raise RequestError("inactive_or_wrong_stay")
    occupants = [row for row in snapshot["stay_guests"]
                 if row["stay_id"] == stay_id and row["guest_id"] == guest_id
                 and not row.get("left_at")]
    if len(occupants) != 1:
        raise RequestError("guest_not_active_occupant")
    return stay


def _staff_may_create(actor):
    return actor["department"] == "reception" or bool(
        {"request_admin", "hotel_manager"} & set(actor["roles"]))


def _base_event(request, actor, operation_id, event_type, from_status, to_status,
                occurred_at, operation_signature, reason=None):
    event = {
        "event_id": _event_id(operation_id),
        "operation_id": operation_id,
        "operation_signature": operation_signature,
        "request_id": request["request_id"],
        "hotel_id": request["hotel_id"],
        "sequence": request["version"],
        "event_type": event_type,
        "from_status": from_status,
        "to_status": to_status,
        "actor_id": actor["actor_id"],
        "actor_kind": actor["kind"],
        "actor_department": actor.get("department"),
        "occurred_at": occurred_at,
        "reason": reason,
        "commit_state": "pending",
    }
    return event


def _plan(base_request, request, event):
    request["last_event_id"] = event["event_id"]
    request["last_operation_signature"] = event["operation_signature"]
    return {"base_request": deepcopy(base_request),
            "target_request": request, "event": event}


def _same_creation(existing, candidate):
    fields = (
        "hotel_id", "stay_id", "room_id", "guest_id", "origin", "category",
        "category_detail", "department", "description", "urgency", "sensitive",
    )
    return all(existing.get(field) == candidate.get(field) for field in fields)


def create_request(snapshot, draft, actor, staff_directory, existing_requests, *,
                   at, request_id=None):
    """Validate and plan a request creation, or identify an exact retry."""
    allowed = {
        "hotel_id", "stay_id", "room_id", "guest_id", "origin", "category",
        "description", "urgency", "idempotency_key", "sensitive",
    }
    if not isinstance(draft, dict) or set(draft) - allowed or set(draft) != allowed:
        raise RequestError("invalid_request_draft")
    hotel_id = _uuid(draft["hotel_id"], "invalid_hotel_id")
    stay_id = _uuid(draft["stay_id"], "invalid_stay_id")
    room_id = _uuid(draft["room_id"], "invalid_room_id")
    guest_id = _uuid(draft["guest_id"], "invalid_guest_id")
    trusted = _trusted_actor(actor, hotel_id, staff_directory)
    _active_stay(snapshot, stay_id, room_id, guest_id)
    if trusted["kind"] == "guest" and trusted["guest_id"] != guest_id:
        raise AuthorizationError("cross_guest_access")
    if trusted["kind"] == "staff" and not _staff_may_create(trusted):
        raise AuthorizationError("manual_request_requires_reception")
    if draft["origin"] not in ORIGINS:
        raise RequestError("invalid_origin")
    if trusted["kind"] == "guest" and draft["origin"] != "guest":
        raise AuthorizationError("guest_origin_mismatch")
    if trusted["kind"] == "staff" and draft["origin"] == "guest":
        raise AuthorizationError("staff_origin_mismatch")
    if draft["urgency"] not in URGENCIES:
        raise RequestError("invalid_urgency")
    if type(draft["sensitive"]) is not bool:
        raise RequestError("invalid_sensitive_flag")
    if draft["sensitive"] and not (
            trusted["kind"] == "staff" and
            {"incident_manager", "hotel_manager"} & set(trusted["roles"])):
        raise AuthorizationError("sensitive_classification_requires_authority")
    category, department, triage = route_category(draft["category"])
    description = _text(draft["description"], "invalid_description", 1000)
    idempotency_key = _text(draft["idempotency_key"], "invalid_idempotency_key", 200)
    created = _at(at)
    ack_minutes, due_minutes = TARGET_MINUTES[draft["urgency"]]
    candidate = {
        "request_id": _uuid(request_id or str(uuid4()), "invalid_request_id"),
        "idempotency_key": idempotency_key,
        "hotel_id": hotel_id,
        "stay_id": stay_id,
        "room_id": room_id,
        "guest_id": guest_id,
        "origin": draft["origin"],
        "category": category,
        "category_detail": _text(draft["category"], "invalid_category", 200),
        "department": department,
        "description": description,
        "urgency": draft["urgency"],
        "status": "received",
        "assigned_staff_id": None,
        "triage_required": triage,
        "sensitive": draft["sensitive"],
        "created_at": created.isoformat(),
        "updated_at": created.isoformat(),
        "received_at": created.isoformat(),
        "acknowledge_by": (created + timedelta(minutes=ack_minutes)).isoformat(),
        "due_at": (created + timedelta(minutes=due_minutes)).isoformat(),
        "version": 1,
        "last_event_id": None,
        "last_operation_signature": None,
    }
    if not isinstance(existing_requests, list):
        raise RequestError("invalid_existing_requests")
    for existing in existing_requests:
        validate_request(existing)
        if existing["hotel_id"] == hotel_id and existing["idempotency_key"] == idempotency_key:
            if _same_creation(existing, candidate):
                return {"kind": "duplicate", "request": deepcopy(existing), "plan": None}
            raise ConflictError("idempotency_conflict")
        if existing["request_id"] == candidate["request_id"]:
            raise ConflictError("duplicate_request_id")
    operation_id = _operation_id(hotel_id, candidate["request_id"], "create:" + idempotency_key)
    operation_signature = _signature({
        "kind": "create", "idempotency_key": idempotency_key,
        "request": {field: candidate.get(field) for field in (
            "hotel_id", "stay_id", "room_id", "guest_id", "origin", "category",
            "category_detail", "department", "description", "urgency", "sensitive",
        )},
    })
    event = _base_event(candidate, trusted, operation_id, "created", None,
                        "received", created.isoformat(), operation_signature)
    plan = _plan(None, candidate, event)
    return {"kind": "created", "request": deepcopy(plan["target_request"]),
            "plan": plan}


def validate_request(request):
    required = {
        "request_id", "idempotency_key", "hotel_id", "stay_id", "room_id",
        "guest_id", "origin", "category", "category_detail", "department",
        "description", "urgency", "status", "assigned_staff_id", "triage_required",
        "sensitive", "created_at", "updated_at", "received_at", "acknowledge_by",
        "due_at", "version", "last_event_id",
        "last_operation_signature",
    }
    if not isinstance(request, dict) or not required <= set(request) or (
            set(request) - required - OPTIONAL_REQUEST_FIELDS):
        raise RequestError("invalid_request_record")
    for field in ("request_id", "hotel_id", "stay_id", "room_id", "guest_id"):
        _uuid(request[field], "invalid_request_record")
    _uuid(request["last_event_id"], "invalid_request_record")
    signature = request["last_operation_signature"]
    if not isinstance(signature, str) or len(signature) != 64 or any(
            char not in "0123456789abcdef" for char in signature):
        raise RequestError("invalid_request_record")
    if request["origin"] not in ORIGINS or request["department"] not in DEPARTMENTS:
        raise RequestError("invalid_request_record")
    if request["urgency"] not in URGENCIES or request["status"] not in STATUSES:
        raise RequestError("invalid_request_record")
    if type(request["triage_required"]) is not bool or type(request["sensitive"]) is not bool:
        raise RequestError("invalid_request_record")
    if type(request["version"]) is not int or request["version"] < 1:
        raise RequestError("invalid_request_record")
    _text(request["idempotency_key"], "invalid_request_record", 200)
    _text(request["category_detail"], "invalid_request_record", 200)
    _text(request["description"], "invalid_request_record", 1000)
    if request["assigned_staff_id"] is not None:
        _text(request["assigned_staff_id"], "invalid_request_record", 200)
    routed_category, routed_department, needs_triage = route_category(request["category"])
    if (routed_category != request["category"] or routed_department != request["department"] or
            needs_triage != request["triage_required"]):
        raise RequestError("invalid_request_record")
    for field in ("created_at", "updated_at", "received_at", "acknowledge_by", "due_at"):
        _at(request[field])
    for field in OPTIONAL_REQUEST_FIELDS - {"assigned_staff_id"}:
        if request.get(field) is not None:
            _at(request[field])
    if _at(request["updated_at"]) < _at(request["created_at"]):
        raise RequestError("invalid_request_record")
    timestamp_for_status = {
        "assigned": "assigned_at", "acknowledged": "acknowledged_at",
        "in_progress": "in_progress_at", "resolved": "resolved_at",
        "reopened": "reopened_at", "cancelled": "cancelled_at",
        "escalated": "escalated_at",
    }.get(request["status"])
    if timestamp_for_status and not request.get(timestamp_for_status):
        raise RequestError("invalid_request_record")
    if request["status"] in {"assigned", "acknowledged", "in_progress", "resolved"} and not (
            request["assigned_staff_id"]):
        raise RequestError("invalid_request_record")
    if request["status"] in {"received", "reopened"} and request["assigned_staff_id"] is not None:
        raise RequestError("invalid_request_record")
    return request


def _is_admin(actor):
    return bool({"request_admin", "hotel_manager"} & set(actor["roles"]))


def _same_department_authority(request, actor):
    return actor["department"] == request["department"] and (
        actor["actor_id"] == request.get("assigned_staff_id") or
        "department_supervisor" in actor["roles"])


def _authorize_transition(request, target, actor, staff_index, assignee_id,
                          sensitive_escalation, snapshot):
    current = request["status"]
    if target not in TRANSITIONS[current]:
        raise ConflictError("invalid_status_transition")
    if actor["kind"] == "guest":
        if target != "reopened" or request["guest_id"] != actor["guest_id"]:
            raise AuthorizationError("guest_transition_forbidden")
        if snapshot is None:
            raise AuthorizationError("active_stay_required")
        _active_stay(snapshot, request["stay_id"], request["room_id"], request["guest_id"])
        return
    if target == "assigned":
        if not (_is_admin(actor) or actor["department"] == "reception"):
            raise AuthorizationError("assignment_requires_reception")
        assignee = staff_index.get(assignee_id)
        if not assignee or not assignee["active"]:
            raise RequestError("invalid_assignee")
        if assignee["department"] != request["department"]:
            raise AuthorizationError("wrong_department_assignee")
        return
    if target in {"acknowledged", "in_progress", "resolved"}:
        if not (_is_admin(actor) or _same_department_authority(request, actor)):
            raise AuthorizationError("assigned_department_authority_required")
        return
    if target == "reopened":
        if not (_is_admin(actor) or actor["department"] == "reception"):
            raise AuthorizationError("reopen_requires_reception")
        return
    if target == "cancelled":
        if not (_is_admin(actor) or actor["department"] == "reception" or
                _same_department_authority(request, actor)):
            raise AuthorizationError("cancel_requires_authority")
        return
    if target == "escalated":
        if sensitive_escalation and not (
                {"incident_manager", "hotel_manager"} & set(actor["roles"])):
            raise AuthorizationError("sensitive_escalation_requires_authority")
        if not (_is_admin(actor) or actor["department"] == "reception" or
                _same_department_authority(request, actor)):
            raise AuthorizationError("escalation_requires_authority")


def transition_request(request, target_status, actor, staff_directory, *, at,
                       operation_key, assignee_id=None, reason=None,
                       sensitive_escalation=False, snapshot=None):
    """Plan one authorized, auditable status transition."""
    validate_request(request)
    trusted = _trusted_actor(actor, request["hotel_id"], staff_directory)
    staff_index = _staff_index(staff_directory, request["hotel_id"])
    if target_status not in STATUSES:
        raise ConflictError("invalid_status_transition")
    if type(sensitive_escalation) is not bool:
        raise RequestError("invalid_sensitive_escalation")
    if sensitive_escalation and target_status != "escalated":
        raise RequestError("sensitive_flag_only_for_escalation")
    if target_status != "assigned" and assignee_id is not None:
        raise RequestError("assignee_only_for_assignment")
    if target_status in {"reopened", "cancelled", "escalated"}:
        reason = _text(reason, "transition_reason_required", 1000)
    elif reason is not None:
        reason = _text(reason, "invalid_transition_reason", 1000)
    operation_id = _operation_id(
        request["hotel_id"], request["request_id"], operation_key)
    event_id = _event_id(operation_id)
    operation_signature = _signature({
        "kind": "transition", "target_status": target_status,
        "assignee_id": assignee_id, "reason": reason,
        "sensitive_escalation": sensitive_escalation,
    })
    if request["status"] == target_status and request["last_event_id"] == event_id:
        if request["last_operation_signature"] != operation_signature:
            raise ConflictError("idempotency_conflict")
        return {"kind": "duplicate", "request": deepcopy(request), "plan": None}
    _authorize_transition(request, target_status, trusted, staff_index, assignee_id,
                          sensitive_escalation, snapshot)
    occurred = _at(at)
    if occurred < _at(request["updated_at"]):
        raise ConflictError("non_monotonic_timestamp")
    updated = deepcopy(request)
    base_request = deepcopy(request)
    updated["version"] += 1
    updated["status"] = target_status
    updated["updated_at"] = occurred.isoformat()
    timestamp_field = {
        "assigned": "assigned_at", "acknowledged": "acknowledged_at",
        "in_progress": "in_progress_at", "resolved": "resolved_at",
        "reopened": "reopened_at", "cancelled": "cancelled_at",
        "escalated": "escalated_at",
    }.get(target_status)
    if timestamp_field:
        updated[timestamp_field] = occurred.isoformat()
    if target_status == "assigned":
        updated["assigned_staff_id"] = assignee_id
    if target_status == "reopened":
        updated["assigned_staff_id"] = None
    if target_status == "escalated" and sensitive_escalation:
        updated["sensitive"] = True
    event = _base_event(updated, trusted, operation_id, "status_changed",
                        request["status"], target_status, occurred.isoformat(),
                        operation_signature, reason)
    plan = _plan(base_request, updated, event)
    return {"kind": "transitioned", "request": deepcopy(plan["target_request"]),
            "plan": plan}


def triage_request(request, category, actor, staff_directory, *, at, operation_key,
                   reason):
    """Classify an unknown request without skipping the Received state."""
    validate_request(request)
    trusted = _trusted_actor(actor, request["hotel_id"], staff_directory)
    if trusted["kind"] != "staff" or not (
            _is_admin(trusted) or trusted["department"] == "reception"):
        raise AuthorizationError("triage_requires_reception")
    canonical, department, triage = route_category(category)
    if triage:
        raise RequestError("triage_category_still_unknown")
    normalized_reason = _text(reason, "triage_reason_required", 1000)
    operation_id = _operation_id(request["hotel_id"], request["request_id"], operation_key)
    operation_signature = _signature({
        "kind": "triage", "category": canonical,
        "category_detail": category.strip(), "reason": normalized_reason,
    })
    if request["last_event_id"] == _event_id(operation_id):
        if request["last_operation_signature"] != operation_signature:
            raise ConflictError("idempotency_conflict")
        return {"kind": "duplicate", "request": deepcopy(request), "plan": None}
    if not request["triage_required"] or request["status"] != "received":
        raise ConflictError("request_not_awaiting_triage")
    occurred = _at(at)
    if occurred < _at(request["updated_at"]):
        raise ConflictError("non_monotonic_timestamp")
    updated = deepcopy(request)
    base_request = deepcopy(request)
    base_version = request["version"]
    updated.update(category=canonical, category_detail=category.strip(),
                   department=department, triage_required=False,
                   updated_at=occurred.isoformat(), version=base_version + 1)
    event = _base_event(updated, trusted, operation_id, "triaged", "received",
                        "received", occurred.isoformat(), operation_signature,
                        normalized_reason)
    plan = _plan(base_request, updated, event)
    return {"kind": "triaged", "request": deepcopy(plan["target_request"]),
            "plan": plan}


def request_view(request, actor, staff_directory, *, snapshot=None):
    """Return a role-scoped request view after validating the active actor."""
    validate_request(request)
    trusted = _trusted_actor(actor, request["hotel_id"], staff_directory)
    if trusted["kind"] == "guest":
        if trusted["guest_id"] != request["guest_id"]:
            raise AuthorizationError("cross_guest_access")
        if snapshot is None:
            raise AuthorizationError("active_stay_required")
        # Historical tickets remain tied to their original physical room.
        # The guest may still view their own ticket after an authorized move,
        # but creation and guest reopening still require the *current* room.
        _active_stay(snapshot, request["stay_id"], None, request["guest_id"])
        return {key: deepcopy(request[key]) for key in (
            "category", "description", "urgency", "status", "created_at",
            "updated_at",
        )}
    else:
        privileged = _is_admin(trusted) or trusted["department"] == "reception"
        departmental = trusted["department"] == request["department"]
        if request["sensitive"] and not (
                {"incident_manager", "hotel_manager"} & set(trusted["roles"])):
            raise AuthorizationError("sensitive_request_access_denied")
        if not (privileged or departmental):
            raise AuthorizationError("wrong_department_access")
    return deepcopy(request)


def _event_matches(left, right):
    return {k: v for k, v in left.items() if k != "commit_state"} == {
        k: v for k, v in right.items() if k != "commit_state"}


def reconcile_write(plan, persisted_request, persisted_events):
    """Choose the only safe next persistence step after a write or timeout.

    The adapter must serialize mutations for one request while applying an action.
    Workpeg SDK 0.152.0 documentation does not describe compare-and-swap.
    """
    if not isinstance(plan, dict) or set(plan) != {"base_request", "target_request", "event"}:
        raise RequestError("invalid_write_plan")
    target, expected_event = plan["target_request"], plan["event"]
    validate_request(target)
    if not isinstance(persisted_events, list):
        raise RequestError("invalid_persisted_events")
    matches = [event for event in persisted_events
               if event.get("operation_id") == expected_event["operation_id"]]
    if len(matches) > 1:
        return "manual_reconciliation_duplicate_events"
    if len(matches) == 0:
        if persisted_request is not None and persisted_request == target:
            return "manual_reconciliation_request_without_event"
        return ("append_pending_event" if persisted_request == plan["base_request"]
                else "manual_reconciliation_request_conflict")
    event = matches[0]
    if not _event_matches(event, expected_event) or event.get("commit_state") not in {
            "pending", "committed"}:
        return "manual_reconciliation_event_conflict"
    if event["commit_state"] == "committed":
        return "complete" if persisted_request == target else "manual_reconciliation_committed_mismatch"
    if persisted_request == target:
        return "commit_event"
    if persisted_request == plan["base_request"]:
        return "apply_request"
    return "manual_reconciliation_request_conflict"


def request_row_payload(request, position):
    """Full-data Workpeg row payload; required because PATCH replaces data."""
    validate_request(request)
    if type(position) not in (int, float):
        raise RequestError("invalid_row_position")
    return {"data": {key: value for key, value in request.items() if value is not None},
            "position": position, "namespace": "active",
            "inherit_business_permission": False,
            "inherit_individual_permissions": False}


def event_row_payload(event, position):
    required = {
        "event_id", "operation_id", "request_id", "hotel_id", "sequence",
        "operation_signature", "event_type", "from_status", "to_status", "actor_id", "actor_kind",
        "actor_department", "occurred_at", "reason", "commit_state",
    }
    if not isinstance(event, dict) or set(event) != required:
        raise RequestError("invalid_audit_event")
    for field in ("event_id", "operation_id", "request_id", "hotel_id"):
        _uuid(event[field], "invalid_audit_event")
    signature = event["operation_signature"]
    if not isinstance(signature, str) or len(signature) != 64 or any(
            char not in "0123456789abcdef" for char in signature):
        raise RequestError("invalid_audit_event")
    if event["to_status"] not in STATUSES or event["commit_state"] not in {"pending", "committed"}:
        raise RequestError("invalid_audit_event")
    _at(event["occurred_at"])
    if type(position) not in (int, float):
        raise RequestError("invalid_row_position")
    return {"data": {key: value for key, value in event.items() if value is not None},
            "position": position, "namespace": "audit",
            "inherit_business_permission": False,
            "inherit_individual_permissions": False}
