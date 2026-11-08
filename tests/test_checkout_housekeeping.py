"""Offline checkout and housekeeping contracts use synthetic hotel records only."""
import unittest
from copy import deepcopy
from datetime import timedelta, timezone
from unittest.mock import patch
from zoneinfo import ZoneInfoNotFoundError

from domain.checkout_commands import (
    OperationContext,
    OperationRejected,
    prepare_checkout,
    prepare_housekeeping_transition,
    reconcile_checkout_readback,
    reconcile_housekeeping_readback,
)
from domain.fixtures import synthetic_hotel, uid
from domain.hotel import validate_snapshot
from domain.service_requests import create_request


BUSINESS_ID = uid("checkout-business")
HOTEL_ID = uid("checkout-hotel")
STAY_ID = uid("stay")
ROOM_ID = uid("205")
OCCUPANT_ID = uid("occupant")


class CheckoutHousekeepingTests(unittest.TestCase):
    def setUp(self):
        self.hotel = synthetic_hotel()
        self.context = self.context_for()

    def context_for(self, **changes):
        values = {
            "business_id": BUSINESS_ID,
            "snapshot_business_id": BUSINESS_ID,
            "hotel_id": HOTEL_ID,
            "snapshot_hotel_id": HOTEL_ID,
            "actor_id": "fictional-staff-actor",
            "actor_role": "receptionist",
            "authorization_verified": True,
            "snapshot_fresh": True,
            "serialization_guard_held": True,
            "authoritative_now": "2026-11-09T10:00:00+01:00",
        }
        values.update(changes)
        return OperationContext(**values)

    def checkout(self, snapshot=None, **kwargs):
        values = {
            "stay_id": STAY_ID,
            "checked_out_at": "2026-11-09T09:00:00+01:00",
            "today": "2026-11-09",
            "hotel_timezone": "Africa/Lagos",
            "idempotency_key": "checkout-op-0000001",
            "context": self.context,
        }
        values.update(kwargs)
        with self._zone_patch(values["hotel_timezone"]):
            return prepare_checkout(self.hotel if snapshot is None else snapshot, **values)

    def housekeeping(self, snapshot=None, **kwargs):
        values = {
            "room_id": uid("203"),
            "target_status": "cleaning",
            "occurred_at": "2026-11-09T09:00:00+01:00",
            "today": "2026-11-09",
            "hotel_timezone": "Africa/Lagos",
            "idempotency_key": "housekeeping-op-0001",
            "context": self.context_for(
                actor_role="department_staff", actor_department="housekeeping",
            ),
            "service_requests": None,
        }
        values.update(kwargs)
        with self._zone_patch(values["hotel_timezone"]):
            return prepare_housekeeping_transition(
                self.hotel if snapshot is None else snapshot, **values,
            )

    @staticmethod
    def _zone_patch(hotel_timezone):
        if hotel_timezone == "Mars/Olympus":
            return patch("domain.checkout_commands.ZoneInfo",
                         side_effect=ZoneInfoNotFoundError)
        return patch("domain.checkout_commands.ZoneInfo",
                     return_value=timezone(timedelta(hours=1)))

    def test_checkout_plan_marks_stay_occupants_and_room_dirty_without_persistence(self):
        self.hotel["reservations"][2]["party_size"] = 2
        self.hotel["stay_guests"].append({
            "entity_id": uid("second-occupant"), "stay_id": STAY_ID,
            "guest_id": uid("Guest B"), "joined_at": "2026-11-06T12:00:00+01:00",
        })
        plan = self.checkout()

        self.assertFalse(plan.persisted)
        self.assertTrue(plan.requires_authoritative_guard)
        self.assertTrue(plan.requires_durable_idempotency)
        self.assertTrue(plan.requires_complete_readback)
        self.assertEqual(plan.stay_after["status"], "checked_out")
        self.assertEqual(plan.stay_after["checked_out_at"], "2026-11-09T09:00:00+01:00")
        self.assertEqual(len(plan.occupants_after), 2)
        self.assertTrue(all(row["left_at"] == plan.stay_after["checked_out_at"]
                            for row in plan.occupants_after))
        self.assertEqual(plan.room_after["housekeeping"], "dirty")
        self.assertEqual(plan.room_before["housekeeping"], "ready")
        self.assertEqual(plan.room_after["enabled"], plan.room_before["enabled"])
        self.assertEqual(self.hotel["stays"][0]["status"], "checked_in")
        self.assertEqual(self.hotel["rooms"][4]["housekeeping"], "ready")

    def test_checkout_can_plan_overdue_departure_but_not_before_check_in(self):
        plan = self.checkout()
        self.assertEqual(plan.stay_before["status"], "checked_in")
        with self.assertRaisesRegex(OperationRejected, "checkout_before_check_in"):
            self.checkout(
                checked_out_at="2026-11-05T14:00:00+01:00", today="2026-11-05",
                context=self.context_for(authoritative_now="2026-11-05T14:30:00+01:00"),
            )

    def test_duplicate_and_inactive_checkout_fail_closed(self):
        plan = self.checkout()
        updated = deepcopy(self.hotel)
        updated["stays"][0] = plan.stay_after
        updated["stay_guests"] = list(plan.occupants_after)
        updated["rooms"][4] = plan.room_after
        validate_snapshot(updated)
        with self.assertRaisesRegex(OperationRejected, "stay_not_checked_in"):
            self.checkout(updated, idempotency_key="checkout-op-0000002")

    def test_checkout_rejects_naive_invalid_and_wrong_local_date_times(self):
        cases = [
            ({"checked_out_at": "2026-11-09T09:00:00"}, "invalid_operation_timestamp"),
            ({"checked_out_at": "bad"}, "invalid_operation_timestamp"),
            ({"checked_out_at": "2026-11-09T11:00:00+01:00"}, "operation_timestamp_in_future"),
            ({"today": "not-a-date"}, "invalid_operational_date"),
            ({"today": "2026-11-08"}, "operational_date_not_authoritative"),
            ({"hotel_timezone": "Mars/Olympus"}, "authoritative_hotel_timezone_unavailable"),
            ({"hotel_timezone": ""}, "invalid_authoritative_hotel_timezone"),
            ({"context": self.context_for(authoritative_now=None)}, "authoritative_clock_unavailable"),
        ]
        for arguments, reason in cases:
            with self.subTest(reason=reason), self.assertRaisesRegex(OperationRejected, reason):
                self.checkout(**arguments)

    def test_checkout_rejects_timezone_boundary_and_offset_not_hotel_date(self):
        context = self.context_for(authoritative_now="2026-11-08T22:30:00+00:00")
        with self.assertRaisesRegex(OperationRejected,
                                    "operation_timestamp_operational_date_mismatch"):
            self.checkout(
                context=context, today="2026-11-08",
                checked_out_at="2026-11-08T23:45:00+00:00",
            )

    def test_checkout_requires_authorized_role_scope_freshness_and_serialization(self):
        cases = [
            (self.context_for(actor_role="guest"), "authorized_checkout_staff_required"),
            (self.context_for(actor_role="department_staff"), "authorized_checkout_staff_required"),
            (self.context_for(authorization_verified=False), "authorized_staff_required"),
            (self.context_for(business_id=uid("other-business")), "wrong_business"),
            (self.context_for(hotel_id=uid("other-hotel")), "wrong_hotel"),
            (self.context_for(snapshot_fresh=False), "stale_snapshot"),
            (self.context_for(serialization_guard_held=False),
             "authoritative_serialization_unavailable"),
            (None, "trusted_operation_context_required"),
        ]
        for context, reason in cases:
            with self.subTest(reason=reason), self.assertRaisesRegex(OperationRejected, reason):
                self.checkout(context=context)

    def test_checkout_requires_registered_occupants_and_all_departures_at_or_before_checkout(self):
        missing = deepcopy(self.hotel)
        missing["stay_guests"] = []
        with self.assertRaisesRegex(OperationRejected, "invalid_or_incomplete_snapshot"):
            self.checkout(missing)

        none_remaining = deepcopy(self.hotel)
        none_remaining["stay_guests"][0]["left_at"] = "2026-11-08T10:00:00+01:00"
        closed = self.checkout(none_remaining)
        self.assertEqual(closed.stay_after["status"], "checked_out")
        self.assertEqual(closed.occupants_after[0]["left_at"], "2026-11-08T10:00:00+01:00")

        future_arrival = deepcopy(self.hotel)
        future_arrival["stay_guests"][0]["joined_at"] = "2026-11-10T10:00:00+01:00"
        with self.assertRaisesRegex(OperationRejected, "occupant_arrival_after_checkout"):
            self.checkout(future_arrival)

        late = deepcopy(self.hotel)
        late["reservations"][2]["party_size"] = 2
        late["stay_guests"][0]["left_at"] = "2026-11-10T10:00:00+01:00"
        late["stay_guests"].append({
            "entity_id": uid("late-test-active-occupant"), "stay_id": STAY_ID,
            "guest_id": uid("Guest B"), "joined_at": "2026-11-06T12:00:00+01:00",
        })
        with self.assertRaisesRegex(OperationRejected, "occupant_departure_after_checkout"):
            self.checkout(late)

    def test_reused_checkout_key_with_changed_payload_is_rejected(self):
        first = self.checkout()
        prior = {
            "idempotency_key": first.idempotency_key,
            "operation_id": first.operation_id,
            "operation_signature": first.operation_signature,
        }
        with self.assertRaisesRegex(
                OperationRejected, "idempotency_key_reused_for_different_operation"):
            self.checkout(
                checked_out_at="2026-11-09T08:30:00+01:00", prior_operation=prior,
            )
        with self.assertRaisesRegex(
                OperationRejected, "operation_already_attempted_readback_required"):
            self.checkout(prior_operation=prior)

    def test_checkout_readback_requires_operation_evidence_and_classifies_partial_writes(self):
        plan = self.checkout()
        operation = {
            "operation_id": plan.operation_id,
            "idempotency_key": plan.idempotency_key,
            "operation_signature": plan.operation_signature,
        }
        self.assertEqual(reconcile_checkout_readback(
            plan, self.hotel, context=self.context, operation_record=operation,
        ), "source_rows_observed_replan_under_fresh_guard")
        self.assertEqual(reconcile_checkout_readback(
            plan, self.hotel, context=self.context,
        ), "operation_evidence_missing_manual_reconciliation")

        partial = deepcopy(self.hotel)
        partial["rooms"][4] = plan.room_after
        self.assertEqual(reconcile_checkout_readback(
            plan, partial, context=self.context, operation_record=operation,
        ), "partial_or_conflicting_rows_manual_reconciliation")

        expected = deepcopy(self.hotel)
        expected["stays"][0] = plan.stay_after
        expected["stay_guests"] = list(plan.occupants_after)
        expected["rooms"][4] = plan.room_after
        validate_snapshot(expected)
        self.assertEqual(reconcile_checkout_readback(
            plan, expected, context=self.context, operation_record=operation,
        ), "target_rows_observed_do_not_repeat")

    def test_housekeeping_dirty_to_cleaning_and_cleaning_to_inspection(self):
        first = self.housekeeping()
        self.assertFalse(first.persisted)
        self.assertEqual(first.expected_status, "dirty")
        self.assertEqual(first.target_status, "cleaning")
        self.assertEqual(self.hotel["rooms"][2]["housekeeping"], "dirty")

        in_progress = deepcopy(self.hotel)
        in_progress["rooms"][2] = first.room_after
        second = self.housekeeping(
            in_progress, target_status="inspection",
            idempotency_key="housekeeping-op-0002",
        )
        self.assertEqual(second.expected_status, "cleaning")
        self.assertEqual(second.target_status, "inspection")

    def test_housekeeping_requires_valid_order_and_prevents_duplicate_or_bypassed_inspection(self):
        with self.assertRaisesRegex(OperationRejected, "invalid_housekeeping_transition"):
            self.housekeeping(target_status="ready")
        with self.assertRaisesRegex(OperationRejected, "duplicate_housekeeping_transition"):
            self.housekeeping(target_status="dirty")
        with self.assertRaisesRegex(OperationRejected, "invalid_housekeeping_transition"):
            self.housekeeping(target_status="inspection")

        inspecting = deepcopy(self.hotel)
        inspecting["rooms"][2]["housekeeping"] = "inspection"
        cleaner = self.context_for(actor_role="department_staff", actor_department="housekeeping")
        with self.assertRaisesRegex(OperationRejected, "housekeeping_supervisor_required"):
            self.housekeeping(inspecting, target_status="ready", context=cleaner)
        manager = self.context_for(actor_role="manager", safety_snapshot_complete=True)
        approved = self.housekeeping(
            inspecting, target_status="ready", context=manager, service_requests=[],
        )
        self.assertFalse(approved.persisted)
        with self.assertRaisesRegex(OperationRejected, "maintenance_safety_evidence_required"):
            self.housekeeping(
                inspecting, target_status="ready",
                context=self.context_for(actor_role="manager"), service_requests=[],
            )

    def test_housekeeping_role_and_context_gates_fail_closed(self):
        cases = [
            (self.context_for(actor_role="guest"), "housekeeping_staff_required"),
            (self.context_for(actor_role="department_staff", actor_department="maintenance"),
             "housekeeping_staff_required"),
            (self.context_for(actor_role="receptionist"), "housekeeping_staff_required"),
            (self.context_for(serialization_guard_held=False),
             "authoritative_serialization_unavailable"),
            (self.context_for(snapshot_fresh=False), "stale_snapshot"),
            (self.context_for(hotel_id=uid("other-hotel")), "wrong_hotel"),
        ]
        for context, reason in cases:
            with self.subTest(reason=reason), self.assertRaisesRegex(OperationRejected, reason):
                self.housekeeping(context=context)

    def test_ready_refuses_occupied_disabled_and_maintenance_blocked_rooms(self):
        manager = self.context_for(actor_role="manager", safety_snapshot_complete=True)
        occupied = deepcopy(self.hotel)
        occupied["rooms"][4]["housekeeping"] = "inspection"
        with self.assertRaisesRegex(OperationRejected, "room_physically_occupied"):
            self.housekeeping(occupied, room_id=ROOM_ID, target_status="ready", context=manager)

        blocked = deepcopy(self.hotel)
        blocked["rooms"][5]["housekeeping"] = "inspection"
        blocked["room_blocks"].append({
            "entity_id": uid("ready-block"), "room_id": uid("206"),
            "start": "2026-11-08", "end": "2026-11-10",
            "reason": "Synthetic active safety block", "status": "active",
        })
        validate_snapshot(blocked)
        with self.assertRaisesRegex(OperationRejected, "active_maintenance_block"):
            self.housekeeping(
                blocked, room_id=uid("206"), target_status="ready", context=manager,
                service_requests=[],
            )

        disabled = deepcopy(self.hotel)
        disabled["rooms"][5].update(enabled=False, housekeeping="inspection")
        with self.assertRaisesRegex(OperationRejected, "room_disabled"):
            self.housekeeping(
                disabled, room_id=uid("206"), target_status="ready", context=manager,
                service_requests=[],
            )

    def test_ready_is_blocked_by_unresolved_maintenance_request(self):
        snapshot = deepcopy(self.hotel)
        snapshot["reservations"].append({
            "entity_id": uid("ready-service-reservation"),
            "guest_id": uid("Guest A"), "room_type_id": uid("standard"),
            "room_id": uid("206"), "arrival": "2026-11-05",
            "departure": "2026-11-08", "party_size": 1,
            "source": "advance", "status": "confirmed",
        })
        snapshot["stays"].append({
            "entity_id": uid("ready-service-stay"),
            "reservation_id": uid("ready-service-reservation"),
            "room_id": uid("206"), "status": "checked_in",
            "checked_in_at": "2026-11-05T15:00:00+01:00",
        })
        snapshot["stay_guests"].append({
            "entity_id": uid("ready-service-occupant"),
            "stay_id": uid("ready-service-stay"), "guest_id": uid("Guest A"),
            "joined_at": "2026-11-05T15:00:00+01:00",
        })
        snapshot["rooms"][5]["housekeeping"] = "inspection"
        validate_snapshot(snapshot)
        staff = [
            {"actor_id": "front", "hotel_id": HOTEL_ID, "department": "reception",
             "roles": [], "active": True},
            {"actor_id": "engineer", "hotel_id": HOTEL_ID, "department": "maintenance",
             "roles": [], "active": True},
        ]
        request = create_request(
            snapshot,
            {"hotel_id": HOTEL_ID, "stay_id": uid("ready-service-stay"),
             "room_id": uid("206"), "guest_id": uid("Guest A"),
             "origin": "guest", "category": "plumbing",
             "description": "Synthetic unresolved leak report.", "urgency": "high",
             "idempotency_key": "guest-room206-request-001", "sensitive": False},
            {"actor_id": "guest-session", "hotel_id": HOTEL_ID,
             "kind": "guest", "guest_id": uid("Guest A")},
            staff, [], at="2026-11-06T12:00:00+01:00",
            request_id=uid("room206-maintenance-request"),
        )["request"]
        snapshot["stays"][1].update(
            status="checked_out", checked_out_at="2026-11-07T10:00:00+01:00",
        )
        snapshot["stay_guests"][1]["left_at"] = "2026-11-07T10:00:00+01:00"
        validate_snapshot(snapshot)
        manager = self.context_for(actor_role="manager", safety_snapshot_complete=True)
        with self.assertRaisesRegex(OperationRejected, "unresolved_maintenance_request"):
            self.housekeeping(
                snapshot, room_id=uid("206"), target_status="ready", context=manager,
                service_requests=[request],
            )
        cross_hotel_request = dict(request, hotel_id=uid("other-hotel"))
        with self.assertRaisesRegex(OperationRejected, "wrong_hotel"):
            self.housekeeping(
                snapshot, room_id=uid("206"), target_status="ready", context=manager,
                service_requests=[cross_hotel_request],
            )

    def test_cleaning_never_releases_a_maintenance_block(self):
        blocked = deepcopy(self.hotel)
        blocked["rooms"][2]["housekeeping"] = "dirty"
        blocked["room_blocks"].append({
            "entity_id": uid("cleaning-block"), "room_id": uid("203"),
            "start": "2026-11-08", "end": "2026-11-10",
            "reason": "Synthetic maintenance", "status": "active",
        })
        validate_snapshot(blocked)
        before_blocks = deepcopy(blocked["room_blocks"])
        plan = self.housekeeping(blocked)
        self.assertEqual(plan.room_after["housekeeping"], "cleaning")
        self.assertEqual(blocked["room_blocks"], before_blocks)
        self.assertFalse(hasattr(plan, "room_blocks"))

    def test_housekeeping_readback_does_not_retry_or_claim_persistence(self):
        plan = self.housekeeping()
        operation = {
            "operation_id": plan.operation_id,
            "idempotency_key": plan.idempotency_key,
            "operation_signature": plan.operation_signature,
        }
        self.assertEqual(reconcile_housekeeping_readback(
            plan, self.hotel, context=self.context_for(
                actor_role="department_staff", actor_department="housekeeping",
            ), operation_record=operation,
        ), "source_state_observed_replan_under_fresh_guard")
        applied = deepcopy(self.hotel)
        applied["rooms"][2] = plan.room_after
        self.assertEqual(reconcile_housekeeping_readback(
            plan, applied, context=self.context_for(
                actor_role="department_staff", actor_department="housekeeping",
            ), operation_record=operation,
        ), "target_state_observed_do_not_repeat")


if __name__ == "__main__":
    unittest.main()
