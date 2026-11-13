"""Offline regressions for the read-only Workpeg Function acceptance action."""
import base64
import importlib.util
import inspect
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

from domain.workpeg_adapter import table_contracts
from domain.workpeg_function_tables import WorkpegFunctionTables


ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "function" / "app" / "main.py"
DOCKERFILE = ROOT / "function" / "Dockerfile"
BUSINESS = "00000000-0000-4000-8000-000000000099"
ACTOR = "owner@example.test"
PRIVATE_MARKER = "fictional-token-value-do-not-return"


def load_module():
    spec = importlib.util.spec_from_file_location("roomay_readonly_function", ENTRY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def function_context(*, peg="roomay", business=BUSINESS, staff=ACTOR,
                     phase="post_save_hook"):
    claims = base64.urlsafe_b64encode(
        json.dumps({"peg_namespace": peg}).encode("ascii")
    ).decode("ascii").rstrip("=")
    return {
        "business": business,
        "token": "header." + claims + ".signature",
        "staff": {"email": staff},
        "phase": phase,
    }


def canonical_inventory():
    groups = {"roomay_hotel_v1": [], "roomay_requests_v1": []}
    for index, contract in enumerate(table_contracts(), start=1):
        table = dict(contract)
        table["uuid"] = f"00000000-0000-4000-8000-{index:012d}"
        groups[contract["namespace"]].append(table)
    return groups


class FakeTransport:
    def __init__(self, *, status=200, inventory=None, error=None):
        self.statuses = list(status) if isinstance(status, (tuple, list)) else [status, status]
        self.inventory = inventory if inventory is not None else canonical_inventory()
        self.error = error
        self.calls = []

    def request(self, method, url, headers, body, timeout):
        self.calls.append((method, url, headers, body, timeout))
        if self.error:
            raise self.error
        status = self.statuses.pop(0) if self.statuses else 200
        namespace = parse_qs(urlsplit(url).query).get("namespace", [None])[0]
        return status, self.inventory.get(namespace) if status == 200 else None


class FunctionReadOnlyAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.module = load_module()

    def invoke(self, *, context=None, payload=None, transport=None):
        transport = transport or FakeTransport()

        def factory(platform_context, *, expected_business_id):
            return WorkpegFunctionTables(
                platform_context,
                expected_business_id=expected_business_id,
                transport=transport,
            )

        with patch.object(self.module, "WorkpegFunctionTables", factory):
            result = self.module.main(
                function_context() if context is None else context,
                {} if payload is None else payload,
            )
        return result, transport

    def test_documented_signature_and_sanitized_success(self):
        self.assertEqual(tuple(inspect.signature(self.module.main).parameters),
                         ("context", "payload"))
        result, transport = self.invoke()
        self.assertEqual(result, {
            "authorization": "authorized",
            "inventory": "complete",
            "peg_scope": "match",
            "business_scope": "match",
            "actor_presence": "verified",
        })
        self.assertEqual([call[0] for call in transport.calls], ["GET", "GET"])
        self.assertEqual([parse_qs(urlsplit(call[1]).query)["namespace"][0]
                          for call in transport.calls],
                         ["roomay_hotel_v1", "roomay_requests_v1"])
        self.assertTrue(all(call[3] is None for call in transport.calls))
        self.assertNotIn(ACTOR, json.dumps(result))
        self.assertNotIn(BUSINESS, json.dumps(result))
        self.assertNotIn(PRIVATE_MARKER, json.dumps(result))

    def test_payload_cannot_substitute_identity_business_or_token(self):
        transport = FakeTransport()
        with self.assertRaisesRegex(ValueError, "^invalid_workpeg_function_envelope$"):
            self.invoke(payload={"staff": {"email": ACTOR}, "business": BUSINESS,
                                 "token": PRIVATE_MARKER}, transport=transport)
        self.assertEqual(transport.calls, [])

    def test_wrong_peg_and_invalid_business_fail_before_reads(self):
        for context, field in (
            (function_context(peg="other-peg"), "peg_scope"),
            (function_context(business="not-a-uuid"), "business_scope"),
        ):
            with self.subTest(field=field):
                result, transport = self.invoke(context=context)
                self.assertEqual(result["authorization"], "denied")
                self.assertEqual(result[field], "mismatch")
                self.assertEqual(transport.calls, [])

    def test_missing_actor_and_non_action_phase_fail_closed(self):
        result, transport = self.invoke(context=function_context(staff=""))
        self.assertEqual(result["actor_presence"], "unverified")
        self.assertEqual(transport.calls, [])
        for phase in ("pre_save_hook", None):
            with self.subTest(phase=phase):
                with self.assertRaisesRegex(
                        RuntimeError, "^roomay_readonly_action_context_invalid$"):
                    self.module.main(function_context(phase=phase), {})

    def test_401_403_404_and_transport_failures_never_claim_authorization(self):
        for status in (401, 403, 404):
            with self.subTest(status=status):
                result, transport = self.invoke(transport=FakeTransport(status=status))
                self.assertNotEqual(result["authorization"], "authorized")
                self.assertEqual(result["inventory"], "incomplete")
                self.assertNotIn(str(status), json.dumps(result))
                self.assertEqual(len(transport.calls), 1)
        result, _transport = self.invoke(
            transport=FakeTransport(error=RuntimeError(PRIVATE_MARKER)))
        self.assertNotEqual(result["authorization"], "authorized")
        self.assertNotIn(PRIVATE_MARKER, json.dumps(result))

    def test_unexpected_validation_exception_is_sanitized_after_reads(self):
        transport = FakeTransport()
        def factory(context, *, expected_business_id):
            return WorkpegFunctionTables(
                context, expected_business_id=expected_business_id,
                transport=transport)

        with patch.object(self.module, "WorkpegFunctionTables", factory):
            with patch.object(self.module, "resolve_tables_for_write",
                              side_effect=RuntimeError(PRIVATE_MARKER)):
                result = self.module.main(function_context(), {})
        self.assertEqual(result, {
            "authorization": "authorized", "inventory": "incomplete",
            "peg_scope": "match", "business_scope": "match",
            "actor_presence": "verified",
        })
        self.assertNotIn(PRIVATE_MARKER, json.dumps(result))

    def test_missing_duplicate_and_malformed_metadata_are_incomplete(self):
        scenarios = []
        missing = canonical_inventory()
        missing["roomay_hotel_v1"].pop()
        scenarios.append(missing)
        duplicate = canonical_inventory()
        duplicate["roomay_hotel_v1"].append(duplicate["roomay_hotel_v1"][0])
        scenarios.append(duplicate)
        malformed = canonical_inventory()
        malformed["roomay_requests_v1"][0]["columns"] = None
        scenarios.append(malformed)
        for value in scenarios:
            with self.subTest(hotel_tables=len(value["roomay_hotel_v1"])):
                result, transport = self.invoke(
                    transport=FakeTransport(inventory=value))
                self.assertEqual(result, {
                    "authorization": "authorized",
                    "inventory": "incomplete",
                    "peg_scope": "match",
                    "business_scope": "match",
                    "actor_presence": "verified",
                })
                self.assertEqual(len(transport.calls), 2)

    def test_no_row_reads_or_mutations_are_possible_in_this_path(self):
        result, transport = self.invoke()
        self.assertEqual(result["authorization"], "authorized")
        self.assertEqual(len(transport.calls), 2)
        self.assertTrue(all(method == "GET" and body is None
                            for method, _url, _headers, body, _timeout in transport.calls))

    def test_function_image_packages_checked_canonical_domain_subset(self):
        dockerfile = DOCKERFILE.read_text(encoding="utf-8")
        self.assertIn(
            "FROM registry.gitlab.com/workpeg/workpeg-sdk/pegfn-base:0.157.0",
            dockerfile,
        )
        self.assertIn("COPY app /app/app", dockerfile)
        self.assertIn("COPY domain /app/domain", dockerfile)
        self.assertIsNone(re.search(r"(?im)^\s*(RUN|ENTRYPOINT|USER|EXPOSE|ADD)\s", dockerfile))
        self.assertNotIn("pip install", "\n".join(
            line for line in dockerfile.splitlines()
            if not line.lstrip().startswith("#")
        ))
        from tools.sync_function_domain import main as check_mirror
        self.assertEqual(check_mirror(["--check"]), 0)

    def test_entrypoint_imports_with_function_directory_as_only_project_root(self):
        result = subprocess.run(
            [sys.executable, "-c", "from app.main import main; assert callable(main)"],
            cwd=ROOT / "function",
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_production_manifest_stays_ui_only(self):
        manifest = json.loads((ROOT / "workpeg.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest, {"namespace": "roomay"})
        self.assertEqual((ROOT / "function" / "requirements.txt").read_text(
            encoding="utf-8"), "")


if __name__ == "__main__":
    unittest.main()
