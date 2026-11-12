import unittest
from copy import deepcopy

from domain.fixtures import synthetic_hotel, uid
from domain.service_request_schema import proposed_service_request_tables
from domain.service_requests import (
    AuthorizationError, ConflictError, RequestError, create_request,
    event_row_payload, reconcile_write, request_row_payload, request_view,
    route_category, transition_request, triage_request, validate_request,
)


HOTEL = uid("request-hotel")
TIMES = [f"2026-11-06T{hour:02d}:00:00+01:00" for hour in range(12, 23)]


class ServiceRequestLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.hotel = synthetic_hotel()
        self.staff = [
            self.staff_record("front", "reception"),
            self.staff_record("housekeeper", "housekeeping"),
            self.staff_record("housekeeping-lead", "housekeeping", ["department_supervisor"]),
            self.staff_record("engineer", "maintenance"),
            self.staff_record("server", "food_and_beverage"),
            self.staff_record("manager", "reception", [
                "request_admin", "hotel_manager", "incident_manager",
            ]),
        ]
        self.guest = {
            "actor_id": "guest-session-c", "hotel_id": HOTEL,
            "kind": "guest", "guest_id": uid("Guest C"),
        }
        self.draft = {
            "hotel_id": HOTEL,
            "stay_id": uid("stay"),
            "room_id": uid("205"),
            "guest_id": uid("Guest C"),
            "origin": "guest",
            "category": "extra_towels",
            "description": "Please bring two additional towels.",
            "urgency": "normal",
            "idempotency_key": "guest-session-c:message-100",
            "sensitive": False,
        }

    @staticmethod
    def staff_record(actor_id, department, roles=None):
        return {"actor_id": actor_id, "hotel_id": HOTEL, "department": department,
                "roles": roles or [], "active": True}

    @staticmethod
    def staff_actor(actor_id):
        return {"actor_id": actor_id, "hotel_id": HOTEL, "kind": "staff"}

    def create(self, **changes):
        draft = dict(self.draft, **changes)
        return create_request(
            self.hotel, draft, self.guest, self.staff, [], at=TIMES[0],
            request_id=uid("service-request-1"),
        )

    def transition(self, request, target, actor_id, index, **kwargs):
        return transition_request(
            request, target, self.staff_actor(actor_id), self.staff,
            at=TIMES[index], operation_key=f"op-{index}-{target}", **kwargs,
        )

    def test_canonical_creation_verifies_stay_room_guest_and_audit(self):
        outcome = self.create()
        request = outcome["request"]
        self.assertEqual(outcome["kind"], "created")
        self.assertEqual(request["status"], "received")
        self.assertEqual(request["department"], "housekeeping")
        self.assertEqual(request["room_id"], uid("205"))
        self.assertEqual(request["version"], 1)
        self.assertEqual(request["last_event_id"], outcome["plan"]["event"]["event_id"])
        self.assertLess(request["acknowledge_by"], request["due_at"])
        event = outcome["plan"]["event"]
        self.assertEqual(event["actor_id"], self.guest["actor_id"])
        self.assertEqual(event["to_status"], "received")
        self.assertEqual(event["commit_state"], "pending")
        validate_request(request)

    def test_full_happy_path_is_strict_and_audited(self):
        request = self.create()["request"]
        steps = [
            ("assigned", "front", {"assignee_id": "housekeeper"}),
            ("acknowledged", "housekeeper", {}),
            ("in_progress", "housekeeper", {}),
            ("resolved", "housekeeper", {}),
        ]
        for index, (status, actor, options) in enumerate(steps, start=1):
            before = request
            outcome = self.transition(request, status, actor, index, **options)
            request = outcome["request"]
            self.assertEqual(request["status"], status)
            self.assertEqual(request["version"], before["version"] + 1)
            self.assertEqual(outcome["plan"]["event"]["from_status"], before["status"])
            self.assertEqual(outcome["plan"]["event"]["sequence"], request["version"])
        self.assertEqual(request["assigned_staff_id"], "housekeeper")
        self.assertIn("resolved_at", request)

    def test_invalid_transitions_and_guest_self_resolution_are_rejected(self):
        request = self.create()["request"]
        with self.assertRaisesRegex(ConflictError, "invalid_status_transition"):
            self.transition(request, "resolved", "front", 1)
        with self.assertRaisesRegex(AuthorizationError, "guest_transition_forbidden"):
            transition_request(
                request, "cancelled", self.guest, self.staff, at=TIMES[1],
                operation_key="guest-cancel", reason="Changed mind", snapshot=self.hotel,
            )
        assigned = self.transition(
            request, "assigned", "front", 1, assignee_id="housekeeper")["request"]
        with self.assertRaisesRegex(AuthorizationError, "guest_transition_forbidden"):
            transition_request(
                assigned, "acknowledged", self.guest, self.staff, at=TIMES[2],
                operation_key="guest-ack", snapshot=self.hotel,
            )

    def test_duplicate_creation_is_reconciled_and_conflicting_reuse_rejected(self):
        first = self.create()["request"]
        duplicate = create_request(
            self.hotel, self.draft, self.guest, self.staff, [first], at=TIMES[1],
            request_id=uid("ignored-on-exact-retry"),
        )
        self.assertEqual(duplicate["kind"], "duplicate")
        self.assertIsNone(duplicate["plan"])
        conflict = dict(self.draft, description="A different request with the same key")
        with self.assertRaisesRegex(ConflictError, "idempotency_conflict"):
            create_request(
                self.hotel, conflict, self.guest, self.staff, [first], at=TIMES[1],
                request_id=uid("service-request-2"),
            )

    def test_reception_can_create_phone_request_but_department_staff_cannot(self):
        phone_draft = dict(
            self.draft, origin="phone", idempotency_key="front:phone-call-1")
        made = create_request(
            self.hotel, phone_draft, self.staff_actor("front"), self.staff, [],
            at=TIMES[0], request_id=uid("phone-request"),
        )
        self.assertEqual(made["request"]["origin"], "phone")
        with self.assertRaisesRegex(AuthorizationError, "manual_request_requires_reception"):
            create_request(
                self.hotel, phone_draft, self.staff_actor("housekeeper"), self.staff, [],
                at=TIMES[0], request_id=uid("unauthorized-phone-request"),
            )

    def test_transition_operation_is_idempotent(self):
        request = self.create()["request"]
        outcome = transition_request(
            request, "assigned", self.staff_actor("front"), self.staff,
            at=TIMES[1], operation_key="assign-once", assignee_id="housekeeper",
        )
        retry = transition_request(
            outcome["request"], "assigned", self.staff_actor("front"), self.staff,
            at=TIMES[2], operation_key="assign-once", assignee_id="housekeeper",
        )
        self.assertEqual(retry["kind"], "duplicate")
        self.assertIsNone(retry["plan"])
        with self.assertRaisesRegex(ConflictError, "idempotency_conflict"):
            transition_request(
                outcome["request"], "assigned", self.staff_actor("front"), self.staff,
                at=TIMES[2], operation_key="assign-once", assignee_id="housekeeping-lead",
            )

    def test_unknown_category_routes_to_human_triage_before_assignment(self):
        outcome = self.create(category="something surprising")
        request = outcome["request"]
        self.assertEqual(route_category("something surprising"),
                         ("unknown", "reception", True))
        self.assertTrue(request["triage_required"])
        with self.assertRaisesRegex(ConflictError, "request_not_awaiting_triage"):
            triage_request(
                self.create()["request"], "plumbing", self.staff_actor("front"),
                self.staff, at=TIMES[1], operation_key="bad-triage", reason="Known already",
            )
        triaged = triage_request(
            request, "plumbing", self.staff_actor("front"), self.staff,
            at=TIMES[1], operation_key="triage-plumbing",
            reason="Guest confirmed a plumbing issue",
        )["request"]
        self.assertEqual(triaged["department"], "maintenance")
        self.assertFalse(triaged["triage_required"])
        duplicate = triage_request(
            triaged, "plumbing", self.staff_actor("front"), self.staff,
            at=TIMES[2], operation_key="triage-plumbing",
            reason="Guest confirmed a plumbing issue",
        )
        self.assertEqual(duplicate["kind"], "duplicate")
        with self.assertRaisesRegex(AuthorizationError, "wrong_department_assignee"):
            self.transition(triaged, "assigned", "front", 2, assignee_id="housekeeper")
        assigned = self.transition(
            triaged, "assigned", "front", 2, assignee_id="engineer")["request"]
        self.assertEqual(assigned["assigned_staff_id"], "engineer")

    def test_department_routing_contracts_are_explicit(self):
        expected = {
            "extra_towels": "housekeeping",
            "plumbing": "maintenance",
            "room_service": "food_and_beverage",
            "transport": "reception",
        }
        for category, department in expected.items():
            with self.subTest(category=category):
                self.assertEqual(route_category(category), (category, department, False))
        self.assertEqual(route_category("not-in-catalogue"),
                         ("unknown", "reception", True))

    def test_authorized_cancellation_and_reopen_require_audit_reasons(self):
        request = self.create()["request"]
        with self.assertRaisesRegex(RequestError, "transition_reason_required"):
            self.transition(request, "cancelled", "front", 1)
        cancelled = self.transition(
            request, "cancelled", "front", 1,
            reason="Guest confirmed the request is no longer needed",
        )["request"]
        self.assertEqual(cancelled["status"], "cancelled")
        reopened = self.transition(
            cancelled, "reopened", "front", 2,
            reason="Guest called reception to restore the request",
        )["request"]
        self.assertEqual(reopened["status"], "reopened")

    def test_wrong_department_and_unassigned_staff_cannot_operate_request(self):
        assigned = self.transition(
            self.create()["request"], "assigned", "front", 1,
            assignee_id="housekeeper")["request"]
        with self.assertRaisesRegex(AuthorizationError, "assigned_department_authority_required"):
            self.transition(assigned, "acknowledged", "engineer", 2)
        with self.assertRaisesRegex(AuthorizationError, "assigned_department_authority_required"):
            self.transition(assigned, "acknowledged", "front", 2)
        acknowledged = self.transition(
            assigned, "acknowledged", "housekeeping-lead", 2)["request"]
        self.assertEqual(acknowledged["status"], "acknowledged")

    def test_expired_stay_and_cross_guest_creation_are_rejected(self):
        expired = synthetic_hotel()
        expired["stays"][0].update(
            status="checked_out", checked_out_at="2026-11-06T10:00:00+01:00")
        expired["stay_guests"][0]["left_at"] = "2026-11-06T10:00:00+01:00"
        with self.assertRaisesRegex(RequestError, "inactive_or_wrong_stay"):
            create_request(
                expired, self.draft, self.guest, self.staff, [], at=TIMES[0],
                request_id=uid("expired"),
            )
        other_guest = dict(self.guest, guest_id=uid("Guest B"))
        with self.assertRaisesRegex(AuthorizationError, "cross_guest_access"):
            create_request(
                self.hotel, self.draft, other_guest, self.staff, [], at=TIMES[0],
                request_id=uid("wrong-guest"),
            )

    def test_sensitive_escalation_requires_privileged_staff(self):
        assigned = self.transition(
            self.create()["request"], "assigned", "front", 1,
            assignee_id="housekeeper")["request"]
        with self.assertRaisesRegex(AuthorizationError, "sensitive_escalation_requires_authority"):
            self.transition(
                assigned, "escalated", "housekeeper", 2,
                reason="Possible safety concern", sensitive_escalation=True,
            )
        escalated = self.transition(
            assigned, "escalated", "manager", 2,
            reason="Manager accepted safety escalation", sensitive_escalation=True,
        )["request"]
        self.assertTrue(escalated["sensitive"])
        self.assertEqual(escalated["status"], "escalated")
        with self.assertRaisesRegex(AuthorizationError, "sensitive_request_access_denied"):
            request_view(escalated, self.staff_actor("housekeeper"), self.staff)
        self.assertEqual(
            request_view(escalated, self.staff_actor("manager"), self.staff)["request_id"],
            escalated["request_id"],
        )

    def test_resolved_request_can_be_reopened_but_not_silently(self):
        request = self.create()["request"]
        request = self.transition(request, "assigned", "front", 1,
                                  assignee_id="housekeeper")["request"]
        request = self.transition(request, "acknowledged", "housekeeper", 2)["request"]
        request = self.transition(request, "in_progress", "housekeeper", 3)["request"]
        request = self.transition(request, "resolved", "housekeeper", 4)["request"]
        with self.assertRaisesRegex(RequestError, "transition_reason_required"):
            transition_request(
                request, "reopened", self.guest, self.staff, at=TIMES[5],
                operation_key="reopen-no-reason", snapshot=self.hotel,
            )
        reopened = transition_request(
            request, "reopened", self.guest, self.staff, at=TIMES[5],
            operation_key="reopen-valid", reason="Towels did not arrive",
            snapshot=self.hotel,
        )["request"]
        self.assertEqual(reopened["status"], "reopened")
        self.assertIsNone(reopened["assigned_staff_id"])

    def test_cross_hotel_cross_guest_and_cross_department_views_fail_closed(self):
        request = self.create()["request"]
        wrong_hotel = dict(self.guest, hotel_id=uid("other-hotel"))
        with self.assertRaisesRegex(AuthorizationError, "cross_hotel_access"):
            request_view(request, wrong_hotel, self.staff, snapshot=self.hotel)
        wrong_guest = dict(self.guest, guest_id=uid("Guest B"))
        with self.assertRaisesRegex(AuthorizationError, "cross_guest_access"):
            request_view(request, wrong_guest, self.staff, snapshot=self.hotel)
        with self.assertRaisesRegex(AuthorizationError, "wrong_department_access"):
            request_view(request, self.staff_actor("engineer"), self.staff)
        visible = request_view(request, self.staff_actor("housekeeper"), self.staff)
        self.assertEqual(visible["request_id"], request["request_id"])

    def test_failed_write_reconciliation_never_blindly_retries(self):
        plan = self.create()["plan"]
        event = plan["event"]
        target = plan["target_request"]
        self.assertEqual(reconcile_write(plan, None, []), "append_pending_event")
        self.assertEqual(reconcile_write(plan, None, [event]), "apply_request")
        self.assertEqual(reconcile_write(plan, target, [event]), "commit_event")
        committed = dict(event, commit_state="committed")
        self.assertEqual(reconcile_write(plan, target, [committed]), "complete")
        self.assertEqual(
            reconcile_write(plan, None, [committed]),
            "manual_reconciliation_committed_mismatch",
        )
        conflicting = dict(event, actor_id="someone-else")
        self.assertEqual(
            reconcile_write(plan, None, [conflicting]),
            "manual_reconciliation_event_conflict",
        )
        self.assertEqual(
            reconcile_write(plan, None, [event, dict(event)]),
            "manual_reconciliation_duplicate_events",
        )
        same_version_conflict = dict(target, description="Concurrent unrelated edit")
        same_version_conflict["version"] = plan["base_request"]["version"] if plan["base_request"] else 1
        self.assertEqual(
            reconcile_write(plan, same_version_conflict, []),
            "manual_reconciliation_request_conflict",
        )

    def test_corrupt_persisted_request_is_rejected_before_use(self):
        request = self.create()["request"]
        cases = [
            ("department", "maintenance"),
            ("triage_required", True),
            ("last_event_id", None),
            ("assigned_staff_id", "housekeeper"),
            ("updated_at", "2026-11-05T10:00:00+01:00"),
        ]
        for field, value in cases:
            with self.subTest(field=field):
                broken = dict(request, **{field: value})
                with self.assertRaisesRegex(RequestError, "invalid_request_record"):
                    validate_request(broken)

    def test_workpeg_row_contract_preserves_full_data_and_restrictive_inheritance(self):
        plan = self.create()["plan"]
        request_payload = request_row_payload(plan["target_request"], 1000)
        event_payload = event_row_payload(plan["event"], 1000)
        self.assertEqual(request_payload["data"]["description"], self.draft["description"])
        self.assertNotIn("assigned_staff_id", request_payload["data"])
        for payload in (request_payload, event_payload):
            self.assertFalse(payload["inherit_business_permission"])
            self.assertFalse(payload["inherit_individual_permissions"])

    def test_schema_uses_only_documented_types_and_owner_only_defaults(self):
        tables = proposed_service_request_tables()
        self.assertEqual([table["alias"] for table in tables], [
            "roomay-service-requests-v1", "roomay-service-request-audit-v1",
        ])
        for table in tables:
            self.assertEqual(table["permission"], "700")
            self.assertEqual(table["namespace"], "roomay_requests_v1")
            for column in table["columns"]:
                self.assertIn(column["type"], {
                    "text", "number", "boolean", "datetime", "uuid", "mutable_select",
                })
        tables[0]["columns"][0]["name"] = "changed"
        self.assertEqual(
            proposed_service_request_tables()[0]["columns"][0]["name"], "request_id")


if __name__ == "__main__":
    unittest.main()
