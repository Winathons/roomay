import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class CompiledHotelDataTests(unittest.TestCase):
    def test_generated_controller_against_mocked_workpeg_runtime(self):
        node = shutil.which("node")
        workpeg = shutil.which("workpeg") or str(ROOT / ".venv" / "Scripts" / "workpeg.exe")
        if not node or not Path(workpeg).exists():
            self.skipTest("Node and the pinned Workpeg CLI are required")
        with tempfile.TemporaryDirectory(dir=ROOT) as output:
            build = subprocess.run(
                [workpeg, "ui", "build", str(ROOT / "ui"), "--out", output],
                cwd=ROOT, capture_output=True, text=True, check=False,
            )
            self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
            result = subprocess.run(
                [node, str(ROOT / "tests" / "hotel_data.cjs"), output],
                cwd=ROOT, capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("11 compiled hotel-data scenarios passed", result.stdout)


if __name__ == "__main__":
    unittest.main()
