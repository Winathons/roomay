"""Offline tests for the isolated compiled first-table setup controller."""
import ast
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from domain.schema_provisioning import prepare_first_room_types_creation
from tests.test_schema_provisioning import BUSINESS, context
from workpeg.ui.build import build_ui


class CompiledDevTableSetup(unittest.TestCase):
    def test_controller_compiles_and_runs_with_mocked_workpeg(self):
        self.assertIsNotNone(shutil.which("node"), "Node 24 is required for compiled UI scenarios")
        root = Path(__file__).resolve().parents[1]
        scratch = root / "build"
        scratch.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as output:
            build_ui(str(root / "ui/dev_table_setup.py"), output, peg_namespace="roomay")
            result = subprocess.run(
                ["node", str(root / "tests/dev_table_setup.cjs"), output],
                capture_output=True, text=True, timeout=60,
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        print(result.stdout.strip())

    def test_ui_payload_matches_canonical_room_types_contract(self):
        proposal = prepare_first_room_types_creation(
            **context(), tables_by_namespace={"roomay_hotel_v1": [], "roomay_requests_v1": []})
        payload = proposal["payload"]
        source = Path(__file__).resolve().parents[1] / "ui/dev_table_setup.py"
        module = ast.parse(source.read_text(encoding="utf-8"))
        controller = next(node for node in module.body
                          if isinstance(node, ast.ClassDef) and node.name == "DevTableSetup")
        method = next(node for node in controller.body
                      if isinstance(node, ast.FunctionDef) and node.name == "room_types_payload")
        namespace_assignment = next(node for node in module.body
                                    if isinstance(node, ast.Assign)
                                    and any(isinstance(target, ast.Name)
                                            and target.id == "TABLE_NAMESPACE"
                                            for target in node.targets))
        namespace = ast.literal_eval(namespace_assignment.value)

        class ResolveNamespace(ast.NodeTransformer):
            def visit_Name(self, node):
                if node.id == "TABLE_NAMESPACE":
                    return ast.copy_location(ast.Constant(value=namespace), node)
                return node

        return_node = ResolveNamespace().visit(method.body[0])
        ui_payload = ast.literal_eval(return_node.value)
        self.assertEqual(ui_payload, payload)
        self.assertEqual(payload["name"], "room_types")
        self.assertEqual(payload["namespace"], "roomay_hotel_v1")
        self.assertEqual(payload["permission"], "700")
        self.assertEqual(payload["metadata"], {"extra": {"contract": "roomay.hotel.v1"}})
        self.assertEqual(
            [(column["id"], column["name"], column["type"], column["position"], column["required"])
             for column in payload["columns"]],
            [("business_id", "business_id", "uuid", 500, True),
             ("entity_id", "entity_id", "uuid", 1000, True),
             ("name", "name", "text", 2000, True),
             ("capacity", "capacity", "number", 3000, True)],
        )
        self.assertEqual(BUSINESS, context()["target_business_id"])


if __name__ == "__main__":
    unittest.main()
