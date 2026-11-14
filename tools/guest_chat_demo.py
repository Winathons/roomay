"""Loopback-only sample hotel journey backed by Roomay domain contracts.

It never contacts Workpeg, YarnGPT or PostgreSQL. Vapi text chat or voice call
requires separate local opt-in, valid configuration and a guest-session choice.
It is not registered in the released Peg UI.
"""

from dataclasses import dataclass, field, replace
from copy import deepcopy
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import argparse
import json
import os
import re
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from domain.access_control import AccessContext
from domain.conversation_intake import (
    ConversationScope, classify_text, handle_conversation_turn,
    is_explicit_hotel_problem,
)
from domain.fixtures import synthetic_hotel, uid
from domain.reception import build_reception_snapshot
from domain.service_requests import (
    CATEGORY_DEPARTMENTS, DEPARTMENTS, AuthorizationError, ConflictError,
    RequestError, reconcile_write, request_view, transition_request,
)
from tools.vapi_chat import VapiChatClient, VapiChatUnavailable


LOOPBACK = "127.0.0.1"
PORT_DEFAULT = 8765
SESSION_COOKIE = "roomay_local_session"
SESSION_TTL_SECONDS = 20 * 60
MAX_SESSIONS = 32
MAX_BODY_BYTES = 4096
MAX_GUEST_TEXT_CHARS = 1000
MAX_VAPI_CALL_SECONDS = 180
MAX_VAPI_CALLS_PER_SESSION = 3
# Synthetic hotel calendar uses Nigeria's current fixed UTC+01:00 offset.
DEMO_TIMEZONE = timezone(timedelta(hours=1), name="Africa/Lagos")
SAMPLE_PROPERTY_NAME = "The Linden House"
_ROOM_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,19}$")
_ROOM_RESPONSE = re.compile(r"^(?:room\s+|rm\s+)?([A-Za-z0-9][A-Za-z0-9-]{0,19})$", re.I)
_ROOM_CLAIM = re.compile(r"\b(?:room|rm)\s+(?:(?:number|no\.?)\s*)?#?([A-Za-z0-9-]*\d[A-Za-z0-9-]*)\b", re.I)

# Only standalone social turns count. "Hi, the AC is broken" is still a request.
_SOCIAL_GREETING = frozenset((
    "hi", "hello", "hey", "hi there", "hello there", "hey there",
    "hi are you here", "hi are you there", "are you here", "are you there",
    "good morning", "good afternoon", "good evening", "how are you",
    "what's good remi", "whats good remi", "what's good", "whats good",
    "how you dey", "how body", "how far",
))
_CASUAL_GREETING_SEQUENCE = re.compile(
    r"^(?:hey|hi|hello)(?:\s+(?:hey|hi|hello)){0,2}(?:\s+(?:there|remi))?$"
)
_PIDGIN_HOW_FAR = re.compile(r"^how\s+far(?:\s+remi)?$")
_SOCIAL_THANKS = frozenset(("thanks", "thank you", "thank you very much"))


def _social_kind(text):
    normalized = re.sub(r"\s+", " ", re.sub(r"[,.!?]", "", text.lower()).strip())
    if (normalized in _SOCIAL_GREETING or _CASUAL_GREETING_SEQUENCE.fullmatch(normalized)
            or _PIDGIN_HOW_FAR.fullmatch(normalized)):
        return "greeting"
    if normalized in _SOCIAL_THANKS:
        return "thanks"
    return None


_UNSAFE_AI_ACTION_CLAIM = re.compile(
    r"\b(?:i(?:'ve| have)\s+(?:sent|submitted|saved|created|booked|confirmed|assigned|notified)"
    r"|your\s+(?:request|booking|reservation).{0,50}\b(?:sent|submitted|saved|created|booked|confirmed|assigned|received|resolved|completed)"
    r"|(?:staff|housekeeping|maintenance)\s+(?:has\s+been\s+)?(?:notified|assigned|sent)\b)",
    re.IGNORECASE,
)


def _claims_hotel_action(text):
    return isinstance(text, str) and bool(_UNSAFE_AI_ACTION_CLAIM.search(text))


class DemoError(ValueError):
    def __init__(self, code, status=400):
        self.code = code
        self.status = status
        super().__init__(code)


@dataclass
class DemoSession:
    context: AccessContext
    scope: ConversationScope
    conversation_id: str
    messages: list = field(default_factory=list)
    state: str = "ready"
    pending: dict | None = None
    clarification: dict | None = None
    active_turn_id: str | None = None
    revision: int = 0
    completed_revision: int | None = None
    completed_reply: str | None = None
    pending_at: str | None = None
    ai_chat_consent: bool = False
    ai_chat_status: str = "disabled"
    vapi_chat_previous_id: str | None = None
    vapi_chat_turns: int = 0
    demo_requests: list = field(default_factory=list)
    demo_audit: list = field(default_factory=list)
    vapi_calls_started: int = 0
    vapi_call_started_at: float | None = None
    active_role: str = "guest"
    last_activity: float = field(default_factory=time.monotonic)
    lock: object = field(default_factory=threading.RLock)


