"""Offline contract for trusted staff request actions.

This module is an adapter seam, not Workpeg authentication or persistence.
Production callers must inject a server-side identity resolver and a
business-scoped request reader. No browser role or identity fields are accepted.
Plans remain unpersisted; Workpeg row writes and permission grants are not made.
"""
from copy import deepcopy
from dataclasses import dataclass
from uuid import NAMESPACE_URL, UUID, uuid5

from .access_control import (
    AccessContext, AccessDenied, authorize_access, project_service_request,
)
from .hotel import parse_instant
from .service_requests import (
    AuthorizationError, ConflictError, DEPARTMENTS, RequestError, STATUSES,
    TRANSITIONS, reconcile_write, transition_request, validate_request,
)


ACTION_TARGETS = {
    "assign": "assigned",
    "acknowledge": "acknowledged",
    "start_work": "in_progress",
    "resolve": "resolved",
    "escalate": "escalated",
}

COMMAND_FIELDS = {
    "request_id", "action", "operation_key", "expected_version",
    "expected_fingerprint", "assignee_id", "reason",
}


class StaffActionError(ValueError):
    """Stable safe refusal code; never includes row or provider contents."""

    def __init__(self, code):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class StaffActionPlan:
    state: str
    action: str
    request_id: str
    target_status: str
    plan: dict | None
    persisted: bool


def _uuid(value):
    if not isinstance(value, str):
        return False
    try:
        return str(UUID(value)) == value
    except (ValueError, TypeError, AttributeError):
        return False


def _audit_history_is_consistent(request, events):
    """Require the complete, committed audit chain for the current request.

    Audit rows can omit nullable Workpeg columns, so normalize only those
    optional fields. Unknown/missing required fields, gaps, duplicate IDs,
    pending events, or a chain that does not describe the request are refused.
    """
    if not isinstance(events, list) or not events:
        return False
    normalized = []
    required = {
        "event_id", "operation_id", "operation_signature", "request_id",
        "hotel_id", "sequence", "event_type", "to_status", "actor_id",
        "actor_kind", "occurred_at", "commit_state",
    }
    optional = {"from_status", "actor_department", "reason"}
    for event in events:
        if (not isinstance(event, dict) or required - set(event)
                or set(event) - required - optional):
            return False
        item = dict(event)
        for name in optional:
            item.setdefault(name, None)
        if (not all(_uuid(item.get(name)) for name in
                    ("event_id", "operation_id", "request_id", "hotel_id"))
                or item["event_id"] != str(uuid5(
                    NAMESPACE_URL, "roomay:request-event:" + item["operation_id"]))
                or not isinstance(item["operation_signature"], str)
                or len(item["operation_signature"]) != 64
                or any(char not in "0123456789abcdef"
                       for char in item["operation_signature"])
                or type(item["sequence"]) is not int
                or item["sequence"] < 1
                or item["event_type"] not in ("created", "status_changed", "triaged")
                or item["to_status"] not in STATUSES
                or not isinstance(item["actor_id"], str)
                or not item["actor_id"].strip()
                or item["actor_kind"] not in ("guest", "staff")
                or item["commit_state"] != "committed"):
            return False
        try:
            occurred = parse_instant(item["occurred_at"])
        except (TypeError, ValueError):
            return False
        department = item["actor_department"]
        if item["actor_kind"] == "guest":
            if department is not None:
                return False
        elif department not in DEPARTMENTS:
            return False
        if item["event_type"] == "created":
            if (item["sequence"] != 1 or item["from_status"] is not None
                    or item["to_status"] != "received"):
                return False
        elif item["event_type"] == "triaged":
            if (item["sequence"] == 1 or item["from_status"] != "received"
                    or item["to_status"] != "received"
                    or item["actor_kind"] != "staff"
                    or department != "reception"):
                return False
        elif (item["sequence"] == 1 or item["from_status"] not in STATUSES):
            return False
        reason = item["reason"]
        if reason is not None and (not isinstance(reason, str) or not reason.strip()):
            return False
        normalized.append((item, occurred))

    normalized.sort(key=lambda pair: pair[0]["sequence"])
    if len(normalized) != request.get("version"):
        return False
    event_ids = set()
    operation_ids = set()
    previous_status = None
    previous_time = None
    for index, (event, occurred) in enumerate(normalized, start=1):
        if (event["sequence"] != index
                or event["event_id"] in event_ids
                or event["operation_id"] in operation_ids
                or event["request_id"] != request.get("request_id")
                or event["hotel_id"] != request.get("hotel_id")
                or (previous_time is not None and occurred < previous_time)):
            return False
        event_ids.add(event["event_id"])
        operation_ids.add(event["operation_id"])
        if index > 1:
            if event["event_type"] == "triaged":
                if previous_status != "received":
                    return False
            elif (event["event_type"] != "status_changed"
                    or event["from_status"] != previous_status
                    or event["to_status"] not in TRANSITIONS[previous_status]):
                return False
        previous_status = event["to_status"]
        previous_time = occurred

    latest = normalized[-1][0]
    try:
        updated_at_matches = previous_time == parse_instant(request["updated_at"])
    except (KeyError, TypeError, ValueError):
        return False
    try:
        validate_request(request)
    except RequestError:
        return False
    return bool(
        latest["event_id"] == request["last_event_id"]
        and latest["operation_signature"] == request["last_operation_signature"]
        and latest["sequence"] == request["version"]
        and latest["to_status"] == request["status"]
        and updated_at_matches
    )


