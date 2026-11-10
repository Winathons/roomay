"""Isolated database tests for the real Roomay guest/staff request API.

SQLite here is test-only. Production configuration and migrations require
PostgreSQL; Workpeg is represented by an in-memory read-only snapshot port.
"""
from datetime import datetime, timezone
import inspect
import json
from http.cookies import SimpleCookie
from pathlib import Path
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from unittest import TestCase
from uuid import uuid4

from fastapi import HTTPException, Request, Response
from sqlalchemy import create_engine, delete, event, select
from sqlalchemy.engine import URL
from sqlalchemy.orm import sessionmaker
from workpeg.auth import SignInStart, WorkpegIdentity

from backend.app import PrepareBody, ConfirmBody, create_app, _digest
from backend.models import (
    Base, GuestInvitation, GuestSession, HotelBinding, OperationalAudit,
    OperationalRequest, PendingRequest, StaffBinding, StaffSession,
)
from domain.fixtures import synthetic_hotel, uid


BUSINESS_ID = uid("backend-business")
HOTEL_ID = uid("backend-hotel")
GUEST_ID = uid("Guest C")
STAY_ID = uid("stay")
ROOM_ID = uid("205")
OCCUPANT_ID = uid("occupant")
AT = datetime(2026, 11, 10, 10, 0, tzinfo=timezone.utc)


class SnapshotReader:
    def __init__(self):
        self.snapshot = synthetic_hotel()
        self.snapshot["room_blocks"] = []
        self.businesses = []
        self.failure = False

    def read_snapshot(self, business_id):
        self.businesses.append(business_id)
        if self.failure:
            raise RuntimeError("synthetic Workpeg outage")
        if business_id != BUSINESS_ID:
            raise RuntimeError("wrong business")
        return self.snapshot


class MockWorkpegAuth:
    def __init__(self, identities):
        self.identities = identities
        self.counter = 0
        self.starts = {}

    def begin(self):
        self.counter += 1
        state = f"oidc-state-{self.counter}"
        start = SignInStart(url="https://accounts.workpeg.test/authorize",
                            state=state, code_verifier="test-verifier",
                            nonce=f"nonce-{self.counter}")
        self.starts[state] = start
        return start

    def complete(self, *, code, state, start):
        if state != start.state or code not in self.identities:
            raise ValueError("invalid mock callback")
        return self.identities[code]


class LocalClient:
    """Invoke the real route handlers with an isolated cookie/request context."""
    def __init__(self, app, base_url):
        self.app, self.base_url = app, base_url
        self.cookies = {}

    def request(self, method, path, **kwargs):
        params = dict(kwargs.pop("params", {}) or {})
        body = kwargs.pop("json", None)
        headers = dict(kwargs.pop("headers", {}) or {})
        headers.setdefault("Origin", self.base_url)
        path_only = path.split("?", 1)[0]
        if "?" in path:
            from urllib.parse import parse_qsl
            params.update(dict(parse_qsl(path.split("?", 1)[1])))
        cookie_header = "; ".join(f"{key}={value}" for key, value in self.cookies.items())
        raw_headers = [(key.lower().encode(), value.encode()) for key, value in headers.items()]
        if cookie_header:
            raw_headers.append((b"cookie", cookie_header.encode()))
        scope = {"type": "http", "method": method, "path": path_only,
                 "raw_path": path_only.encode(), "root_path": "", "scheme": "https",
                 "query_string": b"", "headers": raw_headers,
                 "server": ("roomay.test", 443), "client": ("127.0.0.1", 50000),
                 "http_version": "1.1", "app": self.app, "state": {}}
        from urllib.parse import urlencode
        scope["query_string"] = urlencode(params).encode()
        matched = None
        route_scope = {}
        for route in self.app.router.routes:
            match, child_scope = route.matches(scope)
            if match.value == 2 and method in (route.methods or set()):
                matched, route_scope = route, child_scope
                break
        if matched is None:
            return LocalResponse(404, {"detail": "not_found"})
        request = Request({**scope, **route_scope})
        arguments = {}
        dependency_response = Response()
        for name, parameter in inspect.signature(matched.endpoint).parameters.items():
            if name == "request":
                arguments[name] = request
            elif name == "response":
                arguments[name] = dependency_response
            elif name == "body":
                annotation = parameter.annotation
                arguments[name] = annotation(**body) if inspect.isclass(annotation) and hasattr(annotation, "model_validate") else body
            elif name in route_scope.get("path_params", {}):
                arguments[name] = route_scope["path_params"][name]
            elif name in params:
                arguments[name] = params[name]
        try:
            result = matched.endpoint(**arguments)
        except HTTPException as error:
            return LocalResponse(error.status_code, {"detail": error.detail}, error.headers or {})
        response = LocalResponse.from_result(result)
        header_source = result.headers if isinstance(result, Response) else dependency_response.headers
        if not isinstance(result, Response):
            response.headers = header_source
        for value in header_source.getlist("set-cookie"):
            cookie = SimpleCookie()
            cookie.load(value)
            for key, morsel in cookie.items():
                if morsel["max-age"] == "0":
                    self.cookies.pop(key, None)
                else:
                    self.cookies[key] = morsel.value
        return response

    def get(self, path, **kwargs):
        return self.request("GET", path, **kwargs)

    def post(self, path, **kwargs):
        return self.request("POST", path, **kwargs)

    def close(self):
        self.cookies.clear()


