import unittest
from copy import deepcopy

from domain.fixtures import synthetic_hotel, uid
from domain.hotel import overlaps, room_eligibility, validate_snapshot
from domain.schema import proposed_tables


class HotelRules(unittest.TestCase):
    def setUp(self):
        self.data = synthetic_hotel()
        self.walk_in = self.data["reservations"][1]

    def eligible(self, room="202", **kwargs):
        return room_eligibility(self.data, uid("walk-in"), uid(room), **kwargs)

    def test_fixtures_are_deterministic_valid_and_independent(self):
        self.assertEqual(self.data, synthetic_hotel())
        validate_snapshot(self.data)
        self.assertEqual(len(self.data["rooms"]), 10)
        self.assertEqual(len(self.data["room_types"]), 2)
        self.data["rooms"][0]["number"] = "changed"
        self.assertEqual(synthetic_hotel()["rooms"][0]["number"], "201")

    def test_half_open_overlap_cases(self):
        for start, end, expected in [
            ("2026-11-01", "2026-11-03", False),
            ("2026-11-05", "2026-11-07", False),
            ("2026-11-03", "2026-11-05", True),
            ("2026-11-02", "2026-11-04", True),
            ("2026-11-04", "2026-11-06", True),
            ("2026-11-01", "2026-11-09", True),
        ]:
            with self.subTest(start=start, end=end):
                self.assertEqual(overlaps("2026-11-03", "2026-11-05", start, end), expected)
                self.assertEqual(overlaps(start, end, "2026-11-03", "2026-11-05"), expected)

    def test_invalid_dates(self):
        for start, end in [("2026-11-03", "2026-11-03"),
                           ("2026-11-04", "2026-11-03"),
                           ("2026-02-29", "2026-03-01"),
                           ("20261103", "2026-11-05"), (None, "2026-11-05")]:
            with self.subTest(start=start), self.assertRaises(ValueError):
                overlaps(start, end, "2026-11-01", "2026-11-02")
        self.assertTrue(overlaps("2028-02-29", "2028-03-02", "2028-03-01", "2028-03-03"))

    def test_walk_in_reservation_is_not_occupancy(self):
        before = deepcopy(self.data)
        self.assertEqual(self.eligible(check_in=True, today="2026-11-06", staff_approved=True), ())
        self.assertFalse(any(s["room_id"] == uid("202") for s in self.data["stays"]))
        self.assertEqual(self.data, before)

    def test_dirty_room_and_occupied_blocked_room(self):
        self.walk_in["room_id"] = uid("203")
        self.assertEqual(self.eligible("203"), ())  # future allocation may await cleaning
        self.assertIn("housekeeping_not_ready", self.eligible(
            "203", check_in=True, today="2026-11-06", staff_approved=True))
        self.walk_in["status"] = "pending_confirmation"
        self.walk_in.pop("room_id")
        reasons = self.eligible("205", check_in=True, today="2026-11-06")
        self.assertTrue({"occupied", "maintenance_block", "reservation_overlap"} <= set(reasons))

    def test_pending_and_cancelled_cannot_check_in(self):
        for status, reason in [("pending_confirmation", "not_confirmed"), ("cancelled", "cancelled")]:
            self.walk_in["status"] = status
            self.assertIn(reason, self.eligible(check_in=True, today="2026-11-06", staff_approved=True))

    def test_approval_dates_assignment_and_disabled_room(self):
        self.assertIn("staff_approval_required", self.eligible(check_in=True, today="2026-11-06"))
        for today in ("2026-11-05", "2026-11-07"):
            self.assertIn("outside_booking_dates", self.eligible(check_in=True, today=today))
        self.assertIn("room_not_assigned", self.eligible("204", check_in=True, today="2026-11-06"))
        self.data["rooms"][1]["enabled"] = False
        self.assertIn("room_disabled", self.eligible())
        self.assertIn("wrong_room_type", self.eligible("210"))

    def test_pending_and_cancelled_do_not_hold_inventory(self):
        other = dict(self.walk_in, entity_id=uid("other"))
        self.data["reservations"].append(other)
        for status in ("pending_confirmation", "cancelled"):
            other["status"] = status
            self.assertEqual(self.eligible(), ())
        other["status"] = "confirmed"
        with self.assertRaisesRegex(ValueError, "conflicting confirmed"):
            self.eligible()

    def test_overlap_blocks_pending_candidate_and_allows_adjacent_booking(self):
        self.walk_in.update(status="pending_confirmation", room_id=uid("201"),
                            arrival="2026-11-14", departure="2026-11-16")
        self.assertIn("reservation_overlap", self.eligible("201"))
        self.walk_in.update(arrival="2026-11-15", departure="2026-11-16")
        self.assertEqual(self.eligible("201"), ())

    def test_block_release_and_end_boundary(self):
        block = self.data["room_blocks"][0]
        block["room_id"] = uid("202")
        self.assertIn("maintenance_block", self.eligible())
        block["status"] = "released"
        self.assertEqual(self.eligible(), ())
        block.update(status="active", start="2026-11-04", end="2026-11-06")
        self.assertEqual(self.eligible(), ())

    def test_overdue_stay_still_occupies_room(self):
        self.walk_in.update(status="pending_confirmation", arrival="2026-12-01", departure="2026-12-02")
        self.assertIn("occupied", self.eligible("205"))

    def test_used_reservation_cannot_check_in_again(self):
        stay = self.data["stays"][0]
        stay.update(status="checked_out", checked_out_at="2026-11-06T10:00:00+01:00")
        self.data["stay_guests"][0]["left_at"] = stay["checked_out_at"]
        reasons = room_eligibility(self.data, uid("in-house"), uid("205"),
                                   check_in=True, today="2026-11-06", staff_approved=True)
        self.assertIn("reservation_already_used", reasons)
        self.assertNotIn("occupied", reasons)

    def test_invalid_records_fail_closed(self):
        cases = [
            ("rooms", "housekeeping", "vacant"),
            ("rooms", "room_type_id", uid("missing")),
            ("rooms", "enabled", "true"),
            ("reservations", "party_size", 0),
            ("reservations", "party_size", True),
            ("reservations", "party_size", 3),
            ("reservations", "room_id", None),
            ("reservations", "room_type_id", uid("suite")),
            ("stays", "checked_in_at", "2026-11-05T15:00:00"),
            ("stays", "status", "checked_out"),
            ("stays", "reservation_id", uid("walk-in")),
            ("stay_guests", "joined_at", "2026-11-04T15:00:00Z"),
            ("stay_guests", "left_at", "2026-11-04T15:00:00Z"),
            ("room_blocks", "end", "2026-11-05"),
        ]
        for table, key, value in cases:
            with self.subTest(table=table, key=key, value=value):
                data = synthetic_hotel()
                data[table][0][key] = value
                with self.assertRaises(ValueError):
                    validate_snapshot(data)

    def test_duplicate_keys_numbers_and_occupants(self):
        for table in ("rooms", "stay_guests"):
            data = synthetic_hotel()
            data[table].append(dict(data[table][0]))
            with self.assertRaises(ValueError):
                validate_snapshot(data)
            data[table][-1]["entity_id"] = uid("duplicate")
            with self.assertRaises(ValueError):
                validate_snapshot(data)

    def test_stay_requires_registered_occupant(self):
        self.data["stay_guests"] = []
        with self.assertRaises(ValueError):
            validate_snapshot(self.data)

    def test_incomplete_snapshot_fails_closed(self):
        for table in self.data:
            data = synthetic_hotel()
            del data[table]
            with self.assertRaises(ValueError):
                validate_snapshot(data)

    def test_multiple_active_stays_rejected_even_without_booking_overlap(self):
        # Past planned departure does not end physical occupancy.
        booking = dict(self.data["reservations"][2], entity_id=uid("earlier"),
                       arrival="2026-11-01", departure="2026-11-04")
        self.data["reservations"].append(booking)
        self.data["stays"].append(dict(self.data["stays"][0],
                                       entity_id=uid("earlier-stay"),
                                       reservation_id=uid("earlier"),
                                       checked_in_at="2026-11-01T15:00:00Z"))
        with self.assertRaisesRegex(ValueError, "multiple active stays"):
            validate_snapshot(self.data)

    def test_checkout_and_occupant_history_must_agree(self):
        stay = self.data["stays"][0]
        stay.update(status="checked_out", checked_out_at="2026-11-04T10:00:00Z")
        with self.assertRaisesRegex(ValueError, "checkout before"):
            validate_snapshot(self.data)
        stay["checked_out_at"] = "2026-11-06T10:00:00Z"
        with self.assertRaisesRegex(ValueError, "occupant exceeds stay"):
            validate_snapshot(self.data)
        self.data["stay_guests"][0]["left_at"] = "2026-11-06T11:00:00+01:00"
        validate_snapshot(self.data)  # equal instants across different UTC offsets

    def test_unknown_candidate_fails(self):
        with self.assertRaises(ValueError):
            self.eligible("999")

    def test_schema_uses_documented_types_and_choices(self):
        tables = proposed_tables()
        for table in tables:
            self.assertEqual(table["permission"], 700)
            for column in table["columns"]:
                self.assertIn(column["type"], {"text", "number", "uuid", "boolean", "datetime", "mutable_select"})
        tables[0]["columns"][0]["name"] = "mutated"
        self.assertEqual(proposed_tables()[0]["columns"][0]["name"], "entity_id")


if __name__ == "__main__":
    unittest.main()
