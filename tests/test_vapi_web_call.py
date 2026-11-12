"""Mocked acceptance tests for the Vapi browser call adapter."""
import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class VapiWebCallTests(unittest.TestCase):
    def test_mocked_vapi_call_browser_scenarios(self):
        node = shutil.which("node")
        self.assertIsNotNone(node, "Node is required for the Vapi browser harness")
        result = subprocess.run(
            [node, str(ROOT / "tests" / "vapi_web_call.cjs")],
            cwd=ROOT, capture_output=True, text=True, timeout=30, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("13 Vapi Web call scenarios passed", result.stdout)


if __name__ == "__main__":
    unittest.main()
