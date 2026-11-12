"""Offline lifecycle tests for the rendered Remi orb custom element."""

from pathlib import Path
import shutil
import subprocess
import unittest


class RoomayOrbRenderingTests(unittest.TestCase):
    def test_canvas_component_lifecycle_and_fallback(self):
        node = shutil.which("node")
        self.assertIsNotNone(node, "Node is required for the orb component harness")
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [node, str(root / "tests" / "roomay_orb.cjs")],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("7 Roomay orb rendering scenarios passed", result.stdout)


if __name__ == "__main__":
    unittest.main()
