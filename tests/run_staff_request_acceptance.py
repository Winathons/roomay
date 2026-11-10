"""Consolidated offline acceptance for staff service-request operations."""
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

MODULES = (
    "tests.test_staff_actions",
    "tests.test_service_requests",
    "tests.test_access_control",
    "tests.test_workpeg_adapter",
    "tests.test_reception_ui",
    "tests.test_release_candidate",
)


def main():
    loader = unittest.defaultTestLoader
    suite = unittest.TestSuite(loader.loadTestsFromName(name) for name in MODULES)
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    outcome = "PASS" if result.wasSuccessful() else "FAIL"
    print("STAFF REQUEST ACCEPTANCE: {} ({} tests, {} failures, {} errors)".format(
        outcome, result.testsRun, len(result.failures), len(result.errors)))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