def _new_synthetic_scope():
    """Create fictional guest authority inside the local demo process only."""
    hotel = synthetic_hotel()
    business_id = uid("conversation-business")
    hotel_id = uid("conversation-hotel")
    guest_id = uid("Guest C")
    now = datetime.now(DEMO_TIMEZONE).replace(microsecond=0)
    today = now.date()
    reservations = hotel["reservations"]
    by_id = {record["entity_id"]: record for record in reservations}
    by_id[uid("in-house")].update(
        arrival=today.isoformat(), departure=(today + timedelta(days=1)).isoformat())
    by_id[uid("future")].update(
        arrival=today.isoformat(),
        departure=(today + timedelta(days=2)).isoformat())
    by_id[uid("walk-in")].update(
        arrival=(today - timedelta(days=1)).isoformat(),
        departure=today.isoformat())
    names = {uid("Guest A"): "Tola Ibrahim", uid("Guest B"): "Chidi Nwosu",
             uid("Guest C"): "Amara Okafor"}
    for guest in hotel["guests"]:
        guest["display_name"] = names[guest["entity_id"]]
    room_type_names = {uid("standard"): "Classic Queen", uid("suite"): "Garden Suite"}
    for room_type in hotel["room_types"]:
        room_type["name"] = room_type_names[room_type["entity_id"]]
    checkin_at = now.isoformat()
    hotel["stays"][0]["checked_in_at"] = checkin_at
    hotel["stay_guests"][0]["joined_at"] = checkin_at
    hotel["room_blocks"][0].update(
        start=(today - timedelta(days=1)).isoformat(),
        end=(today + timedelta(days=1)).isoformat())
    hotel["room_blocks"][0]["room_id"] = uid("203")
    second_checkin = (now - timedelta(days=1)).isoformat()
    hotel["stays"].append({
        "entity_id": uid("stay-walk-in"), "reservation_id": uid("walk-in"),
        "room_id": uid("202"), "status": "checked_in", "checked_in_at": second_checkin,
    })
    hotel["stay_guests"].append({
        "entity_id": uid("occupant-walk-in"), "stay_id": uid("stay-walk-in"),
        "guest_id": uid("Guest B"), "joined_at": second_checkin,
    })
    staff_directory = [
        {"actor_id": uid("offline-demo-reception"), "hotel_id": hotel_id,
         "department": "reception", "roles": [], "active": True},
        {"actor_id": uid("offline-demo-housekeeping"), "hotel_id": hotel_id,
         "department": "housekeeping", "roles": [], "active": True},
    ]
    context = AccessContext(
        actor_id=uid("offline-demo-guest-actor"), business_id=business_id,
        hotel_id=hotel_id, role="guest", authenticated=True,
        membership_verified=True, business_binding_verified=True,
        guest_id=guest_id,
    )
    scope = ConversationScope(
        business_id=business_id, record_business_id=business_id,
        trusted_snapshot_hotel_id=hotel_id, snapshot=hotel,
        stay_id=uid("stay"), room_id=uid("205"), staff_directory=staff_directory,
        existing_requests=[],
    )
    return context, scope


def _department_label(value):
    if value not in DEPARTMENTS:
        return "Reception"
    return value.replace("_", " ").title()


def _category_label(value):
    if value == "unknown":
        return "Needs human triage"
    if value not in CATEGORY_DEPARTMENTS:
        return "Guest request"
    return value.replace("_", " ").title()


def _public_summary(text, intent):
    """Expose only guest text and plain labels; never the intake internal object."""
    return {
        "description": text,
        "category": _category_label(intent.get("category")),
        "department": _department_label(intent.get("department")),
    }


