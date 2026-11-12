"""WOR-12 room transfer regression: synthetic, offline, no Workpeg writes."""
import unittest
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta, timezone
from unittest.mock import patch

from domain.checkout_commands import OperationContext, OperationRejected, prepare_checkout
from domain.fixtures import synthetic_hotel, uid
from domain.hotel import validate_snapshot
from domain.room_transfer import (
    prepare_room_transfer, reconcile_room_transfer_readback,
)
from domain.service_requests import (
    AuthorizationError, RequestError, create_request, request_view,
)


BUSINESS = uid("room-transfer-business")
HOTEL = uid("room-transfer-hotel")
STAY = uid("stay")
FROM_ROOM = uid("205")
TO_ROOM = uid("204")


class RoomTransferTests(unittest.TestCase):
    def setUp(self):
        self.hotel = synthetic_hotel()
        self.context = OperationContext(
            business_id=BUSINESS, snapshot_business_id=BUSINESS,
            hotel_id=HOTEL, snapshot_hotel_id=HOTEL,
            actor_id="verified-reception", actor_role="receptionist",
            authorization_verified=True, snapshot_fresh=True,
            serialization_guard_held=True,
            authoritative_now="2026-11-07T10:00:00+01:00",
            safety_snapshot_complete=True,
        )
        self.staff = [
            dict(actor_id="verified-reception", hotel_id=HOTEL,
                 department="reception", active=True, roles=["request_admin"]),
        ]
        self.guest = dict(actor_id="verified-guest-session", hotel_id=HOTEL,
                          kind="guest", guest_id=uid("Guest C"))
        self.draft = dict(
            hotel_id=HOTEL, stay_id=STAY, room_id=FROM_ROOM,
            guest_id=uid("Guest C"), origin="guest",
            category="air_conditioning", description="Air conditioning broken",
            urgency="normal", idempotency_key="room-move-request-001",
            sensitive=False,
        )
        self.request = create_request(
            self.hotel, self.draft, self.guest, self.staff, [],
            at="2026-11-06T12:00:00+01:00",
            request_id=uid("room-move-service-request"),
        )["request"]

    def plan(self, snapshot=None, **updates):
        args = dict(
            stay_id=STAY, to_room_id=TO_ROOM, moved_at="2026-11-07T09:00:00+01:00",
            today="2026-11-07", hotel_timezone="Africa/Lagos",
            reason="Guest needs another room due to cooling fault",
            idempotency_key="room-transfer-test-0001",
            context=self.context, service_requests=[self.request],
        )
        args.update(updates)
        zone = timezone(timedelta(hours=1))
        with patch("domain.checkout_commands.ZoneInfo", return_value=zone), patch(
                "domain.room_transfer.ZoneInfo", return_value=zone):
            return prepare_room_transfer(
                self.hotel if snapshot is None else snapshot, **args,
            )

    def applied(self, plan, snapshot=None):
        snap = deepcopy(self.hotel if snapshot is None else snapshot)
        snap["reservations"] = [
            dict(plan.reservation_after) if r["entity_id"] == plan.reservation_id else r
            for r in snap["reservations"]
        ]
        snap["stays"] = [
            dict(plan.stay_after) if row["entity_id"] == plan.stay_id else row
            for row in snap["stays"]
        ]
        snap["rooms"] = [
            dict(plan.old_room_after) if row["entity_id"] == plan.from_room_id else row
            for row in snap["rooms"]
        ]
        validate_snapshot(snap)
        return snap

    def test_move_proposal_changes_stay_booking_and_old_room_only(self):
        before = deepcopy(self.hotel)
        plan = self.plan()
        self.assertEqual(plan.stay_before["room_id"], FROM_ROOM)
        self.assertEqual(plan.stay_after["room_id"], TO_ROOM)
        self.assertEqual(plan.reservation_after["room_id"], TO_ROOM)
        self.assertEqual(plan.old_room_before["housekeeping"], "ready")
        self.assertEqual(plan.old_room_after["housekeeping"], "dirty")
        self.assertEqual(plan.new_room_after, plan.new_room_before)
        self.assertEqual(plan.historical_request_ids, (self.request["request_id"],))
        self.assertEqual(plan.open_old_room_request_ids, (self.request["request_id"],))
        self.assertEqual(plan.audit_intent["from_room_id"], FROM_ROOM)
        self.assertEqual(plan.audit_intent["to_room_id"], TO_ROOM)
        self.assertEqual(plan.audit_intent["actor_id"], self.context.actor_id)
        self.assertFalse(plan.persisted)
        self.assertTrue(plan.requires_complete_readback)
        self.assertTrue(plan.requires_authoritative_guard)
        self.assertTrue(plan.requires_durable_idempotency)
        self.assertEqual(before, self.hotel)
        post = self.applied(plan)
        self.assertEqual(post["stays"][0]["status"], "checked_in")
        self.assertEqual(post["stays"][0]["room_id"], TO_ROOM)
        self.assertEqual(post["rooms"][4]["housekeeping"], "dirty")
        self.assertEqual(post["rooms"][3]["housekeeping"], "ready")
        self.assertEqual(post["stay_guests"], before["stay_guests"])

    def test_move_preserves_guest_request_history_and_identity_scope(self):
        plan = self.plan()
        post = self.applied(plan)
        self.assertEqual(self.request["room_id"], FROM_ROOM)
        view = request_view(self.request, self.guest, self.staff, snapshot=post)
        self.assertEqual(view["status"], "received")
        self.assertNotIn("room_id", view)
        with self.assertRaisesRegex(AuthorizationError, "cross_guest_access"):
            request_view(self.request, dict(self.guest, guest_id=uid("Guest A")),
                         self.staff, snapshot=post)
        with self.assertRaisesRegex(RequestError, "inactive_or_wrong_stay"):
            create_request(
                post, dict(self.draft, idempotency_key="old-room-replay-002"),
                self.guest, self.staff, [],
                at="2026-11-07T09:20:00+01:00",
                request_id=uid("new-old-room-request"),
            )
        new_draft = dict(self.draft, room_id=TO_ROOM,
                         idempotency_key="new-room-request-002")
        new_request = create_request(
            post, new_draft, self.guest, self.staff, [],
            at="2026-11-07T09:20:00+01:00",
            request_id=uid("new-destination-request"),
        )["request"]
        self.assertEqual(new_request["room_id"], TO_ROOM)

    def test_checked_out_stay_cannot_view_historical_ticket(self):
        plan = self.plan()
        post = self.applied(plan)
        with patch("domain.checkout_commands.ZoneInfo",
                   return_value=timezone(timedelta(hours=1))):
            checkout = prepare_checkout(
                post, stay_id=STAY, checked_out_at="2026-11-07T09:30:00+01:00",
                today="2026-11-07", hotel_timezone="Africa/Lagos",
                idempotency_key="checkout-after-transfer-1", context=self.context,
            )
        self.assertEqual(checkout.room_id, TO_ROOM)
        self.assertEqual(checkout.room_after["housekeeping"], "dirty")
        post["stays"][0] = checkout.stay_after
        post["stay_guests"] = list(checkout.occupants_after)
        post["rooms"][3] = checkout.room_after
        validate_snapshot(post)
        with self.assertRaisesRegex(RequestError, "inactive_or_wrong_stay"):
            request_view(self.request, self.guest, self.staff, snapshot=post)

    def test_target_must_be_ready_enabled_unoccupied_same_type_and_unblocked(self):
        cases = [
            ("203", "housekeeping_not_ready"),
            ("205", "same_room_transfer"),
            ("207", "wrong_room_type"),
            ("202", "reservation_overlap"),
        ]
        for target, reason in cases:
            with self.subTest(target=target), self.assertRaisesRegex(
                    OperationRejected, reason):
                self.plan(to_room_id=uid(target))
        disabled = deepcopy(self.hotel)
        disabled["rooms"][3]["enabled"] = False
        with self.assertRaisesRegex(OperationRejected, "room_disabled"):
            self.plan(disabled)
        dirty = deepcopy(self.hotel)
        dirty["rooms"][3]["housekeeping"] = "inspection"
        with self.assertRaisesRegex(OperationRejected, "housekeeping_not_ready"):
            self.plan(dirty)

    def test_active_block_remains_unsafe_after_planned_end(self):
        blocked = deepcopy(self.hotel)
        blocked["room_blocks"].append(dict(
            entity_id=uid("target-block"), room_id=TO_ROOM,
            start="2026-11-06", end="2026-11-07",
            reason="Fault not yet cleared", status="active",
        ))
        with self.assertRaisesRegex(OperationRejected, "active_maintenance_block"):
            self.plan(blocked)
        blocked["room_blocks"][-1]["status"] = "released"
        self.assertEqual(self.plan(blocked).to_room_id, TO_ROOM)

    def test_no_unapproved_concurrency_or_foreign_business(self):
        cases = [
            ({"snapshot_business_id": uid("other-business")}, "wrong_business"),
            ({"snapshot_hotel_id": uid("other-hotel")}, "wrong_hotel"),
            ({"authorization_verified": False}, "authorized_staff_required"),
            ({"actor_role": "department_staff"}, "authorized_checkout_staff_required"),
            ({"actor_role": "ai_agent"}, "authorized_checkout_staff_required"),
            ({"snapshot_fresh": False}, "stale_snapshot"),
            ({"serialization_guard_held": False}, "authoritative_serialization_unavailable"),
            ({"safety_snapshot_complete": False}, "complete_room_safety_snapshot_required"),
        ]
        for changes, error in cases:
            with self.subTest(changes=changes), self.assertRaisesRegex(OperationRejected, error):
                self.plan(context=replace(self.context, **changes))

    def test_requires_valid_time_actor_reason_stay_and_snapshot(self):
        for updates, reason in [
            ({"reason": "  "}, "room_move_reason_required"),
            ({"idempotency_key": "short"}, "invalid_idempotency_key"),
            ({"moved_at": "2026-11-07T12:00:00+01:00"}, "operation_timestamp_in_future"),
            ({"moved_at": "2026-11-04T09:00:00+01:00", "today": "2026-11-04",
              "context": replace(self.context, authoritative_now="2026-11-04T10:00:00+01:00")},
             "transfer_before_check_in"),
            ({"service_requests": None}, "complete_request_history_required"),
            ({"to_room_id": uid("unknown")}, "unknown_target_room"),
            ({"stay_id": uid("unknown")}, "unknown_stay"),
        ]:
            with self.subTest(reason=reason), self.assertRaisesRegex(OperationRejected, reason):
                self.plan(**updates)
        bad = deepcopy(self.hotel)
        del bad["room_blocks"]
        with self.assertRaisesRegex(OperationRejected, "invalid_or_incomplete_snapshot"):
            self.plan(bad)

    def test_readback_classifies_all_or_none_and_partial_recovery(self):
        plan = self.plan()
        proof = dict(
            operation_id=plan.operation_id, idempotency_key=plan.idempotency_key,
            operation_signature=plan.operation_signature,
        )
        self.assertEqual(reconcile_room_transfer_readback(
            plan, self.hotel, context=self.context, operation_record=proof,
        ), "source_rows_observed_replan_under_fresh_guard")
        self.assertEqual(reconcile_room_transfer_readback(
            plan, self.hotel, context=self.context,
        ), "operation_evidence_missing_manual_reconciliation")
        post = self.applied(plan)
        self.assertEqual(reconcile_room_transfer_readback(
            plan, post, context=self.context, operation_record=proof,
        ), "target_rows_observed_do_not_repeat")
        partial = deepcopy(self.hotel)
        partial["stays"][0]["room_id"] = TO_ROOM  # reservation not changed
        self.assertEqual(reconcile_room_transfer_readback(
            plan, partial, context=self.context, operation_record=proof,
        ), "invalid_readback_manual_reconciliation")
        changed = self.applied(plan)
        changed["rooms"][3]["housekeeping"] = "inspection"
        self.assertEqual(reconcile_room_transfer_readback(
            plan, changed, context=self.context, operation_record=proof,
        ), "partial_or_conflicting_rows_manual_reconciliation")

    def test_duplicate_operation_and_request_history_inconsistency(self):
        plan = self.plan()
        proof = dict(
            operation_id=plan.operation_id, idempotency_key=plan.idempotency_key,
            operation_signature=plan.operation_signature,
        )
        with self.assertRaisesRegex(OperationRejected, "operation_already_attempted_readback_required"):
            self.plan(prior_operation=proof)
        with self.assertRaisesRegex(OperationRejected, "idempotency_key_reused_for_different_operation"):
            self.plan(reason="Alternative reason", prior_operation=proof)
        with self.assertRaisesRegex(OperationRejected, "duplicate_request_history"):
            self.plan(service_requests=[self.request, deepcopy(self.request)])
        wrong_hotel = dict(self.request, hotel_id=uid("other-hotel"))
        with self.assertRaisesRegex(OperationRejected, "wrong_hotel_request_history"):
            self.plan(service_requests=[wrong_hotel])


if __name__ == "__main__":
    unittest.main()
