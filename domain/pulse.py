"""WOR-21: read-only Roomay Pulse suggestions from complete trusted snapshots.

No background scheduling, AI inference, Workpeg writes, escalation, guest
notification, or automatic room blocks. Pulse is strictly advisory.
"""
from dataclasses import dataclass
from datetime import timedelta
from hashlib import sha256
import json
from re import fullmatch
from uuid import UUID, NAMESPACE_URL, uuid5

from .hotel import parse_instant, validate_snapshot
from .service_requests import validate_request


_OPEN = frozenset({
    "received", "assigned", "acknowledged", "in_progress", "reopened", "escalated",
})
_MANAGEMENT = frozenset({"owner", "manager", "incident_manager"})


class PulseRejected(ValueError):
    """Sanitized reason for withholding potentially sensitive Pulse data."""


@dataclass(frozen=True)
class PulseContext:
    """Untrusted claims: production adapters must derive them from real sessions."""

    business_id: str
    snapshot_business_id: str
    hotel_id: str
    snapshot_hotel_id: str
    actor_id: str
    actor_role: str
    authorization_verified: bool
    snapshot_fresh: bool
    requests_complete: bool


@dataclass(frozen=True)
class PulsePolicy:
    min_complaints: int = 3
    window_minutes: int = 180
    acknowledgement_grace_minutes: int = 0
    resolution_grace_minutes: int = 0


@dataclass(frozen=True)
class IncidentSuggestion:
    suggestion_id: str
    hotel_id: str
    category: str
    department: str
    kind: str
    request_ids: tuple
    room_ids: tuple
    first_reported_at: str
    last_reported_at: str
    acknowledged_count: int
    open_request_count: int
    explanation: str
    status: str = "suggested"
    persisted: bool = False


@dataclass(frozen=True)
class OverdueSignal:
    request_id: str
    room_id: str
    category: str
    status: str
    acknowledgement_overdue: bool
    resolution_overdue: bool
    acknowledge_by: str
    due_at: str
    requires_staff_review: bool = True
    escalation_sent: bool = False


@dataclass(frozen=True)
class PulseSnapshot:
    hotel_id: str
    observed_at: str
    suggestions: tuple
    overdue: tuple
    read_only: bool = True


@dataclass(frozen=True)
class PulseReviewPlan:
    suggestion_id: str
    action: str
    operation_id: str
    idempotency_key: str
    operation_signature: str
    audit_intent: dict
    requires_authoritative_guard: bool = True
    requires_committed_audit: bool = True
    requires_complete_readback: bool = True
    persisted: bool = False


def _scope(context):
    if not isinstance(context, PulseContext):
        raise PulseRejected("trusted_management_context_required")
    for field in (
        "business_id", "snapshot_business_id", "hotel_id", "snapshot_hotel_id",
    ):
        value = getattr(context, field)
        if not isinstance(value, str):
            raise PulseRejected("invalid_management_scope")
        try:
            if str(UUID(value)) != value:
                raise ValueError
        except (ValueError, TypeError):
            raise PulseRejected("invalid_management_scope") from None
    if context.business_id != context.snapshot_business_id:
        raise PulseRejected("wrong_business")
    if context.hotel_id != context.snapshot_hotel_id:
        raise PulseRejected("wrong_hotel")
    if (context.authorization_verified is not True
            or context.actor_role not in _MANAGEMENT
            or not isinstance(context.actor_id, str)
            or not context.actor_id.strip()):
        raise PulseRejected("management_authorization_required")
    if context.snapshot_fresh is not True or context.requests_complete is not True:
        raise PulseRejected("complete_fresh_request_snapshot_required")


def _policy(policy):
    if not isinstance(policy, PulsePolicy):
        raise PulseRejected("invalid_pulse_policy")
    for key, low, high in (
        ("min_complaints", 2, 20),
        ("window_minutes", 5, 1440),
        ("acknowledgement_grace_minutes", 0, 1440),
        ("resolution_grace_minutes", 0, 1440),
    ):
        value = getattr(policy, key)
        if type(value) is not int or not low <= value <= high:
            raise PulseRejected("invalid_pulse_policy")


