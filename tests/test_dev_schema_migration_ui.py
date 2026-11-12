"""Compiled offline tests for the isolated WOR-59 migration controller."""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from domain.schema_migration import ordered_contracts
from workpeg.ui.build import build_ui


class CompiledSchemaMigrationUiTests(unittest.TestCase):
    def test_compiled_controller_and_contract_parity(self):
        self.assertIsNotNone(shutil.which("node"), "Node is required for compiled UI scenarios")
        root = Path(__file__).resolve().parents[1]
        scratch = root / "build"
        scratch.mkdir(exist_ok=True)
        expected = {item["name"]: item for item in ordered_contracts()}
        with tempfile.TemporaryDirectory(dir=scratch) as temp:
            output = Path(temp) / "compiled"
            output.mkdir()
            expected_file = Path(temp) / "canonical.json"
            expected_file.write_text(json.dumps(expected), encoding="utf-8")
            build_ui(str(root / "ui/dev_schema_migration.py"), str(output), peg_namespace="roomay")
            result = subprocess.run(
                ["node", str(root / "tests/dev_schema_migration_ui.cjs"),
                 str(output), str(expected_file)],
                capture_output=True, text=True, timeout=60,
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        print(result.stdout.strip())


if __name__ == "__main__":
    unittest.main()
