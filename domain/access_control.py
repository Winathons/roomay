"""Offline least-privilege access policy for Roomay hotel data.

This module evaluates already-verified access claims. It does not authenticate
Workpeg users, verify membership, or enforce hosted table permissions. Only a
trusted Workpeg adapter may construct ``AccessContext`` from authenticated
business-session data and a server-maintained staff directory.
"""
from copy import deepcopy
from dataclasses import dataclass
from uuid import UUID

from .hotel import validate_snapshot
from .service_requests import validate_request


DEPARTMENTS = {"reception", "housekeeping", "maintenance", "food_and_beverage"}
ROLES = {
    "owner_operator", "manager", "receptionist", "department_staff", "guest",
    "nonmember",
}
GUEST_SCOPED_RESOURCES = {"guest_profile", "guest_stay_summary", "guest_service_requests"}


class AccessDenied(ValueError):
    """Stable, non-sensitive refusal code for an offline policy decision."""

    def __init__(self, code):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class AccessContext:
    """Trusted-adapter claims used to evaluate policy, never client credentials.

    Boolean verification fields are assertions at this pure domain boundary;
    their truth must be established by the server-side adapter, not supplied by
    a browser, URL, AI action, or guest request.
    """

    actor_id: str
    business_id: str
    hotel_id: str
    role: str
    authenticated: bool
    membership_verified: bool
    business_binding_verified: bool
    department: str | None = None
    guest_id: str | None = None
    privileges: tuple = ()


# Proposed product policy. Workpeg enforcement is not verified by these sets.
PERMISSIONS = {
    "room_inventory": {
        "owner_operator": {"read", "update"}, "manager": {"read", "update"},
        "receptionist": {"read"}, "department_staff": {"read"},
    },
    "room_availability": {
        "owner_operator": {"read"}, "manager": {"read"}, "receptionist": {"read"},
    },
    "reservations": {
        "owner_operator": {"read", "create_request", "confirm", "cancel"},
        "manager": {"read", "create_request", "confirm", "cancel"},
        "receptionist": {"read", "create_request", "confirm", "cancel"},
    },
    "check_in_records": {
        "owner_operator": {"read", "check_in", "check_out"},
        "manager": {"read", "check_in", "check_out"},
        "receptionist": {"read", "check_in", "check_out"},
    },
    "guest_personal_data": {
        "owner_operator": {"read", "update"}, "manager": {"read", "update"},
        "receptionist": {"read"},
    },
    "registered_occupants": {
        "owner_operator": {"read", "update"}, "manager": {"read", "update"},
        "receptionist": {"read"},
    },
    "housekeeping_status": {
        "owner_operator": {"read", "update"}, "manager": {"read", "update"},
        "receptionist": {"read"}, "department_staff": {"read", "update"},
    },
    "room_maintenance_blocks": {
        "owner_operator": {"read", "create", "update", "release"},
        "manager": {"read", "create", "update", "release"},
        "receptionist": {"read"},
        "department_staff": {"read", "create", "update", "release"},
    },
    "maintenance_requests": {
        "owner_operator": {"read", "create", "update"},
        "manager": {"read", "create", "update"},
        "receptionist": {"read", "create"},
        "department_staff": {"read", "update"},
    },
    "service_requests": {
        "owner_operator": {"read", "create", "assign", "triage", "update", "cancel"},
        "manager": {"read", "create", "assign", "triage", "update", "cancel"},
        "receptionist": {"read", "create", "assign", "triage", "cancel"},
        "department_staff": {"read", "acknowledge", "update", "resolve"},
    },
    "audit_trails": {"owner_operator": {"read"}, "manager": {"read"}},
    "management_information": {"owner_operator": {"read"}, "manager": {"read"}},
    "guest_profile": {
        "owner_operator": {"read"}, "manager": {"read"}, "receptionist": {"read"},
        "guest": {"read"},
    },
    "guest_stay_summary": {"guest": {"read"}},
    "guest_service_requests": {"guest": {"read", "create"}},
}

SAFE_MESSAGES = {
    "authorization_context_missing": "Access could not be verified.",
    "authorization_context_invalid": "Access could not be verified.",
    "unauthenticated": "Sign in through Workpeg to continue.",
    "membership_unverified": "Access to this hotel's records is not verified.",
    "business_binding_unverified": "Access to this hotel's records is not verified.",
    "wrong_business": "These records are outside the active hotel business.",
    "wrong_hotel": "These records are outside the active hotel.",
    "not_hotel_member": "This account is not authorized for this hotel's records.",
    "access_denied": "This information is not available to your role.",
    "guest_scope_denied": "This guest information is not available to this account.",
    "wrong_department": "This request is outside your department's access.",
    "invalid_hotel_snapshot": "Hotel records failed validation and are hidden.",
    "invalid_record_reference": "Hotel records failed validation and are hidden.",
    "data_unavailable": "Hotel information is temporarily unavailable.",
}


