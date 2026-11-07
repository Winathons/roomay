"""Domain projection and compiled receptionist regression tests."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from domain.fixtures import synthetic_hotel
from domain.hotel import room_eligibility
from domain.reception import build_reception_snapshot
from ui.hotel_data import HotelData


ROOT = Path(__file__).resolve().parents[1]


class ReceptionProjectionTests(unittest.TestCase):
    def test_today_projection_preserves_reservation_and_stay_distinction(self):
        view = build_reception_snapshot(synthetic_hotel(), [], "2026-11-06")
        self.assertEqual(view["metrics"], {
            "in_house": 1, "arrivals": 1, "departures": 0,
            "ready_for_check_in": 1, "overdue_active_stays": 0,
            "needs_cleaning": 1, "maintenance_blocked_rooms": 1,
            "open_requests": 0,
        })
        self.assertEqual(view["arrivals"][0]["room"], "202")
        self.assertEqual(view["in_house"][0]["room"], "205")
        self.assertNotEqual(view["arrivals"][0]["guest"], view["in_house"][0]["guest"])

    def test_overdue_stay_remains_physically_in_house(self):
        hotel = synthetic_hotel()
        booking = next(item for item in hotel["reservations"]
                       if item["entity_id"] == hotel["stays"][0]["reservation_id"])
        booking["departure"] = "2026-11-06"
        view = build_reception_snapshot(hotel, [], "2026-11-07")
        self.assertEqual(view["metrics"]["in_house"], 1)
        self.assertEqual(view["metrics"]["departures"], 0)
        self.assertEqual(view["metrics"]["overdue_active_stays"], 1)
        self.assertEqual(view["in_house"][0]["departure_status"], "OVERDUE")
        self.assertEqual(view["overdue_departures"][0]["room"], "205")

    def test_compiled_readiness_mirror_is_pinned_to_canonical_rules(self):
        hotel = synthetic_hotel()
        app = HotelData()
        app.operational_date = "2026-11-06"
        app.rooms = hotel["rooms"]
        app.reservations = hotel["reservations"]
        app.stays = hotel["stays"]
        app.room_blocks = hotel["room_blocks"]
        for booking in hotel["reservations"]:
            room = next(item for item in hotel["rooms"]
                        if item["entity_id"] == booking["room_id"])
            expected = room_eligibility(
                hotel, booking["entity_id"], room["entity_id"], check_in=True,
                today="2026-11-06", staff_approved=True,
            )
            self.assertEqual(tuple(app.readiness_reasons(booking, room)), expected)

    def test_release_router_exposes_only_real_business_reception(self):
        source = (ROOT / "ui" / "main.py").read_text(encoding="utf-8")
        self.assertIn('Route("/b/[business_id]/reception", HotelData)', source)
        for forbidden in ("/demo/reception", "/dev-smoke", "/hotel-data", "ReceptionDemo"):
            self.assertNotIn(forbidden, source)
        ui_source = (ROOT / "ui" / "hotel_data.py").read_text(encoding="utf-8")
        for forbidden in ("create_table", "add_row", "update_row", "WORKPEG_PK"):
            self.assertNotIn(forbidden, ui_source)

    def test_compiled_reception_controller(self):
        self.assertIsNotNone(shutil.which("node"), "Node is required")
        workpeg = shutil.which("workpeg") or str(ROOT / ".venv" / "Scripts" / "workpeg.exe")
        with tempfile.TemporaryDirectory(dir=ROOT) as output:
            build = subprocess.run(
                [workpeg, "ui", "build", str(ROOT / "ui"), "--out", output],
                cwd=ROOT, capture_output=True, text=True, check=False,
            )
            self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
            result = subprocess.run(
                ["node", str(ROOT / "tests" / "reception.cjs"), output],
                cwd=ROOT, capture_output=True, text=True, timeout=60,
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("compiled reception controller", result.stdout)


if __name__ == "__main__":
    unittest.main()
