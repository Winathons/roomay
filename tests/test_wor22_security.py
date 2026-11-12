"""WOR-22 offline security matrix: role scope, privacy projections and audit.

These tests exercise pure Python contracts with synthetic identities only.
They do NOT establish Workpeg session authentication, table grants, or a
persisted/committed Workpeg audit in a hosted hotel business.
"""
import unittest
from copy import deepcopy

from domain.access_control import (
    AccessContext, AccessDenied, authorize_access, project_service_request,
    project_guest_profile, safe_error_message,
)
from domain.fixtures import synthetic_hotel, uid
from domain.service_requests import create_request
from domain.staff_actions import _audit_history_is_consistent


class WOR22SecurityContracts(unittest.TestCase):
    def setUp(self):
        self.business = uid("wor22-business")
        self.hotel_id = uid("wor22-hotel")
        self.guest_id = uid("Guest C")
        self.snapshot = synthetic_hotel()
        self.staff = [
            {"actor_id": "front", "hotel_id": self.hotel_id,
             "department": "reception", "roles": [], "active": True},
            {"actor_id": "housekeeper", "hotel_id": self.hotel_id,
             "department": "housekeeping", "roles": [], "active": True},
        ]
        self.created = create_request(
            self.snapshot,
            {
                "hotel_id": self.hotel_id,
                "stay_id": uid("stay"),
                "room_id": uid("205"),
                "guest_id": self.guest_id,
                "origin": "guest",
                "category": "extra_towels",
                "description": "Please bring two extra towels.",
                "urgency": "normal",
                "idempotency_key": "wor22:fictional:request-001",
                "sensitive": False,
            },
            {"actor_id": "fictional-guest-session",
             "hotel_id": self.hotel_id, "kind": "guest",
             "guest_id": self.guest_id},
            self.staff, [],
            at="2026-11-06T12:00:00+01:00",
            request_id=uid("wor22-request"),
        )
        self.request = self.created["request"]

    def context(self, role, *, department=None, guest_id=None, privileges=(),
                authenticated=True, membership_verified=True,
                business_binding_verified=True):
        return AccessContext(
            actor_id="fictional-staff-or-guest",
            business_id=self.business,
            hotel_id=self.hotel_id,
            role=role,
            department=department,
            guest_id=guest_id,
            privileges=privileges,
            authenticated=authenticated,
            membership_verified=membership_verified,
            business_binding_verified=business_binding_verified,
        )

    def allow(self, ctx, resource, action, **kwargs):
        return authorize_access(
            ctx, business_id=self.business,
            record_business_id=self.business,
            resource=resource, action=action, **kwargs,
        )

    def test_staff_role_permissions_are_explicit_for_high_impact_operations(self):
        cases = [
            ("owner_operator", None, "reservations", "confirm", True),
            ("manager", None, "check_in_records", "check_out", True),
            ("receptionist", None, "reservations", "confirm", True),
            ("receptionist", None, "check_in_records", "check_in", True),
            ("receptionist", None, "room_maintenance_blocks", "release", False),
            ("receptionist", None, "guest_personal_data", "update", False),
            ("receptionist", None, "audit_trails", "read", False),
            ("department_staff", "housekeeping", "housekeeping_status", "update", True),
            ("department_staff", "housekeeping", "reservations", "read", False),
            ("department_staff", "housekeeping", "check_in_records", "check_in", False),
            ("department_staff", "housekeeping", "room_maintenance_blocks", "release", False),
            ("department_staff", "maintenance", "room_maintenance_blocks", "release", True),
            ("department_staff", "maintenance", "housekeeping_status", "update", False),
            ("department_staff", "maintenance", "guest_personal_data", "read", False),
            ("department_staff", "maintenance", "audit_trails", "read", False),
            ("manager", None, "audit_trails", "read", True),
        ]
        for role, department, resource, action, allowed in cases:
            with self.subTest(role=role, department=department,
                              resource=resource, action=action):
                ctx = self.context(role, department=department)
                if allowed:
                    self.assertTrue(self.allow(ctx, resource, action))
                else:
                    with self.assertRaises(AccessDenied):
                        self.allow(ctx, resource, action)

    def test_guest_ai_or_room_number_cannot_grant_critical_actions(self):
        guest = self.context("guest", guest_id=self.guest_id)
        for resource, action in (
            ("reservations", "confirm"),
            ("check_in_records", "check_in"),
            ("check_in_records", "check_out"),
            ("room_maintenance_blocks", "release"),
            ("service_requests", "resolve"),
            ("audit_trails", "read"),
            ("management_information", "read"),
            ("staff_administration", "grant"),
        ):
            with self.subTest(resource=resource, action=action):
                with self.assertRaises(AccessDenied):
                    self.allow(guest, resource, action,
                               record_guest_id=self.guest_id)

    def test_unverified_expired_or_nonmember_contexts_are_denied(self):
        cases = [
            self.context("manager", authenticated=False),
            self.context("manager", membership_verified=False),
            self.context("manager", business_binding_verified=False),
            self.context("nonmember"),
            self.context("department_staff", department="fake-department"),
        ]
        for ctx in cases:
            with self.subTest(role=ctx.role, department=ctx.department):
                with self.assertRaises(AccessDenied):
                    self.allow(ctx, "reservations", "read")

    def test_wrong_hotel_and_wrong_business_access_is_denied(self):
        ctx = self.context("manager")
        for kwargs in (
            {"business_id": uid("another-business")},
            {"record_business_id": uid("another-business")},
            {"record_hotel_id": uid("another-hotel")},
        ):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(AccessDenied):
                    authorize_access(
                        ctx, business_id=kwargs.get("business_id", self.business),
                        record_business_id=kwargs.get("record_business_id", self.business),
                        record_hotel_id=kwargs.get("record_hotel_id", self.hotel_id),
                        resource="reservations", action="read",
                    )

    def test_reception_request_view_excludes_writer_and_audit_internals(self):
        front = self.context("receptionist")
        projected = project_service_request(
            front, business_id=self.business, record_business_id=self.business,
            request=self.request,
        )
        for needed in ("request_id", "room_id", "stay_id", "guest_id",
                       "department", "status", "description"):
            self.assertIn(needed, projected)
        for internal in ("idempotency_key", "last_event_id",
                         "last_operation_signature"):
            self.assertNotIn(internal, projected)
        self.assertEqual(projected["description"], self.request["description"])
        self.assertEqual(
            project_service_request(
                self.context("manager"), business_id=self.business,
                record_business_id=self.business, request=self.request,
            )["request_id"],
            self.request["request_id"],
        )

    def test_department_only_sees_minimal_non_sensitive_own_queue_record(self):
        worker = self.context("department_staff", department="housekeeping")
        view = project_service_request(
            worker, business_id=self.business,
            record_business_id=self.business, request=self.request,
        )
        self.assertEqual(view["department"], "housekeeping")
        for field in ("guest_id", "stay_id", "hotel_id", "idempotency_key",
                      "last_event_id", "last_operation_signature"):
            self.assertNotIn(field, view)

        maintenance = self.context("department_staff", department="maintenance")
        with self.assertRaisesRegex(AccessDenied, "wrong_department"):
            project_service_request(
                maintenance, business_id=self.business,
                record_business_id=self.business, request=self.request,
            )
        sensitive = dict(self.request, sensitive=True)
        with self.assertRaisesRegex(AccessDenied, "access_denied"):
            project_service_request(
                worker, business_id=self.business,
                record_business_id=self.business, request=sensitive,
            )
        with self.assertRaisesRegex(AccessDenied, "access_denied"):
            project_service_request(
                self.context("receptionist"), business_id=self.business,
                record_business_id=self.business, request=sensitive,
            )

    def test_guest_only_gets_current_active_stay_profile_and_request(self):
        guest = self.context("guest", guest_id=self.guest_id)
        own = project_service_request(
            guest, business_id=self.business,
            record_business_id=self.business, request=self.request,
            snapshot=self.snapshot, trusted_snapshot_hotel_id=self.hotel_id,
        )
        self.assertIn("status", own)
        for field in ("guest_id", "stay_id", "room_id", "request_id", "idempotency_key"):
            self.assertNotIn(field, own)
        other = self.context("guest", guest_id=uid("Guest A"))
        with self.assertRaisesRegex(AccessDenied, "guest_scope_denied"):
            project_service_request(
                other, business_id=self.business,
                record_business_id=self.business, request=self.request,
                snapshot=self.snapshot, trusted_snapshot_hotel_id=self.hotel_id,
            )
        with self.assertRaisesRegex(AccessDenied, "guest_scope_denied"):
            project_guest_profile(
                other, business_id=self.business,
                record_business_id=self.business, snapshot=self.snapshot,
                guest_id=self.guest_id, trusted_snapshot_hotel_id=self.hotel_id,
            )
        checked_out = deepcopy(self.snapshot)
        checked_out["stays"][0].update(
            status="checked_out", checked_out_at="2026-11-06T13:00:00+01:00",
        )
        checked_out["stay_guests"][0]["left_at"] = "2026-11-06T13:00:00+01:00"
        with self.assertRaisesRegex(AccessDenied, "guest_scope_denied"):
            project_service_request(
                guest, business_id=self.business,
                record_business_id=self.business, request=self.request,
                snapshot=checked_out, trusted_snapshot_hotel_id=self.hotel_id,
            )

    def test_uncommitted_or_tampered_audit_is_not_valid_success_evidence(self):
        event = deepcopy(self.created["plan"]["event"])
        self.assertEqual(event["commit_state"], "pending")
        self.assertFalse(_audit_history_is_consistent(self.request, [event]))
        event["commit_state"] = "committed"
        self.assertTrue(_audit_history_is_consistent(self.request, [event]))
        mutations = (
            {"commit_state": "pending"},
            {"actor_id": ""},
            {"actor_kind": "staff"},
            {"sequence": 2},
            {"to_status": "resolved"},
            {"occurred_at": "not-a-time"},
        )
        for changes in mutations:
            with self.subTest(changes=changes):
                tampered = dict(event, **changes)
                self.assertFalse(_audit_history_is_consistent(self.request, [tampered]))

    def test_safe_error_copy_does_not_reveal_private_details(self):
        secret = "private synthetic guest contact + fake token"
        rendered = safe_error_message(RuntimeError(secret))
        self.assertNotIn(secret, rendered)
        self.assertEqual(rendered, "Hotel information is temporarily unavailable.")


if __name__ == "__main__":
    unittest.main()
