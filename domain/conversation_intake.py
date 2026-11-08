"""Channel-neutral, offline guest conversation intake contracts.

This module classifies text or validates a provider's structured suggestion,
checks a trusted active-stay scope, and prepares the existing canonical service
request plan only after explicit guest confirmation. It never submits or saves.
"""
from dataclasses import dataclass
import re
from uuid import NAMESPACE_URL, uuid5

from .access_control import (
    AccessContext, AccessDenied, authorize_access, authorize_hotel_snapshot,
)
from .service_requests import (
    CATEGORY_DEPARTMENTS, AuthorizationError, ConflictError, RequestError,
    create_request, route_category,
)


CHANNELS = {"typed_chat", "vapi"}
INTENTS = {"service_request", "room_enquiry", "unknown", "emergency"}
URGENCIES = {"low", "normal", "high", "urgent"}
_ROOM_NUMBER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,19}$")
_ROOM_IN_TEXT = re.compile(
    r"\b(?:room|rm)(?:\s+(?:number|no\.?))?\s*#?\s*([A-Za-z0-9][A-Za-z0-9-]{0,19})\b", re.I,
)
_ROOM_FILLER = {"a", "and", "dey", "has", "have", "is", "the", "to"}
_EMERGENCY_TERMS = (
    "emergency", "fire", "smoke", "medical emergency", "someone is hurt",
    "someone is injured", "electric shock", "sparking", "gas smell",
)
_URGENT_TERMS = ("urgent", "urgently", "asap", "immediately", "right now")


class IntakeError(ValueError):
    """Stable, non-sensitive intake validation error."""

    def __init__(self, code):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class ConversationScope:
    """Claims and rows supplied by a future trusted, server-side adapter.

    This value is not an authentication credential. Never build it from fields
    sent by a browser, guest, Vapi tool call, or model. A trusted adapter must
    resolve these values from the authenticated business and hotel mapping.
    """

    business_id: str
    record_business_id: str
    trusted_snapshot_hotel_id: str
    snapshot: dict
    stay_id: str
    room_id: str
    staff_directory: list
    existing_requests: list


def _clean_text(value):
    if not isinstance(value, str):
        raise IntakeError("invalid_text")
    text = value.strip()
    if not text or len(text) > 1000:
        raise IntakeError("invalid_text")
    return text


def _room_number(text):
    found = [value for value in _ROOM_IN_TEXT.findall(text)
             if value.lower() not in _ROOM_FILLER]
    if len(found) == 1:
        return found[0]
    return None


def _is_emergency(text):
    lowered = text.lower()
    return any(term in lowered for term in _EMERGENCY_TERMS)


def _urgency(text):
    lowered = text.lower()
    return "urgent" if any(term in lowered for term in _URGENT_TERMS) else "normal"


def _intent(kind, category, urgency, room_number):
    canonical, department, triage = route_category(category)
    return {
        "intent": kind,
        "category": canonical,
        "department": department,
        "urgency": urgency,
        "room_number": room_number,
        "triage_required": triage,
    }


def classify_text(text):
    """Classify a short transcript using conservative local phrase rules.

    This is a deterministic offline fallback and test contract, not an AI model
    or a speech recognizer. Unknown but sufficiently described requests route
    to Reception for human triage.
    """
    original = _clean_text(text)
    lowered = original.lower()
    room_number = _room_number(original)
    if _is_emergency(original):
        return _intent("emergency", "unknown", "urgent", room_number)
    urgency = _urgency(original)
    if any(term in lowered for term in (
            "room enquiry", "room inquiry", "room rate", "room type",
            "room available", "room availability", "available rooms",
            "book a room", "reservation", "vacant room")):
        return _intent("room_enquiry", "general_help", urgency, room_number)
    if (re.search(r"\b(?:ac|a/c)\b", lowered) or any(term in lowered for term in (
            "air conditioning", "air conditioner", "aircon", "faulty ac",
            "no dey cool", "not cooling", "isn't cooling"))):
        return _intent("service_request", "air_conditioning", urgency, room_number)
    if any(term in lowered for term in ("towel", "towels", "linen", "bedsheet", "bed sheet")):
        return _intent("service_request", "extra_towels", urgency, room_number)
    if any(term in lowered for term in (
            "plumbing", "leak", "leaking", "pipe burst", "burst pipe",
            "water dey leak", "tap is dripping")):
        return _intent("service_request", "plumbing", urgency, room_number)
    return _intent("unknown", "unknown", urgency, room_number)


