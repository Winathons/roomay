"""Projection and compiled-controller tests for the offline receptionist UI."""
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from workpeg.ui.build import build_ui

from domain.reception_demo import DEMO_LABEL, build_reception_demo


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ui"))
from reception import (  # noqa: E402
    ARRIVALS, DATE_LABEL, DEPARTURES, IN_HOUSE, METRICS, PENDING_ENQUIRIES, REQUESTS,
    ROOMS, ReceptionDemo,
)


class ReceptionUIProjectionTests(unittest.TestCase):
    def test_compiler_literals_match_canonical_domain_projection(self):
        demo = build_reception_demo()
        self.assertEqual(DATE_LABEL, demo["date_label"])
        self.assertEqual(METRICS, demo["metrics"])
        self.assertEqual(ROOMS, demo["rooms"])
        self.assertEqual(REQUESTS, demo["requests"])
        self.assertEqual(ARRIVALS, demo["arrivals"])
        self.assertEqual(DEPARTURES, demo["departures"])
        self.assertEqual(IN_HOUSE, demo["in_house"])
        self.assertEqual(PENDING_ENQUIRIES, demo["pending_enquiries"])

    def test_runtime_state_defaults_match_reviewed_literals(self):
        self.assertEqual(ReceptionDemo.metrics.default, METRICS)
        self.assertEqual(ReceptionDemo.rooms.default, ROOMS)
        self.assertEqual(ReceptionDemo.requests.default, REQUESTS)
        self.assertEqual(ReceptionDemo.arrivals.default, ARRIVALS)
        self.assertEqual(ReceptionDemo.in_house.default, IN_HOUSE)
        self.assertEqual(ReceptionDemo.pending_enquiries.default, PENDING_ENQUIRIES)

    def test_route_is_explicitly_offline(self):
        source = (ROOT / "ui/reception.py").read_text(encoding="utf-8")
        self.assertIn(r'DEMO_LABEL = "DEMO DATA \N{EM DASH} NOT CONNECTED TO LIVE WORKPEG"', source)
        for forbidden in (
            "workpeg.get_tables", "workpeg.create_table", "workpeg.get_rows",
            "workpeg.add_row", "workpeg.update_row", "WORKPEG_PK",
        ):
            self.assertNotIn(forbidden, source)

    def test_offline_compiled_controller(self):
        self.assertIsNotNone(shutil.which("node"), "Node is required for compiled UI tests")
        scratch = ROOT / "build"
        scratch.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as output:
            build_ui(str(ROOT / "ui/main.py"), output, peg_namespace="roomay")
            result = subprocess.run(
                ["node", str(ROOT / "tests/reception.cjs"), output],
                capture_output=True, text=True, timeout=60,
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        print(result.stdout.strip())


if __name__ == "__main__":
    unittest.main()