class GuestChatDemo:
    """Loopback-only journey store; all hotel actions are synthetic and in memory."""

    def __init__(self, *, max_sessions=MAX_SESSIONS, clock=time.monotonic,
                 chat_provider=None):
        self.max_sessions = max_sessions
        self.clock = clock
        self.chat_provider = chat_provider
        self._sessions = {}
        # Shared scenarios are short-lived, process-memory-only fixtures. The
        # join code is an internal QA convenience, never an authentication token.
        self._scenarios = {}
        self._lock = threading.RLock()

    def claim_vapi_call(self, session_id, *, max_duration=MAX_VAPI_CALL_SECONDS):
        session = self._get_session(session_id)
        with session.lock:
            if session.active_role != "guest":
                raise DemoError("demo_guest_role_required", 403)
            now = self.clock()
            if session.vapi_call_started_at is not None:
                # Recover a stale browser tab only after the bounded call window.
                if now - session.vapi_call_started_at <= max_duration + 15:
                    raise DemoError("voice_call_already_active", 409)
                session.vapi_call_started_at = None
            if session.vapi_calls_started >= MAX_VAPI_CALLS_PER_SESSION:
                raise DemoError("voice_demo_limit_reached", 429)
            session.vapi_call_started_at = now
            session.vapi_calls_started += 1
            return {"call_limit": MAX_VAPI_CALL_SECONDS,
                    "calls_remaining": MAX_VAPI_CALLS_PER_SESSION - session.vapi_calls_started}

    def release_vapi_call(self, session_id):
        session = self._get_session(session_id)
        with session.lock:
            if session.active_role != "guest":
                raise DemoError("demo_guest_role_required", 403)
            session.vapi_call_started_at = None
            return {"released": True}

    def _expire_sessions(self):
        now = self.clock()
        expired_scenarios = [code for code, scenario in self._scenarios.items()
                             if now - scenario["last_activity"] > SESSION_TTL_SECONDS]
        for code in expired_scenarios:
            self._scenarios.pop(code, None)
        expired = [key for key, session in self._sessions.items()
                   if (now - session.last_activity > SESSION_TTL_SECONDS
                       or session.qa_scenario_code not in self._scenarios)]
        for key in expired:
            self._sessions.pop(key, None)

    def create_qa_scenario(self):
        """Create a synthetic shared scenario and return its local-only join code."""
        with self._lock:
            self._expire_sessions()
            if len(self._scenarios) >= self.max_sessions:
                raise DemoError("demo_capacity_reached", 429)
            code = secrets.token_urlsafe(24)
            context, scope = _new_synthetic_scope()
            self._scenarios[code] = {
                "context": context, "scope": scope, "requests": [], "audit": [],
                "last_activity": self.clock(), "lock": threading.RLock(),
            }
            return {"scenario_code": code, "expires_in_seconds": SESSION_TTL_SECONDS,
                    "persistence": "process_memory_only"}

    def create_session(self, *, role="guest", scenario_code=None):
        with self._lock:
            self._expire_sessions()
            if len(self._sessions) >= self.max_sessions:
                raise DemoError("demo_capacity_reached", 429)
            session_id = secrets.token_urlsafe(32)
            if scenario_code is None:
                scenario_code = self.create_qa_scenario()["scenario_code"]
            scenario = self._scenarios.get(scenario_code)
            if scenario is None:
                raise DemoError("demo_scenario_expired", 401)
            if role not in {"guest", "reception", "housekeeping"}:
                raise DemoError("invalid_demo_role")
            context, scope = scenario["context"], scenario["scope"]
            session = DemoSession(context, scope, str(uuid4()))
            session.active_role = role
            session.qa_scenario_code = scenario_code
            session.demo_requests = scenario["requests"]
            session.demo_audit = scenario["audit"]
            # All independent browser sessions in one QA scenario serialize
            # their local transitions through the same in-process lock.
            session.lock = scenario["lock"]
            session.ai_chat_status = "available" if self.chat_provider is not None else "disabled"
            session.messages.append({
                "role": "assistant",
                "text": ("Welcome to Roomay. Tell us what you need and we’ll help route it. "
                         "This example stay is at The Linden House."),
            })
            self._sessions[session_id] = session
            return session_id, self.role_view(session_id)

    def resume_session(self, session_id):
        """Return the same process-memory journey after a browser reload."""
        return self.role_view(session_id)

    def _get_session(self, session_id):
        if not isinstance(session_id, str) or not session_id:
            raise DemoError("demo_session_expired", 401)
        with self._lock:
            self._expire_sessions()
            session = self._sessions.get(session_id)
            if session is None:
                raise DemoError("demo_session_expired", 401)
            session.last_activity = self.clock()
            scenario = self._scenarios.get(session.qa_scenario_code)
            if scenario is None:
                self._sessions.pop(session_id, None)
                raise DemoError("demo_session_expired", 401)
            scenario["last_activity"] = self.clock()
            return session

    @staticmethod
    def _view(session):
        pending = None
        if session.pending is not None:
            pending = {
                "revision": session.pending["revision"],
                "summary": dict(session.pending["summary"]),
            }
        return {
            "messages": [dict(message) for message in session.messages],
            "state": session.state,
            "pending": pending,
            "submitted": False,
            "persisted": False,
            "ai_chat": {
                "available": session.ai_chat_status != "disabled",
                "consented": session.ai_chat_consent,
                "status": session.ai_chat_status,
            },
        }

    def set_ai_chat_consent(self, session_id, enabled):
        if type(enabled) is not bool:
            raise DemoError("invalid_chat_consent")
        session = self._get_session(session_id)
        with session.lock:
            if session.active_role != "guest":
                raise DemoError("demo_guest_role_required", 403)
            if enabled and self.chat_provider is None:
                raise DemoError("chat_ai_unavailable", 409)
            session.ai_chat_consent = enabled
            session.ai_chat_status = "ready" if enabled else (
                "available" if self.chat_provider is not None else "disabled")
            if not enabled:
                # Do not let Vapi context resume if the guest later opts in again.
                session.vapi_chat_previous_id = None
            return self.role_view(session_id)

    @staticmethod
    def _now():
        return datetime.now(DEMO_TIMEZONE).replace(microsecond=0).isoformat()

    @staticmethod
    def _staff_actor(session, department):
        match = next((row for row in session.scope.staff_directory
                      if row["department"] == department), None)
        if match is None:
            raise DemoError("demo_role_unavailable", 409)
        return {"actor_id": match["actor_id"], "hotel_id": match["hotel_id"],
                "kind": "staff"}

    @staticmethod
    def _advance_demo_transaction(session, plan):
        """Apply canonical pending-event/request/committed-event steps in memory."""
        request_id = plan["target_request"]["request_id"]
        current = next((deepcopy(row) for row in session.demo_requests
                        if row["request_id"] == request_id), None)
        events = [deepcopy(event) for event in session.demo_audit
                  if event["request_id"] == request_id]
        for _ in range(5):
            step = reconcile_write(plan, current, events)
            if step == "append_pending_event":
                events.append(deepcopy(plan["event"]))
            elif step == "apply_request":
                current = deepcopy(plan["target_request"])
            elif step == "commit_event":
                event = next(item for item in events
                             if item["operation_id"] == plan["event"]["operation_id"])
                event["commit_state"] = "committed"
            elif step == "complete":
                if current is None:
                    raise DemoError("demo_reconciliation_failed", 409)
                # These lists are shared by every independent browser session
                # joined to the same local scenario. Mutate in place so all
                # workspace projections observe the verified transition.
                session.demo_requests[:] = [row for row in session.demo_requests
                                            if row["request_id"] != request_id]
                session.demo_requests.append(deepcopy(current))
                session.demo_audit[:] = [event for event in session.demo_audit
                                         if event["request_id"] != request_id]
                session.demo_audit.extend(deepcopy(events))
                retained = [row for row in session.scope.existing_requests
                            if row["request_id"] != request_id]
                retained.append(deepcopy(current))
                session.scope.existing_requests[:] = retained
                return deepcopy(current)
            else:
                raise DemoError("demo_reconciliation_failed", 409)
        raise DemoError("demo_reconciliation_failed", 409)

    @staticmethod
    def _safe_request(request, hotel, role):
        guest = next((row["display_name"] for row in hotel["guests"]
                      if row["entity_id"] == request["guest_id"]), "Fictional guest")
        room = next((row["number"] for row in hotel["rooms"]
                     if row["entity_id"] == request["room_id"]), "—")
        events = sorted((event for event in request.get("_demo_events", [])),
                        key=lambda event: event.get("sequence", 0))
        return {"request_id": request["request_id"],
                "description": request["description"], "category": request["category"],
                "department": request["department"], "urgency": request["urgency"],
                "status": request["status"], "room": room,
                "guest": guest if role == "reception" else None,
                "history": [event["to_status"] for event in events]}

    @staticmethod
    def _safe_history(session, request_id):
        return [
            event["to_status"] for event in sorted(
                (row for row in session.demo_audit if row["request_id"] == request_id),
                key=lambda row: row["sequence"],
            )
        ]

    def role_view(self, session_id):
        """Return only the active workspace projection, never all roles at once."""
        session = self._get_session(session_id)
        with session.lock:
            hotel = session.scope.snapshot
            today = datetime.now(DEMO_TIMEZONE).date().isoformat()
            stay = next(item for item in hotel["stays"]
                        if item["entity_id"] == session.scope.stay_id)
            booking = next(item for item in hotel["reservations"]
                           if item["entity_id"] == stay["reservation_id"])
            guest = next(item for item in hotel["guests"]
                         if item["entity_id"] == session.context.guest_id)
            room = next(item for item in hotel["rooms"]
                        if item["entity_id"] == stay["room_id"])
            room_type = next(item for item in hotel["room_types"]
                             if item["entity_id"] == room["room_type_id"])
            base = {"workspace": session.active_role, "property_name": SAMPLE_PROPERTY_NAME,
                    "example_property": True}

            if session.active_role == "guest":
                actor = {"actor_id": session.context.actor_id,
                         "hotel_id": session.context.hotel_id, "kind": "guest",
                         "guest_id": session.context.guest_id}
                requests = []
                for request in session.demo_requests:
                    if request["guest_id"] != session.context.guest_id:
                        continue
                    visible = request_view(request, actor, session.scope.staff_directory,
                                           snapshot=hotel)
                    requests.append({
                        "description": visible["description"],
                        "category": _category_label(visible["category"]),
                        "department": _department_label(request["department"]),
                        "urgency": visible["urgency"], "status": visible["status"],
                        "created_at": visible["created_at"],
                    })
                return {**base, "guest": {
                    "name": guest["display_name"], "room": room["number"],
                    "room_type": room_type["name"], "check_in": booking["arrival"],
                    "check_out": booking["departure"], "stay_status": stay["status"],
                    "reservation_status": booking["status"],
                }, "requests": requests, "chat": self._view(session),
                    "reception_contact": {"available": False,
                        "message": "Reception contact details have not been configured for this example property."}}

            if session.active_role == "reception":
                projection = build_reception_snapshot(
                    hotel, session.demo_requests, today, session.demo_audit)
                requests = []
                actor = self._staff_actor(session, "reception")
                for request in session.demo_requests:
                    visible = request_view(request, actor, session.scope.staff_directory)
                    enriched = deepcopy(request)
                    enriched["_demo_events"] = [
                        row for row in session.demo_audit
                        if row["request_id"] == request["request_id"]
                    ]
                    requests.append(self._safe_request(
                        {**enriched, **visible}, hotel, "reception"))
                return {**base, "date": today, "metrics": projection["metrics"],
                    "arrivals": projection["arrivals"], "departures": projection["departures"],
                    "overdue_departures": projection["overdue_departures"],
                    "in_house": projection["in_house"], "rooms": projection["rooms"],
                    "requests": requests}

            if session.active_role == "housekeeping":
                actor = self._staff_actor(session, "housekeeping")
                requests = []
                for request in session.demo_requests:
                    if (request["department"] != "housekeeping"
                            or request["assigned_staff_id"] != actor["actor_id"]):
                        continue
                    visible = request_view(request, actor, session.scope.staff_directory)
                    requests.append({
                        "request_id": visible["request_id"],
                        "description": visible["description"],
                        "category": _category_label(visible["category"]),
                        "urgency": visible["urgency"], "status": visible["status"],
                        "room": next((row["number"] for row in hotel["rooms"]
                                      if row["entity_id"] == visible["room_id"]), "—"),
                        "activity": self._safe_history(session, request["request_id"]),
                    })
                return {**base, "requests": requests}

            raise DemoError("workspace_unavailable", 403)

    def switch_role(self, session_id, role):
        if role not in {"guest", "reception", "housekeeping"}:
            raise DemoError("invalid_demo_role")
        session = self._get_session(session_id)
        with session.lock:
            session.active_role = role
        return self.role_view(session_id)

    def session_role(self, session_id):
        return self._get_session(session_id).active_role

    def assign_latest_to_housekeeping(self, session_id, request_id=None):
        session = self._get_session(session_id)
        with session.lock:
            if session.active_role != "reception":
                raise DemoError("demo_reception_role_required", 403)
            if not session.demo_requests:
                raise DemoError("no_demo_request", 409)
            request = next((row for row in session.demo_requests
                            if request_id is not None and row["request_id"] == request_id),
                           session.demo_requests[-1] if request_id is None else None)
            if request is None:
                raise DemoError("request_unavailable", 404)
            if request["department"] != "housekeeping":
                raise DemoError("demo_assignment_unavailable", 409)
            actor = self._staff_actor(session, "reception")
            assignee_id = next(row["actor_id"] for row in session.scope.staff_directory
                               if row["department"] == request["department"])
            try:
                result = transition_request(
                    request, "assigned", actor, session.scope.staff_directory,
                    at=self._now(), operation_key="demo-assign-housekeeping-v1",
                    assignee_id=assignee_id,
                )
                if result["kind"] == "transitioned":
                    self._advance_demo_transaction(session, result["plan"])
            except (AuthorizationError, ConflictError, RequestError, StopIteration):
                raise DemoError("demo_assignment_unavailable", 409) from None
            return self.role_view(session_id)

    def department_action(self, session_id, action, request_id=None):
        targets = {"acknowledge": "acknowledged", "start": "in_progress",
                   "resolve": "resolved"}
        if action not in targets:
            raise DemoError("invalid_department_action")
        session = self._get_session(session_id)
        with session.lock:
            if session.active_role != "housekeeping":
                raise DemoError("demo_housekeeping_role_required", 403)
            if not session.demo_requests:
                raise DemoError("no_demo_request", 409)
            request = next((row for row in session.demo_requests
                            if request_id is not None and row["request_id"] == request_id),
                           session.demo_requests[-1] if request_id is None else None)
            if request is None:
                raise DemoError("request_unavailable", 404)
            if request["department"] != "housekeeping":
                raise DemoError("demo_department_action_unavailable", 409)
            actor = self._staff_actor(session, "housekeeping")
            try:
                result = transition_request(
                    request, targets[action], actor, session.scope.staff_directory,
                    at=self._now(), operation_key="demo-housekeeping-" + action + "-v1",
                )
                if result["kind"] == "transitioned":
                    self._advance_demo_transaction(session, result["plan"])
            except (AuthorizationError, ConflictError, RequestError):
                raise DemoError("demo_department_action_unavailable", 409) from None
            return self.role_view(session_id)

    @staticmethod
    def _append(session, role, text):
        session.messages.append({"role": role, "text": text})
        if len(session.messages) > 40:
            session.messages = session.messages[-40:]

    @staticmethod
    def _room_reply(text):
        match = _ROOM_RESPONSE.fullmatch(text.strip())
        if not match:
            return text.strip()
        room = match.group(1)
        if (not _ROOM_TOKEN.fullmatch(room)
                or not any(character.isdigit() for character in room)):
            return text.strip()
        return "room " + room

    def send_message(self, session_id, text, *, _provider_status="ok"):
        if not isinstance(text, str) or not text.strip() or len(text.strip()) > MAX_GUEST_TEXT_CHARS:
            raise DemoError("invalid_message")
        session = self._get_session(session_id)
        with session.lock:
            if session.active_role != "guest":
                raise DemoError("demo_guest_role_required", 403)
            text = text.strip()
            session.completed_revision = None
            session.completed_reply = None
            self._append(session, "guest", text)

            session.revision += 1
            candidate = classify_text(text)
            social = _social_kind(text)
            combined_text = text
            turn_id = str(uuid4())

            # Continue a previously requested clarification with the guest's
            # answer. A spoken/typed room is still only a mismatch check against
            # the trusted scope, never identity evidence.
            if session.clarification is not None and not social:
                previous = session.clarification["text"]
                clarification_reply = (self._room_reply(text)
                                       if session.clarification["kind"] == "room_number"
                                       else text)
                combined_text = previous + " " + clarification_reply
                turn_id = session.clarification["turn_id"]
                candidate = classify_text(combined_text)
                session.clarification = None

            actionable = (candidate["intent"] in {"service_request", "room_enquiry", "emergency"}
                          or is_explicit_hotel_problem(combined_text))

            # A room number by itself is context for a real follow-up, not a
            # request and never a way to authenticate or change the stay.
            standalone_room = _ROOM_RESPONSE.fullmatch(text)
            if (candidate["intent"] == "unknown" and session.clarification is None
                    and standalone_room is not None
                    and any(character.isdigit() for character in standalone_room.group(1))):
                session.clarification = {
                    "kind": "problem_description",
                    "text": "room " + standalone_room.group(1),
                    "turn_id": turn_id,
                }
                session.state = "needs_clarification"
                session.active_turn_id = None
                self._append(session, "assistant",
                             "What do you need help with in that room? Please describe the issue.")
                return self._view(session)

            if candidate["intent"] == "unknown" and not social and len(text.split()) <= 3:
                session.clarification = {
                    "kind": "problem_description", "text": text, "turn_id": turn_id,
                }
                session.state = "needs_clarification"
                session.active_turn_id = None
                self._append(session, "assistant", "Could you briefly describe what is happening?")
                return self._view(session)

            # A pending proposal is not silently canceled by a greeting or a new
            # topic. Keep it visible; refuse stacking a second operational draft.
            if session.pending is not None and (actionable or _ROOM_CLAIM.search(text)):
                if candidate["intent"] == "emergency":
                    session.pending = None
                    session.pending_at = None
                    self._append(session, "assistant",
                                 "I’ve cleared the earlier unsubmitted draft. "
                                 "This may be urgent. Contact Reception immediately; "
                                 "if anyone is in immediate danger, follow the hotel’s "
                                 "emergency procedure. This system has not contacted anyone.")
                    session.state = "handoff"
                    session.active_turn_id = None
                    return self._view(session)
                else:
                    # Run the proposed second message through the canonical
                    # scope/room checks before preserving the current proposal.
                    # This catches a wrong-room claim instead of masking it as
                    # a generic 'one proposal at a time' response.
                    preflight_text = (combined_text if candidate["intent"] in {
                        "service_request", "room_enquiry", "emergency"}
                        else session.pending["text"] + " " + combined_text)
                    preflight = handle_conversation_turn(
                        preflight_text, channel="typed_chat",
                        conversation_id=session.conversation_id, turn_id=str(uuid4()),
                        at=self._now(), confirmed=False,
                        access_context=session.context, scope=session.scope,
                    )
                    if preflight["state"] == "handoff":
                        session.pending = None
                        session.pending_at = None
                        session.state = "handoff"
                        self._append(session, "assistant", preflight["message"])
                    else:
                        self._append(session, "assistant",
                                     "There is already a request proposal above. Confirm or cancel it before starting another request.")
                    return self._view(session)

            if actionable:
                # Operational proposals always pass through the canonical domain
                # validator. The conversational model never selects a department,
                # authorizes an action, or sees these request details.
                session.vapi_chat_previous_id = None
                session.ai_chat_status = "ready" if session.ai_chat_consent else (
                    "available" if self.chat_provider is not None else "disabled")
                session.clarification = None
                session.active_turn_id = turn_id
                turn_at = self._now()
                result = handle_conversation_turn(
                    combined_text, channel="typed_chat", conversation_id=session.conversation_id,
                    turn_id=turn_id, at=turn_at, confirmed=False,
                    provider_status=_provider_status, access_context=session.context,
                    scope=session.scope,
                )
                session.state = result["state"]
                if result["state"] == "awaiting_confirmation":
                    intent = result.get("internal", {}).get("intent", {})
                    session.pending = {
                        "revision": session.revision, "text": combined_text,
                        "turn_id": turn_id, "summary": _public_summary(combined_text, intent),
                    }
                    session.pending_at = turn_at
                    session.active_turn_id = None
                elif result.get("clarification"):
                    session.clarification = {
                        "kind": result["clarification"], "text": text,
                        "turn_id": turn_id,
                    }
                else:
                    session.active_turn_id = None
                self._append(session, "assistant", result["message"])
                return self._view(session)

            # Text about hotel facts must never be answered from model memory.
            # classify_text maps supported property-information topics to the
            # safe Reception handoff above; this is an additional status guard.
            normalized = re.sub(r"\s+", " ", text.casefold())
            if any(term in normalized for term in (
                    "breakfast", "check-out", "checkout", "wifi", "wi-fi",
                    "parking", "pool", "hotel address", "amenities", "room rate",
                    "available rooms", "availability")):
                self._append(session, "assistant",
                             "I don't have verified hotel details for that. Please contact Reception for current information.")
                session.state = "ready"
                session.active_turn_id = None
                return self._view(session)

            # Natural chat is optional and requires an explicit per-session
            # guest consent. Provider failure does not fall through to action logic.
            if (self.chat_provider is not None and session.ai_chat_consent
                    and session.vapi_chat_turns < 30 and _provider_status == "ok"):
                try:
                    chat_id, reply = self.chat_provider.reply(
                        text, previous_chat_id=session.vapi_chat_previous_id)
                    if _claims_hotel_action(reply):
                        raise VapiChatUnavailable("unsafe_response")
                    session.vapi_chat_previous_id = chat_id
                    session.vapi_chat_turns += 1
                    session.ai_chat_status = "ready"
                    self._append(session, "assistant", reply)
                except Exception:
                    session.ai_chat_status = "unavailable"
                    self._append(session, "assistant",
                                 "I’m having trouble reaching Remi’s chat service right now. You can try again, or contact Reception for help.")
                session.state = "ready"
                session.active_turn_id = None
                return self._view(session)

            session.state = "needs_clarification" if session.clarification else "ready"
            session.active_turn_id = None
            if social == "thanks":
                reply = "You're welcome. What else would you like to chat about?"
            elif social == "greeting":
                reply = "Hello! I’m here to help with your stay. What would you like to talk about?"
            elif self.chat_provider is not None and not session.ai_chat_consent:
                reply = "Remi’s text AI is off until you choose to share messages with the chat provider. You can still ask about service requests or contact Reception."
            else:
                reply = "I’m here to help with your stay. You can ask me a question or describe something you need."
            self._append(session, "assistant", reply)
            return self._view(session)

    def confirm(self, session_id, revision):
        if isinstance(revision, bool) or not isinstance(revision, int):
            raise DemoError("confirmation_out_of_date", 409)
        session = self._get_session(session_id)
        with session.lock:
            if session.active_role != "guest":
                raise DemoError("demo_guest_role_required", 403)
            if (session.completed_revision == revision and session.completed_reply is not None):
                return self._view(session)
            pending = session.pending
            if pending is None or pending["revision"] != revision:
                raise DemoError("confirmation_out_of_date", 409)

            result = handle_conversation_turn(
                pending["text"], channel="typed_chat",
                conversation_id=session.conversation_id,
                turn_id=pending["turn_id"], at=session.pending_at or self._now(),
                confirmed=True, access_context=session.context, scope=session.scope,
            )
            session.pending = None
            session.pending_at = None
            session.state = result["state"]
            intent = result.get("internal", {}).get("intent", {})
            if result["state"] == "prepared":
                plan = result.get("internal", {}).get("request_plan", {})
                request = plan.get("target_request")
                if isinstance(request, dict) and isinstance(plan, dict):
                    self._advance_demo_transaction(session, plan)
                department = _department_label(intent.get("department"))
                reply = (f"Your request is ready for {department} in this example session. "
                         "It has not been sent to hotel staff.")
                session.completed_revision = revision
                session.completed_reply = reply
            else:
                reply = result["message"]
                session.completed_revision = None
                session.completed_reply = None
            session.active_turn_id = None
            self._append(session, "assistant", reply)
            return self._view(session)

    def cancel(self, session_id, revision):
        if isinstance(revision, bool) or not isinstance(revision, int):
            raise DemoError("confirmation_out_of_date", 409)
        session = self._get_session(session_id)
        with session.lock:
            if session.active_role != "guest":
                raise DemoError("demo_guest_role_required", 403)
            if session.pending is None or session.pending["revision"] != revision:
                raise DemoError("confirmation_out_of_date", 409)
            session.pending = None
            session.pending_at = None
            session.state = "cancelled"
            session.completed_revision = None
            session.completed_reply = None
            session.active_turn_id = None
            session.clarification = None
            self._append(session, "assistant",
                         "Canceled. Nothing was prepared, sent to staff, or saved.")
            return self._view(session)


