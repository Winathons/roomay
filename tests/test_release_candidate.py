"""Release gates for the compiled UI-only Roomay artifact."""
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from domain.fixtures import synthetic_hotel


ROOT = Path(__file__).resolve().parents[1]


class UiOnlyReleaseGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.output = tempfile.TemporaryDirectory(dir=ROOT)
        workpeg = shutil.which("workpeg") or str(
            ROOT / ".venv" / "Scripts" / "workpeg.exe"
        )
        build = subprocess.run(
            [workpeg, "ui", "build", str(ROOT / "ui"), "--out", cls.output.name],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
        if build.returncode != 0:
            cls.output.cleanup()
            raise AssertionError(build.stdout + build.stderr)
        output = Path(cls.output.name)
        cls.app_js = (output / "app.js").read_text(encoding="utf-8")
        cls.index_html = (output / "index.html").read_text(encoding="utf-8")
        cls.artifact_text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted(output.iterdir())
            if path.is_file()
        )

    @classmethod
    def tearDownClass(cls):
        cls.output.cleanup()

    def test_manifest_is_ui_only_and_function_source_is_isolated(self):
        manifest = json.loads((ROOT / "workpeg.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest.get("namespace"), "roomay")
        self.assertNotIn("function", manifest)
        self.assertNotIn("runtime", manifest)
        self.assertTrue((ROOT / "function" / "app" / "main.py").is_file())
        self.assertTrue((ROOT / "function" / "Dockerfile").is_file())
        for marker in ("app.main:main", "RunFunctionAction", "run_function"):
            self.assertNotIn(marker, self.app_js)

    def test_compiled_router_exposes_only_release_routes(self):
        routes = re.findall(r'\{path:"([^"]+)",app:', self.app_js)
        self.assertEqual(routes, ["/", "/b/[business_id]/reception"])
        self.assertIn('<meta name="peg-namespace" content="roomay">', self.index_html)
        for marker in (
            "/demo/reception",
            "/dev-smoke",
            "/hotel-data",
            "/dev-table-setup",
            "DevSmoke",
            "DevTableSetup",
            "ReceptionDemo",
            "Roomay Dev Smoke",
            "roomay-dev-smoke-v1",
        ):
            self.assertNotIn(marker, self.app_js)

    def test_compiled_artifact_is_read_only_and_contains_no_fixture_or_secret(self):
        helpers = set(re.findall(r"Workpeg\.wp([A-Z][A-Za-z0-9]*)\(", self.app_js))
        self.assertEqual(helpers, {"GetRows", "GetTables"})

        fixture = synthetic_hotel()
        forbidden_records = [guest["display_name"] for guest in fixture["guests"]]
        forbidden_records.extend(guest["entity_id"] for guest in fixture["guests"])
        forbidden_records.append("Synthetic Test Guest")
        for marker in forbidden_records:
            self.assertNotIn(marker, self.app_js)

        for pattern in (
            r"WORKPEG_PK",
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
            r"Bearer\s+eyJ[A-Za-z0-9_-]+\.",
            r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.",
        ):
            self.assertIsNone(re.search(pattern, self.artifact_text, re.IGNORECASE))


if __name__ == "__main__":
    unittest.main()
