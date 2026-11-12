"""WOR-11 front-desk verification tests: entirely synthetic, offline."""
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta, timezone
from unittest import TestCase
from unittest.mock import patch

from domain.fixtures import synthetic_hotel, uid
from domain.hotel import validate_snapshot
from domain.front_desk_checkin import (
    FrontDeskVerification, prepare_verified_walk_in_check_in,
    reconcile_verified_check_in_readback,
)
from domain.reservation_commands import ReservationRejected, WriteContext


class FrontDeskCheckInTests(TestCase):
    def setUp(self):
        self.hotel = synthetic_hotel()
        self.hotel["reservations"].append(dict(
            entity_id=uid("walkin-frontdesk-verified"),
            guest_id=uid("Guest A"), room_type_id=uid("standard"),
            room_id=uid("204"), arrival="2026-11-06",
            departure="2026-11-08", party_size=1,
            source="walk_in", status="confirmed",
        ))
        self.business = uid("frontdesk-business")
        self.context = WriteContext(
            business_id=self.business, snapshot_business_id=self.business,
            actor_id=uid("authorized-frontdesk-staff"), actor_role="receptionist",
            authorization_verified=True, snapshot_fresh=True,
            serialization_guard_held=True,
            authoritative_now="2026-11-06T16:00:00+01:00",
        )
        self.review = FrontDeskVerification(
            reservation_id=uid("walkin-frontdesk-verified"),
            primary_guest_id=uid("Guest A"),
            occupant_guest_ids=(uid("Guest A"),),
            reviewed_by_actor_id=self.context.actor_id,
            reviewed_at="2026-11-06T15:50:00+01:00",
            identity_verified_in_person=True, contact_confirmed=True,
            rate_reviewed=True, payment_disposition="provider_paid",
            payment_evidence_source="verified_provider_callback",
        )

    def plan(self, *, review=None, context=None, snapshot=None,
             checked_in_at="2026-11-06T15:55:00+01:00",
             idempotency_key="walkin-verified-checkin-0001"):
        with patch("domain.reservation_commands.ZoneInfo",
                   return_value=timezone(timedelta(hours=1))):
            return prepare_verified_walk_in_check_in(
                self.hotel if snapshot is None else snapshot,
                review=self.review if review is None else review,
                context=self.context if context is None else context,
                checked_in_at=checked_in_at, today="2026-11-06",
                hotel_timezone="Africa/Lagos", idempotency_key=idempotency_key,
            )

    def test_reviewed_checkin_is_unpersisted_without_personal_details(self):
        original = deepcopy(self.hotel)
        result = self.plan()
        self.assertFalse(result.persisted)
        self.assertFalse(result.check_in.persisted)
        self.assertTrue(result.requires_authoritative_guard)
        self.assertTrue(result.requires_durable_idempotency)
        self.assertTrue(result.requires_committed_audit)
        self.assertTrue(result.requires_complete_readback)
        self.assertEqual(result.check_in.stay_record["status"], "checked_in")
        self.assertEqual(result.check_in.stay_record["room_id"], uid("204"))
        self.assertEqual(len(result.check_in.occupant_records), 1)
        self.assertEqual(result.audit_intent["actor_id"], self.context.actor_id)
        self.assertEqual(result.audit_intent["payment_disposition"], "provider_paid")
        for forbidden in ("scan", "passport", "document", "contact_detail", "phone", "email"):
            self.assertNotIn(forbidden, str(result.audit_intent).lower())
        self.assertEqual(original, self.hotel)

    def test_repeat_is_deterministic_but_never_auto_committed(self):
        first = self.plan()
        again = self.plan()
        self.assertEqual(first.operation_id, again.operation_id)
        self.assertEqual(first.operation_signature, again.operation_signature)
        self.assertEqual(first.check_in, again.check_in)
        self.assertFalse(again.persisted)
        other = self.plan(review=replace(
            self.review, payment_disposition="payment_deferred",
            payment_evidence_source="authorized_hotel_payment_policy",
        ))
        self.assertEqual(first.operation_id, other.operation_id)
        self.assertNotEqual(first.operation_signature, other.operation_signature)

    def test_fails_closed_without_in_person_id_contact_and_rate(self):
        for changes, reason in (
            ({"identity_verified_in_person": False}, "identity_verification_required"),
            ({"contact_confirmed": False}, "contact_confirmation_required"),
            ({"rate_reviewed": False}, "agreed_rate_review_required"),
            ({"reviewed_by_actor_id": uid("other-staff")}, "review_actor_mismatch"),
            ({"primary_guest_id": uid("Guest B")}, "review_primary_guest_mismatch"),
        ):
            with self.subTest(changes=changes), self.assertRaisesRegex(
                    ReservationRejected, reason):
                self.plan(review=replace(self.review, **changes))

    def test_payment_screenshot_or_untrusted_client_state_never_count_as_paid(self):
        for change in (
            {"payment_evidence_source": "screenshot"},
            {"payment_evidence_source": "guest_claim"},
            {"payment_disposition": "provider_paid",
             "payment_evidence_source": "authorized_hotel_payment_policy"},
            {"payment_disposition": "pending"},
        ):
            with self.subTest(change=change), self.assertRaisesRegex(
                    ReservationRejected, "trusted_payment_evidence_required"):
                self.plan(review=replace(self.review, **change))
        for disposition in ("payment_deferred", "no_payment_due"):
            with self.subTest(disposition=disposition):
                result = self.plan(review=replace(
                    self.review, payment_disposition=disposition,
                    payment_evidence_source="authorized_hotel_payment_policy",
                ))
                self.assertEqual(result.audit_intent["payment_disposition"], disposition)

    def test_missing_unverified_extra_or_cross_guest_occupants_refused(self):
        for verified, reason in (
            ((uid("Guest B"),), "occupant_verification_mismatch"),
            ((uid("Guest A"), uid("Guest A")), "occupant_verification_mismatch"),
            ((), "verified_occupants_required"),
            ((uid("Guest A"), uid("Guest B")), "party_size_exceeded"),
        ):
            with self.subTest(verified=verified), self.assertRaisesRegex(
                    ReservationRejected, reason):
                self.plan(review=replace(self.review, occupant_guest_ids=verified))
        malformed = replace(self.review, occupant_guest_ids=(uid("Guest A"), "not-uuid"))
        with self.assertRaisesRegex(ReservationRejected, "invalid_verified_guest_id"):
            self.plan(review=malformed)

    def test_verified_multi_occupant_stay_records_each_guest(self):
        hotel = deepcopy(self.hotel)
        hotel["reservations"][-1]["party_size"] = 2
        review = replace(self.review, occupant_guest_ids=(uid("Guest A"), uid("Guest B")))
        plan = self.plan(review=review, snapshot=hotel)
        self.assertEqual(len(plan.check_in.occupant_records), 2)
        self.assertEqual({row["guest_id"] for row in plan.check_in.occupant_records},
                         {uid("Guest A"), uid("Guest B")})

    def test_review_must_precede_arrival_and_be_fresh(self):
        for reviewed_at, reason in (
            ("2026-11-06T16:02:00+01:00", "front_desk_review_stale_or_future"),
            ("2026-11-06T15:56:00+01:00", "front_desk_review_stale_or_future"),
            ("2026-11-06T15:00:00+01:00", "front_desk_review_stale_or_future"),
            ("2026-11-06T15:50:00", "valid_front_desk_review_time_required"),
        ):
            with self.subTest(reviewed_at=reviewed_at), self.assertRaisesRegex(
                    ReservationRejected, reason):
                self.plan(review=replace(self.review, reviewed_at=reviewed_at))

    def test_only_verified_reception_and_fresh_business_can_plan(self):
        for change, reason in (
            ({"actor_role": "guest"}, "authorized_staff_required"),
            ({"actor_role": "ai_agent"}, "authorized_staff_required"),
            ({"authorization_verified": False}, "authorized_staff_required"),
            ({"snapshot_business_id": uid("another-business")}, "wrong_business"),
            ({"snapshot_fresh": False}, "stale_snapshot"),
            ({"serialization_guard_held": False}, "authoritative_serialization_unavailable"),
        ):
            with self.subTest(change=change), self.assertRaisesRegex(
                    ReservationRejected, reason):
                self.plan(context=replace(self.context, **change))

    def test_room_ineligibility_blocks_verified_checkin(self):
        disabled = deepcopy(self.hotel)
        disabled["rooms"][3]["enabled"] = False
        with self.assertRaisesRegex(ReservationRejected, "room_disabled"):
            self.plan(snapshot=disabled)
        dirty = deepcopy(self.hotel)
        dirty["rooms"][3]["housekeeping"] = "dirty"
        with self.assertRaisesRegex(ReservationRejected, "housekeeping_not_ready"):
            self.plan(snapshot=dirty)
        blocked = deepcopy(self.hotel)
        blocked["room_blocks"].append(dict(
            entity_id=uid("checkin-active-block"), room_id=uid("204"),
            start="2026-11-05", end="2026-11-06",
            reason="Plumbing inspection", status="active",
        ))
        with self.assertRaisesRegex(ReservationRejected, "maintenance_block"):
            self.plan(snapshot=blocked)

    def test_reconciliation_requires_matching_committed_audit_and_rows(self):
        plan = self.plan()
        self.assertEqual(reconcile_verified_check_in_readback(
            plan, self.hotel, context=self.context,
        ), "operation_or_audit_evidence_missing_manual_reconciliation")
        proof = dict(
            operation_id=plan.operation_id,
            idempotency_key=plan.idempotency_key,
            operation_signature=plan.operation_signature,
            audit_committed=True,
        )
        self.assertEqual(reconcile_verified_check_in_readback(
            plan, self.hotel, context=self.context, operation_record=proof,
        ), "committed_audit_and_rows_disagree_manual_reconciliation")
        partial = deepcopy(self.hotel)
        partial["stays"].append(dict(plan.check_in.stay_record))
        self.assertEqual(reconcile_verified_check_in_readback(
            plan, partial, context=self.context, operation_record=proof,
        ), "committed_audit_and_rows_disagree_manual_reconciliation")
        finished = deepcopy(self.hotel)
        finished["stays"].append(dict(plan.check_in.stay_record))
        finished["stay_guests"].extend(dict(row) for row in plan.check_in.occupant_records)
        validate_snapshot(finished)
        self.assertEqual(reconcile_verified_check_in_readback(
            plan, finished, context=self.context, operation_record=proof,
        ), "verified_check_in_observed_do_not_repeat")
        bad = dict(proof, operation_signature="mismatch")
        self.assertEqual(reconcile_verified_check_in_readback(
            plan, finished, context=self.context, operation_record=bad,
        ), "operation_or_audit_evidence_missing_manual_reconciliation")
        bad["operation_signature"] = plan.operation_signature
        bad["audit_committed"] = False
        self.assertEqual(reconcile_verified_check_in_readback(
            plan, finished, context=self.context, operation_record=bad,
        ), "operation_or_audit_evidence_missing_manual_reconciliation")

    def test_only_walk_in_booking_accepted(self):
        booking = deepcopy(self.hotel)
        booking["reservations"][-1]["source"] = "advance"
        with self.assertRaisesRegex(ReservationRejected, "walk_in_reservation_required"):
            self.plan(snapshot=booking)


if __name__ == "__main__":
    import unittest
    unittest.main()