def _decode_cookie(value):
    cookie = SimpleCookie()
    try:
        cookie.load(value or "")
    except Exception:
        return None
    morsel = cookie.get(SESSION_COOKIE)
    return morsel.value if morsel else None


def _vapi_web_config(environ, *, enabled):
    """Return only a public-key browser configuration; never read a private key."""
    if not enabled:
        return None
    env = os.environ if environ is None else environ
    public_key = env.get("ROOMAY_VAPI_PUBLIC_KEY", "")
    assistant_id = env.get("ROOMAY_VAPI_TEST_ASSISTANT_ID", "")
    voice = env.get("ROOMAY_VAPI_TEST_ASSISTANT_VOICE", "").strip().lower()
    model_provider = env.get("ROOMAY_VAPI_TEST_LLM_PROVIDER", "").strip().lower()
    model_name = env.get("ROOMAY_VAPI_TEST_LLM_MODEL", "").strip()
    if (not isinstance(public_key, str) or not 16 <= len(public_key) <= 512
            or not re.fullmatch(r"[A-Za-z0-9_.-]+", public_key)
            or not isinstance(assistant_id, str)
            or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", assistant_id)
            or voice != "remi"
            or model_provider not in {"openai", "anthropic", "google", "azure-openai"}
            or not re.fullmatch(r"[A-Za-z0-9._-]{1,80}", model_name)):
        return None
    return {"public_key": public_key, "assistant_id": assistant_id,
            "voice_label": "Remi", "model_provider": model_provider,
            "model_name": model_name, "max_duration_seconds": MAX_VAPI_CALL_SECONDS}