def _read_snapshot(hotel, requests, *, context, now, policy):
    _scope(context)
    _policy(policy)
    try:
        indexes = validate_snapshot(hotel)
        instant = parse_instant(now)
    except (ValueError, KeyError, TypeError, OverflowError):
        raise PulseRejected("invalid_or_incomplete_pulse_snapshot") from None
    if not isinstance(requests, list):
        raise PulseRejected("complete_fresh_request_snapshot_required")
    seen = set()
    safe = []
    for request in requests:
        try:
            validate_request(request)
            created = parse_instant(request["received_at"])
            updated = parse_instant(request["updated_at"])
        except (ValueError, KeyError, TypeError, OverflowError):
            raise PulseRejected("invalid_pulse_request_record") from None
        request_id = request["request_id"]
        if request["hotel_id"] != context.hotel_id:
            raise PulseRejected("wrong_hotel_request")
        if request_id in seen:
            raise PulseRejected("duplicate_pulse_request")
        seen.add(request_id)
        # Historical tickets may refer to a room a guest has moved out of.
        if (request["room_id"] not in indexes["rooms"]
                or request["stay_id"] not in indexes["stays"]
                or request["guest_id"] not in indexes["guests"]):
            raise PulseRejected("unknown_request_room_or_stay")
        if created > instant or updated > instant:
            raise PulseRejected("future_pulse_request")
        # Do not expose even the existence of sensitive requests through Pulse.
        if not request["sensitive"]:
            safe.append(request)
    return instant, safe


def _group_complaints(requests, context, now, policy):
    by_category = {}
    for request in requests:
        if (request["status"] in _OPEN
                and request["category"] != "unknown"):
            by_category.setdefault(request["category"], []).append(request)
    suggestions = []
    window = timedelta(minutes=policy.window_minutes)
    for category, items in sorted(by_category.items()):
        ordered = sorted(items, key=lambda r: (parse_instant(r["received_at"]), r["request_id"]))
        groups = []
        group = []
        for item in ordered:
            if (group and parse_instant(item["received_at"])
                    - parse_instant(group[0]["received_at"]) > window):
                groups.append(group)
                group = []
            group.append(item)
        if group:
            groups.append(group)
        for members in groups:
            if len(members) < policy.min_complaints:
                continue
            request_ids = tuple(sorted(item["request_id"] for item in members))
            room_ids = tuple(sorted({item["room_id"] for item in members}))
            kind = "multi_room_pattern" if len(room_ids) > 1 else "repeated_room_issue"
            suggestion_id = str(uuid5(
                NAMESPACE_URL,
                "roomay:pulse:suggestion:v1:"
                + context.business_id + ":" + context.hotel_id + ":"
                + category + ":" + ":".join(request_ids),
            ))
            explanation = (
                f"{len(request_ids)} open {category} requests in "
                f"{len(room_ids)} room(s) within {policy.window_minutes} minutes; "
                "a pattern for staff review, not a confirmed shared cause"
            )
            suggestions.append(IncidentSuggestion(
                suggestion_id=suggestion_id,
                hotel_id=context.hotel_id,
                category=category,
                department=members[0]["department"],
                kind=kind, request_ids=request_ids, room_ids=room_ids,
                first_reported_at=members[0]["received_at"],
                last_reported_at=members[-1]["received_at"],
                acknowledged_count=sum(
                    item.get("acknowledged_at") is not None for item in members
                ),
                open_request_count=len(request_ids),
                explanation=explanation,
            ))
    return tuple(sorted(suggestions, key=lambda a: (a.first_reported_at, a.suggestion_id)))