def _canonical_uuid(value):
    if not isinstance(value, str):
        return False
    try:
        return str(UUID(value)) == value
    except (ValueError, TypeError, AttributeError):
        return False


def _verified_context(context):
    if not isinstance(context, AccessContext):
        raise AccessDenied("authorization_context_missing")
    if (not isinstance(context.actor_id, str) or not context.actor_id.strip()
            or not _canonical_uuid(context.business_id)
            or not _canonical_uuid(context.hotel_id)
            or not isinstance(context.role, str)
            or context.role not in ROLES
            or type(context.authenticated) is not bool
            or type(context.membership_verified) is not bool
            or type(context.business_binding_verified) is not bool
            or not isinstance(context.privileges, tuple)
            or any(not isinstance(item, str)
                   or item not in {"incident_manager", "hotel_manager"}
                   for item in context.privileges)):
        raise AccessDenied("authorization_context_invalid")
    if context.role == "nonmember":
        raise AccessDenied("not_hotel_member")
    if context.authenticated is not True:
        raise AccessDenied("unauthenticated")
    if context.membership_verified is not True:
        raise AccessDenied("membership_unverified")
    if context.business_binding_verified is not True:
        raise AccessDenied("business_binding_unverified")
    if context.role == "department_staff":
        if (not isinstance(context.department, str)
                or context.department not in DEPARTMENTS
                or context.guest_id is not None):
            raise AccessDenied("authorization_context_invalid")
    elif context.role == "guest":
        if (context.department is not None or not _canonical_uuid(context.guest_id)
                or context.privileges):
            raise AccessDenied("authorization_context_invalid")
    elif context.department is not None or context.guest_id is not None:
        raise AccessDenied("authorization_context_invalid")
    return context


def validate_hotel_snapshot(snapshot):
    """Run canonical hotel referential checks before exposing snapshot data."""
    try:
        return validate_snapshot(snapshot)
    except (ValueError, TypeError, KeyError):
        raise AccessDenied("invalid_hotel_snapshot") from None


def authorize_access(
    context, *, business_id, record_business_id, resource, action,
    record_guest_id=None, record_department=None, record_hotel_id=None,
    sensitive=False,
):
    """Authorize one proposed read/write against verified scope claims.

    ``business_id`` and record business identity must both match the active
    business binding. This is still an offline policy evaluation, not proof of
    Workpeg identity or hosted row permissions.
    """
    actor = _verified_context(context)
    if not _canonical_uuid(business_id) or not _canonical_uuid(record_business_id):
        raise AccessDenied("authorization_context_invalid")
    if (actor.business_id != business_id
            or record_business_id != actor.business_id):
        raise AccessDenied("wrong_business")
    if record_hotel_id is not None:
        if not _canonical_uuid(record_hotel_id):
            raise AccessDenied("invalid_record_reference")
        if record_hotel_id != actor.hotel_id:
            raise AccessDenied("wrong_hotel")
    if (type(sensitive) is not bool or not isinstance(resource, str)
            or not isinstance(action, str)):
        raise AccessDenied("authorization_context_invalid")
    permissions = PERMISSIONS.get(resource)
    if permissions is None or action not in permissions.get(actor.role, set()):
        raise AccessDenied("access_denied")
    if record_guest_id is not None and not _canonical_uuid(record_guest_id):
        raise AccessDenied("invalid_record_reference")
    if actor.role == "guest":
        if resource not in GUEST_SCOPED_RESOURCES or record_guest_id != actor.guest_id:
            raise AccessDenied("guest_scope_denied")
    if actor.role == "department_staff":
        if resource == "housekeeping_status" and actor.department != "housekeeping":
            raise AccessDenied("access_denied")
        if resource in {"maintenance_requests", "room_maintenance_blocks"} \
                and actor.department != "maintenance":
            raise AccessDenied("access_denied")
        if resource == "service_requests":
            if (not isinstance(record_department, str)
                    or record_department not in DEPARTMENTS):
                raise AccessDenied("invalid_record_reference")
            if record_department != actor.department:
                raise AccessDenied("wrong_department")
    if sensitive and not (
        actor.role in {"owner_operator", "manager"}
        or {"incident_manager", "hotel_manager"} & set(actor.privileges)
    ):
        raise AccessDenied("access_denied")
    return True


