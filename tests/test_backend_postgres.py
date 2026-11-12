"""PostgreSQL 16 integration tests for the real Roomay API and migrations.

Set ROOMAY_TEST_DATABASE_URL to the loopback-only Postgres 16 Compose database
to enable this class. Each test migrates into and removes its own random schema;
the module refuses nonlocal URLs, unexpected ports, and non-roomay databases.
"""
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import unittest
from uuid import uuid4
from unittest.mock import patch

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import make_url

from backend.models import Base, GuestSession, OperationalAudit, OperationalRequest, PendingRequest
from tests.test_guest_backend import GuestBackendTests, LocalClient


TEST_DATABASE_URL = os.environ.get("ROOMAY_TEST_DATABASE_URL", "")


@unittest.skipUnless(TEST_DATABASE_URL, "PostgreSQL 16 Compose database is not configured")
class PostgreSQLGuestBackendIntegrationTests(GuestBackendTests):
    """Run the actual app routes and migrations against isolated PG schemas."""

    def setUp(self):
        parsed = make_url(TEST_DATABASE_URL)
        if (parsed.drivername != "postgresql+psycopg"
                or parsed.host not in {"localhost", "127.0.0.1", "::1"}
                or parsed.port != 55432
                or parsed.database != "roomay"):
            raise RuntimeError("postgres_test_database_must_be_local_compose_roomay")

        self.schema_name = "roomay_it_" + uuid4().hex
        self.admin_engine = create_engine(parsed, pool_pre_ping=True)
        self.schema_created = False
        try:
            with self.admin_engine.connect() as connection:
                version = str(connection.exec_driver_sql(
                    "SELECT current_setting('server_version_num')").scalar_one())
            if not version.startswith("16"):
                raise RuntimeError("postgres_test_requires_version_16")
            with self.admin_engine.begin() as connection:
                connection.exec_driver_sql(f'CREATE SCHEMA "{self.schema_name}"')
            self.schema_created = True

            query = dict(parsed.query)
            query["options"] = f"-csearch_path={self.schema_name}"
            self.schema_url = parsed.set(query=query).render_as_string(hide_password=False)
            old_database_url = os.environ.get("ROOMAY_DATABASE_URL")
            os.environ["ROOMAY_DATABASE_URL"] = self.schema_url
            try:
                migration_config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
                command.upgrade(migration_config, "head")
            finally:
                if old_database_url is None:
                    os.environ.pop("ROOMAY_DATABASE_URL", None)
                else:
                    os.environ["ROOMAY_DATABASE_URL"] = old_database_url

            self.engine = create_engine(self.schema_url, pool_pre_ping=True)
            self._configure_fixture(self.engine, create_schema=False)
        except Exception:
            self._drop_test_schema()
            raise

    def _drop_test_schema(self):
        engine = getattr(self, "admin_engine", None)
        schema_name = getattr(self, "schema_name", None)
        if (engine is not None and schema_name is not None
                and getattr(self, "schema_created", False)):
            with engine.begin() as connection:
                connection.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE')
            self.schema_created = False
        if engine is not None:
            engine.dispose()

    def tearDown(self):
        client = getattr(self, "client", None)
        if client is not None:
            client.close()
        engine = getattr(self, "engine", None)
        if engine is not None:
            engine.dispose()
        self._drop_test_schema()

    def test_concurrent_duplicate_staff_transition_commits_one_audit_event(self):
        guest = self.issue_and_redeem()
        prepared = self.origin_post(guest, "/guest/requests/prepare", json={
            "category": "extra_towels", "description": "Please bring towels",
            "urgency": "normal", "idempotency_key": str(uuid4()),
        }).json()
        confirmed = self.origin_post(guest, "/guest/requests/confirm", json={
            "confirmation_handle": prepared["confirmation_handle"],
        })
        self.assertEqual(confirmed.status_code, 200, confirmed.text)
        request_id = confirmed.json()["reference"]

        self.assertEqual(self.staff_login(self.client, "reception-code").status_code, 303)
        assigned = self.origin_post(
            self.client, f"/staff/requests/{request_id}/transitions", json={
                "action": "assign", "operation_key": str(uuid4()),
                "assignee_id": "staff-housekeeping",
            })
        self.assertEqual(assigned.status_code, 200, assigned.text)
        housekeeping = LocalClient(self.app, self.origin)
        self.assertEqual(self.staff_login(housekeeping, "housekeeping-code").status_code, 303)
        cookies = dict(housekeeping.cookies)
        operation_key = str(uuid4())

        def acknowledge(_):
            client = LocalClient(self.app, self.origin)
            client.cookies.update(cookies)
            try:
                return self.origin_post(
                    client, f"/staff/requests/{request_id}/transitions", json={
                        "action": "acknowledge", "operation_key": operation_key,
                    })
            finally:
                client.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(acknowledge, range(2)))
        self.assertEqual([response.status_code for response in responses], [200, 200],
                         [response.text for response in responses])
        self.assertTrue(all(response.json()["persisted"] for response in responses))

        with self.sessions() as db:
            saved = db.get(OperationalRequest, request_id)
            audits = db.scalars(select(OperationalAudit).where(
                OperationalAudit.request_id == request_id).order_by(
                    OperationalAudit.sequence)).all()
            self.assertEqual(saved.request_data["status"], "acknowledged")
            self.assertEqual([row.sequence for row in audits], [1, 2, 3])
            self.assertTrue(all(row.commit_state == "committed" for row in audits))
        housekeeping.close()
        guest.close()

    def test_concurrent_guest_prepares_serialize_the_hourly_rate_limit(self):
        guest = self.issue_and_redeem()
        cookies = dict(guest.cookies)

        def prepare(_):
            client = LocalClient(self.app, self.origin)
            client.cookies.update(cookies)
            try:
                return self.origin_post(client, "/guest/requests/prepare", json={
                    "category": "extra_towels", "description": "Please bring towels",
                    "urgency": "normal", "idempotency_key": str(uuid4()),
                }).status_code
            finally:
                client.close()

        with patch("backend.app.PREPARES_PER_GUEST_HOUR", 1):
            with ThreadPoolExecutor(max_workers=2) as pool:
                statuses = list(pool.map(prepare, range(2)))
        self.assertEqual(sorted(statuses), [200, 429])
        with self.sessions() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(PendingRequest)), 1)
            self.assertIsNotNone(db.scalar(select(GuestSession)))
        guest.close()


def load_tests(loader, tests, pattern):
    # Imported base test class is intentionally reused for PostgreSQL but must
    # not also be collected here as a second SQLite suite.
    return loader.loadTestsFromTestCase(PostgreSQLGuestBackendIntegrationTests)


if __name__ == "__main__":
    unittest.main()
