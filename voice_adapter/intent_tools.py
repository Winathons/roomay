"""Authenticated, non-mutating Vapi function-tool boundary.

This adapter routes caller intent only. Vapi provider authentication does not
authenticate a guest, and this module deliberately has no hotel-data, booking,
guest-session, Workpeg, or persistence capability.
"""

from collections import OrderedDict
from dataclasses import dataclass
import hashlib
import hmac
import json
import os
import re
import threading
import time

from domain.conversation_intake import classify_text


TOOL_NAME = "roomay_route_caller_intent"
MAX_REQUEST_BYTES = 32 * 1024
MAX_TOOL_CALLS = 4
MAX_UTTERANCE_CHARS = 1000
REPLAY_TTL_SECONDS = 600
REPLAY_CAPACITY = 1024

_BOOKING_TERMS = re.compile(r"\b(book|booking|reservation|reserve|availability|available room|vacant room)\b|\broom\s+(?:rate|rates|price|prices)\b", re.I)
_HUMAN_TERMS = re.compile(r"\b(receptionist|reception|front desk|frontdesk|human|real person|operator|speak to someone|talk to someone|speak to staff|agent)\b", re.I)
_PIN_TERMS = re.compile(r"\b(pin|stay code|verification code|forgot.*code|forgot.*pin)\b", re.I)
_PUBLIC_TERMS = re.compile(
    r"\b(address|location|directions|amenities|facilities|wifi|wi-fi|parking|check[- ]?in time|check[- ]?out time|restaurant|pool|swimming|opening hours)\b",
    re.I,
)
_EMERGENCY_TERMS = re.compile(
    r"\b(emergency|fire|smoke|medical emergency|someone is hurt|someone is injured|electric shock|sparking|gas smell|person dey bleed|i dey bleed|someone is bleeding)\b",
    re.I,
)


@dataclass(frozen=True)
class ToolConfig:
    bearer_token: str
    requests_per_minute: int = 60

    def validate(self):
        if not isinstance(self.bearer_token, str) or len(self.bearer_token) < 32:
            raise ValueError("tool_bearer_token_must_be_32_chars")
        if (isinstance(self.requests_per_minute, bool)
                or not isinstance(self.requests_per_minute, int)
                or not 1 <= self.requests_per_minute <= 600):
            raise ValueError("invalid_tool_rate_limit")

    @classmethod
    def from_environment(cls, environ=None):
        env = os.environ if environ is None else environ
        try:
            limit = int(env.get("ROOMAY_VAPI_TOOL_REQUESTS_PER_MINUTE", "60"))
        except (TypeError, ValueError):
            raise ValueError("invalid_tool_configuration") from None
        config = cls(env.get("ROOMAY_VAPI_TOOL_BEARER_TOKEN", ""), limit)
        config.validate()
        return config


def route_caller_intent(utterance):
    """Return a minimal safe routing result without echoing caller content."""
    if not isinstance(utterance, str):
        return _result("unavailable", "I could not process that request. Please contact Reception.")
    text = utterance.strip()
    if not text or len(text) > MAX_UTTERANCE_CHARS:
        return _result("unavailable", "I could not process that request. Please contact Reception.")

    if _EMERGENCY_TERMS.search(text):
        return _result(
            "human_handoff",
            "This may be urgent. Contact Reception immediately and follow the hotel's emergency procedure. This system has not contacted or transferred you.",
            handoff=True,
        )
    if _HUMAN_TERMS.search(text):
        return _result(
            "human_handoff",
            "You are asking for a receptionist. This function cannot transfer the call; please use the hotel's receptionist transfer option.",
            handoff=True,
        )
    if _PIN_TERMS.search(text):
        return _result(
            "verification_unavailable",
            "Stay verification is unavailable in this call service. Please contact Reception; do not share a PIN here.",
            handoff=True,
            verification_required=True,
        )
    if _BOOKING_TERMS.search(text):
        return _result(
            "booking_enquiry",
            "Reception can check booking options. No availability, price, or reservation has been verified or confirmed.",
            department="reception",
        )

    try:
        intent = classify_text(text)
    except (TypeError, ValueError, AttributeError):
        intent = None
    if intent and intent.get("intent") == "service_request":
        department = intent.get("department")
        if department not in {"housekeeping", "maintenance", "food_and_beverage", "reception"}:
            return _result("unavailable", "Please contact Reception for help.")
        return _result(
            "guest_verification_required",
            "I can understand the type of help you need, but I cannot verify an active stay or submit a request here. Please contact Reception to continue.",
            department=department,
            verification_required=True,
        )

    if intent and intent.get("intent") == "room_enquiry":
        return _result(
            "public_enquiry_unavailable",
            "I do not have verified room information or availability in this call service. Please ask Reception; nothing has been quoted or reserved.",
            department="reception",
        )

    if _PUBLIC_TERMS.search(text):
        return _result(
            "public_enquiry_unavailable",
            "I do not have verified hotel information available in this call service. Please ask Reception; no hotel details were assumed.",
            department="reception",
        )

    return {
        "state": "needs_clarification",
        "message": "Are you calling about hotel information, a new booking, help with an existing stay, or a receptionist?",
        "handoff_required": False,
        "department": None,
        "verification_required": False,
        "submitted": False,
        "persisted": False,
    }


