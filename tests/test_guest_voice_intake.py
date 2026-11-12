"""Offline browser-API tests against the actual voice-intake JavaScript."""
import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class GuestVoiceIntakeBrowserTests(unittest.TestCase):
    def test_mocked_browser_voice_scenarios(self):
        node = shutil.which("node")
        self.assertIsNotNone(node, "Node is required for browser voice controller tests")
        result = subprocess.run(
            [node, str(ROOT / "tests" / "guest_voice_intake.cjs")],
            cwd=ROOT, capture_output=True, text=True, timeout=30, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(
            "23 guest voice intake browser scenarios passed", result.stdout,
        )


if __name__ == "__main__":
    unittest.main()