def _vapi_chat_client(environ, *, enabled):
    """Load a private-key client only after explicit local operator opt-in."""
    if not enabled:
        return None
    environ = os.environ if environ is None else environ
    private_key = environ.get("ROOMAY_VAPI_CHAT_PRIVATE_KEY", "")
    assistant_id = environ.get("ROOMAY_VAPI_CHAT_ASSISTANT_ID", "")
    try:
        return VapiChatClient(private_key, assistant_id)
    except (TypeError, ValueError):
        return None


def make_server(demo=None, port=PORT_DEFAULT, *, enable_local_qa=False,
                enable_vapi_web_call=False, vapi_environment=None,
                enable_vapi_chat=False, chat_environment=None):
    chat_client = _vapi_chat_client(chat_environment, enabled=enable_vapi_chat)
    demo = demo or GuestChatDemo(chat_provider=chat_client)
    if enable_vapi_web_call and not enable_local_qa:
        raise ValueError("vapi_web_call_requires_local_qa")
    if enable_vapi_chat and not enable_local_qa:
        raise ValueError("vapi_chat_requires_local_qa")
    vapi_config = _vapi_web_config(vapi_environment, enabled=enable_vapi_web_call)
    assets = Path(__file__).with_name("guest_chat_demo_assets")
    allowed_hosts = {"127.0.0.1", "localhost"}

    class Handler(BaseHTTPRequestHandler):
        server_version = "RoomayLocalJourney/1"
        sys_version = ""

        def log_message(self, format, *args):
            # Guest text and cookies must never appear in local HTTP logs.
            return

        def _local_host(self):
            try:
                host = urlsplit("//" + self.headers.get("Host", "")).hostname
                port_value = urlsplit("//" + self.headers.get("Host", "")).port
            except ValueError:
                return False
            return host in allowed_hosts and port_value == self.server.server_port

        def _same_origin(self):
            try:
                origin = urlsplit(self.headers.get("Origin", ""))
                origin_port = origin.port or (443 if origin.scheme == "https" else 80)
            except ValueError:
                return False
            return (origin.scheme == "http" and origin.hostname in allowed_hosts
                    and origin_port == self.server.server_port)

        def _send(self, status, body, *, content_type="application/json; charset=utf-8",
                  extra=(), allow_vapi_web_call=False):
            if isinstance(body, str):
                payload = body.encode("utf-8")
            else:
                payload = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Frame-Options", "DENY")
            for name, value in extra:
                self.send_header(name, value)
            if content_type.startswith("text/html"):
                connect_sources = "'self'"
                frame_sources = "'self'"
                if allow_vapi_web_call:
                    # The SDK creates calls through api.vapi.ai and joins a
                    # Daily room. The browser-reported call-machine assets use
                    # these exact HTTPS hosts; keep provider origins out of
                    # pages that do not load Call Remi.
                    connect_sources += (
                        " https://api.vapi.ai https://*.daily.co wss://*.daily.co"
                        " https://c.dailywebrtc.com https://d.dailywebrtc.net"
                        " https://c.dailywebrtc.net"
                    )
                    frame_sources += " https://*.daily.co"
                self.send_header(
                    "Content-Security-Policy",
                    "default-src 'self'; script-src 'self'; style-src 'self'; "
                    f"connect-src {connect_sources}; frame-src {frame_sources}; "
                    "img-src 'self'; object-src 'none'; "
                    "base-uri 'none'; form-action 'self'; frame-ancestors 'none'",
                )
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):
            if not self._local_host():
                return self._send(403, {"error": "loopback_only"})
            if self.path == "/":
                self.send_response(302)
                self.send_header("Location", "/stay")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                return
            pages = {
                "/stay": ("index.html", "guest"),
                "/staff/reception": ("reception.html", "reception"),
                "/staff/housekeeping": ("housekeeping.html", "housekeeping"),
            }
            if self.path == "/__qa/":
                if not enable_local_qa:
                    return self._send(404, {"error": "not_found"})
                pages[self.path] = ("qa.html", "qa")
            page = pages.get(self.path)
            if page is not None:
                name, expected_role = page
                session_id = _decode_cookie(self.headers.get("Cookie", ""))
                if expected_role in {"reception", "housekeeping"}:
                    try:
                        if demo.session_role(session_id) != expected_role:
                            return self._workspace_denied(403)
                    except DemoError:
                        return self._workspace_denied(401)
                elif expected_role == "guest" and session_id:
                    try:
                        if demo.session_role(session_id) != "guest":
                            return self._workspace_denied(403)
                    except DemoError:
                        # A stale guest cookie can safely start a fresh example session.
                        pass
                try:
                    content = (assets / name).read_text(encoding="utf-8")
                except OSError:
                    return self._send(500, {"error": "workspace_unavailable"})
                if name == "index.html" and vapi_config is not None:
                    content = content.replace(
                        "<!-- optional-vapi-sdk -->",
                        '<script src="/vapi_sdk.js" defer></script>',
                    )
                return self._send(
                    200, content, content_type="text/html; charset=utf-8",
                    allow_vapi_web_call=(name == "index.html" and vapi_config is not None),
                )
            paths = {
                "/app.css": ("app.css", "text/css; charset=utf-8"),
                "/voice_intake.js": ("voice_intake.js", "text/javascript; charset=utf-8"),
                "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                "/vapi_call.js": ("vapi_call.js", "text/javascript; charset=utf-8"),
                "/roomay-orb.js": ("roomay-orb.js", "text/javascript; charset=utf-8"),
            }
            if vapi_config is not None:
                paths["/vapi_sdk.js"] = ("vapi_sdk.js", "text/javascript; charset=utf-8")
            if enable_local_qa:
                paths["/qa.js"] = ("qa.js", "text/javascript; charset=utf-8")
            asset = paths.get(self.path)
            if asset is None:
                return self._send(404, {"error": "not_found"})
            name, content_type = asset
            try:
                content = (assets / name).read_text(encoding="utf-8")
            except OSError:
                return self._send(500, {"error": "demo_asset_unavailable"})
            self._send(200, content, content_type=content_type)

        def _workspace_denied(self, status):
            message = ("This workspace is not available for this session. "
                       "Use the correct signed-in hotel workspace.")
            recovery = ("<p><a href=\"/__qa/\">Return to the internal workspace selector</a> "
                        "to choose a local test role.</p>" if enable_local_qa else "")
            home_path = "/__qa/" if enable_local_qa else "/stay"
            content = ("<!doctype html><html lang=\"en\"><meta charset=\"utf-8\">"
                       "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
                       "<title>Workspace unavailable | ROOMAY</title>"
                       "<link rel=\"stylesheet\" href=\"/app.css\"><body><main class=\"page-shell\">"
                       f"<header class=\"topbar\"><a class=\"brand\" href=\"{home_path}\">"
                       "<span class=\"brand-mark\" aria-hidden=\"true\">R</span>"
                       "<span class=\"brand-name\">roomay<span class=\"brand-period\">.</span></span>"
                       "</a></header><section class=\"empty-panel\" role=\"alert\"><h1>Workspace unavailable</h1>"
                       f"<p>{message}</p>{recovery}</section></main></body></html>")
            self._send(status, content, content_type="text/html; charset=utf-8")

        def _json_body(self):
            if self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json":
                raise DemoError("invalid_content_type")
            raw_length = self.headers.get("Content-Length", "")
            if not raw_length.isdigit():
                raise DemoError("invalid_content_length")
            length = int(raw_length)
            if length <= 0 or length > MAX_BODY_BYTES:
                raise DemoError("request_too_large" if length > MAX_BODY_BYTES else "empty_request", 413)
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise DemoError("truncated_request")
            try:
                value = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                raise DemoError("invalid_json") from None
            if not isinstance(value, dict):
                raise DemoError("invalid_request")
            return value

        def do_POST(self):
            if not self._local_host() or not self._same_origin():
                return self._send(403, {"error": "same_origin_required"})
            allowed_api = {"/api/session", "/api/message", "/api/confirm", "/api/cancel",
                           "/api/assign", "/api/staff-action"}
            if chat_client is not None:
                allowed_api.add("/api/chat/consent")
            if vapi_config is not None:
                allowed_api.update({"/api/voice/config", "/api/voice/claim", "/api/voice/release"})
            if enable_local_qa:
                allowed_api.update({"/api/qa/select", "/api/qa/scenario"})
            if self.path not in allowed_api:
                return self._send(404, {"error": "not_found"})
            try:
                body = self._json_body()
                if self.path == "/api/voice/config":
                    if body:
                        raise DemoError("invalid_request")
                    session_id = _decode_cookie(self.headers.get("Cookie", ""))
                    if demo.session_role(session_id) != "guest":
                        raise DemoError("demo_guest_role_required", 403)
                    return self._send(200, {
                        "enabled": True,
                        "publicKey": vapi_config["public_key"],
                        "assistantId": vapi_config["assistant_id"],
                        "assistantLabel": "Remi",
                        "modelProvider": vapi_config["model_provider"],
                        "modelName": vapi_config["model_name"],
                        "maxDurationSeconds": vapi_config["max_duration_seconds"],
                    })
                if self.path == "/api/voice/claim":
                    if body:
                        raise DemoError("invalid_request")
                    session_id = _decode_cookie(self.headers.get("Cookie", ""))
                    return self._send(200, demo.claim_vapi_call(session_id))
                if self.path == "/api/voice/release":
                    if body:
                        raise DemoError("invalid_request")
                    session_id = _decode_cookie(self.headers.get("Cookie", ""))
                    return self._send(200, demo.release_vapi_call(session_id))
                if self.path == "/api/session":
                    if body:
                        raise DemoError("invalid_request")
                    session_id = _decode_cookie(self.headers.get("Cookie", ""))
                    try:
                        view = demo.resume_session(session_id) if session_id else None
                    except DemoError:
                        view = None
                    if view is None:
                        session_id, view = demo.create_session()
                        cookie = self._session_cookie(session_id)
                        return self._send(200, view, extra=(("Set-Cookie", cookie),))
                    return self._send(200, view)

                if self.path == "/api/chat/consent":
                    if set(body) != {"enabled"} or type(body["enabled"]) is not bool:
                        raise DemoError("invalid_chat_consent")
                    session_id = _decode_cookie(self.headers.get("Cookie", ""))
                    if session_id is None:
                        raise DemoError("demo_session_expired", 401)
                    return self._send(200, demo.set_ai_chat_consent(session_id, body["enabled"]))

                if self.path == "/api/qa/select":
                    if (set(body) not in ({"role"}, {"role", "scenario_code"})
                            or body["role"] not in {"guest", "reception", "housekeeping"}
                            or ("scenario_code" in body and not isinstance(body["scenario_code"], str))):
                        raise DemoError("invalid_workspace")
                    if "scenario_code" in body:
                        session_id, _ = demo.create_session(
                            role=body["role"], scenario_code=body["scenario_code"])
                        target = {"guest": "/stay", "reception": "/staff/reception",
                                  "housekeeping": "/staff/housekeeping"}[body["role"]]
                        return self._send(200, {"path": target}, extra=(
                            ("Set-Cookie", self._session_cookie(session_id)),))
                    session_id = _decode_cookie(self.headers.get("Cookie", ""))
                    set_cookie = None
                    try:
                        demo.session_role(session_id)
                    except DemoError:
                        session_id, _ = demo.create_session()
                        set_cookie = self._session_cookie(session_id)
                    demo.switch_role(session_id, body["role"])
                    target = {"guest": "/stay", "reception": "/staff/reception",
                              "housekeeping": "/staff/housekeeping"}[body["role"]]
                    extra = (("Set-Cookie", set_cookie),) if set_cookie else ()
                    return self._send(200, {"path": target}, extra=extra)

                if self.path == "/api/qa/scenario":
                    if body:
                        raise DemoError("invalid_request")
                    scenario = demo.create_qa_scenario()
                    return self._send(200, scenario)

                session_id = _decode_cookie(self.headers.get("Cookie", ""))
                if session_id is None:
                    raise DemoError("demo_session_expired", 401)
                if self.path == "/api/message":
                    if set(body) != {"text"}:
                        raise DemoError("invalid_request")
                    demo.send_message(session_id, body["text"])
                    view = demo.role_view(session_id)
                elif self.path == "/api/confirm":
                    if set(body) != {"revision"}:
                        raise DemoError("invalid_request")
                    demo.confirm(session_id, body["revision"])
                    view = demo.role_view(session_id)
                elif self.path == "/api/cancel":
                    if set(body) != {"revision"}:
                        raise DemoError("invalid_request")
                    demo.cancel(session_id, body["revision"])
                    view = demo.role_view(session_id)
                elif self.path == "/api/assign":
                    if set(body) != {"request_id"} or not isinstance(body["request_id"], str):
                        raise DemoError("invalid_request")
                    view = demo.assign_latest_to_housekeeping(session_id, body["request_id"])
                else:
                    if (set(body) != {"action", "request_id"}
                            or not isinstance(body["request_id"], str)):
                        raise DemoError("invalid_request")
                    view = demo.department_action(session_id, body["action"], body["request_id"])
                self._send(200, view)
            except DemoError as error:
                self._send(error.status, {"error": error.code})
            except Exception:
                # Do not return exception text; it could contain private state.
                self._send(500, {"error": "demo_temporarily_unavailable"})

        @staticmethod
        def _session_cookie(session_id):
            return (f"{SESSION_COOKIE}={session_id}; Path=/; Max-Age={SESSION_TTL_SECONDS}; "
                    "HttpOnly; SameSite=Strict")

    server = ThreadingHTTPServer((LOOPBACK, port), Handler)
    server.daemon_threads = True
    server.enable_local_qa = enable_local_qa
    server.enable_vapi_web_call = vapi_config is not None
    return server


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run the local Roomay example journey on loopback.")
    parser.add_argument("--port", type=int, default=PORT_DEFAULT)
    parser.add_argument("--enable-local-qa", action="store_true",
                        help="Enable the loopback-only role selection page for internal acceptance testing.")
    parser.add_argument("--enable-vapi-web-call", action="store_true",
                        help="Enable on-click Vapi calls in local QA; requires Vapi public-key, test-assistant and Remi voice env settings.")
    parser.add_argument("--enable-vapi-chat", action="store_true",
                        help="Enable opt-in Vapi text chat in local QA; requires server-only ROOMAY_VAPI_CHAT_PRIVATE_KEY and ROOMAY_VAPI_CHAT_ASSISTANT_ID. Provider usage may be billable and logged.")
    args = parser.parse_args(argv)
    server = make_server(port=args.port, enable_local_qa=args.enable_local_qa,
                         enable_vapi_web_call=args.enable_vapi_web_call,
                         enable_vapi_chat=args.enable_vapi_chat)
    print(f"Roomay local example journey listening at http://{LOOPBACK}:{server.server_port}/stay")
    if args.enable_local_qa:
        print(f"Internal test role selection: http://{LOOPBACK}:{server.server_port}/__qa/")
    if args.enable_vapi_web_call:
        print("Vapi browser calls: enabled only when local public-key/test-assistant/Remi settings validate; no call starts automatically.")
    if args.enable_vapi_chat:
        print("Vapi text chat: available only with valid server-side configuration and explicit guest consent; no provider call starts automatically.")
    print("Example records and request states are process-local; no hotel systems are contacted. Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