def validate_intent_output(text, candidate):
    """Validate structured classifier output without trusting its routing.

    The supplied original text is retained as the eventual request description;
    the provider cannot replace it with a fabricated summary. Department is
    recomputed from the canonical service-request catalogue.
    """
    original = _clean_text(text)
    if _is_emergency(original):
        return _intent("emergency", "unknown", "urgent", _room_number(original))
    required = {"intent", "category", "department", "urgency", "room_number"}
    if not isinstance(candidate, dict) or set(candidate) != required:
        raise IntakeError("invalid_classifier_output")
    kind = candidate["intent"]
    category = candidate["category"]
    department = candidate["department"]
    urgency = candidate["urgency"]
    room_number = candidate["room_number"]
    if (not isinstance(kind, str) or kind not in INTENTS
            or not isinstance(category, str)
            or category not in set(CATEGORY_DEPARTMENTS) | {"unknown"}
            or not isinstance(urgency, str) or urgency not in URGENCIES):
        raise IntakeError("invalid_classifier_output")
    if room_number is not None and (
            not isinstance(room_number, str) or not _ROOM_NUMBER.fullmatch(room_number)):
        raise IntakeError("invalid_classifier_output")
    # A model may not invent or infer a room number that the guest did not say.
    if room_number != _room_number(original):
        raise IntakeError("invalid_classifier_output")
    canonical, expected_department, triage = route_category(category)
    if department != expected_department:
        raise IntakeError("incorrect_department")
    if kind == "service_request" and (category == "unknown" or triage):
        raise IntakeError("invalid_classifier_output")
    if kind == "room_enquiry" and category != "general_help":
        raise IntakeError("invalid_classifier_output")
    if kind == "emergency" and (category != "unknown" or urgency != "urgent"):
        raise IntakeError("invalid_classifier_output")
    if kind == "unknown" and category != "unknown":
        raise IntakeError("invalid_classifier_output")
    return {
        "intent": kind, "category": canonical, "department": expected_department,
        "urgency": urgency, "room_number": room_number,
        "triage_required": triage,
    }


def provider_unavailable(state="failed"):
    """Return a fixed safe state for provider timeout/failure; never echo details."""
    if not isinstance(state, str) or state not in {"timeout", "failed"}:
        state = "failed"
    return _result(
        "unavailable",
        "I couldn't safely understand that message. Please contact Reception.",
        failure_code="classifier_" + state,
    )


def _result(state, message, *, intent=None, plan=None, handoff=False,
            clarification=None, failure_code=None):
    internal = {}
    if intent is not None:
        internal["intent"] = dict(intent)
    if failure_code is not None:
        internal["failure_code"] = failure_code
    if plan is not None:
        internal["request_plan"] = plan
    return {
        "state": state,
        "message": message,
        "clarification": clarification,
        "handoff_required": handoff,
        # Only state/message/clarification/handoff_required are guest-facing.
        # Adapters must never serialize `internal` to a guest channel.
        "internal": internal,
        "submitted": False,
        "persisted": False,
    }


def _safe_handoff(message, intent=None, failure_code=None):
    return _result("handoff", message, intent=intent, handoff=True,
                   failure_code=failure_code)


def _verify_guest_scope(access_context, scope, intent):
    if not isinstance(access_context, AccessContext) or not isinstance(scope, ConversationScope):
        raise AccessDenied("authorization_context_missing")
    if access_context.role != "guest" or not access_context.guest_id:
        raise AccessDenied("guest_scope_denied")
    authorize_hotel_snapshot(
        access_context,
        business_id=scope.business_id,
        record_business_id=scope.record_business_id,
        resource="guest_stay_summary",
        action="read",
        snapshot=scope.snapshot,
        trusted_snapshot_hotel_id=scope.trusted_snapshot_hotel_id,
        record_guest_id=access_context.guest_id,
        stay_id=scope.stay_id,
        room_id=scope.room_id,
    )
    authorize_access(
        access_context,
        business_id=scope.business_id,
        record_business_id=scope.record_business_id,
        record_hotel_id=scope.trusted_snapshot_hotel_id,
        record_guest_id=access_context.guest_id,
        resource="guest_service_requests",
        action="create",
    )
    rooms = [room for room in scope.snapshot["rooms"]
             if room["entity_id"] == scope.room_id]
    if len(rooms) != 1 or rooms[0]["number"] != intent["room_number"]:
        raise AccessDenied("guest_scope_denied")


