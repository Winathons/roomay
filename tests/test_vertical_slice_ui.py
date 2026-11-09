"""Build and execute the actual compiled WOR-60 controller offline."""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from domain.schema_migration import ordered_contracts
from domain.workpeg_adapter import contract_by_key
from workpeg.ui.build import build_ui
from tests.test_vertical_slice import BUSINESS, DATE, NOW, ZONE, prepare, rows_inventory


class CompiledVerticalSliceUiTests(unittest.TestCase):
    def test_compiled_controller_is_offline_gated_and_matches_domain_plan(self):
        self.assertIsNotNone(shutil.which("node"), "Node is required for compiled UI tests")
        root = Path(__file__).resolve().parents[1]
        scratch = root / "build"
        scratch.mkdir(exist_ok=True)
        plan = prepare(rows_inventory())
        contracts = {key: value for key, value in contract_by_key().items()}
        fixture = {
            "business": BUSINESS, "date": DATE, "now": NOW, "zone": ZONE,
            "room_type": rows_inventory()["room_types"][0]["data"],
            "records": plan["records"],
            "contracts": contracts,
        }
        with tempfile.TemporaryDirectory(dir=scratch) as temp:
            output = Path(temp) / "compiled"
            output.mkdir()
            expected_file = Path(temp) / "canonical.json"
            expected_file.write_text(json.dumps(fixture), encoding="utf-8")
            build_ui(str(root / "ui/dev_vertical_slice.py"), str(output), peg_namespace="roomay")
            result = subprocess.run(
                ["node", str(root / "tests/dev_vertical_slice_ui.cjs"), str(output), str(expected_file)],
                capture_output=True, text=True, timeout=120,
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        print(result.stdout.strip())


if __name__ == "__main__":
    unittest.main()
