"""Loopback-only offline guest chat demo backed by WOR-18 domain contracts.

Run from the repository root with ``python -m tools.guest_chat_demo``. This server never contacts
Workpeg, Vapi, YarnGPT, or any other remote service.
"""

from dataclasses import dataclass, field, replace
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import argparse
import json
import re
import secrets
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from domain.access_control import AccessContext
from domain.conversation_intake import ConversationScope, handle_conversation_turn
from domain.fixtures import synthetic_hotel, uid
from domain.service_requests import CATEGORY_DEPARTMENTS, DEPARTMENTS


LOOPBACK = "127.0.0.1"
PORT_DEFAULT = 8765
SESSION_COOKIE = "roomay_offline_demo"
SESSION_TTL_SECONDS = 20 * 60
MAX_SESSIONS = 32
MAX_BODY_BYTES = 4096
MAX_GUEST_TEXT_CHARS = 1000
DEMO_TIMESTAMP = "2026-11-06T12:00:00+01:00"
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
    last_activity: float = field(default_factory=time.monotonic)
    lock: object = field(default_factory=threading.RLock)


def _new_synthetic_scope():
    """Create fictional guest authority inside the local demo process only."""
    hotel = synthetic_hotel()
    business_id = uid("conversation-business")
    hotel_id = uid("conversation-hotel")
    guest_id = uid("Guest C")
    context = AccessContext(
        actor_id=uid("offline-demo-guest-actor"), business_id=business_id,
        hotel_id=hotel_id, role="guest", authenticated=True,
        membership_verified=True, business_binding_verified=True,
        guest_id=guest_id,
    )
    scope = ConversationScope(
        business_id=business_id, record_business_id=business_id,
        trusted_snapshot_hotel_id=hotel_id, snapshot=hotel,
        stay_id=uid("stay"), room_id=uid("205"), staff_directory=[],
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
    """In-memory, per-session adapter that delegates all request rules to WOR-18."""

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
                         "and hotel staff cannot see this conversation."),
            })
            self._sessions[session_id] = session
            return session_id, self._view(session)

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
            text = text.strip()
            if session.pending is not None:
                session.pending = None
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

            result = handle_conversation_turn(
                combined, channel="typed_chat", conversation_id=session.conversation_id,
                turn_id=turn_id, at=DEMO_TIMESTAMP, confirmed=False,
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
            if (session.completed_revision == revision and session.completed_reply is not None):
                return self._view(session)
            pending = session.pending
            if pending is None or pending["revision"] != revision:
                raise DemoError("confirmation_out_of_date", 409)

            result = handle_conversation_turn(
                pending["text"], channel="typed_chat",
                conversation_id=session.conversation_id,
                turn_id=pending["turn_id"], at=DEMO_TIMESTAMP,
                confirmed=True, access_context=session.context, scope=session.scope,
            )
            session.pending = None
            session.state = result["state"]
            intent = result.get("internal", {}).get("intent", {})
            if result["state"] == "prepared":
                plan = result.get("internal", {}).get("request_plan", {})
                request = plan.get("target_request")
                if isinstance(request, dict):
                    session.scope.existing_requests.append(request)
                department = _department_label(intent.get("department"))
                reply = (f"The {department} request has been prepared in this offline demo. "
                         "It has not been sent to hotel staff or saved; no ticket was created.")
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
            if session.pending is None or session.pending["revision"] != revision:
                raise DemoError("confirmation_out_of_date", 409)
            session.pending = None
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
            if self.path not in ("/api/session", "/api/message", "/api/confirm", "/api/cancel"):
                return self._send(404, {"error": "not_found"})
            try:
                body = self._json_body()
                if self.path == "/api/session":
                    if body:
                        raise DemoError("invalid_request")
                    session_id, view = demo.create_session()
                    cookie = (f"{SESSION_COOKIE}={session_id}; Path=/; Max-Age={SESSION_TTL_SECONDS}; "
                              "HttpOnly; SameSite=Strict")
                    return self._send(200, view, extra=(("Set-Cookie", cookie),))

                session_id = _decode_cookie(self.headers.get("Cookie", ""))
                if session_id is None:
                    raise DemoError("demo_session_expired", 401)
                if self.path == "/api/message":
                    if set(body) != {"text"}:
                        raise DemoError("invalid_request")
                    view = demo.send_message(session_id, body["text"])
                elif self.path == "/api/confirm":
                    if set(body) != {"revision"}:
                        raise DemoError("invalid_request")
                    view = demo.confirm(session_id, body["revision"])
                else:
                    if set(body) != {"revision"}:
                        raise DemoError("invalid_request")
                    view = demo.cancel(session_id, body["revision"])
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
    parser = argparse.ArgumentParser(description="Run the offline Roomay guest chat demo on loopback.")
    parser.add_argument("--port", type=int, default=PORT_DEFAULT)
    args = parser.parse_args(argv)
    server = make_server(port=args.port)
    print(f"Roomay offline guest chat listening at http://{LOOPBACK}:{server.server_port}/")
    print("Synthetic data only. No request is submitted or saved. Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
