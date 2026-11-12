"""WOR-72: isolated formnow-style public booking-inquiry intake and collector.

No Workpeg API or external service is called, and no production app exists.
"""
import asyncio
from datetime import datetime, timezone
from uuid import uuid4
import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from public_intake.api import TrustedStaff, create_intake_app
from public_intake.queue import (
    Base, IntakePortal, QueuedInquiry, RATE_PER_MINUTE,
    LEASE_SECONDS, QUEUE_TTL_SECONDS, acknowledge, lease, purge_expired,
)
from public_intake.sync import collect_batch, verified_receipt, SyncError


BUSINESS = "10000000-0000-4000-8000-000000000001"
OTHER_BUSINESS = "10000000-0000-4000-8000-000000000002"
HOTEL = "20000000-0000-4000-8000-000000000001"
OTHER_HOTEL = "20000000-0000-4000-8000-000000000002"
PORTAL = "30000000-0000-4000-8000-000000000001"
OTHER_PORTAL = "30000000-0000-4000-8000-000000000002"
TABLE = "40000000-0000-4000-8000-000000000001"


class Clock:
    def __init__(self):
        self.now = 1794528000  # 2026-11-13T00:00:00Z

    def __call__(self):
        return self.now


class IntakeTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False},
                                    poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(self.engine, expire_on_commit=False)
        self.clock = Clock()
        self.actor = TrustedStaff(BUSINESS, HOTEL, "owner-test-subject", True)
        self.secret = b"local-only-synthetic-rate-limit-key-not-production"
        with self.Session.begin() as db:
            db.add_all([
                IntakePortal(portal_id=PORTAL, business_id=BUSINESS, hotel_id=HOTEL),
                IntakePortal(portal_id=OTHER_PORTAL, business_id=OTHER_BUSINESS,
                             hotel_id=OTHER_HOTEL),
            ])
        self.app = create_intake_app(
            session_factory=self.Session, rate_limit_secret=self.secret,
            staff_resolver=lambda _request: self.actor,
            clock=self.clock, test_mode=True)
        self.client = TestClient(self.app)
        self.key = str(uuid4())

    def tearDown(self):
        self.client.close()
        self.engine.dispose()

    def payload(self, **updates):
        body = {
            "idempotency_key": self.key,
            "arrival": "2026-11-14", "departure": "2026-11-16",
            "party_size": 2, "email": " Guest@Example.Test ",
            "room_type": "standard", "note": "Need a quiet room", "consent": True,
        }
        body.update(updates)
        return body

    def submit(self, portal=PORTAL, **updates):
        return self.client.post(
            f"/api/v1/public/portals/{portal}/booking-inquiries",
            json=self.payload(**updates))

    def staff_lease(self, limit=20):
        return self.client.post("/api/v1/staff/inquiries/lease", json={"limit": limit})

    def receipt(self, item, **changes):
        out = {
            "source_id": item["id"], "business_id": item["business_id"],
            "hotel_id": item["hotel_id"], "payload_digest": item["payload_digest"],
            "table_uuid": TABLE, "row_id": 7,
        }
        out.update(changes)
        return out

    def ack(self, item, receipt=None, *, token=None):
        return self.client.post("/api/v1/staff/inquiries/ack", json={
            "id": item["id"], "lease_token": token or item["lease_token"],
            "readback": receipt or self.receipt(item),
        })

    def test_deployment_requires_separate_explicit_approval(self):
        with self.assertRaisesRegex(RuntimeError, "deployment_not_authorized"):
            create_intake_app(session_factory=self.Session, rate_limit_secret=self.secret)
        with self.assertRaisesRegex(RuntimeError, "intake_rate_limit_key_missing"):
            create_intake_app(session_factory=self.Session, rate_limit_secret=b"short",
                              test_mode=True)

    def test_public_queue_does_not_claim_confirmation_or_workpeg_delivery(self):
        reply = self.submit()
        self.assertEqual(reply.status_code, 202, reply.text)
        body = reply.json()
        self.assertEqual(body["status"], "queued_pending_staff_collection")
        self.assertFalse(body["booking_confirmed"])
        self.assertFalse(body["workpeg_delivery_confirmed"])
        self.assertNotIn("Guest@Example", reply.text)
        self.assertNotIn("quiet room", reply.text)
        self.assertEqual(reply.headers["Cache-Control"], "no-store")
        with self.Session() as db:
            row = db.scalar(select(QueuedInquiry))
            self.assertEqual(row.business_id, BUSINESS)
            self.assertEqual(row.hotel_id, HOTEL)
            self.assertEqual(row.data["email"], "guest@example.test")
            self.assertEqual(row.expires_at-row.created_at, QUEUE_TTL_SECONDS)
            self.assertIsNone(row.workpeg_row_id)

    def test_idempotency_returns_same_receipt_and_conflicts_on_changed_body(self):
        first = self.submit()
        again = self.submit(email="guest@example.test", note="Need a quiet room")
        self.assertEqual(first.status_code, 202)
        self.assertEqual(again.status_code, 202)
        self.assertEqual(first.json()["receipt_id"], again.json()["receipt_id"])
        conflict = self.submit(note="a different inquiry")
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.json()["error"], "idempotency_conflict")
        with self.Session() as db:
            self.assertEqual(len(db.scalars(select(QueuedInquiry)).all()), 1)

    def test_no_client_supplied_business_or_hotel_identity_is_accepted(self):
        self.assertEqual(self.submit(business_id=OTHER_BUSINESS).status_code, 422)
        self.assertEqual(self.submit(hotel_id=OTHER_HOTEL).status_code, 422)
        self.assertEqual(self.submit(portal="not-a-real-portal").status_code, 422)
        self.assertEqual(self.submit(portal=str(uuid4())).status_code, 404)
        with self.Session.begin() as db:
            db.get(IntakePortal, PORTAL).active = False
        self.assertEqual(self.submit().status_code, 404)

    def test_public_validation_rejects_missing_consent_and_invalid_inquiry(self):
        bodies = (
            {"consent": False}, {"consent": "true"},
            {"arrival": "2026-11-10"}, {"departure": "2026-11-14"},
            {"party_size": 0}, {"party_size": True},
            {"email": "invalid"}, {"note": "X"*501},
            {"idempotency_key": "not-a-uuid"},
        )
        for change in bodies:
            with self.subTest(change=change):
                self.assertEqual(self.submit(**change).status_code, 422)
        with self.Session() as db:
            self.assertEqual(len(db.scalars(select(QueuedInquiry)).all()), 0)

    def test_public_rate_limit_is_backed_by_the_database(self):
        for i in range(RATE_PER_MINUTE):
            self.assertEqual(self.submit(idempotency_key=str(uuid4())).status_code, 202)
        rate_limited = self.submit(idempotency_key=str(uuid4()))
        self.assertEqual(rate_limited.status_code, 429)
        self.assertEqual(rate_limited.json()["error"], "rate_limited")
        self.clock.now += 60
        self.assertEqual(self.submit(idempotency_key=str(uuid4())).status_code, 202)

    def test_staff_requires_real_authorizer_and_owner_role(self):
        missing = create_intake_app(session_factory=self.Session,
                                    rate_limit_secret=self.secret,
                                    test_mode=True, clock=self.clock)
        with TestClient(missing) as client:
            self.assertEqual(client.post("/api/v1/staff/inquiries/lease",
                                         json={"limit": 1}).status_code, 503)
        self.submit()
        self.actor = TrustedStaff(BUSINESS, HOTEL, "member", False)
        self.assertEqual(self.staff_lease().status_code, 403)
        self.actor = TrustedStaff(BUSINESS, HOTEL, "owner", True)
        self.assertEqual(len(self.staff_lease().json()["items"]), 1)

    def test_staff_business_and_hotel_scope_cannot_be_selected_by_request(self):
        self.submit()
        self.actor = TrustedStaff(OTHER_BUSINESS, OTHER_HOTEL, "owner-other", True)
        self.assertEqual(self.staff_lease().json()["items"], [])
        self.actor = TrustedStaff(BUSINESS, OTHER_HOTEL, "owner-other-hotel", True)
        self.assertEqual(self.staff_lease().json()["items"], [])
        self.actor = TrustedStaff(BUSINESS, HOTEL, "real-owner", True)
        self.assertEqual(len(self.staff_lease().json()["items"]), 1)
        self.assertEqual(self.staff_lease().json()["items"], [], "active lease is exclusive")

    def test_expired_lease_may_be_released_but_stale_token_may_not_ack(self):
        self.submit()
        first = self.staff_lease().json()["items"][0]
        self.clock.now += LEASE_SECONDS + 1
        second = self.staff_lease().json()["items"][0]
        self.assertEqual(first["id"], second["id"])
        self.assertNotEqual(first["lease_token"], second["lease_token"])
        self.assertEqual(self.ack(first).status_code, 409)
        self.assertEqual(self.ack(second).status_code, 200)
        self.assertEqual(self.staff_lease().json()["items"], [])

    def test_ack_requires_matching_persisted_readback_and_same_staff_lease(self):
        self.submit()
        item = self.staff_lease().json()["items"][0]
        self.assertEqual(self.ack(item, token="different-token").status_code, 409)
        self.assertEqual(self.ack(item, self.receipt(item, source_id=str(uuid4()))).status_code, 409)
        self.assertEqual(self.ack(item, self.receipt(item, payload_digest="bad")).status_code, 409)
        self.assertEqual(self.ack(item, self.receipt(item, row_id=0)).status_code, 422)
        self.actor = TrustedStaff(BUSINESS, HOTEL, "second-owner", True)
        self.assertEqual(self.ack(item).status_code, 409)
        self.actor = TrustedStaff(OTHER_BUSINESS, OTHER_HOTEL, "other-owner", True)
        self.assertEqual(self.ack(item).status_code, 404)
        self.actor = TrustedStaff(BUSINESS, HOTEL, "owner-test-subject", True)
        ok = self.ack(item)
        self.assertEqual(ok.status_code, 200, ok.text)
        self.assertTrue(ok.json()["acknowledged"])
        with self.Session() as db:
            row = db.get(QueuedInquiry, item["id"])
            self.assertEqual(row.data, {}, "temporary guest PII purged on ack")
            self.assertEqual(row.workpeg_row_id, 7)
            self.assertIsNone(row.lease_token_digest)
        self.assertEqual(self.submit().json()["status"], "collected_pending_manual_review")
        self.assertFalse(self.submit().json()["booking_confirmed"])

    def test_expired_inquiries_are_not_leased_and_can_be_purged(self):
        self.submit()
        self.clock.now += QUEUE_TTL_SECONDS
        self.assertEqual(self.staff_lease().json()["items"], [])
        with self.Session.begin() as db:
            self.assertEqual(purge_expired(db, now=self.clock.now), 1)
        with self.Session() as db:
            self.assertEqual(len(db.scalars(select(QueuedInquiry)).all()), 0)

    def test_invalid_staff_limit_refused(self):
        self.assertEqual(self.staff_lease(limit=0).status_code, 422)
        self.assertEqual(self.staff_lease(limit=100).status_code, 422)

    def test_collector_only_acks_after_independent_workpeg_readback(self):
        self.submit()
        item = self.staff_lease().json()["items"][0]
        outer = self

        class FakePeg:
            def __init__(self):
                self.current = None
                self.writes = 0

            async def find_by_source(self, source_id):
                return self.current

            async def write_unconfirmed_inquiry(self, leased_item):
                self.writes += 1
                self.current = outer.receipt(leased_item)

        peg = FakePeg()

        async def ack_item(leased_item, receipt):
            response = outer.ack(leased_item, receipt)
            return response.status_code == 200 and response.json()["acknowledged"] is True

        result = asyncio.run(collect_batch([item], writer=peg, ack=ack_item))
        self.assertEqual(result, [{"id": item["id"], "status": "collected_pending_manual_review"}])
        self.assertEqual(peg.writes, 1)
        self.assertEqual(len(self.staff_lease().json()["items"]), 0)

    def test_collector_rejects_failed_write_mismatched_readback_and_ack_failures(self):
        self.submit()
        item = self.staff_lease().json()["items"][0]
        outer = self

        class FakePeg:
            def __init__(self, mode):
                self.mode = mode
                self.current = None
                self.writes = 0

            async def find_by_source(self, source_id):
                return self.current

            async def write_unconfirmed_inquiry(self, leased_item):
                self.writes += 1
                if self.mode == "failure":
                    raise ConnectionError("fictional outage")
                self.current = outer.receipt(leased_item)
                if self.mode == "bad_readback":
                    self.current["hotel_id"] = OTHER_HOTEL

        called = []

        async def pretend_ack(leased_item, receipt):
            called.append(receipt)
            return False

        for mode in ("failure", "bad_readback", "fine"):
            peg = FakePeg(mode)
            result = asyncio.run(collect_batch([item], writer=peg, ack=pretend_ack))
            self.assertEqual(result[0]["status"], "collection_unverified")
            self.assertEqual(len(called), 1 if mode == "fine" else 0)
            with self.Session() as db:
                self.assertIsNone(db.get(QueuedInquiry, item["id"]).acknowledged_at)

    def test_collector_detects_preexisting_row_after_lost_ack(self):
        self.submit()
        item = self.staff_lease().json()["items"][0]
        outer = self

        class FakePeg:
            def __init__(self):
                self.writes = 0
            async def find_by_source(self, _id):
                return outer.receipt(item)
            async def write_unconfirmed_inquiry(self, _item):
                self.writes += 1

        peg = FakePeg()
        async def ack_item(leased_item, receipt):
            return outer.ack(leased_item, receipt).status_code == 200
        results = asyncio.run(collect_batch([item], writer=peg, ack=ack_item))
        self.assertEqual(results[0]["status"], "collected_pending_manual_review")
        self.assertEqual(peg.writes, 0)


if __name__ == "__main__":
    unittest.main()
