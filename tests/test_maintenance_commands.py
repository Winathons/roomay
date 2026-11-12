"""WOR-20: deterministic safety tests; no Workpeg or database writes."""
from copy import deepcopy
from dataclasses import replace
import unittest

from domain.checkout_commands import OperationContext, OperationRejected
from domain.fixtures import synthetic_hotel, uid
from domain.hotel import room_eligibility, validate_snapshot
from domain.maintenance_commands import (
    eligible_reassignment_rooms, prepare_maintenance_block,
    prepare_maintenance_release, prepare_safe_reassignment,
)


class MaintenanceSafetyTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = synthetic_hotel()
        self.business = uid("fictional-maintenance-business")
        self.hotel = uid("fictional-maintenance-hotel")
        self.context = OperationContext(
            business_id=self.business, snapshot_business_id=self.business,
            hotel_id=self.hotel, snapshot_hotel_id=self.hotel,
            actor_id="verified-manager", actor_role="manager",
            authorization_verified=True, snapshot_fresh=True,
            serialization_guard_held=True,
            authoritative_now="2026-11-12T10:00:00+01:00",
            safety_snapshot_complete=True,
        )

    def block(self, room="201", **changes):
        inputs = dict(
            room_id=uid(room), start="2026-11-12", end="2026-11-16",
            reason="Synthetic air conditioning fault",
            resolution_conditions="Qualified technician verifies repair",
            idempotency_key="maintenance-block-0001", context=self.context,
        )
        inputs.update(changes)
        return prepare_maintenance_block(self.snapshot, **inputs)

    def apply_block(self):
        plan = self.block()
        self.snapshot["room_blocks"].append(dict(plan.block_after))
        validate_snapshot(self.snapshot)
        return plan

    def test_block_is_unpersisted_and_preserves_active_booking(self):
        before = deepcopy(self.snapshot)
        plan = self.block()
        self.assertEqual(before, self.snapshot)
        self.assertFalse(plan.persisted)
        self.assertTrue(plan.requires_authoritative_guard)
        self.assertTrue(plan.requires_durable_idempotency)
        self.assertTrue(plan.requires_complete_readback)
        self.assertEqual(plan.block_after["status"], "active")
        self.assertEqual(plan.block_after["room_id"], uid("201"))
        self.assertEqual(plan.resolution_conditions,
                         "Qualified technician verifies repair")
        self.assertEqual(plan.audit_intent["actor_id"], "verified-manager")
        self.assertEqual(plan.affected_active_stays, ())
        self.assertEqual(plan.room_before, plan.room_after)

    def test_planned_booking_becomes_ineligible_after_block(self):
        self.apply_block()
        reasons = room_eligibility(
            self.snapshot, uid("future"), uid("201"), check_in=True,
            today="2026-11-13", staff_approved=True,
        )
        self.assertIn("maintenance_block", reasons)

    def test_block_remains_unsafe_after_planned_end_until_release(self):
        self.snapshot["reservations"][1].update(
            status="pending_confirmation", room_id=uid("202"),
            arrival="2026-11-17", departure="2026-11-19",
        )
        self.snapshot["room_blocks"].append(dict(
            entity_id=uid("scheduled-end-block"), room_id=uid("202"),
            start="2026-11-12", end="2026-11-14", status="active",
            reason="Synthetic failed air conditioning",
        ))
        self.assertIn("maintenance_block", room_eligibility(
            self.snapshot, uid("walk-in"), uid("202"),
        ))
        self.snapshot["room_blocks"][-1]["status"] = "released"
        self.assertNotIn("maintenance_block", room_eligibility(
            self.snapshot, uid("walk-in"), uid("202"),
        ))

    def test_future_block_does_not_affect_earlier_completed_booking(self):
        self.snapshot["reservations"][1].update(status="pending_confirmation")
        self.snapshot["room_blocks"].append(dict(
            entity_id=uid("future-maintenance"), room_id=uid("202"),
            start="2026-11-10", end="2026-11-12", status="active",
            reason="Synthetic future repair",
        ))
        self.assertNotIn("maintenance_block", room_eligibility(
            self.snapshot, uid("walk-in"), uid("202"),
        ))

    def test_occupied_room_can_be_blocked_but_not_auto_evicted(self):
        self.snapshot["room_blocks"] = []  # simulate first report in Room 205
        plan = self.block(
            "205", idempotency_key="maintenance-occupied-room-1",
            start="2026-11-09", end="2026-11-15",
        )
        self.assertEqual(plan.affected_active_stays, (uid("stay"),))
        self.assertEqual(self.snapshot["stays"][0]["status"], "checked_in")
        self.assertEqual(plan.room_before, plan.room_after)

    def test_existing_active_block_refuses_new_overlapping_block(self):
        with self.assertRaisesRegex(OperationRejected, "active_maintenance_block_exists"):
            self.block("205", start="2026-11-12", end="2026-11-16")

    def test_wrong_business_hotel_and_unauthorized_roles_fail_closed(self):
        for update, reason in (
            ({"snapshot_business_id": uid("wrong-business")}, "wrong_business"),
            ({"snapshot_hotel_id": uid("wrong-hotel")}, "wrong_hotel"),
            ({"authorization_verified": False}, "authorized_staff_required"),
            ({"snapshot_fresh": False}, "stale_snapshot"),
            ({"serialization_guard_held": False}, "authoritative_serialization_unavailable"),
            ({"safety_snapshot_complete": False}, "complete_room_safety_snapshot_required"),
            ({"actor_role": "department_staff", "actor_department": "maintenance"}, "maintenance_supervisor_required"),
            ({"actor_role": "receptionist"}, "maintenance_supervisor_required"),
            ({"actor_role": "ai_agent"}, "maintenance_supervisor_required"),
            ({"authoritative_now": None}, "authoritative_clock_unavailable"),
        ):
            with self.subTest(update=update), self.assertRaisesRegex(OperationRejected, reason):
                self.block(context=replace(self.context, **update))

    def test_proposed_maintenance_supervisor_requires_maintenance_department(self):
        supervisor = replace(
            self.context, actor_role="maintenance_supervisor",
            actor_department="maintenance",
        )
        self.assertEqual(self.block(context=supervisor).action,
                         "create_maintenance_block")
        with self.assertRaisesRegex(OperationRejected, "maintenance_supervisor_required"):
            self.block(context=replace(supervisor, actor_department="housekeeping"))

    def test_invalid_block_request_fails_closed(self):
        for update, reason in (
            ({"room_id": uid("unknown")}, "unknown_room"),
            ({"start": "2026-11-16", "end": "2026-11-16"}, "invalid_block_interval"),
            ({"reason": ""}, "maintenance_reason_required"),
            ({"resolution_conditions": ""}, "resolution_conditions_required"),
            ({"idempotency_key": "short"}, "invalid_idempotency_key"),
        ):
            with self.subTest(update=update), self.assertRaisesRegex(OperationRejected, reason):
                self.block(**update)
        missing = deepcopy(self.snapshot)
        del missing["room_blocks"]
        with self.assertRaisesRegex(OperationRejected, "invalid_or_incomplete_snapshot"):
            prepare_maintenance_block(
                missing, room_id=uid("201"), start="2026-11-12",
                end="2026-11-14", reason="Broken plumbing",
                resolution_conditions="Inspect pipe repair",
                idempotency_key="missing-table-key-1", context=self.context,
            )

    def test_duplicate_operation_requires_durable_readback(self):
        plan = self.block()
        prior = {
            "idempotency_key": plan.idempotency_key,
            "operation_id": plan.operation_id,
            "operation_signature": plan.operation_signature,
        }
        with self.assertRaisesRegex(OperationRejected, "operation_already_attempted_readback_required"):
            self.block(prior_operation=prior)
        with self.assertRaisesRegex(OperationRejected, "idempotency_key_reused_for_different_operation"):
            self.block(reason="Different room fault", prior_operation=prior)
        self.snapshot["room_blocks"].append(plan.block_after)
        with self.assertRaisesRegex(OperationRejected, "operation_already_attempted_readback_required"):
            self.block()

    def test_release_requires_verified_repair_and_supervisor(self):
        block = self.snapshot["room_blocks"][0]
        args = dict(
            block_id=block["entity_id"], verified_repair=True,
            verification_reference="Service ticket verified by manager",
            idempotency_key="maintenance-release-0001",
            context=self.context,
        )
        before = deepcopy(self.snapshot)
        plan = prepare_maintenance_release(self.snapshot, **args)
        self.assertFalse(plan.persisted)
        self.assertEqual(plan.block_before["status"], "active")
        self.assertEqual(plan.block_after["status"], "released")
        self.assertEqual(plan.room_before["housekeeping"], "ready")
        self.assertEqual(plan.room_after["housekeeping"], "inspection")
        self.assertEqual(plan.affected_active_stays, (uid("stay"),))
        self.assertEqual(before, self.snapshot)
        for updates, reason in (
            ({"verified_repair": False}, "repair_verification_required"),
            ({"verification_reference": ""}, "verification_reference_required"),
            ({"context": replace(self.context, actor_role="department_staff",
                                 actor_department="housekeeping")}, "maintenance_supervisor_required"),
            ({"context": replace(self.context, actor_role="ai_agent")}, "maintenance_supervisor_required"),
            ({"context": replace(self.context, snapshot_business_id=uid("wrong"))}, "wrong_business"),
        ):
            with self.subTest(updates=updates), self.assertRaisesRegex(OperationRejected, reason):
                prepare_maintenance_release(self.snapshot, **dict(args, **updates))
        self.snapshot["room_blocks"][0]["status"] = "released"
        with self.assertRaisesRegex(OperationRejected, "block_already_released"):
            prepare_maintenance_release(self.snapshot, **args)

    def test_release_leaves_dirty_room_dirty(self):
        self.snapshot["rooms"][4]["housekeeping"] = "dirty"
        plan = prepare_maintenance_release(
            self.snapshot, block_id=uid("block"), verified_repair=True,
            verification_reference="Maintenance team repair verified",
            idempotency_key="release-dirty-room-1", context=self.context,
        )
        self.assertEqual(plan.room_after["housekeeping"], "dirty")

    def test_alternatives_only_include_enabled_ready_available_same_type(self):
        self.apply_block()
        choices = eligible_reassignment_rooms(
            self.snapshot, reservation_id=uid("future"), context=self.context,
        )
        numbers = {choice["number"] for choice in choices}
        self.assertTrue({"202", "204", "206"} <= numbers)
        self.assertFalse({"201", "203", "205", "207"} & numbers)
        # Reassignment is advisory and cannot silently alter an occupied room.
        self.assertEqual(self.snapshot["reservations"][0]["room_id"], uid("201"))

    def test_safe_reassignment_requires_staff_confirmation_and_audit(self):
        self.apply_block()
        old = deepcopy(self.snapshot)
        plan = prepare_safe_reassignment(
            self.snapshot, reservation_id=uid("future"),
            alternative_room_id=uid("204"),
            idempotency_key="maintenance-reassign-001",
            context=replace(self.context, actor_role="receptionist"),
        )
        self.assertEqual(plan.reservation_before["room_id"], uid("201"))
        self.assertEqual(plan.reservation_after["room_id"], uid("204"))
        self.assertEqual(plan.reservation_after["status"], "confirmed")
        self.assertFalse(plan.persisted)
        self.assertEqual(plan.audit_intent["from_room_id"], uid("201"))
        self.assertEqual(plan.audit_intent["to_room_id"], uid("204"))
        self.assertEqual(old, self.snapshot)
        # Applying the plan is a hypothetical adapter readback, not a real write.
        candidate = deepcopy(self.snapshot)
        candidate["reservations"][0] = dict(plan.reservation_after)
        validate_snapshot(candidate)

    def test_reassignment_rejects_dirty_occupied_wrong_type_and_role(self):
        self.apply_block()
        for candidate in ("203", "205", "207", "201"):
            with self.subTest(candidate=candidate), self.assertRaisesRegex(
                OperationRejected, "alternative_room_not_eligible"
            ):
                prepare_safe_reassignment(
                    self.snapshot, reservation_id=uid("future"),
                    alternative_room_id=uid(candidate),
                    idempotency_key="maintenance-reassign-002",
                    context=self.context,
                )
        with self.assertRaisesRegex(OperationRejected, "authorized_reception_staff_required"):
            eligible_reassignment_rooms(
                self.snapshot, reservation_id=uid("future"),
                context=replace(self.context, actor_role="maintenance_supervisor",
                                actor_department="maintenance"),
            )

    def test_in_house_guest_requires_distinct_room_transfer_workflow(self):
        with self.assertRaisesRegex(OperationRejected, "in_house_transfer_requires_separate_workflow"):
            eligible_reassignment_rooms(
                self.snapshot, reservation_id=uid("in-house"), context=self.context,
            )
        without_block = deepcopy(self.snapshot)
        without_block["room_blocks"] = []
        with self.assertRaisesRegex(OperationRejected, "reservation_not_affected_by_maintenance"):
            eligible_reassignment_rooms(
                without_block, reservation_id=uid("future"), context=self.context,
            )

    def test_concurrent_or_stale_reassignment_requires_external_guard(self):
        self.apply_block()
        for update, reason in (
            ({"serialization_guard_held": False}, "authoritative_serialization_unavailable"),
            ({"snapshot_fresh": False}, "stale_snapshot"),
            ({"safety_snapshot_complete": False}, "complete_room_safety_snapshot_required"),
        ):
            with self.subTest(update=update), self.assertRaisesRegex(OperationRejected, reason):
                prepare_safe_reassignment(
                    self.snapshot, reservation_id=uid("future"),
                    alternative_room_id=uid("204"),
                    idempotency_key="maintenance-reassign-003",
                    context=replace(self.context, **update),
                )


if __name__ == "__main__":
    unittest.main()
