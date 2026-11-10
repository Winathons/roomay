"""Offline, server-boundary facade for a future Housekeeping request endpoint.

The module composes trusted Workpeg identity resolution, least-privilege
projection and the canonical service-action gateway. It does not implement
HTTP hosting, Workpeg authentication, table access, or persistence.
"""
from dataclasses import dataclass
from uuid import UUID

from .access_control import AccessContext, AccessDenied
from .staff_actions import StaffActionError, StaffActionGateway, project_staff_inbox


_IDENTITY_FIELDS = {
    "authenticated", "membership_verified", "business_binding_verified",
    "active", "actor_id", "business_id", "hotel_id", "department", "roles",
    "staff_directory",
}
_HOUSEKEEPING_ACTIONS = {"acknowledge", "start_work", "resolve", "escalate"}
_PRIVATE_REQUEST_FIELDS = {
    "guest_id", "stay_id", "hotel_id", "idempotency_key",
    "last_event_id", "last_operation_signature",
}


class HousekeepingServiceError(ValueError):
    """Sanitized refusal code for a server caller."""

    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _canonical_uuid(value):
    if not isinstance(value, str):
        return False
    try:
        return str(UUID(value)) == value
    except (ValueError, TypeError, AttributeError):
        return False


class _FixedIdentity:
    """Pass one freshly resolved server identity into the canonical gateway."""

    def __init__(self, identity):
        self.identity = identity

    def resolve(self, _session_proof):
        return self.identity


@dataclass
class HousekeepingRequestService:
    """Expose only a Housekeeping inbox projection and safe action receipt.

    The identity resolver must verify a server-held session handle on every
    request. Both readers are server-side, business-bound ports with complete
    pagination; production implementations are deliberately not supplied.
    """

    identity_resolver: object
    inbox_reader: object
    request_reader: object
    trusted_clock: object

    def __post_init__(self):
        if not callable(getattr(self.identity_resolver, "resolve", None)):
            raise HousekeepingServiceError("trusted_identity_resolver_required")
        if not callable(getattr(self.inbox_reader, "list_requests", None)):
            raise HousekeepingServiceError("trusted_inbox_reader_required")
        if not callable(getattr(self.request_reader, "read_request", None)):
            raise HousekeepingServiceError("trusted_request_reader_required")
        if not callable(self.trusted_clock):
            raise HousekeepingServiceError("trusted_clock_required")

    def _resolve_housekeeping(self, session_proof):
        try:
            identity = self.identity_resolver.resolve(session_proof)
        except Exception:
            raise HousekeepingServiceError("staff_identity_unavailable") from None
        if (not isinstance(identity, dict) or set(identity) != _IDENTITY_FIELDS
                or identity["authenticated"] is not True
                or identity["membership_verified"] is not True
                or identity["business_binding_verified"] is not True
                or identity["active"] is not True
                or not isinstance(identity["actor_id"], str)
                or not identity["actor_id"].strip()
                or not _canonical_uuid(identity["business_id"])
                or not _canonical_uuid(identity["hotel_id"])
                or identity["department"] != "housekeeping"
                or not isinstance(identity["roles"], list)
                or not all(isinstance(role, str) for role in identity["roles"])
                or not isinstance(identity["staff_directory"], list)):
            raise HousekeepingServiceError("housekeeping_access_denied")
        actors = [row for row in identity["staff_directory"]
                  if isinstance(row, dict)
                  and row.get("actor_id") == identity["actor_id"]]
        if (len(actors) != 1 or actors[0].get("active") is not True
                or actors[0].get("hotel_id") != identity["hotel_id"]
                or actors[0].get("department") != "housekeeping"
                or actors[0].get("roles") != identity["roles"]):
            raise HousekeepingServiceError("housekeeping_access_denied")
        return identity

    @staticmethod
    def _access_context(identity):
        privileges = tuple(role for role in identity["roles"]
                           if role in {"incident_manager", "hotel_manager"})
        return AccessContext(
            actor_id=identity["actor_id"],
            business_id=identity["business_id"],
            hotel_id=identity["hotel_id"],
            role="department_staff",
            authenticated=True,
            membership_verified=True,
            business_binding_verified=True,
            department="housekeeping",
            privileges=privileges,
        )

    def inbox(self, session_proof):
        """Read a complete business snapshot and return only policy fields."""
        identity = self._resolve_housekeeping(session_proof)
        try:
            snapshot = self.inbox_reader.list_requests(identity["business_id"])
        except Exception:
            raise HousekeepingServiceError("housekeeping_inbox_unavailable") from None
        if (not isinstance(snapshot, dict)
                or set(snapshot) != {"business_id", "hotel_id", "complete", "requests"}
                or snapshot["business_id"] != identity["business_id"]
                or snapshot["hotel_id"] != identity["hotel_id"]
                or snapshot["complete"] is not True
                or not isinstance(snapshot["requests"], list)):
            raise HousekeepingServiceError("housekeeping_inbox_unavailable")
        seen = set()
        for request in snapshot["requests"]:
            if not isinstance(request, dict):
                raise HousekeepingServiceError("housekeeping_inbox_unavailable")
            request_id = request.get("request_id")
            if not _canonical_uuid(request_id) or request_id in seen:
                raise HousekeepingServiceError("housekeeping_inbox_unavailable")
            seen.add(request_id)
        try:
            projected = project_staff_inbox(
                self._access_context(identity), snapshot["requests"],
                business_id=identity["business_id"],
                record_business_id=snapshot["business_id"],
            )
        except (AccessDenied, ValueError, TypeError, KeyError):
            raise HousekeepingServiceError("housekeeping_inbox_unavailable") from None
        if any(_PRIVATE_REQUEST_FIELDS & set(item) for item in projected):
            raise HousekeepingServiceError("housekeeping_inbox_unavailable")
        return {"state": "loaded", "requests": projected}

    def prepare_action(self, session_proof, command):
        """Prepare one canonical action without returning its private plan."""
        identity = self._resolve_housekeeping(session_proof)
        if (not isinstance(command, dict)
                or command.get("action") not in _HOUSEKEEPING_ACTIONS):
            raise HousekeepingServiceError("housekeeping_action_not_allowed")
        gateway = StaffActionGateway(
            _FixedIdentity(identity), self.request_reader, self.trusted_clock,
        )
        try:
            plan = gateway.prepare(session_proof, command)
        except StaffActionError as error:
            raise HousekeepingServiceError(error.code) from None
        return {
            "state": plan.state,
            "action": plan.action,
            "request_id": plan.request_id,
            "status": plan.target_status,
            "persisted": plan.persisted,
        }
