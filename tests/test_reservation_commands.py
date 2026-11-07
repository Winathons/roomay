"""WOR-9: real reservation-state invariants; no Workpeg network access."""
import unittest
from copy import deepcopy

from domain.fixtures import synthetic_hotel, uid
from domain.hotel import validate_snapshot
from domain.reservation_commands import (
    ReservationRejected,
    WriteContext,
    prepare_booking_request,
    prepare_authorized_room_confirmation,
    prepare_cancellation,
    prepare_check_in,
    prepare_room_confirmation,
    prepare_walk_in_request,
    reconcile_check_in_readback,
)


class ReservationCommandTests(unittest.TestCase):
    def setUp(self):
        self.hotel = synthetic_hotel()
        self.pending = self.hotel["reservations"][1]
        self.pending["status"] = "pending_confirmation"

    def request(self, **overrides):
        kwargs = dict(
            idempotency_key="guest-check-in-20261106-0001",
            guest_id=uid("Guest A"),
            room_type_id=uid("standard"),
            arrival="2026-11-16",
            departure="2026-11-18",
            party_size=1,
            source="advance",
        )
        kwargs.update(overrides)
        return prepare_booking_request(self.hotel, **kwargs)

    def confirm(self, room="204", **kwargs):
        params = dict(
            reservation_id=uid("walk-in"),
            room_id=uid(room),
            staff_authorized=True,
        )
        params.update(kwargs)
        return prepare_room_confirmation(self.hotel, **params)

    def test_request_is_pending_and_not_an_active_stay(self):
        original = deepcopy(self.hotel)
        plan = self.request()
        self.assertEqual(plan.action, "create_pending_request")
        self.assertEqual(plan.record["status"], "pending_confirmation")
        self.assertNotIn("room_id", plan.record)
        self.assertTrue(plan.requires_authoritative_guard)
        self.assertFalse(plan.persisted)
        self.assertEqual(self.hotel, original)

    def test_deterministic_request_key_and_safe_repeat(self):
        a = self.request()
        self.assertEqual(a.reservation_id, self.request().reservation_id)
        self.hotel["reservations"].append(dict(a.record))
        validate_snapshot(self.hotel)
        retry = self.request()
        self.assertEqual(retry.action, "already_requested")
        self.assertFalse(retry.persisted)

        self.hotel["reservations"][-1]["status"] = "confirmed"
        self.hotel["reservations"][-1]["room_id"] = uid("204")
        self.assertEqual(self.request().action, "already_requested")

    def test_idempotency_conflict_rejected(self):
        first = self.request()
        self.hotel["reservations"].append(dict(first.record))
        with self.assertRaisesRegex(ReservationRejected, "idempotency_key_reused"):
            self.request(arrival="2026-11-17")

    def test_request_validation_rejects_unknown_guests_types_sources(self):
        for overrides, reason in [
            ({"guest_id": uid("nobody")}, "unknown_guest"),
            ({"room_type_id": uid("missing")}, "unknown_room_type"),
            ({"source": "auto_confirmed"}, "invalid_source"),
            ({"party_size": 3}, "invalid_party_size"),
            ({"party_size": True}, "invalid_party_size"),
            ({"arrival": "2026-11-18"}, "invalid_date_range"),
            ({"idempotency_key": "short"}, "invalid_idempotency_key"),
            ({"idempotency_key": "unsafe/other"}, "invalid_idempotency_key"),
        ]:
            with self.subTest(overrides=overrides):
                with self.assertRaises(ReservationRejected) as e:
                    self.request(**overrides)
                self.assertIn(reason, e.exception.reasons)

    def test_walk_in_is_a_request_until_authorized_confirmation(self):
        plan = self.request(source="walk_in")
        self.assertEqual(plan.record["source"], "walk_in")
        self.assertEqual(plan.record["status"], "pending_confirmation")
        self.assertEqual(len(self.hotel["stays"]), 1)

    def test_only_authorized_staff_may_plan_confirmation(self):
        for supplied in (False, None, "yes", 1):
            with self.subTest(value=supplied):
                with self.assertRaisesRegex(ReservationRejected, "authorized_staff_required"):
                    self.confirm(staff_authorized=supplied)

    def test_confirmation_proposes_transition_but_does_not_save(self):
        original = deepcopy(self.hotel)
        plan = self.confirm()
        self.assertEqual(plan.action, "confirm_reservation")
        self.assertEqual(plan.expected_status, "pending_confirmation")
        self.assertEqual(plan.record["status"], "confirmed")
        self.assertEqual(plan.record["room_id"], uid("204"))
        self.assertTrue(plan.requires_authoritative_guard)
        self.assertFalse(plan.persisted)
        self.assertEqual(self.hotel, original)

    def test_invalid_reservation_states_cannot_confirm(self):
        for status in ("confirmed", "cancelled"):
            self.pending["status"] = status
            with self.subTest(status=status):
                with self.assertRaisesRegex(ReservationRejected, "reservation_not_pending"):
                    self.confirm()

    def test_occupied_blocked_or_disabled_room_rejected(self):
        # 205 is occupied and maintenance-blocked; 203 is dirty but a future
        # allocation is permitted before any actual check-in.
        with self.assertRaises(ReservationRejected) as err:
            self.confirm("205")
        self.assertIn("occupied", err.exception.reasons)
        self.assertIn("maintenance_block", err.exception.reasons)
        self.hotel["rooms"][3]["enabled"] = False  # room 204
        with self.assertRaisesRegex(ReservationRejected, "room_disabled"):
            self.confirm("204")

    def test_two_competing_plans_require_authoritative_serialization(self):
        second = dict(self.pending, entity_id=uid("second-request"), guest_id=uid("Guest A"))
        self.hotel["reservations"].append(second)
        one = self.confirm()
        two = prepare_room_confirmation(self.hotel, reservation_id=uid("second-request"),
                                         room_id=uid("204"), staff_authorized=True)
        self.assertTrue(one.requires_authoritative_guard)
        self.assertTrue(two.requires_authoritative_guard)
        self.assertFalse(one.persisted or two.persisted)
        # After one confirmed save is *observed* in the new authoritative
        # snapshot, another confirmation must be rejected for that date.
        self.pending.update(one.record)
        with self.assertRaisesRegex(ReservationRejected, "reservation_overlap"):
            prepare_room_confirmation(self.hotel, reservation_id=uid("second-request"),
                                      room_id=uid("204"), staff_authorized=True)

    def test_cancellation_cannot_erase_an_active_stay(self):
        with self.assertRaisesRegex(ReservationRejected, "reservation_already_used"):
            prepare_cancellation(self.hotel, reservation_id=uid("in-house"), staff_authorized=True)
        with self.assertRaisesRegex(ReservationRejected, "authorized_staff_required"):
            prepare_cancellation(self.hotel, reservation_id=uid("walk-in"), staff_authorized=False)

    def test_cancel_pending_request_requires_persistence(self):
        original = deepcopy(self.hotel)
        plan = prepare_cancellation(self.hotel, reservation_id=uid("walk-in"),
                                    staff_authorized=True)
        self.assertEqual(plan.expected_status, "pending_confirmation")
        self.assertEqual(plan.record["status"], "cancelled")
        self.assertFalse(plan.persisted)
        self.assertEqual(self.hotel, original)
        self.pending["status"] = "cancelled"
        repeat = prepare_cancellation(self.hotel, reservation_id=uid("walk-in"),
                                      staff_authorized=True)
        self.assertEqual(repeat.action, "already_cancelled")


