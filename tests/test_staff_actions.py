"""Offline staff action gateway, department isolation and write reconciliation."""
from copy import deepcopy
import unittest

from domain.access_control import AccessContext, AccessDenied
from domain.fixtures import synthetic_hotel, uid
from domain.service_requests import create_request, event_row_payload, request_view
from domain.staff_actions import (
    StaffActionError, StaffActionGateway, next_persistence_step,
    project_staff_inbox,
)


BUSINESS = uid("wor49-business")
HOTEL_ID = uid("wor49-hotel")
NOWS = iter([
    "2026-11-06T12:01:00+01:00", "2026-11-06T12:02:00+01:00",
    "2026-11-06T12:03:00+01:00", "2026-11-06T12:04:00+01:00",
    "2026-11-06T12:05:00+01:00", "2026-11-06T12:06:00+01:00",
])


def staff_directory():
    return [
        {"actor_id": "front", "hotel_id": HOTEL_ID, "department": "reception",
         "roles": [], "active": True},
        {"actor_id": "housekeeper", "hotel_id": HOTEL_ID,
         "department": "housekeeping", "roles": [], "active": True},
        {"actor_id": "maintenance", "hotel_id": HOTEL_ID,
         "department": "maintenance", "roles": [], "active": True},
        {"actor_id": "manager", "hotel_id": HOTEL_ID, "department": "reception",
         "roles": ["request_admin", "hotel_manager", "incident_manager"],
         "active": True},
    ]


class FakeIdentityResolver:
    def __init__(self, actor_id="front", department="reception", roles=None,
                 **overrides):
        self.calls = []
        row = next(item for item in staff_directory() if item["actor_id"] == actor_id)
        row["department"] = department
        row["roles"] = roles or []
        self.value = {
            "authenticated": True, "membership_verified": True,
            "business_binding_verified": True, "active": True,
            "actor_id": actor_id, "business_id": BUSINESS, "hotel_id": HOTEL_ID,
            "department": department, "roles": roles or [],
            "staff_directory": [row, *[item for item in staff_directory()
                                         if item["actor_id"] != actor_id]],
        }
        self.value.update(overrides)

    def resolve(self, session_proof):
        self.calls.append(session_proof)
        return deepcopy(self.value)


class FakeRequestReader:
    def __init__(self, request, events):
        self.value = {"business_id": BUSINESS, "hotel_id": HOTEL_ID,
                      "request": deepcopy(request), "fingerprint": "fp-1",
                      "events": deepcopy(events)}
        self.calls = []

    def read_request(self, request_id, business_id):
        self.calls.append((request_id, business_id))
        return deepcopy(self.value)


def initial_request_outcome():
    hotel = synthetic_hotel()
    directory = staff_directory()
    guest_id = uid("Guest C")
    result = create_request(
        hotel,
        {"hotel_id": HOTEL_ID, "stay_id": uid("stay"), "room_id": uid("205"),
         "guest_id": guest_id, "origin": "guest", "category": "extra_towels",
         "description": "Please bring two towels.", "urgency": "normal",
         "idempotency_key": "guest-message-stable-1", "sensitive": False},
        {"actor_id": "opaque-guest-session", "hotel_id": HOTEL_ID,
         "kind": "guest", "guest_id": guest_id},
        directory, [], at="2026-11-06T12:00:00+01:00",
        request_id=uid("wor49-request"),
    )
    return result


def committed(event):
    result = deepcopy(event)
    result["commit_state"] = "committed"
    return result


def action_command(request, action, operation_key, **extra):
    return {"request_id": request["request_id"], "action": action,
            "operation_key": operation_key,
            "expected_version": request["version"],
            "expected_fingerprint": "fp-1", **extra}


