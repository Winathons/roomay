"""Run Roomay's offline reception acceptance set as one report.

Every service response is synthetic or mocked. The selected suites cover the
canonical table/row contracts, complete hotel-to-request validation, the
compiled receptionist controller, auth/error states, release exclusion and
uncertain-write reconciliation. No network client is enabled by this runner.
"""
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


MODULES = (
    "tests.test_workpeg_adapter",
    "tests.test_vertical_slice",
    "tests.test_schema_migration",
    "tests.test_hotel_data_ui",
    "tests.test_reception_ui",
    "tests.test_release_candidate",
)


def main():
    loader = unittest.defaultTestLoader
    suite = unittest.TestSuite(loader.loadTestsFromName(name) for name in MODULES)
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    outcome = "PASS" if result.wasSuccessful() else "FAIL"
    print("RECEPTION ACCEPTANCE: {} ({} tests, {} failures, {} errors)".format(
        outcome, result.testsRun, len(result.failures), len(result.errors)))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