class SafeCheckInContractTests(unittest.TestCase):
    def setUp(self):
        self.hotel = synthetic_hotel()
        self.business = uid("Roomay development business")
        self.context = WriteContext(
            business_id=self.business, snapshot_business_id=self.business,
            actor_id=uid("authorized receptionist"), actor_role="receptionist",
            authorization_verified=True, snapshot_fresh=True,
            serialization_guard_held=True,
        )
        self.request = {
            "entity_id": uid("walkin-checkin"), "guest_id": uid("Guest A"),
            "room_type_id": uid("standard"), "room_id": uid("204"),
            "arrival": "2026-11-06", "departure": "2026-11-08",
            "party_size": 1, "source": "walk_in", "status": "confirmed",
        }
        self.hotel["reservations"].append(self.request)

    def plan(self, **kwargs):
        params = dict(
            reservation_id=self.request["entity_id"],
            occupant_guest_ids=[uid("Guest A")],
            checked_in_at="2026-11-06T15:00:00+01:00", today="2026-11-06",
            idempotency_key="walkin-attempt-0001", context=self.context,
        )
        params.update(kwargs)
        return prepare_check_in(self.hotel, **params)

    def test_walk_in_request_stays_pending_and_creates_no_stay(self):
        hotel = synthetic_hotel()
        request = prepare_walk_in_request(
            hotel, idempotency_key="walkin-request-0001", guest_id=uid("Guest A"),
            room_type_id=uid("standard"), arrival="2026-11-06", departure="2026-11-08",
            party_size=1, context=self.context,
        )
        self.assertEqual(request.record["status"], "pending_confirmation")
        self.assertNotIn("room_id", request.record)
        self.assertEqual(request.action, "create_pending_request")
        self.assertFalse(request.persisted)
        self.assertEqual(len(hotel["stays"]), 1)
        self.assertEqual(hotel["stays"][0]["reservation_id"], uid("in-house"))

    def test_walkin_retry_is_idempotent_and_unserialized_create_refuses(self):
        hotel = synthetic_hotel()
        args = dict(
            idempotency_key="walkin-request-0002", guest_id=uid("Guest A"),
            room_type_id=uid("standard"), arrival="2026-11-06", departure="2026-11-08",
            party_size=1, context=self.context,
        )
        first = prepare_walk_in_request(hotel, **args)
        hotel["reservations"].append(dict(first.record))
        retry = prepare_walk_in_request(hotel, **args)
        self.assertEqual(retry.action, "already_requested")
        self.assertFalse(retry.persisted)
        unguarded = WriteContext(**{**self.context.__dict__, "serialization_guard_held": False})
        with self.assertRaisesRegex(ReservationRejected, "authoritative_serialization_unavailable"):
            prepare_walk_in_request(hotel, **{**args, "context": unguarded,
                                               "idempotency_key": "walkin-request-0003"})

    def test_room_confirmation_requires_fresh_authorized_serialized_context(self):
        for changes, reason in [
            ({"authorization_verified": False}, "authorized_staff_required"),
            ({"actor_role": "guest"}, "authorized_staff_required"),
            ({"snapshot_fresh": False}, "stale_snapshot"),
            ({"serialization_guard_held": False}, "authoritative_serialization_unavailable"),
            ({"snapshot_business_id": uid("other business")}, "wrong_business"),
        ]:
            with self.subTest(changes=changes):
                context = WriteContext(**{**self.context.__dict__, **changes})
                with self.assertRaisesRegex(ReservationRejected, reason):
                    prepare_authorized_room_confirmation(
                        self.hotel, reservation_id=uid("walk-in"),
                        room_id=uid("204"), context=context,
                    )

    def test_authorized_confirmation_plans_pending_transition_only(self):
        pending = dict(self.request, entity_id=uid("new pending walkin"),
                       arrival="2026-11-09", departure="2026-11-11",
                       status="pending_confirmation")
        pending.pop("room_id")
        self.hotel["reservations"].append(pending)
        plan = prepare_authorized_room_confirmation(
            self.hotel, reservation_id=pending["entity_id"],
            room_id=uid("204"), context=self.context,
        )
        self.assertEqual(plan.record["status"], "confirmed")
        self.assertEqual(plan.record["room_id"], uid("204"))
        self.assertFalse(plan.persisted)

    def test_checkin_plan_is_separate_from_confirmed_reservation_and_not_persisted(self):
        plan = self.plan()
        self.assertEqual(plan.action, "check_in_guest")
        self.assertEqual(plan.stay_record["status"], "checked_in")
        self.assertEqual(plan.stay_record["reservation_id"], self.request["entity_id"])
        self.assertEqual(len(plan.occupant_records), 1)
        self.assertEqual(self.request["status"], "confirmed")
        self.assertEqual(len(self.hotel["stays"]), 1)  # only the unrelated synthetic stay
        self.assertFalse(plan.persisted)
        self.assertTrue(plan.requires_authoritative_guard)

    def test_checkin_fails_closed_for_missing_authority_stale_or_wrong_business(self):
        for changes, reason in [
            ({"authorization_verified": False}, "authorized_staff_required"),
            ({"actor_role": "housekeeping"}, "authorized_staff_required"),
            ({"snapshot_fresh": False}, "stale_snapshot"),
            ({"serialization_guard_held": False}, "authoritative_serialization_unavailable"),
            ({"snapshot_business_id": uid("different business")}, "wrong_business"),
        ]:
            with self.subTest(changes=changes):
                context = WriteContext(**{**self.context.__dict__, **changes})
                with self.assertRaisesRegex(ReservationRejected, reason):
                    self.plan(context=context)

    def test_checkin_rejects_dirty_occupied_or_maintenance_blocked_room(self):
        self.hotel["rooms"][3]["housekeeping"] = "dirty"  # Room 204
        with self.assertRaisesRegex(ReservationRejected, "housekeeping_not_ready"):
            self.plan()

        # Use an eligible interval beginning on the scheduled checkout date.
        self.request.update(arrival="2026-11-08", departure="2026-11-10", room_id=uid("205"))
        with self.assertRaises(ReservationRejected) as error:
            self.plan(today="2026-11-08", checked_in_at="2026-11-08T15:00:00+01:00")
        self.assertIn("occupied", error.exception.reasons)
        self.assertIn("maintenance_block", error.exception.reasons)

    def test_checkin_rejects_invalid_dates_unconfirmed_and_duplicate_attempts(self):
        with self.assertRaisesRegex(ReservationRejected, "outside_booking_dates"):
            self.plan(today="2026-11-08", checked_in_at="2026-11-08T15:00:00+01:00")
        with self.assertRaisesRegex(ReservationRejected, "invalid_check_in_time"):
            self.plan(checked_in_at="2026-11-06T15:00:00")
        self.request["status"] = "pending_confirmation"
        self.request.pop("room_id")
        with self.assertRaisesRegex(ReservationRejected, "confirmed_assignment_required"):
            self.plan()

    def test_duplicate_stay_and_occupants_are_rejected_or_idempotently_recognized(self):
        plan = self.plan()
        self.hotel["stays"].append(dict(plan.stay_record))
        self.hotel["stay_guests"].extend(dict(row) for row in plan.occupant_records)
        retry = self.plan()
        self.assertEqual(retry.action, "already_checked_in")
        self.assertFalse(retry.persisted)
        self.hotel["stay_guests"].clear()
        with self.assertRaises(ReservationRejected):
            self.plan()

    def test_overlapping_confirmed_booking_blocks_room_checkin(self):
        other = dict(self.request)
        other.update(entity_id=uid("overlapping reservation"), arrival="2026-11-06",
                     departure="2026-11-07", room_id=uid("202"))
        self.hotel["reservations"].append(other)
        with self.assertRaises(ReservationRejected):
            self.plan()

    def test_same_key_is_deterministic_and_simultaneous_unserialized_attempt_fails_closed(self):
        first, second = self.plan(), self.plan()
        self.assertEqual(first.stay_record, second.stay_record)
        unguarded = WriteContext(**{**self.context.__dict__, "serialization_guard_held": False})
        with self.assertRaisesRegex(ReservationRejected, "authoritative_serialization_unavailable"):
            self.plan(context=unguarded, idempotency_key="walkin-attempt-0002")

    def test_uncertain_write_readback_never_authorizes_blind_duplicate(self):
        plan = self.plan()
        self.assertEqual(reconcile_check_in_readback(plan, self.hotel, context=self.context),
                         "rows_absent_retry_only_under_held_guard")
        self.hotel["stays"].append(dict(plan.stay_record))
        self.hotel["stay_guests"].extend(dict(row) for row in plan.occupant_records)
        self.assertEqual(reconcile_check_in_readback(plan, self.hotel, context=self.context),
                         "expected_rows_observed_do_not_repeat")
        self.hotel["stay_guests"].clear()
        self.assertEqual(reconcile_check_in_readback(plan, self.hotel, context=self.context),
                         "invalid_readback_manual_reconciliation")


if __name__ == "__main__":
    unittest.main()
