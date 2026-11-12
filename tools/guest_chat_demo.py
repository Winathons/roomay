"""Loopback-only synthetic hotel journey backed by Roomay domain contracts.

Run from the repository root with ``python -m tools.guest_chat_demo``. This server never contacts
Workpeg, Vapi, YarnGPT, PostgreSQL, or any other remote service.
"""

from dataclasses import dataclass, field, replace
from copy import deepcopy
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import argparse
import json
import re
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from domain.access_control import AccessContext
from domain.conversation_intake import ConversationScope, handle_conversation_turn
from domain.fixtures import synthetic_hotel, uid
from domain.reception import build_reception_snapshot
from domain.service_requests import (
    CATEGORY_DEPARTMENTS, DEPARTMENTS, AuthorizationError, ConflictError,
    RequestError, reconcile_write, request_view, transition_request,
)


LOOPBACK = "127.0.0.1"
PORT_DEFAULT = 8765
SESSION_COOKIE = "roomay_offline_demo"
SESSION_TTL_SECONDS = 20 * 60
MAX_SESSIONS = 32
MAX_BODY_BYTES = 4096
MAX_GUEST_TEXT_CHARS = 1000
# Synthetic hotel calendar uses Nigeria's current fixed UTC+01:00 offset.
DEMO_TIMEZONE = timezone(timedelta(hours=1), name="Africa/Lagos")
_ROOM_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,19}$")
_ROOM_RESPONSE = re.compile(r"^(?:room\s+|rm\s+)?([A-Za-z0-9][A-Za-z0-9-]{0,19})$", re.I)

# Only standalone social turns count. "Hi, the AC is broken" is still a request.
_SOCIAL_GREETING = frozenset((
    "hi", "hello", "hey", "hi there", "hello there", "hey there",
    "hi are you here", "hi are you there", "are you here", "are you there",
    "good morning", "good afternoon", "good evening", "how are you",
))
_SOCIAL_THANKS = frozenset(("thanks", "thank you", "thank you very much"))


