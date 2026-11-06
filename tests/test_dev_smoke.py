"""Compile the real UI, then exercise its generated JS with SDK responses mocked.

No Python reimplementation of the UI's controller and no live API transport.
"""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from workpeg.ui.build import build_ui


class CompiledDevSmoke(unittest.TestCase):
    def test_offline_compiled_controller(self):
        self.assertIsNotNone(shutil.which("node"), "Node is required for compiled UI tests")
        root = Path(__file__).resolve().parents[1]
        scratch = root / "build"
        scratch.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as output:
            build_ui(str(root / "ui/main.py"), output, peg_namespace="roomay")
            result = subprocess.run(
                ["node", str(root / "tests/dev_smoke.cjs"), output],
                capture_output=True, text=True, timeout=60,
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        print(result.stdout.strip())
