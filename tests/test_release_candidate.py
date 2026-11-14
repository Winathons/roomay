"""Release gates for the compiled UI-only Roomay artifact (WOR-33).

The release source deliberately retains isolated development modules. Only the
freshly compiled Peg artifact is eligible for customer release; checking Python
imports or a router source file alone is not a sufficient release gate.
"""
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from domain.fixtures import synthetic_hotel


ROOT = Path(__file__).resolve().parents[1]
RELEASE_ROUTES = [
    "/",
    "/b/[business_id]",
    "/b/[business_id]/reception",
    "/b/[business_id]/reception/[workspace]",
    "/b/[business_id]/stay",
]
# Match the actual compiled Workpeg SDK 0.152.0 route declarations. Fail if
# the compiler format changes rather than accepting an uninspected bundle.
ROUTE_DECLARATION = re.compile(r"""\{\s*path\s*:\s*["']([^"']+)["']\s*,\s*app\s*:""")
DIAGNOSTIC_MARKERS = (
    "/demo/reception",
    "/dev-smoke",
    "dev-smoke",  # also rejects alternate prefixes/business URLs
    "/hotel-data",
    "/dev-table-setup",
    "/dev-room-types-rows",
    "/dev-schema-migration",
    "/dev-vertical-slice",
    "DevSmoke",
    "DevTableSetup",
    "DevRoomTypesRows",
    "DevSchemaMigration",
    "DevVerticalSlice",
    "Roomay TEST Room Type (Fictional)",
    "ReceptionDemo",
    "Roomay Dev Smoke",
    "roomay-dev-smoke-v1",
    "roomay_smoke",  # blocks the private diagnostic table namespace
)
MUTATING_TABLE_HELPERS = (
    "CreateTable", "UpdateTable", "DeleteTable",
    "AddRow", "AddRows", "UpdateRow", "DeleteRow",
)


def assert_safe_release_bundle(app_js, index_html, artifact_text):
    """Fail closed on added routes, diagnostics, privileged actions, or secrets.

    Check emitted bytes, not merely Python source. The Workpeg browser runtime
    is allowed to implement helpers internally; this gate examines calls from
    the compiled application itself, plus all emitted text for diagnostic and
    credential markers. This is a build-safety gate, not a live role test.
    """
    routes = ROUTE_DECLARATION.findall(app_js)
    if routes != RELEASE_ROUTES:
        raise AssertionError(
            f"compiled release routes changed: expected {RELEASE_ROUTES!r}, got {routes!r}"
        )
    if ('routeParam("workspace")' not in app_js
            or 'Workpeg.contains(["","housekeeping"],Workpeg.routeParam("workspace"))'
            not in app_js):
        raise AssertionError("staff workspace route does not fail closed to approved views")

    if '<meta name="peg-namespace" content="roomay">' not in index_html:
        raise AssertionError("compiled release Peg namespace missing or changed")

    # Scan the entire emitted text, not just the primary route bundle. A future
    # compiler may split code into chunks or embed it inside index.html.
    for marker in DIAGNOSTIC_MARKERS:
        if marker.casefold() in artifact_text.casefold():
            raise AssertionError(f"development marker in release artifact: {marker}")

    # Detect both dot-property calls and bracket-property calls. Unqualified
    # table helper calls are rejected by their known write-capability names.
    helpers = set(re.findall(r"\bWorkpeg\s*\.\s*wp([A-Z][A-Za-z0-9]*)\s*\(", app_js))
    helpers.update(re.findall(
        r"""\bWorkpeg\s*\[\s*["']wp([A-Z][A-Za-z0-9]*)["']\s*\]\s*\(""",
        app_js,
    ))
    if helpers != {"GetRows", "GetTables"}:
        raise AssertionError(f"compiled Workpeg helper calls changed: {sorted(helpers)!r}")

    for helper in MUTATING_TABLE_HELPERS:
        if re.search(r"\bwp" + helper + r"\s*\(", app_js):
            raise AssertionError(f"compiled release invokes table mutation: {helper}")
    for marker in ("app.main:main", "RunFunctionAction", "run_function"):
        if marker in app_js:
            raise AssertionError(f"function invocation in release application: {marker}")

    for pattern in (
        r"WORKPEG_PK",
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
        r"Bearer\s+eyJ[A-Za-z0-9_-]+\.",
        r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.",
    ):
        if re.search(pattern, artifact_text, re.IGNORECASE):
            raise AssertionError("credential-like content in compiled release")


