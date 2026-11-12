"""Offline compiled tests for the isolated WOR-58 controller."""
import ast
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from domain.workpeg_adapter import contract_by_key
from workpeg.ui.build import build_ui


class CompiledDevRoomTypesRows(unittest.TestCase):
    def test_compiled_controller_scenarios(self):
        self.assertIsNotNone(shutil.which("node"), "Node is required for compiled UI scenarios")
        root = Path(__file__).resolve().parents[1]
        scratch = root / "build"
        scratch.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as output:
            build_ui(str(root / "ui/dev_room_types_rows.py"), output, peg_namespace="roomay")
            result = subprocess.run(
                ["node", str(root / "tests/dev_room_types_rows.cjs"), output],
                capture_output=True, text=True, timeout=60,
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        print(result.stdout.strip())

    def test_synthetic_record_uses_canonical_contract_fields(self):
        contract = contract_by_key()["room_types"]
        self.assertEqual(contract["namespace"], "roomay_hotel_v1")
        self.assertEqual(contract["permission"], "700")
        self.assertEqual(
            [(field["id"], field["type"], field["required"]) for field in contract["columns"]],
            [("business_id", "uuid", True), ("entity_id", "uuid", True),
             ("name", "text", True), ("capacity", "number", True)],
        )
        source = Path(__file__).resolve().parents[1] / "ui/dev_room_types_rows.py"
        module = ast.parse(source.read_text(encoding="utf-8"))
        constants = {node.targets[0].id: ast.literal_eval(node.value)
                     for node in module.body if isinstance(node, ast.Assign)
                     and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                     and node.targets[0].id in {"TABLE_NAMESPACE", "ENTITY_ID"}}
        self.assertEqual(constants["TABLE_NAMESPACE"], contract["namespace"])
        self.assertEqual(len(constants["ENTITY_ID"]), 36)


if __name__ == "__main__":
    unittest.main()
