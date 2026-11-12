import unittest

from domain.reception_demo import (
    DEMO_LABEL, build_reception_demo, filter_rooms,
)


class ReceptionDemoProjectionTests(unittest.TestCase):
    def setUp(self):
        self.demo = build_reception_demo()

    def test_today_counts_are_deterministic_and_consistent(self):
        metrics = {metric["label"]: metric["value"] for metric in self.demo["metrics"]}
        self.assertEqual(metrics, {
            "In house": 1,
            "Arrivals": 1,
            "Departures": 0,
            "Ready for check-in": 1,
            "Needs cleaning": 1,
            "Maintenance blocks": 1,
            "Open requests": 3,
        })
        self.assertEqual(len(self.demo["in_house"]), metrics["In house"])
        self.assertEqual(len(self.demo["arrivals"]), metrics["Arrivals"])
        self.assertEqual(len(self.demo["departures"]), metrics["Departures"])

    def test_vital_room_states_preserve_hotel_distinctions(self):
        rooms = {room["number"]: room for room in self.demo["rooms"]}
        self.assertEqual(rooms["202"]["occupancy"], "Arriving today")
        self.assertIn("Ready for arrival", rooms["202"]["filters"])
        self.assertEqual(rooms["203"]["occupancy"], "Vacant")
        self.assertEqual(rooms["203"]["housekeeping"], "Dirty")
        self.assertEqual(rooms["205"]["occupancy"], "In house")
        self.assertEqual(rooms["205"]["maintenance"], "Blocked")
        self.assertIn("not checked in", rooms["202"]["stay_note"])

    def test_room_filters_only_filter_mapped_board_state(self):
        rooms = self.demo["rooms"]
        self.assertEqual(len(filter_rooms(rooms, "All rooms")), 10)
        expected = {
            "In house": ["205"],
            "Ready for arrival": ["202"],
            "Needs cleaning": ["203"],
            "Blocked": ["205"],
        }
        for name, numbers in expected.items():
            with self.subTest(name=name):
                self.assertEqual(
                    [room["number"] for room in filter_rooms(rooms, name)], numbers,
                )

    def test_requests_have_complete_reception_context(self):
        self.assertEqual(len(self.demo["requests"]), 4)
        for request in self.demo["requests"]:
            self.assertTrue(request["description"])
            self.assertTrue(request["category"])
            self.assertTrue(request["department"])
            self.assertIn(request["priority"], {"Low", "Normal", "Urgent"})
            self.assertIn(request["status"], {"New", "Acknowledged", "In progress", "Resolved"})
            self.assertTrue(request["room"])

    def test_demo_label_is_explicit_and_not_a_live_claim(self):
        self.assertEqual(DEMO_LABEL, "DEMO DATA — NOT CONNECTED TO LIVE WORKPEG")
        self.assertNotIn("LIVE DATA", DEMO_LABEL)

    def test_projection_is_fresh(self):
        self.demo["rooms"][0]["number"] = "changed"
        self.assertEqual(build_reception_demo()["rooms"][0]["number"], "201")


if __name__ == "__main__":
    unittest.main()