class LocalResponse:
    def __init__(self, status_code, data=None, headers=None):
        self.status_code = status_code
        self._data = data
        self.headers = headers or {}
        self.text = str(data)

    @classmethod
    def from_result(cls, result):
        if isinstance(result, Response):
            try:
                data = json.loads(result.body) if result.body else None
            except (ValueError, TypeError):
                data = None
            return cls(result.status_code, data, result.headers)
        return cls(200, result, {})

    def json(self):
        return self._data


class GuestBackendTests(TestCase):
    def setUp(self):
        temp_root = Path(__file__).resolve().parents[1] / ".tmp"
        temp_root.mkdir(exist_ok=True)
        self.database_dir = tempfile.TemporaryDirectory(prefix="roomay-test-db-", dir=temp_root)
        database_file = str(Path(self.database_dir.name) / "roomay.sqlite3")
        self.engine = create_engine(
            URL.create("sqlite+pysqlite", database=database_file),
            connect_args={"check_same_thread": False, "timeout": 10},
        )
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(self.engine, expire_on_commit=False)
        self.reader = SnapshotReader()
        self.origin = "https://roomay.test"
        self.auth = MockWorkpegAuth({
            "reception-code": WorkpegIdentity("wp-subject-reception", BUSINESS_ID,
                                               "Roomay test", "member"),
            "housekeeping-code": WorkpegIdentity("wp-subject-housekeeping", BUSINESS_ID,
                                                  "Roomay test", "member"),
            "maintenance-code": WorkpegIdentity("wp-subject-maintenance", BUSINESS_ID,
                                                  "Roomay test", "member"),
            "other-business-code": WorkpegIdentity("wp-subject-other", uid("other-business"),
                                                    "Other", "member"),
            "guest-role-code": WorkpegIdentity("wp-subject-guest", BUSINESS_ID,
                                                "Roomay test", "guest"),
            "owner-code": WorkpegIdentity("wp-subject-owner", BUSINESS_ID,
                                           "Roomay test", "owner"),
        })
        with self.sessions.begin() as db:
            db.add(HotelBinding(business_id=BUSINESS_ID, hotel_id=HOTEL_ID, active=True))
            db.add_all([
                StaffBinding(id=str(uuid4()), business_id=BUSINESS_ID, hotel_id=HOTEL_ID,
                             workpeg_subject="wp-subject-reception", actor_id="staff-reception",
                             department="reception", roles=[], active=True),
                StaffBinding(id=str(uuid4()), business_id=BUSINESS_ID, hotel_id=HOTEL_ID,
                             workpeg_subject="wp-subject-housekeeping", actor_id="staff-housekeeping",
                             department="housekeeping", roles=[], active=True),
                StaffBinding(id=str(uuid4()), business_id=BUSINESS_ID, hotel_id=HOTEL_ID,
                             workpeg_subject="wp-subject-maintenance", actor_id="staff-maintenance",
                             department="maintenance", roles=[], active=True),
            ])
        self.settings = type("Settings", (), {
            "oidc_client_id": "test-client", "oidc_client_secret": "",
            "oidc_redirect_uri": self.origin + "/auth/workpeg/callback",
            "business_id": BUSINESS_ID,
            "hotel_id": HOTEL_ID, "bootstrap_owner_enabled": False,
            "public_base_url": self.origin, "cookie_secure": False,
        })()
        self.app = create_app(session_factory=self.sessions,
                              hotel_reader=self.reader, settings=self.settings,
                              clock=lambda: AT, workpeg_auth=self.auth)
        self.client = LocalClient(self.app, base_url=self.origin)

    def tearDown(self):
        self.client.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()
        self.database_dir.cleanup()

    def staff_login(self, client, code):
        started = client.get("/auth/workpeg/start", follow_redirects=False)
        self.assertEqual(started.status_code, 303)
        state = next(reversed(self.auth.starts))
        callback = client.get("/auth/workpeg/callback",
                              params={"code": code, "state": state},
                              follow_redirects=False)
        return callback

    def origin_post(self, client, path, **kwargs):
        headers = kwargs.pop("headers", {})
        headers["Origin"] = self.origin
        return client.post(path, headers=headers, **kwargs)

    def issue_and_redeem(self):
        response = self.staff_login(self.client, "reception-code")
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/staff")
        stay_id = self.reader.snapshot["stays"][0]["entity_id"]
        guest_id = self.reader.snapshot["stay_guests"][0]["guest_id"]
        issued = self.origin_post(self.client,
                                  f"/staff/stays/{stay_id}/guest-invitations",
                                  json={"stay_id": stay_id, "guest_id": guest_id})
        self.assertEqual(issued.status_code, 200, issued.text)
        self.assertEqual(issued.headers["cache-control"], "no-store")
        secret = issued.json()["invitation"]
        guest = LocalClient(self.app, base_url=self.origin)
        redeemed = self.origin_post(guest, "/guest/invitations/redeem",
                                    json={"invitation": secret})
        self.assertEqual(redeemed.status_code, 200, redeemed.text)
        self.assertTrue(redeemed.json()["verified"])
        return guest

    def test_guest_request_persists_with_committed_audit_and_department_scope(self):
        guest = self.issue_and_redeem()
        key = str(uuid4())
        payload = {"category": "extra_towels", "description": "Please bring two towels",
                   "urgency": "normal", "idempotency_key": key}
        prepared = self.origin_post(guest, "/guest/requests/prepare", json=payload)
        self.assertEqual(prepared.status_code, 200, prepared.text)
        self.assertFalse(prepared.json()["request_persisted"])
        handle = prepared.json()["confirmation_handle"]
        self.assertEqual(prepared.json()["summary"]["department"], "housekeeping")

        # Same client key and exact content gets the same confirmation proposal.
        replay = self.origin_post(guest, "/guest/requests/prepare", json=payload)
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.json()["confirmation_handle"], handle)
        conflict = self.origin_post(guest, "/guest/requests/prepare",
                                    json={**payload, "description": "A different request"})
        self.assertEqual(conflict.status_code, 409)

        confirmed = self.origin_post(guest, "/guest/requests/confirm",
                                     json={"confirmation_handle": handle})
        self.assertEqual(confirmed.status_code, 200, confirmed.text)
        result = confirmed.json()
        self.assertTrue(result["persisted"])
        self.assertEqual(result["status"], "received")
        # A second DB session and a second HTTP read verify actual test DB state.
        with self.sessions() as db:
            record = db.get(OperationalRequest, result["reference"])
            events = db.scalars(select(OperationalAudit).where(
                OperationalAudit.request_id == result["reference"])).all()
            self.assertIsNotNone(record)
            self.assertEqual(record.request_data["department"], "housekeeping")
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0].commit_state, "committed")
        replay_confirm = self.origin_post(guest, "/guest/requests/confirm",
                                         json={"confirmation_handle": handle})
        self.assertEqual(replay_confirm.status_code, 200)
        self.assertEqual(replay_confirm.json()["reference"], result["reference"])
        visible = guest.get("/guest/requests")
        self.assertEqual(visible.status_code, 200)
        self.assertEqual(len(visible.json()), 1)
        self.assertNotIn("guest_id", visible.json()[0])
        self.assertNotIn("stay_id", visible.json()[0])
        self.assertNotIn("room_id", visible.json()[0])

        # Staff identity and department are bound server-side from OIDC subject.
        housekeeping = LocalClient(self.app, base_url=self.origin)
        self.assertEqual(self.staff_login(housekeeping, "housekeeping-code").status_code, 303)
        inbox = housekeeping.get("/staff/requests")
        self.assertEqual(inbox.status_code, 200, inbox.text)
        self.assertEqual(len(inbox.json()), 1)
        self.assertEqual(inbox.json()[0]["department"], "housekeeping")
        self.assertNotIn("guest_id", inbox.json()[0])
        self.assertNotIn("stay_id", inbox.json()[0])

        # Reception assigns to trusted directory entry; department staff acknowledge.
        assigned = self.origin_post(
            self.client, f"/staff/requests/{result['reference']}/transitions",
            json={"action": "assign", "operation_key": str(uuid4()),
                  "assignee_id": "staff-housekeeping"})
        self.assertEqual(assigned.status_code, 200, assigned.text)
        acknowledged = self.origin_post(
            housekeeping, f"/staff/requests/{result['reference']}/transitions",
            json={"action": "acknowledge", "operation_key": str(uuid4())})
        self.assertEqual(acknowledged.status_code, 200, acknowledged.text)
        self.assertEqual(acknowledged.json()["request"]["status"], "acknowledged")
        self.assertNotIn("guest_id", acknowledged.json()["request"])
        self.assertNotIn("stay_id", acknowledged.json()["request"])
        with self.sessions() as db:
            saved = db.get(OperationalRequest, result["reference"])
            audit_rows = db.scalars(select(OperationalAudit).where(
                OperationalAudit.request_id == result["reference"]).order_by(
                    OperationalAudit.sequence)).all()
            self.assertEqual(saved.request_data["status"], "acknowledged")
            self.assertEqual([row.sequence for row in audit_rows], [1, 2, 3])
            self.assertTrue(all(row.commit_state == "committed" for row in audit_rows))
        guest.close()
        housekeeping.close()

    def test_simultaneous_duplicate_confirmation_never_creates_two_requests(self):
        guest = self.issue_and_redeem()
        prepared = self.origin_post(guest, "/guest/requests/prepare", json={
            "category": "extra_towels", "description": "Please bring towels",
            "urgency": "normal", "idempotency_key": str(uuid4()),
        }).json()
        cookie_copy = dict(guest.cookies)
        path = "/guest/requests/confirm"

        def confirm_same_handle(_):
            client = LocalClient(self.app, self.origin)
            client.cookies.update(cookie_copy)
            try:
                return self.origin_post(client, path, json={
                    "confirmation_handle": prepared["confirmation_handle"]
                }).status_code
            finally:
                client.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = list(pool.map(confirm_same_handle, range(2)))
        self.assertTrue(all(status in (200, 503) for status in statuses), statuses)
        with self.sessions() as db:
            requests = db.scalars(select(OperationalRequest)).all()
            audit_rows = db.scalars(select(OperationalAudit)).all()
            self.assertEqual(len(requests), 1)
            self.assertEqual(len(audit_rows), 1)
            self.assertEqual(audit_rows[0].commit_state, "committed")
        guest.close()

    def test_workpeg_membership_business_and_local_staff_binding_are_required(self):
        other = LocalClient(self.app, base_url=self.origin)
        self.assertEqual(self.staff_login(other, "other-business-code").status_code, 403)
        guest_role = LocalClient(self.app, base_url=self.origin)
        self.assertEqual(self.staff_login(guest_role, "guest-role-code").status_code, 403)
        anonymous = LocalClient(self.app, base_url=self.origin)
        denied = anonymous.get("/staff/requests")
        self.assertEqual(denied.status_code, 401)
        other.close()
        guest_role.close()
        anonymous.close()

    def test_explicit_bootstrap_allows_only_first_verified_workpeg_owner(self):
        with self.sessions.begin() as db:
            db.execute(delete(StaffBinding))
        self.settings.bootstrap_owner_enabled = True
        response = self.staff_login(self.client, "owner-code")
        self.assertEqual(response.status_code, 303)
        with self.sessions() as db:
            binding = db.scalar(select(StaffBinding).where(
                StaffBinding.workpeg_subject == "wp-subject-owner"))
            hotel = db.get(HotelBinding, BUSINESS_ID)
            self.assertIsNotNone(binding)
            self.assertEqual(binding.department, "reception")
            self.assertEqual(set(binding.roles), {"hotel_manager", "request_admin"})
            self.assertEqual(hotel.hotel_id, HOTEL_ID)

    def test_owner_bootstrap_does_not_replace_an_existing_staff_mapping(self):
        self.settings.bootstrap_owner_enabled = True
        denied = self.staff_login(self.client, "owner-code")
        self.assertEqual(denied.status_code, 403)
        with self.sessions() as db:
            self.assertIsNone(db.scalar(select(StaffBinding).where(
                StaffBinding.workpeg_subject == "wp-subject-owner")))

    def test_wrong_department_is_hidden_and_cannot_transition_request(self):
        guest = self.issue_and_redeem()
        prepared = self.origin_post(guest, "/guest/requests/prepare", json={
            "category": "extra_towels", "description": "Please bring towels",
            "urgency": "normal", "idempotency_key": str(uuid4()),
        }).json()
        created = self.origin_post(guest, "/guest/requests/confirm",
                                   json={"confirmation_handle": prepared["confirmation_handle"]}).json()
        maintenance = LocalClient(self.app, base_url=self.origin)
        self.assertEqual(self.staff_login(maintenance, "maintenance-code").status_code, 303)
        self.assertEqual(maintenance.get("/staff/requests").json(), [])
        self.assertEqual(maintenance.get("/staff/active-stays").status_code, 403)
        refused = self.origin_post(
            maintenance, f"/staff/requests/{created['reference']}/transitions",
            json={"action": "acknowledge", "operation_key": str(uuid4())})
        self.assertEqual(refused.status_code, 403)
        self.assertNotIn("guest_id", refused.json())
        guest.close()
        maintenance.close()

    def test_local_staff_mapping_revocation_is_immediate(self):
        self.assertEqual(self.staff_login(self.client, "housekeeping-code").status_code, 303)
        with self.sessions.begin() as db:
            binding = db.scalar(select(StaffBinding).where(
                StaffBinding.workpeg_subject == "wp-subject-housekeeping"))
            binding.active = False
        denied = self.client.get("/staff/requests")
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(denied.json(), {"detail": "staff_access_revoked"})

    def test_guest_session_cannot_follow_stay_to_an_unverified_room(self):
        guest = self.issue_and_redeem()
        self.reader.snapshot["stays"][0]["room_id"] = uid("204")
        denied = guest.get("/guest/requests")
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(denied.json(), {"detail": "active_stay_required"})
        guest.close()

    def test_workpeg_read_failure_does_not_fall_back_or_leak_guest_records(self):
        guest = self.issue_and_redeem()
        self.reader.failure = True
        response = guest.get("/guest/requests")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"detail": "hotel_records_unavailable"})
        guest.close()

    def test_invitation_is_one_time_revocable_and_active_stay_scoped(self):
        receptionist = self.staff_login(self.client, "reception-code")
        self.assertEqual(receptionist.status_code, 303)
        stay_id = self.reader.snapshot["stays"][0]["entity_id"]
        guest_id = self.reader.snapshot["stay_guests"][0]["guest_id"]
        result = self.origin_post(self.client,
                                  f"/staff/stays/{stay_id}/guest-invitations",
                                  json={"stay_id": stay_id, "guest_id": guest_id}).json()
        invited = LocalClient(self.app, base_url=self.origin)
        first = self.origin_post(invited, "/guest/invitations/redeem",
                                 json={"invitation": result["invitation"]})
        self.assertEqual(first.status_code, 200)
        second = LocalClient(self.app, base_url=self.origin)
        repeat = self.origin_post(second, "/guest/invitations/redeem",
                                  json={"invitation": result["invitation"]})
        self.assertEqual(repeat.status_code, 401)
        # A checked-out/left occupant immediately loses access on the next read.
        self.reader.snapshot["stays"][0]["status"] = "checked_out"
        self.reader.snapshot["stays"][0]["checked_out_at"] = "2026-11-10T10:00:00+00:00"
        self.reader.snapshot["stay_guests"][0]["left_at"] = "2026-11-10T10:00:00+00:00"
        hidden = invited.get("/guest/requests")
        self.assertEqual(hidden.status_code, 403)
        invited.close()
        second.close()

    def test_reception_can_revoke_guest_invitation_before_redemption(self):
        self.assertEqual(self.staff_login(self.client, "reception-code").status_code, 303)
        stay_id = self.reader.snapshot["stays"][0]["entity_id"]
        guest_id = self.reader.snapshot["stay_guests"][0]["guest_id"]
        issued = self.origin_post(self.client,
                                  f"/staff/stays/{stay_id}/guest-invitations",
                                  json={"stay_id": stay_id, "guest_id": guest_id}).json()
        revoked = self.origin_post(
            self.client, f"/staff/guest-invitations/{issued['invitation_id']}/revoke")
        self.assertEqual(revoked.status_code, 200)
        guest = LocalClient(self.app, self.origin)
        denied = self.origin_post(guest, "/guest/invitations/redeem",
                                  json={"invitation": issued["invitation"]})
        self.assertEqual(denied.status_code, 401)
        self.assertEqual(denied.json(), {"detail": "invitation_invalid_or_expired"})
        guest.close()

    def test_failed_audit_write_rolls_back_request_and_never_reports_success(self):
        guest = self.issue_and_redeem()
        prepared = self.origin_post(guest, "/guest/requests/prepare", json={
            "category": "extra_towels", "description": "Please bring towels",
            "urgency": "normal", "idempotency_key": str(uuid4()),
        }).json()

        def fail_audit(session, flush_context, instances):
            if any(isinstance(row, OperationalAudit) for row in session.new):
                raise RuntimeError("synthetic database failure")

        event.listen(self.sessions, "before_flush", fail_audit)
        try:
            failed = self.origin_post(guest, "/guest/requests/confirm",
                                      json={"confirmation_handle": prepared["confirmation_handle"]})
        finally:
            event.remove(self.sessions, "before_flush", fail_audit)
        self.assertEqual(failed.status_code, 503)
        self.assertFalse(failed.json().get("persisted", False))
        with self.sessions() as db:
            self.assertEqual(db.scalar(select(OperationalRequest)), None)
            self.assertEqual(db.scalar(select(OperationalAudit)), None)
        guest.close()

    def test_guest_session_revoke_and_wrong_origin_fail_closed(self):
        guest = self.issue_and_redeem()
        bad = guest.post("/guest/requests/prepare", json={
            "category": "extra_towels", "description": "Towels",
            "urgency": "normal", "idempotency_key": str(uuid4()),
        }, headers={"Origin": "https://attacker.invalid"})
        self.assertEqual(bad.status_code, 403)
        logout = self.origin_post(guest, "/guest/logout")
        self.assertEqual(logout.status_code, 200)
        self.assertEqual(guest.get("/guest/requests").status_code, 401)
        guest.close()


if __name__ == "__main__":
    import unittest
    unittest.main()