def authorize_hotel_snapshot(
    context, *, business_id, record_business_id, resource, action, snapshot,
    record_guest_id=None, stay_id=None, room_id=None,
):
    """Validate hotel references, then evaluate access without returning data."""
    authorize_access(
        context, business_id=business_id, record_business_id=record_business_id,
        resource=resource, action=action, record_guest_id=record_guest_id,
    )
    indexes = validate_hotel_snapshot(snapshot)
    if resource in GUEST_SCOPED_RESOURCES and record_guest_id not in indexes["guests"]:
        raise AccessDenied("invalid_record_reference")
    if resource == "guest_stay_summary":
        if not _canonical_uuid(stay_id):
            raise AccessDenied("invalid_record_reference")
        stay = indexes["stays"].get(stay_id)
        if (not stay or stay["status"] != "checked_in"
                or (room_id is not None and stay["room_id"] != room_id)):
            raise AccessDenied("guest_scope_denied")
        occupants = [row for row in snapshot["stay_guests"]
                     if row["stay_id"] == stay_id
                     and row["guest_id"] == record_guest_id
                     and not row.get("left_at")]
        if len(occupants) != 1:
            raise AccessDenied("guest_scope_denied")
    return True


def project_room_inventory(
    context, *, business_id, record_business_id, snapshot, room_id,
):
    """Project a validated room with department-staff fields minimized."""
    authorize_hotel_snapshot(
        context, business_id=business_id, record_business_id=record_business_id,
        resource="room_inventory", action="read", snapshot=snapshot,
    )
    room = next((row for row in snapshot["rooms"] if row["entity_id"] == room_id), None)
    if room is None:
        raise AccessDenied("invalid_record_reference")
    if context.role == "department_staff":
        fields = ("entity_id", "number", "room_type_id")
    else:
        fields = ("entity_id", "number", "room_type_id", "enabled", "housekeeping")
    return {key: deepcopy(room[key]) for key in fields}


def project_guest_profile(
    context, *, business_id, record_business_id, snapshot, guest_id,
):
    """Return only the authorized guest profile fields from a valid snapshot."""
    authorize_hotel_snapshot(
        context, business_id=business_id, record_business_id=record_business_id,
        resource="guest_profile", action="read", snapshot=snapshot,
        record_guest_id=guest_id,
    )
    guest = next(row for row in snapshot["guests"] if row["entity_id"] == guest_id)
    # Guest schema currently stores only these fields; never return row metadata.
    return {key: deepcopy(guest[key]) for key in ("entity_id", "display_name")}


def project_service_request(
    context, *, business_id, record_business_id, request, snapshot=None,
):
    """Return the least request detail needed by this role.

    A departmental worker sees only their department's operational request
    fields; guest identity, stay identity, hotel identity, idempotency, and audit
    linkage are omitted. Guest views return only their own public request state.
    """
    actor = _verified_context(context)
    if not isinstance(request, dict):
        raise AccessDenied("invalid_record_reference")
    try:
        validate_request(request)
    except (ValueError, TypeError, KeyError):
        raise AccessDenied("invalid_record_reference") from None
    if actor.role == "guest":
        authorize_access(
            actor, business_id=business_id, record_business_id=record_business_id,
            resource="guest_service_requests", action="read",
            record_guest_id=request.get("guest_id"),
            record_hotel_id=request.get("hotel_id"),
        )
        if snapshot is None:
            raise AccessDenied("guest_scope_denied")
        authorize_hotel_snapshot(
            actor, business_id=business_id, record_business_id=record_business_id,
            resource="guest_stay_summary", action="read", snapshot=snapshot,
            record_guest_id=request.get("guest_id"), stay_id=request.get("stay_id"),
            room_id=request.get("room_id"),
        )
        fields = ("request_id", "category", "description", "urgency", "status",
                  "created_at", "updated_at")
    elif actor.role == "department_staff":
        authorize_access(
            actor, business_id=business_id, record_business_id=record_business_id,
            resource="service_requests", action="read",
            record_department=request.get("department"),
            record_hotel_id=request.get("hotel_id"),
            sensitive=request.get("sensitive", False),
        )
        fields = ("request_id", "room_id", "category", "category_detail",
                  "department", "description", "urgency", "status",
                  "assigned_staff_id", "received_at", "due_at", "assigned_at",
                  "acknowledged_at", "in_progress_at", "resolved_at")
    else:
        authorize_access(
            actor, business_id=business_id, record_business_id=record_business_id,
            resource="service_requests", action="read",
            record_department=request.get("department"),
            record_hotel_id=request.get("hotel_id"),
            sensitive=request.get("sensitive", False),
        )
        fields = tuple(request.keys())
    return {key: deepcopy(request[key]) for key in fields if key in request}


def safe_error_message(error):
    """Map known access codes to fixed text; never echo raw exception details."""
    code = getattr(error, "code", None)
    return SAFE_MESSAGES.get(code, SAFE_MESSAGES["data_unavailable"])