def _overdue(requests, now, policy):
    alerts = []
    ack_grace = timedelta(minutes=policy.acknowledgement_grace_minutes)
    due_grace = timedelta(minutes=policy.resolution_grace_minutes)
    for request in requests:
        if request["status"] not in _OPEN:
            continue
        # Reopened tickets carry their original first-ack deadline. Do not
        # misrepresent that as a fresh acknowledgement deadline.
        missing_ack = (request["status"] in {"received", "assigned", "escalated"}
                       and request.get("acknowledged_at") is None)
        late_ack = (missing_ack and
                    now > parse_instant(request["acknowledge_by"]) + ack_grace)
        late_resolution = now > parse_instant(request["due_at"]) + due_grace
        if late_ack or late_resolution:
            alerts.append(OverdueSignal(
                request_id=request["request_id"], room_id=request["room_id"],
                category=request["category"], status=request["status"],
                acknowledgement_overdue=late_ack, resolution_overdue=late_resolution,
                acknowledge_by=request["acknowledge_by"], due_at=request["due_at"],
            ))
    return tuple(sorted(alerts, key=lambda a: (a.due_at, a.request_id)))


def build_pulse_snapshot(hotel, requests, *, context, as_of, policy=None):
    """Calculate manager-safe signals on read; never schedule or mutate."""
    if policy is None:
        policy = PulsePolicy()
    now, safe = _read_snapshot(
        hotel, requests, context=context, now=as_of, policy=policy,
    )
    return PulseSnapshot(
        hotel_id=context.hotel_id, observed_at=now.isoformat(),
        suggestions=_group_complaints(safe, context, now, policy),
        overdue=_overdue(safe, now, policy),
    )


def prepare_pulse_review(
    pulse, *, suggestion_id, action, notes, context, idempotency_key,
    prior_operation=None,
):
    """Prepare a management accept/dismiss audit intent; do not change tickets."""
    _scope(context)
    if not isinstance(pulse, PulseSnapshot) or not pulse.read_only:
        raise PulseRejected("validated_pulse_snapshot_required")
    if pulse.hotel_id != context.hotel_id:
        raise PulseRejected("wrong_hotel")
    if action not in {"accept", "dismiss"}:
        raise PulseRejected("invalid_incident_review_action")
    suggestion = next(
        (item for item in pulse.suggestions if item.suggestion_id == suggestion_id),
        None,
    )
    if suggestion is None:
        raise PulseRejected("unknown_incident_suggestion")
    if (not isinstance(notes, str) or not 5 <= len(notes.strip()) <= 500):
        raise PulseRejected("incident_review_notes_required")
    notes = notes.strip()
    if (not isinstance(idempotency_key, str)
            or not fullmatch(r"[A-Za-z0-9_-]{12,128}", idempotency_key)):
        raise PulseRejected("invalid_idempotency_key")
    operation_id = str(uuid5(
        NAMESPACE_URL,
        f"roomay:pulse:review:v1:{context.business_id}:{idempotency_key}",
    ))
    payload = {
        "action": action, "suggestion_id": suggestion_id, "notes": notes,
        "request_ids": suggestion.request_ids, "actor_id": context.actor_id,
    }
    signature = sha256(json.dumps(
        payload, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()
    if prior_operation is not None:
        if not isinstance(prior_operation, dict) or (
                prior_operation.get("idempotency_key") != idempotency_key):
            raise PulseRejected("invalid_prior_operation")
        if (prior_operation.get("operation_id") != operation_id or
                prior_operation.get("operation_signature") != signature):
            raise PulseRejected("idempotency_key_reused_for_different_review")
        raise PulseRejected("operation_already_attempted_readback_required")
    return PulseReviewPlan(
        suggestion_id=suggestion_id, action=action, operation_id=operation_id,
        idempotency_key=idempotency_key, operation_signature=signature,
        audit_intent={
            "event": "pulse_review_planned", "action": action,
            "business_id": context.business_id, "hotel_id": context.hotel_id,
            "actor_id": context.actor_id, "suggestion_id": suggestion_id,
            "request_ids": suggestion.request_ids, "notes": notes,
            "operation_id": operation_id,
        },
    )
