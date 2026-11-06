"""WOR-9: real reservation-state invariants; no Workpeg network access."""
import unittest
from copy import deepcopy

from domain.fixtures import synthetic_hotel, uid
from domain.hotel import validate_snapshot
from domain.reservation_commands import (
    ReservationRejected,
    prepare_booking_request,
    prepare_cancellation,
    prepare_room_confirmation,
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
        with self.assertRaisesRegex(ReservationRejected, "authorized_staff_required"):
            self.confirm(staff_authorized=False)

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


if __name__ == "__main__":
    unittest.main()