def project_staff_inbox(context, requests, *, business_id, record_business_id):
    """Return only the request projection authorized for this staff context.

    Department employees receive only their routed department. Reception,
    managers and owners use the existing policy projection; this is still an
    offline contract and does not filter Workpeg rows at the server.
    """
    if not isinstance(context, AccessContext):
        raise AccessDenied("authorization_context_missing")
    if not isinstance(requests, list):
        raise AccessDenied("invalid_record_reference")
    if context.role == "department_staff":
        record_department = context.department
    else:
        record_department = None
    authorize_access(
        context, business_id=business_id, record_business_id=record_business_id,
        resource="service_requests", action="read",
        record_department=record_department,
    )
    projected = []
    for request in requests:
        if not isinstance(request, dict):
            raise AccessDenied("invalid_record_reference")
        if (context.role == "department_staff"
                and request.get("department") != context.department):
            continue
        projected.append(project_service_request(
            context, business_id=business_id,
            record_business_id=record_business_id, request=request,
        ))
    return projected


class StaffActionGateway:
    """Prepare one authorized service-request transition through trusted ports.

    ``identity_resolver.resolve(session_proof)`` must derive authentication,
    business membership, staff subject, department, roles and directory from
    the actual platform session. ``request_reader.read_request`` must read the
    canonical request and audit events from the same authenticated business and
    return the Workpeg row fingerprint. Neither port is implemented here.

    The expected fingerprint/version are stale-read guards, not an atomic
    compare-and-swap. A future writer must serialize per request across all
    writers and perform the existing pending-audit -> request -> committed-audit
    reconciliation sequence before reporting persistence.
    """

    def __init__(self, identity_resolver, request_reader, trusted_clock):
        if not callable(getattr(identity_resolver, "resolve", None)):
            raise StaffActionError("trusted_identity_resolver_required")
        if not callable(getattr(request_reader, "read_request", None)):
            raise StaffActionError("trusted_request_reader_required")
        if not callable(trusted_clock):
            raise StaffActionError("trusted_clock_required")
        self.identity_resolver = identity_resolver
        self.request_reader = request_reader
        self.trusted_clock = trusted_clock

    def prepare(self, session_proof, command):
        """Return a pure plan or a verified idempotent duplicate; never write."""
        if not isinstance(command, dict) or set(command) - COMMAND_FIELDS:
            raise StaffActionError("invalid_staff_command")
        required = {"request_id", "action", "operation_key", "expected_version",
                    "expected_fingerprint"}
        if not required <= set(command):
            raise StaffActionError("invalid_staff_command")
        if (not _uuid(command["request_id"])
                or command["action"] not in ACTION_TARGETS
                or not isinstance(command["operation_key"], str)
                or not command["operation_key"].strip()
                or len(command["operation_key"]) > 200
                or type(command["expected_version"]) is not int
                or command["expected_version"] < 1
                or not isinstance(command["expected_fingerprint"], str)
                or not command["expected_fingerprint"]):
            raise StaffActionError("invalid_staff_command")
        action = command["action"]
        if ((action == "assign") != ("assignee_id" in command)
                or (action == "escalate") != ("reason" in command)
                or ("reason" in command and not isinstance(command["reason"], str))):
            raise StaffActionError("invalid_staff_command")

        try:
            identity = self.identity_resolver.resolve(session_proof)
        except Exception:
            raise StaffActionError("staff_identity_unavailable") from None
        identity_fields = {
            "authenticated", "membership_verified", "business_binding_verified",
            "active", "actor_id", "business_id", "hotel_id", "department",
            "roles", "staff_directory",
        }
        if not isinstance(identity, dict) or set(identity) != identity_fields:
            raise StaffActionError("invalid_trusted_staff_context")
        if (identity["authenticated"] is not True
                or identity["membership_verified"] is not True
                or identity["business_binding_verified"] is not True
                or identity["active"] is not True
                or not _uuid(identity["business_id"])
                or not _uuid(identity["hotel_id"])
                or not isinstance(identity["actor_id"], str)
                or not identity["actor_id"].strip()
                or identity["department"] not in {
                    "reception", "housekeeping", "maintenance", "food_and_beverage"
                }
                or not isinstance(identity["roles"], list)
                or not all(isinstance(role, str) and role for role in identity["roles"])
                or not isinstance(identity["staff_directory"], list)):
            raise StaffActionError("invalid_trusted_staff_context")
        actor_rows = [row for row in identity["staff_directory"]
                      if isinstance(row, dict)
                      and row.get("actor_id") == identity["actor_id"]]
        if (len(actor_rows) != 1 or actor_rows[0].get("active") is not True
                or actor_rows[0].get("hotel_id") != identity["hotel_id"]
                or actor_rows[0].get("department") != identity["department"]
                or actor_rows[0].get("roles") != identity["roles"]):
            raise StaffActionError("staff_directory_binding_failed")

        try:
            loaded = self.request_reader.read_request(
                command["request_id"], identity["business_id"])
        except Exception:
            raise StaffActionError("service_request_unavailable") from None
        loaded_fields = {"business_id", "hotel_id", "request", "fingerprint", "events"}
        if not isinstance(loaded, dict) or set(loaded) != loaded_fields:
            raise StaffActionError("malformed_service_request_read")
        request = loaded["request"]
        if (loaded["business_id"] != identity["business_id"]
                or loaded["hotel_id"] != identity["hotel_id"]
                or not isinstance(request, dict)
                or request.get("request_id") != command["request_id"]
                or request.get("hotel_id") != identity["hotel_id"]
                or not isinstance(loaded["fingerprint"], str)
                or not loaded["fingerprint"]
                or not isinstance(loaded["events"], list)):
            raise StaffActionError("service_request_scope_or_shape_mismatch")
        if not _audit_history_is_consistent(request, loaded["events"]):
            raise StaffActionError("unreconciled_request_audit")

        actor = {"actor_id": identity["actor_id"], "hotel_id": identity["hotel_id"],
                 "kind": "staff"}
        target_status = ACTION_TARGETS[action]
        try:
            outcome = transition_request(
                request, target_status, actor, identity["staff_directory"],
                at=self.trusted_clock(), operation_key=command["operation_key"],
                assignee_id=command.get("assignee_id"),
                reason=command.get("reason"),
                sensitive_escalation=(action == "escalate" and request.get("sensitive") is True),
            )
        except (AuthorizationError, ConflictError, RequestError) as error:
            raise StaffActionError(error.code) from None
        if outcome["kind"] == "duplicate":
            event = next((item for item in loaded["events"]
                          if isinstance(item, dict)
                          and item.get("event_id") == request.get("last_event_id")), None)
            if (event is None or event.get("commit_state") != "committed"
                    or event.get("operation_signature") != request.get("last_operation_signature")
                    or event.get("to_status") != request.get("status")):
                raise StaffActionError("duplicate_outcome_uncertain")
            return StaffActionPlan(
                "verified_duplicate", action, request["request_id"], target_status,
                None, persisted=True,
            )

        if (request["version"] != command["expected_version"]
                or loaded["fingerprint"] != command["expected_fingerprint"]):
            raise StaffActionError("stale_request_snapshot")
        # The state and actor were resolved from trusted ports. Domain plan is
        # retained for the server-side writer; it is never returned to a browser.
        return StaffActionPlan(
            "prepared", action, request["request_id"], target_status,
            deepcopy(outcome["plan"]), persisted=False,
        )


def next_persistence_step(plan, persisted_request, persisted_events):
    """Delegate pending-event/request/commit reconciliation to the canonical rules."""
    try:
        return reconcile_write(plan, persisted_request, persisted_events)
    except (RequestError, TypeError, KeyError, AttributeError):
        raise StaffActionError("persistence_reconciliation_invalid") from None
