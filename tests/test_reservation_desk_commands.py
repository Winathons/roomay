"""WOR-13 reservation desk decisions: synthetic, non-persisted contracts."""
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta, timezone
from unittest import TestCase
from unittest.mock import patch

from domain.fixtures import synthetic_hotel, uid
from domain.hotel import validate_snapshot
from domain.reservation_commands import ReservationRejected, WriteContext
from domain.reservation_desk_commands import (
    StaffReservationReview, prepare_staff_confirmation,
    prepare_staff_cancellation, reconcile_reservation_decision,
)


class ReservationDeskTests(TestCase):
    def setUp(self):
        self.hotel = synthetic_hotel()
        self.hotel["reservations"].append(dict(
            entity_id=uid("online-request"),
            guest_id=uid("Guest A"), room_type_id=uid("standard"),
            arrival="2026-11-06", departure="2026-11-08",
            party_size=1, source="advance", status="pending_confirmation",
        ))
        self.context = WriteContext(
            business_id=uid("reservation-desk-business"),
            snapshot_business_id=uid("reservation-desk-business"),
            actor_id=uid("verified-receptionist"), actor_role="receptionist",
            authorization_verified=True, snapshot_fresh=True,
            serialization_guard_held=True,
            authoritative_now="2026-11-06T10:00:00+01:00",
        )
        self.review = StaffReservationReview(
            reservation_id=uid("online-request"),
            reviewed_by_actor_id=self.context.actor_id,
            reviewed_at="2026-11-06T09:55:00+01:00",
            inventory_reviewed=True, booking_terms_reviewed=True,
        )

    def confirmation(self, snapshot=None, **updates):
        args = dict(
            reservation_id=uid("online-request"), room_id=uid("204"),
            review=self.review, idempotency_key="online-confirmation-op-001",
            context=self.context, hotel_timezone="Africa/Lagos",
        )
        args.update(updates)
        with patch("domain.reservation_desk_commands.ZoneInfo",
                   return_value=timezone(timedelta(hours=1))):
            return prepare_staff_confirmation(
                self.hotel if snapshot is None else snapshot, **args,
            )

    def cancellation(self, snapshot=None, **updates):
        args = dict(
            reservation_id=uid("online-request"), reason="guest_requested",
            idempotency_key="online-cancellation-op-001", context=self.context,
        )
        args.update(updates)
        return prepare_staff_cancellation(
            self.hotel if snapshot is None else snapshot, **args,
        )

    @staticmethod
    def apply(snapshot, plan):
        result = deepcopy(snapshot)
        result["reservations"] = [
            dict(plan.reservation_after) if row["entity_id"] == plan.reservation_id
            else row for row in result["reservations"]
        ]
        validate_snapshot(result)
        return result

    def test_pending_online_request_does_not_reserve_room_or_start_stay(self):
        original = deepcopy(self.hotel)
        plan = self.confirmation()
        self.assertEqual(plan.reservation_before["source"], "advance")
        self.assertEqual(plan.reservation_before["status"], "pending_confirmation")
        self.assertNotIn("room_id", plan.reservation_before)
        self.assertEqual(plan.reservation_after["status"], "confirmed")
        self.assertEqual(plan.reservation_after["room_id"], uid("204"))
        self.assertEqual(plan.audit_intent["actor_id"], self.context.actor_id)
        self.assertEqual(plan.audit_intent["from_status"], "pending_confirmation")
        self.assertEqual(plan.audit_intent["to_status"], "confirmed")
        self.assertTrue(plan.requires_authoritative_guard)
        self.assertTrue(plan.requires_durable_idempotency)
        self.assertTrue(plan.requires_committed_audit)
        self.assertTrue(plan.requires_complete_readback)
        self.assertFalse(plan.persisted)
        self.assertEqual(self.hotel, original)
        self.assertEqual(len(self.hotel["stays"]), 1)
        applied = self.apply(self.hotel, plan)
        self.assertEqual(applied["reservations"][-1]["status"], "confirmed")
        self.assertEqual(len(applied["stays"]), 1)  # still no physical check-in

    def test_multiple_pending_requests_do_not_hold_inventory_but_one_confirmation_does(self):
        contender = dict(self.hotel["reservations"][-1], entity_id=uid("contending-online"),
                         guest_id=uid("Guest B"))
        self.hotel["reservations"].append(contender)
        first = self.confirmation()
        second = self.confirmation(
            reservation_id=contender["entity_id"], review=replace(
                self.review, reservation_id=contender["entity_id"],
            ), idempotency_key="online-contender-confirm-002",
        )
        self.assertFalse(first.persisted or second.persisted)
        committed_hypothetically = self.apply(self.hotel, first)
        with self.assertRaisesRegex(ReservationRejected, "reservation_overlap"):
            self.confirmation(
                committed_hypothetically,
                reservation_id=contender["entity_id"], review=replace(
                    self.review, reservation_id=contender["entity_id"],
                ), idempotency_key="online-contender-confirm-002",
            )

    def test_confirmation_refuses_invalid_room_or_existing_status(self):
        for target, expected in (
            ("205", "occupied"),
            ("207", "wrong_room_type"),
        ):
            with self.subTest(target=target), self.assertRaisesRegex(
                ReservationRejected, expected
            ):
                self.confirmation(room_id=uid(target))
        disabled = deepcopy(self.hotel)
        disabled["rooms"][3]["enabled"] = False
        with self.assertRaisesRegex(ReservationRejected, "room_disabled"):
            self.confirmation(disabled)
        blocked = deepcopy(self.hotel)
        blocked["room_blocks"].append(dict(
            entity_id=uid("reservation-block"), room_id=uid("204"),
            start="2026-11-05", end="2026-11-06",
            reason="Repair not released", status="active",
        ))
        with self.assertRaisesRegex(ReservationRejected, "maintenance_block"):
            self.confirmation(blocked)
        already_confirmed = self.apply(self.hotel, self.confirmation())
        with self.assertRaisesRegex(ReservationRejected, "reservation_not_pending"):
            self.confirmation(already_confirmed)
        cancelled = deepcopy(self.hotel)
        cancelled["reservations"][-1]["status"] = "cancelled"
        with self.assertRaisesRegex(ReservationRejected, "reservation_not_pending"):
            self.confirmation(cancelled)

    def test_future_allocation_does_not_claim_a_dirty_room_is_checkin_ready(self):
        dirty = deepcopy(self.hotel)
        dirty["rooms"][3]["housekeeping"] = "dirty"
        plan = self.confirmation(dirty)
        self.assertFalse(plan.persisted)
        self.assertEqual(plan.reservation_after["status"], "confirmed")
        # Existing model permits provisional future allocation but still rejects
        # a physical check-in until housekeeping authorizes readiness.
        self.assertEqual(dirty["rooms"][3]["housekeeping"], "dirty")

    def test_staff_review_is_fresh_same_actor_and_approved(self):
        for changes, expected in (
            ({"inventory_reviewed": False}, "inventory_review_required"),
            ({"booking_terms_reviewed": False}, "booking_terms_review_required"),
            ({"reviewed_by_actor_id": uid("other-actor")}, "review_actor_mismatch"),
            ({"reservation_id": uid("different")}, "review_reservation_mismatch"),
            ({"reviewed_at": "2026-11-06T08:00:00+01:00"}, "staff_review_stale_or_future"),
            ({"reviewed_at": "2026-11-06T10:01:00+01:00"}, "staff_review_stale_or_future"),
            ({"reviewed_at": "2026-11-06T09:55:00"}, "valid_review_timestamp_required"),
        ):
            with self.subTest(changes=changes), self.assertRaisesRegex(
                ReservationRejected, expected
            ):
                self.confirmation(review=replace(self.review, **changes))
        with self.assertRaisesRegex(ReservationRejected, "trusted_staff_review_required"):
            self.confirmation(review={"inventory_reviewed": True})

    def test_context_must_be_authorized_and_serialized(self):
        for changes, expected in (
            ({"actor_role": "guest"}, "authorized_staff_required"),
            ({"actor_role": "ai_agent"}, "authorized_staff_required"),
            ({"authorization_verified": False}, "authorized_staff_required"),
            ({"snapshot_business_id": uid("other-business")}, "wrong_business"),
            ({"snapshot_fresh": False}, "stale_snapshot"),
            ({"serialization_guard_held": False}, "authoritative_serialization_unavailable"),
            ({"authoritative_now": None}, "authoritative_clock_unavailable"),
        ):
            for operation in (self.confirmation, self.cancellation):
                with self.subTest(changes=changes, operation=operation.__name__):
                    with self.assertRaisesRegex(ReservationRejected, expected):
                        operation(context=replace(self.context, **changes))

    def test_invalid_timezone_and_elapsed_booking_fail_closed(self):
        with self.assertRaisesRegex(ReservationRejected, "authoritative_hotel_timezone_required"):
            self.confirmation(hotel_timezone="")
        past = deepcopy(self.hotel)
        past["reservations"][-1].update(
            arrival="2026-11-01", departure="2026-11-05",
        )
        with self.assertRaisesRegex(ReservationRejected, "booking_departure_already_passed"):
            self.confirmation(past)
        # UTC+03 clock date is 7 Nov, hotel +01 local date still 6 Nov.
        clock = replace(self.context, authoritative_now="2026-11-07T00:30:00+03:00")
        recent_review = replace(
            self.review, reviewed_at="2026-11-07T00:25:00+03:00",
        )
        self.assertEqual(
            self.confirmation(context=clock, review=recent_review).action,
            "confirm_reservation",
        )

    def test_cancel_pending_requires_non_pii_reason_code_and_no_occupancy(self):
        before = deepcopy(self.hotel)
        plan = self.cancellation()
        self.assertEqual(plan.action, "cancel_reservation")
        self.assertEqual(plan.reservation_after["status"], "cancelled")
        self.assertEqual(plan.audit_intent["cancellation_reason"], "guest_requested")
        self.assertIsNone(plan.reservation_after.get("room_id"))
        self.assertEqual(self.hotel, before)
        for reason in ("", "guest@example.com", "unknown_reason", None):
            with self.subTest(reason=reason), self.assertRaisesRegex(
                ReservationRejected, "approved_cancellation_reason_required"
            ):
                self.cancellation(reason=reason)
        cancelled = self.apply(self.hotel, plan)
        with self.assertRaisesRegex(ReservationRejected, "operation_already_attempted_readback_required"):
            self.cancellation(cancelled)

    def test_cancel_confirmed_releases_future_inventory_but_not_active_stay(self):
        confirmed = self.apply(self.hotel, self.confirmation())
        cancelled = self.cancellation(confirmed, reason="hotel_unavailable")
        self.assertEqual(cancelled.reservation_before["status"], "confirmed")
        self.assertEqual(cancelled.reservation_after["status"], "cancelled")
        post = self.apply(confirmed, cancelled)
        self.assertEqual(post["reservations"][-1]["status"], "cancelled")
        with self.assertRaisesRegex(ReservationRejected, "reservation_already_used"):
            self.cancellation(reservation_id=uid("in-house"))

    def test_reused_idempotency_key_requires_readback_and_rejects_changed_operation(self):
        plan = self.confirmation()
        evidence = {
            "idempotency_key": plan.idempotency_key,
            "operation_id": plan.operation_id,
            "operation_signature": plan.operation_signature,
        }
        with self.assertRaisesRegex(ReservationRejected, "operation_already_attempted_readback_required"):
            self.confirmation(prior_operation=evidence)
        with self.assertRaisesRegex(ReservationRejected, "idempotency_key_reused_for_different_operation"):
            self.cancellation(idempotency_key=plan.idempotency_key,
                              prior_operation=evidence)
        self.assertEqual(self.confirmation().operation_id, plan.operation_id)
        self.assertEqual(self.confirmation().operation_signature, plan.operation_signature)

    def test_matching_committed_audit_and_row_required_before_success(self):
        plan = self.confirmation()
        proof = {
            "idempotency_key": plan.idempotency_key,
            "operation_id": plan.operation_id,
            "operation_signature": plan.operation_signature,
            "audit_committed": True,
        }
        self.assertEqual(reconcile_reservation_decision(
            plan, self.hotel, context=self.context, operation_record=proof,
        ), "source_state_observed_manual_reconciliation")
        self.assertEqual(reconcile_reservation_decision(
            plan, self.hotel, context=self.context,
        ), "operation_or_audit_evidence_missing_manual_reconciliation")
        applied = self.apply(self.hotel, plan)
        self.assertEqual(reconcile_reservation_decision(
            plan, applied, context=self.context, operation_record=proof,
        ), "reservation_decision_observed_do_not_repeat")
        mismatch = dict(proof, operation_signature="invalid")
        self.assertEqual(reconcile_reservation_decision(
            plan, applied, context=self.context, operation_record=mismatch,
        ), "operation_or_audit_evidence_missing_manual_reconciliation")
        evidence = dict(proof, audit_committed=False)
        self.assertEqual(reconcile_reservation_decision(
            plan, applied, context=self.context, operation_record=evidence,
        ), "operation_or_audit_evidence_missing_manual_reconciliation")
        conflicted = deepcopy(applied)
        conflicted["reservations"][-1]["status"] = "cancelled"
        self.assertEqual(reconcile_reservation_decision(
            plan, conflicted, context=self.context, operation_record=proof,
        ), "partial_or_conflicting_state_manual_reconciliation")


if __name__ == "__main__":
    import unittest
    unittest.main()