def _result(state, message, *, handoff=False, department=None, verification_required=False):
    return {
        "state": state,
        "message": message,
        "handoff_required": handoff,
        "department": department,
        "verification_required": verification_required,
        "submitted": False,
        "persisted": False,
    }


class _FixedWindowLimiter:
    """Process-local aggregate limiter; deployment must also rate-limit at edge."""

    def __init__(self, limit, *, clock=None):
        self.limit = limit
        self.clock = clock or time.monotonic
        self.window = None
        self.count = 0
        self.lock = threading.Lock()

    def allow(self):
        current = int(self.clock() // 60)
        with self.lock:
            if current != self.window:
                self.window, self.count = current, 0
            if self.count >= self.limit:
                return False
            self.count += 1
            return True


class _ReplayCache:
    """Bounded replay cache stores only hashes and sanitized result documents."""

    def __init__(self, *, clock=None):
        self.clock = clock or time.monotonic
        self.values = OrderedDict()
        self.lock = threading.Lock()

    def run(self, delivery_key, name, arguments, operation):
        cache_key = hashlib.sha256(delivery_key.encode("utf-8")).hexdigest()
        fingerprint = hashlib.sha256(json.dumps(
            [name, arguments], sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")).hexdigest()
        now = self.clock()
        with self.lock:
            for key, (expires, _, _) in list(self.values.items()):
                if expires <= now:
                    del self.values[key]
            previous = self.values.get(cache_key)
            if previous:
                if not hmac.compare_digest(previous[1], fingerprint):
                    return _result("unavailable", "This request could not be safely replayed. Please contact Reception.")
                self.values.move_to_end(cache_key)
                return dict(previous[2])
            result = operation()
            self.values[cache_key] = (now + REPLAY_TTL_SECONDS, fingerprint, dict(result))
            while len(self.values) > REPLAY_CAPACITY:
                self.values.popitem(last=False)
            return result


def _response(start_response, status, body, extra_headers=()):
    payload = json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    headers = [
        ("Content-Type", "application/json; charset=utf-8"),
        ("Content-Length", str(len(payload))),
        ("Cache-Control", "no-store"),
        ("X-Content-Type-Options", "nosniff"),
    ] + list(extra_headers)
    start_response(f"{status} {_STATUS.get(status, 'Error')}", headers)
    return [payload]


_STATUS = {200: "OK", 400: "Bad Request", 401: "Unauthorized", 404: "Not Found", 405: "Method Not Allowed",
           413: "Payload Too Large", 429: "Too Many Requests"}


def _parse_document(environ):
    raw_length = environ.get("CONTENT_LENGTH", "")
    if not raw_length.isdigit() or int(raw_length) <= 0:
        raise ValueError
    length = int(raw_length)
    if length > MAX_REQUEST_BYTES:
        raise OverflowError
    raw = environ["wsgi.input"].read(length)
    if len(raw) != length:
        raise ValueError
    try:
        document = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_json_object,
                              parse_constant=_reject_json_constant)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ValueError from None
    if not isinstance(document, dict) or not isinstance(document.get("message"), dict):
        raise ValueError
    message = document["message"]
    call = message.get("call")
    if call is not None and not isinstance(call, dict):
        raise ValueError
    vapi_call_id = call.get("id", "") if call else ""
    if not isinstance(vapi_call_id, str) or len(vapi_call_id) > 128:
        raise ValueError
    calls = message.get("toolCallList")
    if message.get("type") != "tool-calls" or not isinstance(calls, list) or not calls or len(calls) > MAX_TOOL_CALLS:
        raise ValueError
    return vapi_call_id, calls


def _validate_call(call):
    if not isinstance(call, dict) or call.get("type") != "function":
        raise ValueError
    call_id = call.get("id")
    function = call.get("function")
    if not isinstance(call_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", call_id):
        raise ValueError
    if not isinstance(function, dict) or not isinstance(function.get("name"), str):
        raise ValueError
    name = function["name"]
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", name):
        raise ValueError
    arguments = function.get("arguments")
    if not isinstance(arguments, dict):
        raise ValueError
    if name == TOOL_NAME:
        if set(arguments) != {"utterance"}:
            raise ValueError
        utterance = arguments["utterance"]
        if not isinstance(utterance, str) or not utterance.strip() or len(utterance) > MAX_UTTERANCE_CHARS:
            raise ValueError
    elif len(arguments) > 16:
        raise ValueError
    return call_id, name, arguments


def _unique_json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_json_key")
        result[key] = value
    return result


def _reject_json_constant(_value):
    raise ValueError("invalid_json_constant")


def create_tool_app(config, *, limiter=None, replay_cache=None, router=route_caller_intent):
    """Create the Vapi Server URL tool-calls WSGI handler (no provider I/O)."""
    config.validate()
    request_limiter = limiter or _FixedWindowLimiter(config.requests_per_minute)
    replays = replay_cache or _ReplayCache()

    def app(environ, start_response):
        if environ.get("REQUEST_METHOD") != "POST":
            return _response(start_response, 405, {"error": "method_not_allowed"}, [("Allow", "POST")])
        if environ.get("PATH_INFO", "/") not in {"/", "/tool-calls"}:
            return _response(start_response, 404, {"error": "not_found"})
        if environ.get("CONTENT_TYPE", "").split(";", 1)[0].strip().lower() != "application/json":
            return _response(start_response, 400, {"error": "invalid_request"})
        authorization = environ.get("HTTP_AUTHORIZATION", "")
        prefix = "Bearer "
        supplied = authorization[len(prefix):] if authorization.startswith(prefix) else ""
        if not hmac.compare_digest(supplied.encode("utf-8"), config.bearer_token.encode("utf-8")):
            return _response(start_response, 401, {"error": "unauthorized"}, [("WWW-Authenticate", "Bearer")])
        if not request_limiter.allow():
            return _response(start_response, 429, {"error": "rate_limited"}, [("Retry-After", "60")])
        try:
            vapi_call_id, calls = _parse_document(environ)
            validated = [_validate_call(call) for call in calls]
            if len({item[0] for item in validated}) != len(validated):
                raise ValueError
        except OverflowError:
            return _response(start_response, 413, {"error": "request_too_large"})
        except (ValueError, KeyError, TypeError):
            return _response(start_response, 400, {"error": "invalid_tool_call"})

        results = []
        for call_id, name, arguments in validated:
            def invoke():
                if name != TOOL_NAME:
                    return _result("unavailable", "This Roomay voice action is unavailable. Please contact Reception.")
                try:
                    outcome = router(arguments["utterance"])
                    allowed = {"state", "message", "handoff_required", "department",
                               "verification_required", "submitted", "persisted"}
                    if not isinstance(outcome, dict) or set(outcome) != allowed:
                        raise ValueError
                    if (not isinstance(outcome["state"], str) or not isinstance(outcome["message"], str)
                            or type(outcome["handoff_required"]) is not bool
                            or type(outcome["verification_required"]) is not bool
                            or outcome["department"] not in {None, "housekeeping", "maintenance", "food_and_beverage", "reception"}
                            or outcome["submitted"] is not False or outcome["persisted"] is not False):
                        raise ValueError
                    return dict(outcome)
                except Exception:
                    return _result("unavailable", "This voice service is temporarily unavailable. Please contact Reception.")

            result = replays.run(vapi_call_id + "\0" + call_id, name, arguments, invoke)
            results.append({"name": name, "toolCallId": call_id,
                            "result": json.dumps(result, separators=(",", ":"), ensure_ascii=False)})
        return _response(start_response, 200, {"results": results})

    return app