class ReleaseGuardRegressionTests(unittest.TestCase):
    """Mutation tests ensure the guard itself fails on unsafe compiled input."""

    @staticmethod
    def safe_fixture():
        app = (
            '{path:"/",app:Home},{path:"/b/[business_id]",app:WorkspaceHome}'
            ',{path:"/b/[business_id]/reception",app:HotelData}'
            ',{path:"/b/[business_id]/reception/[workspace]",app:HotelData}'
            ',{path:"/b/[business_id]/stay",app:GuestAccessUnavailable}'
            ';Workpeg.routeParam("workspace");Workpeg.contains(["","housekeeping"],Workpeg.routeParam("workspace"))'
            ';Workpeg.wpGetTables();Workpeg.wpGetRows()'
        )
        index = '<meta name="peg-namespace" content="roomay">'
        return app, index, app + index

    def test_known_good_compiled_shape_is_accepted(self):
        assert_safe_release_bundle(*self.safe_fixture())

    def test_any_extra_route_is_rejected_including_alternate_business_url(self):
        app, index, _ = self.safe_fixture()
        for extra in (
            '{path:"/b/[business_id]/dev-smoke",app:DevSmoke}',
            '{path:"/alternate/b/[business_id]/diagnostics",app:Diagnostics}',
        ):
            with self.subTest(extra=extra), self.assertRaises(AssertionError):
                assert_safe_release_bundle(app + extra, index, app + extra + index)

    def test_unrestricted_workspace_selector_is_rejected(self):
        app, index, artifact = self.safe_fixture()
        unsafe_app = app.replace(
            'Workpeg.contains(["","housekeeping"],Workpeg.routeParam("workspace"))',
            'Workpeg.routeParam("workspace")',
        )
        with self.assertRaisesRegex(AssertionError, "fail closed"):
            assert_safe_release_bundle(unsafe_app, index, unsafe_app + index)

    def test_dev_table_reference_is_rejected_even_outside_app_js(self):
        app, index, artifact = self.safe_fixture()
        with self.assertRaises(AssertionError):
            assert_safe_release_bundle(app, index, artifact + "roomay_smoke")

    def test_all_mutating_helpers_and_bracket_calls_are_rejected(self):
        app, index, artifact = self.safe_fixture()
        for helper in MUTATING_TABLE_HELPERS:
            for snippet in (
                f"Workpeg.wp{helper}()",
                f'Workpeg["wp{helper}"]()',
                f"wp{helper}()",
            ):
                with self.subTest(snippet=snippet), self.assertRaises(AssertionError):
                    assert_safe_release_bundle(app + snippet, index, artifact + snippet)

    def test_token_and_function_markers_are_rejected(self):
        app, index, artifact = self.safe_fixture()
        for marker in ("WORKPEG_PK", "RunFunctionAction", "roomay-dev-smoke-v1"):
            with self.subTest(marker=marker), self.assertRaises(AssertionError):
                assert_safe_release_bundle(app + marker, index, artifact + marker)


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

    def test_compiled_bundle_passes_all_release_safety_gates(self):
        assert_safe_release_bundle(self.app_js, self.index_html, self.artifact_text)

    def test_compiled_artifact_contains_no_synthetic_guest_records(self):
        fixture = synthetic_hotel()
        forbidden_records = [guest["display_name"] for guest in fixture["guests"]]
        forbidden_records.extend(guest["entity_id"] for guest in fixture["guests"])
        forbidden_records.append("Synthetic Test Guest")
        for marker in forbidden_records:
            self.assertNotIn(marker, self.artifact_text)


if __name__ == "__main__":
    unittest.main()
