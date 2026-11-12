"""WOR-72: real, isolated PostgreSQL 16 lease/concurrency verification in CI.

The only acceptable database is ROOMAY's loopback CI service; this does not
contact Workpeg, external services, or any shared hotel database.
"""
from concurrent.futures import ThreadPoolExecutor
import os
from threading import Event
import unittest
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from public_intake.queue import Base, IntakePortal, enqueue, lease, acknowledge
from tests.test_public_intake import BUSINESS, HOTEL, PORTAL, TABLE


URL = os.environ.get("ROOMAY_TEST_DATABASE_URL", "")


@unittest.skipUnless(URL, "isolated ROOMAY PostgreSQL test service unavailable")
class IntakePostgresTests(unittest.TestCase):
    def setUp(self):
        parsed = make_url(URL)
        if (parsed.drivername != "postgresql+psycopg"
                or parsed.host not in ("127.0.0.1", "localhost", "::1")
                or parsed.port != 55432 or parsed.database != "roomay"):
            raise RuntimeError("public_intake_tests_require_local_roomay_postgres")
        self.schema = "roomay_intake_it_" + uuid4().hex
        self.admin = create_engine(parsed, pool_pre_ping=True)
        self.engine = None
        try:
            with self.admin.begin() as db:
                version = str(db.exec_driver_sql(
                    "SELECT current_setting('server_version_num')").scalar_one())
                if not version.startswith("16"):
                    raise RuntimeError("public_intake_requires_postgresql_16")
                db.exec_driver_sql(f'CREATE SCHEMA "{self.schema}"')
            query = dict(parsed.query)
            query["options"] = f"-csearch_path={self.schema}"
            self.engine = create_engine(parsed.set(query=query), pool_pre_ping=True)
            Base.metadata.create_all(self.engine)
            self.Session = sessionmaker(self.engine, expire_on_commit=False)
            with self.Session.begin() as db:
                db.add(IntakePortal(portal_id=PORTAL, business_id=BUSINESS,
                                    hotel_id=HOTEL, active=True))
        except Exception:
            self.tearDown()
            raise

    def tearDown(self):
        if getattr(self, "engine", None) is not None:
            self.engine.dispose()
        if getattr(self, "admin", None) is not None:
            if getattr(self, "schema", None):
                with self.admin.begin() as db:
                    db.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{self.schema}" CASCADE')
            self.admin.dispose()

    def add(self, *, key):
        with self.Session.begin() as db:
            item = enqueue(
                db, portal_id=PORTAL, idempotency_key=key, now=1794528000,
                address="127.0.0.1", secret=b"fixture-rate-limit-key-at-least-32-bytes-long",
                data={"arrival": "2026-11-14", "departure": "2026-11-16",
                      "party_size": 2, "email": "synthetic@example.test", "room_type": "",
                      "note": "", "consent": True})
            return item.inquiry_id

    def test_concurrent_staff_leases_do_not_grant_the_same_item(self):
        first_id = self.add(key=str(uuid4()))
        second_id = self.add(key=str(uuid4()))
        grabbed = Event()
        release = Event()

        def hold_first():
            with self.Session.begin() as db:
                batch = lease(db, business_id=BUSINESS, hotel_id=HOTEL,
                              subject="owner-a", now=1794528000, limit=1)
                grabbed.set()
                if not release.wait(10):
                    raise RuntimeError("test_release_timeout")
            return batch

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(hold_first)
            self.assertTrue(grabbed.wait(10))
            try:
                with self.Session.begin() as db:
                    second = lease(db, business_id=BUSINESS, hotel_id=HOTEL,
                                   subject="owner-b", now=1794528000, limit=1)
            finally:
                release.set()
            first = future.result(timeout=12)
        self.assertEqual(len(first), 1)
        self.assertEqual(len(second), 1)
        self.assertEqual({first[0]["id"], second[0]["id"]}, {first_id, second_id})
        self.assertNotEqual(first[0]["lease_token"], second[0]["lease_token"])

    def test_ack_after_workpeg_readback_is_a_durable_transaction(self):
        ident = self.add(key=str(uuid4()))
        with self.Session.begin() as db:
            item = lease(db, business_id=BUSINESS, hotel_id=HOTEL,
                         subject="owner-a", now=1794528000, limit=1)[0]
            self.assertEqual(item["id"], ident)
        receipt = {"source_id": item["id"], "business_id": BUSINESS,
                   "hotel_id": HOTEL, "payload_digest": item["payload_digest"],
                   "table_uuid": TABLE, "row_id": 78}
        with self.Session.begin() as db:
            self.assertTrue(acknowledge(db, business_id=BUSINESS, hotel_id=HOTEL,
                                        subject="owner-a", inquiry_id=ident,
                                        lease_token=item["lease_token"],
                                        readback=receipt, now=1794528001))
        with self.Session.begin() as db:
            self.assertFalse(acknowledge(db, business_id=BUSINESS, hotel_id=HOTEL,
                                         subject="owner-a", inquiry_id=ident,
                                         lease_token=item["lease_token"],
                                         readback=receipt, now=1794528002))
            self.assertEqual(lease(db, business_id=BUSINESS, hotel_id=HOTEL,
                                   subject="owner-a", now=1794528002), [])