class StaffActionGatewayTests(unittest.TestCase):
    def setUp(self):
        creation = initial_request_outcome()
        self.request = creation["request"]
        self.creation_event = committed(creation["plan"]["event"])
        self.identity = FakeIdentityResolver()
        self.reader = FakeRequestReader(self.request, [self.creation_event])
        self.gateway = StaffActionGateway(
            self.identity, self.reader,
            lambda: "2026-11-06T12:01:00+01:00",
        )

    def test_assignment_and_department_lifecycle_prepare_only(self):
        assign = self.gateway.prepare("trusted-session-proof",
            action_command(self.request, "assign", "delivery-001",
                           assignee_id="housekeeper"))
        self.assertEqual(assign.state, "prepared")
        self.assertEqual(assign.target_status, "assigned")
        self.assertFalse(assign.persisted)
        self.assertEqual(assign.plan["target_request"]["assigned_staff_id"], "housekeeper")
        self.assertEqual(self.identity.calls, ["trusted-session-proof"])
        self.assertEqual(self.reader.calls, [(self.request["request_id"], BUSINESS)])

        directory = self.identity.value["staff_directory"]
        request = assign.plan["target_request"]
        for action, status in (("acknowledge", "acknowledged"),
                               ("start_work", "in_progress"),
                               ("resolve", "resolved")):
            actor = {"actor_id": "housekeeper", "hotel_id": HOTEL_ID, "kind": "staff"}
            from domain.service_requests import transition_request
            result = transition_request(
                request, {"acknowledge": "acknowledged", "start_work": "in_progress",
                          "resolve": "resolved"}[action], actor, directory,
                at="2026-11-06T12:02:00+01:00", operation_key="sequential-" + action,
            )
            request = result["plan"]["target_request"]
            self.assertEqual(request["status"], status)
            self.assertNotIn("persisted", result["plan"])

    def test_browser_role_staff_business_and_department_claims_are_rejected(self):
        for forged in ("role", "actor_id", "staff_id", "department", "business_id",
                       "hotel_id", "roles", "authenticated"):
            command = action_command(self.request, "assign", "forged-" + forged,
                                     assignee_id="housekeeper")
            command[forged] = "manager"
            with self.subTest(field=forged), self.assertRaisesRegex(
                    StaffActionError, "invalid_staff_command"):
                self.gateway.prepare("untrusted-browser-value", command)
        self.assertEqual(self.identity.calls, [])

    def test_unverified_membership_inactive_or_directory_mismatch_fails_closed(self):
        cases = [
            ({"authenticated": False}, "invalid_trusted_staff_context"),
            ({"membership_verified": False}, "invalid_trusted_staff_context"),
            ({"business_binding_verified": False}, "invalid_trusted_staff_context"),
            ({"active": False}, "invalid_trusted_staff_context"),
        ]
        for overrides, code in cases:
            with self.subTest(overrides=overrides):
                identity = FakeIdentityResolver(**overrides)
                gateway = StaffActionGateway(identity, self.reader, lambda: next(NOWS))
                with self.assertRaisesRegex(StaffActionError, code):
                    gateway.prepare("session", action_command(
                        self.request, "assign", "op", assignee_id="housekeeper"))
        identity = FakeIdentityResolver()
        identity.value["department"] = "maintenance"
        gateway = StaffActionGateway(identity, self.reader, lambda: next(NOWS))
        with self.assertRaisesRegex(StaffActionError, "staff_directory_binding_failed"):
            gateway.prepare("session", action_command(
                self.request, "assign", "op", assignee_id="housekeeper"))

    def test_identity_and_read_failures_are_sanitized_and_fail_closed(self):
        class BrokenIdentity:
            def resolve(self, _proof):
                raise RuntimeError("private cookie and guest description")

        broken = StaffActionGateway(BrokenIdentity(), self.reader,
                                    lambda: "2026-11-06T12:01:00+01:00")
        with self.assertRaisesRegex(StaffActionError, "staff_identity_unavailable") as caught:
            broken.prepare("secret-session", action_command(
                self.request, "assign", "op", assignee_id="housekeeper"))
        self.assertNotIn("private cookie", str(caught.exception))

        class BrokenReader:
            def read_request(self, *_args):
                raise RuntimeError("private Workpeg response")

        broken = StaffActionGateway(self.identity, BrokenReader(),
                                    lambda: "2026-11-06T12:01:00+01:00")
        with self.assertRaisesRegex(StaffActionError, "service_request_unavailable") as caught:
            broken.prepare("session", action_command(
                self.request, "assign", "op", assignee_id="housekeeper"))
        self.assertNotIn("private Workpeg", str(caught.exception))

    def test_wrong_business_hotel_and_cross_department_operations_fail(self):
        self.reader.value["business_id"] = uid("other-business")
        with self.assertRaisesRegex(StaffActionError, "service_request_scope_or_shape_mismatch"):
            self.gateway.prepare("session", action_command(
                self.request, "assign", "op", assignee_id="housekeeper"))
        self.reader.value["business_id"] = BUSINESS
        self.reader.value["hotel_id"] = uid("other-hotel")
        with self.assertRaisesRegex(StaffActionError, "service_request_scope_or_shape_mismatch"):
            self.gateway.prepare("session", action_command(
                self.request, "assign", "op", assignee_id="housekeeper"))
        self.reader.value["hotel_id"] = HOTEL_ID

        identity = FakeIdentityResolver(actor_id="maintenance", department="maintenance")
        gateway = StaffActionGateway(identity, self.reader, lambda: next(NOWS))
        with self.assertRaisesRegex(StaffActionError, "assignment_requires_reception"):
            gateway.prepare("session", action_command(
                self.request, "assign", "op", assignee_id="housekeeper"))

    def test_wrong_assignee_department_stale_fingerprint_and_version_are_denied(self):
        with self.assertRaisesRegex(StaffActionError, "wrong_department_assignee"):
            self.gateway.prepare("session", action_command(
                self.request, "assign", "op", assignee_id="maintenance"))
        stale = action_command(self.request, "assign", "op", assignee_id="housekeeper")
        stale["expected_version"] += 1
        with self.assertRaisesRegex(StaffActionError, "stale_request_snapshot"):
            self.gateway.prepare("session", stale)
        stale = action_command(self.request, "assign", "op", assignee_id="housekeeper")
        stale["expected_fingerprint"] = "old-fingerprint"
        with self.assertRaisesRegex(StaffActionError, "stale_request_snapshot"):
            self.gateway.prepare("session", stale)

    def test_invalid_transitions_urgent_sensitivity_and_malformed_commands_fail(self):
        for invalid in (
            {"request_id": self.request["request_id"], "action": "delete"},
            action_command(self.request, "resolve", "too-early"),
            {**action_command(self.request, "assign", "op", assignee_id="housekeeper"),
             "role": "manager"},
        ):
            with self.subTest(invalid=invalid), self.assertRaises(StaffActionError):
                self.gateway.prepare("session", invalid)

        assigned_plan = self.gateway.prepare("session", action_command(
            self.request, "assign", "assign",
            assignee_id="housekeeper")).plan
        assigned = assigned_plan["target_request"]
        self.reader.value["request"] = assigned
        self.reader.value["events"] = [
            self.creation_event, committed(assigned_plan["event"]),
        ]
        identity = FakeIdentityResolver(actor_id="housekeeper", department="housekeeping")
        gateway = StaffActionGateway(identity, self.reader, lambda: next(NOWS))
        command = action_command(assigned, "escalate", "urgent-escalation",
                                 reason="Safety concern")
        command["expected_fingerprint"] = "fp-1"
        prepared = gateway.prepare("session", command)
        self.assertFalse(prepared.persisted)
        self.assertEqual(prepared.target_status, "escalated")

        sensitive = deepcopy(assigned)
        sensitive["sensitive"] = True
        self.reader.value["request"] = sensitive
        unprivileged = FakeIdentityResolver(actor_id="housekeeper", department="housekeeping")
        gateway = StaffActionGateway(unprivileged, self.reader, lambda: next(NOWS))
        with self.assertRaisesRegex(StaffActionError, "sensitive_escalation_requires_authority"):
            gateway.prepare("session", action_command(
                sensitive, "escalate", "sensitive", reason="Safety concern"))

    def test_repeated_delivery_requires_matching_committed_audit(self):
        command = action_command(self.request, "assign", "delivery-001",
                                 assignee_id="housekeeper")
        planned = self.gateway.prepare("session", command)
        current = deepcopy(planned.plan["target_request"])
        event = committed(planned.plan["event"])
        self.reader.value.update(
            request=current, fingerprint="fp-2",
            events=[self.creation_event, event],
        )
        repeated = self.gateway.prepare("session", command)
        self.assertEqual(repeated.state, "verified_duplicate")
        self.assertTrue(repeated.persisted)

        event["commit_state"] = "pending"
        self.reader.value["events"] = [self.creation_event, event]
        with self.assertRaisesRegex(StaffActionError, "unreconciled_request_audit"):
            self.gateway.prepare("session", command)

    def test_new_transition_refuses_missing_pending_duplicate_and_mismatched_audit(self):
        command = action_command(
            self.request, "assign", "audit-gate", assignee_id="housekeeper")
        valid = self.reader.value["events"]
        cases = {
            "missing": [],
            "pending": [dict(valid[0], commit_state="pending")],
            "duplicate": [valid[0], valid[0]],
            "wrong_request": [dict(valid[0], request_id=uid("other-request"))],
            "wrong_version": [dict(valid[0], sequence=2)],
            "wrong_status": [dict(valid[0], to_status="assigned")],
            "wrong_event_id": [dict(valid[0], event_id=uid("other-event"))],
            "wrong_operation_link": [dict(valid[0], operation_id=uid("other-operation"))],
            "wrong_signature": [dict(valid[0], operation_signature="0" * 64)],
            "gap": [dict(valid[0], sequence=2)],
            "malformed": [{**valid[0], "unexpected": "field"}],
        }
        for name, events in cases.items():
            with self.subTest(name=name):
                self.reader.value["events"] = deepcopy(events)
                with self.assertRaisesRegex(
                        StaffActionError, "unreconciled_request_audit"):
                    self.gateway.prepare("session", command)
        self.reader.value["events"] = valid
        self.assertEqual(self.gateway.prepare("session", command).state, "prepared")

    def test_later_action_refuses_uncommitted_prior_event_even_if_request_matches(self):
        command = action_command(
            self.request, "assign", "prior-pending", assignee_id="housekeeper")
        plan = self.gateway.prepare("session", command).plan
        target = deepcopy(plan["target_request"])
        pending = deepcopy(plan["event"])
        self.reader.value.update(
            request=target,
            events=[self.creation_event, pending],
        )
        next_command = action_command(target, "acknowledge", "next-action")
        next_command["expected_fingerprint"] = "fp-2"
        with self.assertRaisesRegex(StaffActionError, "unreconciled_request_audit"):
            self.gateway.prepare("session", next_command)

    def test_pending_audit_request_commit_order_and_partial_failure_reconcile(self):
        plan = self.gateway.prepare("session", action_command(
            self.request, "assign", "sequence", assignee_id="housekeeper")).plan
        event = plan["event"]
        target = plan["target_request"]
        self.assertEqual(next_persistence_step(plan, self.request, []), "append_pending_event")
        self.assertEqual(next_persistence_step(plan, self.request, [event]), "apply_request")
        self.assertEqual(next_persistence_step(plan, target, [event]), "commit_event")
        committed = dict(event, commit_state="committed")
        self.assertEqual(next_persistence_step(plan, target, [committed]), "complete")
        self.assertEqual(next_persistence_step(plan, None, [committed]),
                         "manual_reconciliation_committed_mismatch")
        self.assertEqual(next_persistence_step(plan, self.request, [event, event]),
                         "manual_reconciliation_duplicate_events")
        mismatch = dict(target, status="received")
        self.assertEqual(next_persistence_step(plan, mismatch, [event]),
                         "manual_reconciliation_request_conflict")

    def test_department_inbox_and_guest_status_are_scoped_and_private(self):
        housekeeping = AccessContext(
            "housekeeper", BUSINESS, HOTEL_ID, "department_staff", True, True, True,
            department="housekeeping",
        )
        maintenance = deepcopy(self.request)
        maintenance.update(request_id=uid("maintenance-request"),
                           last_event_id=uid("maintenance-event"),
                           category="plumbing", category_detail="plumbing",
                           department="maintenance")
        rows = [self.request, maintenance]
        inbox = project_staff_inbox(
            housekeeping, rows, business_id=BUSINESS, record_business_id=BUSINESS,
        )
        self.assertEqual(len(inbox), 1)
        self.assertEqual(inbox[0]["department"], "housekeeping")
        for private in ("guest_id", "stay_id", "hotel_id", "idempotency_key",
                        "last_event_id", "last_operation_signature"):
            self.assertNotIn(private, inbox[0])
        maintenance_staff = AccessContext(
            "maintenance", BUSINESS, HOTEL_ID, "department_staff", True, True, True,
            department="maintenance",
        )
        with self.assertRaisesRegex(AccessDenied, "access_denied"):
            sensitive = deepcopy(maintenance)
            sensitive["sensitive"] = True
            project_staff_inbox(maintenance_staff, [sensitive],
                                business_id=BUSINESS, record_business_id=BUSINESS)

        guest = {"actor_id": "opaque", "hotel_id": HOTEL_ID,
                 "kind": "guest", "guest_id": self.request["guest_id"]}
        status = request_view(self.request, guest, staff_directory(),
                              snapshot=synthetic_hotel())
        self.assertEqual(status["status"], "received")
        for private in ("request_id", "guest_id", "stay_id", "hotel_id", "room_id",
                        "assigned_staff_id", "last_event_id",
                        "last_operation_signature", "idempotency_key"):
            self.assertNotIn(private, status)


if __name__ == "__main__":
    unittest.main()