def _social_kind(text):
    normalized = re.sub(r"\s+", " ", text.lower().strip(" \t\r\n.!?,"))
    if normalized in _SOCIAL_GREETING:
        return "greeting"
    if normalized in _SOCIAL_THANKS:
        return "thanks"
    return None


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
    demo_requests: list = field(default_factory=list)
    demo_audit: list = field(default_factory=list)
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
        arrival=(today + timedelta(days=1)).isoformat(),
        departure=(today + timedelta(days=3)).isoformat())
    by_id[uid("walk-in")].update(
        arrival=today.isoformat(), departure=(today + timedelta(days=2)).isoformat())
    checkin_at = now.isoformat()
    hotel["stays"][0]["checked_in_at"] = checkin_at
    hotel["stay_guests"][0]["joined_at"] = checkin_at
    hotel["room_blocks"][0].update(
        start=(today - timedelta(days=1)).isoformat(),
        end=(today + timedelta(days=1)).isoformat())
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

    def __init__(self, *, max_sessions=MAX_SESSIONS, clock=time.monotonic):
        self.max_sessions = max_sessions
        self.clock = clock
        self._sessions = {}
        self._lock = threading.RLock()

    def _expire_sessions(self):
        now = self.clock()
        expired = [key for key, session in self._sessions.items()
                   if now - session.last_activity > SESSION_TTL_SECONDS]
        for key in expired:
            self._sessions.pop(key, None)

    def create_session(self):
        with self._lock:
            self._expire_sessions()
            if len(self._sessions) >= self.max_sessions:
                raise DemoError("demo_capacity_reached", 429)
            session_id = secrets.token_urlsafe(32)
            context, scope = _new_synthetic_scope()
            session = DemoSession(context, scope, str(uuid4()))
            session.messages.append({
                "role": "assistant",
                "text": ("Welcome to Roomay. Tell me what you need and I’ll help route it. "
                         "This page uses a fictional guest context; no real stay is verified "
                         "and no real hotel staff can see this demo."),
            })
            self._sessions[session_id] = session
            return session_id, self.journey_view(session_id)

    def resume_session(self, session_id):
        """Return the same process-memory journey after a browser reload."""
        return self.journey_view(session_id)

    def _get_session(self, session_id):
        if not isinstance(session_id, str) or not session_id:
            raise DemoError("demo_session_expired", 401)
        with self._lock:
            self._expire_sessions()
            session = self._sessions.get(session_id)
            if session is None:
                raise DemoError("demo_session_expired", 401)
            session.last_activity = self.clock()
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
        }

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
                session.demo_requests = [row for row in session.demo_requests
                                         if row["request_id"] != request_id]
                session.demo_requests.append(deepcopy(current))
                session.demo_audit = [event for event in session.demo_audit
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
        return {"description": request["description"], "category": request["category"],
                "department": request["department"], "urgency": request["urgency"],
                "status": request["status"], "room": room,
                "guest": guest if role == "reception" else None,
                "demo_version": request["version"],
                "demo_history": [event["to_status"] for event in events]}

    def journey_view(self, session_id):
        session = self._get_session(session_id)
        with session.lock:
            hotel = session.scope.snapshot
            today = datetime.now(DEMO_TIMEZONE).date().isoformat()
            projection = build_reception_snapshot(
                hotel, session.demo_requests, today, session.demo_audit)
            room = next(item for item in projection["rooms"] if item["number"] == "205")
            stay = next(item for item in hotel["stays"]
                        if item["entity_id"] == session.scope.stay_id)
            booking = next(item for item in hotel["reservations"]
                           if item["entity_id"] == stay["reservation_id"])
            guest = next(item for item in hotel["guests"]
                         if item["entity_id"] == session.context.guest_id)
            guest_requests = []
            department_requests = []
            for request in session.demo_requests:
                guest_projection = request_view(
                    request,
                    {"actor_id": session.context.actor_id, "hotel_id": session.context.hotel_id,
                     "kind": "guest", "guest_id": session.context.guest_id},
                    session.scope.staff_directory, snapshot=hotel,
                )
                if request["guest_id"] == session.context.guest_id:
                    guest_requests.append(guest_projection)
                if request["department"] == "housekeeping":
                    staff_projection = request_view(
                        request, self._staff_actor(session, "housekeeping"),
                        session.scope.staff_directory,
                    )
                    department_requests.append(self._safe_request(
                        staff_projection, hotel, "housekeeping"))
            request_history = {request["request_id"]: [
                deepcopy(event) for event in session.demo_audit
                if event["request_id"] == request["request_id"]
            ] for request in session.demo_requests}
            safe_reception_requests = []
            for item in session.demo_requests:
                enriched = deepcopy(item)
                enriched["_demo_events"] = request_history.get(item["request_id"], [])
                safe_reception_requests.append(
                    self._safe_request(enriched, hotel, "reception"))
            return {
                "demo": True, "notice": "SYNTHETIC DEMO — NO LIVE HOTEL REQUEST SUBMITTED",
                "storage": "This journey is held in this local server process memory; it survives page reload, not a server restart.",
                "role": session.active_role, "date": today,
                "chat": self._view(session),
                "guest": {"name": guest["display_name"], "room": "205",
                          "stay_status": stay["status"], "reservation_status": booking["status"],
                          "departure": booking["departure"],
                          "requests": guest_requests},
                "reception": {"metrics": projection["metrics"],
                              "room": room,
                              "rooms": projection["rooms"],
                              "requests": safe_reception_requests},
                "housekeeping": {"requests": department_requests},
            }

    def switch_role(self, session_id, role):
        if role not in {"guest", "reception", "housekeeping"}:
            raise DemoError("invalid_demo_role")
        session = self._get_session(session_id)
        with session.lock:
            session.active_role = role
        return self.journey_view(session_id)

    def assign_latest_to_housekeeping(self, session_id):
        session = self._get_session(session_id)
        with session.lock:
            if session.active_role != "reception":
                raise DemoError("demo_reception_role_required", 403)
            if not session.demo_requests:
                raise DemoError("no_demo_request", 409)
            request = session.demo_requests[-1]
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
            return self.journey_view(session_id)

    def department_action(self, session_id, action):
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
            request = session.demo_requests[-1]
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
            return self.journey_view(session_id)

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
        if not _ROOM_TOKEN.fullmatch(room):
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
            if session.pending is not None:
                session.pending = None
                session.pending_at = None
                self._append(session, "assistant",
                             "I canceled the earlier unsubmitted draft. Let’s look at your new message.")
            session.completed_revision = None
            session.completed_reply = None
            self._append(session, "guest", text)

            session.revision += 1
            social = _social_kind(text)
            if social is not None:
                # A greeting or thanks is not a new service request or a confirmation.
                # Preserve an existing clarification so the guest can continue.
                session.state = "needs_clarification" if session.clarification else "ready"
                session.active_turn_id = None
                if social == "thanks":
                    reply = "You're welcome. What else can I help you with?"
                elif session.clarification is not None:
                    reply = "Yes, I'm here. Please tell me what you need help with."
                else:
                    reply = "Hello! I'm here to help. What do you need during your stay?"
                self._append(session, "assistant", reply)
                return self._view(session)

            # Room-only statements are contextual information, not service requests.
            # Do not claim that a guest has been authenticated by a room number.
            if session.clarification is None:
                standalone_room = _ROOM_RESPONSE.fullmatch(text)
                if standalone_room is not None:
                    session.clarification = {
                        "kind": "problem_description",
                        "text": "room " + standalone_room.group(1),
                        "turn_id": str(uuid4()),
                    }
                    session.state = "needs_clarification"
                    session.active_turn_id = None
                    self._append(
                        session, "assistant",
                        "What do you need help with in that room? Please describe the issue.",
                    )
                    return self._view(session)

            if session.clarification is not None:
                previous = session.clarification["text"]
                reply = (self._room_reply(text)
                         if session.clarification["kind"] == "room_number" else text)
                combined = previous + " " + reply
                turn_id = session.clarification["turn_id"]
            else:
                combined = text
                turn_id = str(uuid4())
            session.clarification = None
            session.active_turn_id = turn_id

            turn_at = self._now()
            result = handle_conversation_turn(
                combined, channel="typed_chat", conversation_id=session.conversation_id,
                turn_id=turn_id, at=turn_at, confirmed=False,
                provider_status=_provider_status, access_context=session.context,
                scope=session.scope,
            )
            session.state = result["state"]
            if result["state"] == "needs_clarification":
                session.clarification = {
                    "kind": result.get("clarification"),
                    "text": combined,
                    "turn_id": turn_id,
                }
                self._append(session, "assistant", result["message"])
            elif result["state"] == "awaiting_confirmation":
                intent = result.get("internal", {}).get("intent", {})
                summary = _public_summary(combined, intent)
                session.pending = {
                    "revision": session.revision,
                    "text": combined,
                    "turn_id": turn_id,
                    "summary": summary,
                }
                session.pending_at = turn_at
                session.active_turn_id = None
                self._append(session, "assistant", result["message"])
            else:
                session.active_turn_id = None
                self._append(session, "assistant", result["message"])
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
                reply = (f"The request now appears in the synthetic {department} demo workflow. "
                         "It has not been sent to hotel staff or saved to Workpeg. No live hotel request was submitted, no ticket was created, and no real staff were notified.")
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


def make_server(demo=None, port=PORT_DEFAULT):
    demo = demo or GuestChatDemo()
    assets = Path(__file__).with_name("guest_chat_demo_assets")
    allowed_hosts = {"127.0.0.1", "localhost"}

    class Handler(BaseHTTPRequestHandler):
        server_version = "RoomayOfflineDemo/1"
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

        def _send(self, status, body, *, content_type="application/json; charset=utf-8", extra=()):
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
            if self.path == "/":
                self.send_header(
                    "Content-Security-Policy",
                    "default-src 'self'; script-src 'self'; style-src 'self'; "
                    "connect-src 'self'; img-src 'self'; object-src 'none'; "
                    "base-uri 'none'; form-action 'self'; frame-ancestors 'none'",
                )
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):
            if not self._local_host():
                return self._send(403, {"error": "loopback_only"})
            paths = {
                "/": ("index.html", "text/html; charset=utf-8"),
                "/app.css": ("app.css", "text/css; charset=utf-8"),
                "/voice_intake.js": ("voice_intake.js", "text/javascript; charset=utf-8"),
                "/app.js": ("app.js", "text/javascript; charset=utf-8"),
            }
            asset = paths.get(self.path)
            if asset is None:
                return self._send(404, {"error": "not_found"})
            name, content_type = asset
            try:
                content = (assets / name).read_text(encoding="utf-8")
            except OSError:
                return self._send(500, {"error": "demo_asset_unavailable"})
            self._send(200, content, content_type=content_type)

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
            if self.path not in ("/api/session", "/api/message", "/api/confirm", "/api/cancel",
                                 "/api/role", "/api/assign", "/api/staff-action"):
                return self._send(404, {"error": "not_found"})
            try:
                body = self._json_body()
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
                        cookie = (f"{SESSION_COOKIE}={session_id}; Path=/; Max-Age={SESSION_TTL_SECONDS}; "
                                  "HttpOnly; SameSite=Strict")
                        return self._send(200, view, extra=(("Set-Cookie", cookie),))
                    return self._send(200, view)

                session_id = _decode_cookie(self.headers.get("Cookie", ""))
                if session_id is None:
                    raise DemoError("demo_session_expired", 401)
                if self.path == "/api/message":
                    if set(body) != {"text"}:
                        raise DemoError("invalid_request")
                    demo.send_message(session_id, body["text"])
                    view = demo.journey_view(session_id)
                elif self.path == "/api/confirm":
                    if set(body) != {"revision"}:
                        raise DemoError("invalid_request")
                    demo.confirm(session_id, body["revision"])
                    view = demo.journey_view(session_id)
                elif self.path == "/api/cancel":
                    if set(body) != {"revision"}:
                        raise DemoError("invalid_request")
                    demo.cancel(session_id, body["revision"])
                    view = demo.journey_view(session_id)
                elif self.path == "/api/role":
                    if set(body) != {"role"}:
                        raise DemoError("invalid_request")
                    view = demo.switch_role(session_id, body["role"])
                elif self.path == "/api/assign":
                    if body:
                        raise DemoError("invalid_request")
                    view = demo.assign_latest_to_housekeeping(session_id)
                else:
                    if set(body) != {"action"}:
                        raise DemoError("invalid_request")
                    view = demo.department_action(session_id, body["action"])
                self._send(200, view)
            except DemoError as error:
                self._send(error.status, {"error": error.code})
            except Exception:
                # Do not return exception text; it could contain private state.
                self._send(500, {"error": "demo_temporarily_unavailable"})

    server = ThreadingHTTPServer((LOOPBACK, port), Handler)
    server.daemon_threads = True
    return server


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run the synthetic Roomay hotel journey on loopback.")
    parser.add_argument("--port", type=int, default=PORT_DEFAULT)
    args = parser.parse_args(argv)
    server = make_server(port=args.port)
    print(f"Roomay offline guest chat listening at http://{LOOPBACK}:{server.server_port}/")
    print("Synthetic data only; actions stay in server memory and never reach a real hotel system. Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