def handle_conversation_turn(
    text, *, channel, conversation_id, turn_id, at, confirmed=False,
    classifier_output=None, provider_status="ok", access_context=None,
    scope=None,
):
    """Classify, clarify, hand off, or prepare one confirmed guest request.

    `at` must be a trusted, stable timestamp for this confirmation event. The
    same channel/conversation/turn IDs and timestamp must be reused on redelivery
    to obtain the same deterministic idempotency key and plan. This function has
    no submitted or persisted outcome.
    """
    try:
        original = _clean_text(text)
    except IntakeError:
        return _result("unavailable", "Please describe how we can help.",
                       failure_code="invalid_message")
    if not isinstance(channel, str) or channel not in CHANNELS:
        return _result("unavailable", "This conversation channel is unavailable.",
                       failure_code="unsupported_channel")
    if _is_emergency(original):
        emergency = _intent("emergency", "unknown", "urgent", _room_number(original))
        return _safe_handoff(
            "This may be urgent. Contact Reception immediately; if someone is in immediate danger, follow the hotel's emergency procedure. This system has not contacted anyone.",
            emergency, "emergency_handoff",
        )
    if not isinstance(provider_status, str):
        return provider_unavailable("failed")
    if provider_status != "ok":
        if provider_status in {"timeout", "failed"}:
            return provider_unavailable(provider_status)
        return provider_unavailable("failed")
    try:
        intent = (validate_intent_output(original, classifier_output)
                  if classifier_output is not None else classify_text(original))
    except (IntakeError, TypeError, AttributeError):
        return _result("unavailable", "I couldn't safely understand that message. Please contact Reception.",
                       failure_code="invalid_classifier_output")
    if intent["intent"] == "emergency" or intent["urgency"] == "urgent":
        return _safe_handoff(
            "This may be urgent. Contact Reception immediately; if someone is in immediate danger, follow the hotel's emergency procedure. This system has not contacted anyone.",
            intent, "emergency_handoff",
        )
    if intent["intent"] == "room_enquiry":
        return _safe_handoff(
            "I can connect you with Reception for room information. No availability or booking has been confirmed.",
            intent, "room_enquiry_handoff",
        )
    if intent["room_number"] is None:
        return _result(
            "needs_clarification", "Which room are you contacting us about?",
            intent=intent, clarification="room_number",
        )
    if intent["intent"] == "unknown" and len(original.split()) <= 3:
        return _result(
            "needs_clarification", "Could you briefly describe what is happening?",
            intent=intent, clarification="problem_description",
        )
    try:
        _verify_guest_scope(access_context, scope, intent)
    except (AccessDenied, KeyError, TypeError, AttributeError):
        return _safe_handoff(
            "I couldn't verify an active stay for this request. Please contact Reception.",
            intent, "stay_verification_required",
        )
    if type(confirmed) is not bool:
        return _result("unavailable", "Please confirm the request with Reception.",
                       intent=intent, failure_code="invalid_confirmation")
    if not confirmed:
        department = intent["department"].replace("_", " ").title()
        detail = ("Reception will review and triage it" if intent["triage_required"] else
                  "the " + department + " team")
        return _result(
            "awaiting_confirmation",
            "I can prepare this request for " + detail + ". It will not be sent or saved yet. Shall I prepare it?",
            intent=intent,
        )
    try:
        for value in (conversation_id, turn_id):
            if not isinstance(value, str) or not value.strip() or len(value) > 200:
                raise IntakeError("invalid_conversation_id")
        if not isinstance(scope.existing_requests, list):
            raise IntakeError("invalid_existing_requests")
        idempotency_key = str(uuid5(
            NAMESPACE_URL,
            "roomay:conversation-intake:v1:" + scope.business_id + ":" + channel
            + ":" + conversation_id + ":" + turn_id,
        ))
        request_id = str(uuid5(NAMESPACE_URL, "roomay:conversation-request:v1:" + idempotency_key))
        outcome = create_request(
            scope.snapshot,
            {
                "hotel_id": access_context.hotel_id,
                "stay_id": scope.stay_id,
                "room_id": scope.room_id,
                "guest_id": access_context.guest_id,
                "origin": "guest",
                "category": intent["category"],
                "description": original,
                "urgency": intent["urgency"],
                "idempotency_key": idempotency_key,
                "sensitive": False,
            },
            {
                "actor_id": access_context.actor_id,
                "hotel_id": access_context.hotel_id,
                "kind": "guest",
                "guest_id": access_context.guest_id,
            },
            scope.staff_directory,
            scope.existing_requests,
            at=at,
            request_id=request_id,
        )
    except (AccessDenied, AuthorizationError):
        return _safe_handoff(
            "I couldn't verify an active stay for this request. Please contact Reception.",
            intent, "stay_verification_required",
        )
    except ConflictError:
        return _safe_handoff(
            "I couldn't safely prepare this request. Please contact Reception.",
            intent, "request_conflict",
        )
    except (RequestError, IntakeError, TypeError, ValueError, KeyError, AttributeError):
        return _result(
            "unavailable", "I couldn't safely prepare this request. Please contact Reception.",
            intent=intent, failure_code="request_validation_failed",
        )
    if outcome["kind"] == "duplicate":
        return _result(
            "duplicate", "A matching request already exists in the supplied snapshot. No additional request was prepared.",
            intent=intent,
        )
    return _result(
        "prepared",
        "The request is prepared for staff review, but has not been sent or saved. Contact Reception for urgent help.",
        intent=intent,
        plan=outcome["plan"],
    )
