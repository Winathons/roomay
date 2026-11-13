import base64
import json
import unittest
from copy import deepcopy
from urllib.parse import parse_qs, urlparse
from uuid import NAMESPACE_URL, uuid5

from domain.workpeg_adapter import (
    AdapterError,
    FunctionPegScopeAttestation,
    contract_by_key,
    resolve_tables_for_function_scope,
    resolve_tables_for_write,
    table_contracts,
)
from domain.workpeg_function_tables import (
    FunctionTablesError,
    WorkpegFunctionTables,
)
from domain.workpeg_writer import NativeRequestWriter, NativeWriterError


BUSINESS = "00000000-0000-4000-8000-000000000029"
OTHER_BUSINESS = "00000000-0000-4000-8000-000000000099"
PEG_UUID = "4d1ffcbb-f00f-4273-acec-b6463d065881"
ACTOR = "reception-owner@example.invalid"


def uid(label):
    return str(uuid5(NAMESPACE_URL, "roomay-function-scope:" + label))


def token(namespace="roomay"):
    def part(value):
        raw = json.dumps(value, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    return part({"alg": "none"}) + "." + part({"peg_namespace": namespace}) + ".signature"


def table_inventory():
    grouped = {"roomay_hotel_v1": [], "roomay_requests_v1": []}
    for item in table_contracts():
        value = deepcopy(item)
        value["uuid"] = uid("table:" + item["name"])
        value["peg"] = PEG_UUID
        grouped[item["namespace"]].append(value)
    return grouped


class FakeTransport:
    def __init__(self, *, tables=None, status=200, body=None):
        self.tables = deepcopy(tables if tables is not None else table_inventory())
        self.status = status
        self.body = body
        self.calls = []

    def request(self, method, url, headers, body, timeout):
        self.calls.append((method, url, headers, body, timeout))
        if self.status != 200:
            return self.status, self.body
        parsed = urlparse(url)
        if parsed.path.endswith("/tables/"):
            namespace = parse_qs(parsed.query).get("namespace", [None])[0]
            return 200, deepcopy(self.tables[namespace])
        return 200, []


def function_context(*, business=BUSINESS, peg="roomay", staff=ACTOR):
    return {
        "business": business,
        "token": token(peg),
        "staff": {"email": staff},
    }


class FunctionPegScopeTests(unittest.TestCase):
    def client_and_inventory(self, *, context=None, transport=None):
        transport = transport or FakeTransport()
        client = WorkpegFunctionTables(
            context or function_context(), expected_business_id=BUSINESS,
            transport=transport)
        grouped = {
            namespace: client.get_tables(namespace)
            for namespace in ("roomay_hotel_v1", "roomay_requests_v1")
        }
        return client, grouped, transport

    def test_function_token_scope_attests_all_contract_tables_without_uuid_lookup(self):
        client, grouped, transport = self.client_and_inventory()
        attestation = client.attest_inventory(
            grouped, business_id=BUSINESS, actor_id=ACTOR)
        resolved = resolve_tables_for_write(
            grouped, None, scope_attestation=attestation,
            business_id=BUSINESS, actor_id=ACTOR)
        self.assertEqual(len(resolved), 9)
        self.assertEqual(len(transport.calls), 2)
        for method, url, headers, _body, _timeout in transport.calls:
            self.assertEqual(method, "GET")
            self.assertIn("/v1/businesses/" + BUSINESS + "/tables/", url)
            self.assertIn("Authorization", headers)
            self.assertNotIn("Peg-Namespace", headers)
            self.assertNotIn("peg", parse_qs(urlparse(url).query))

    def test_native_writer_accepts_only_function_adapter_for_scoped_ownership(self):
        client, _grouped, _transport = self.client_and_inventory()
        writer = object.__new__(NativeRequestWriter)
        writer.tables = client
        self.assertEqual(len(writer._tables(None, BUSINESS, ACTOR)), 9)

        class UnscopedPort:
            def get_tables(self, namespace):
                return table_inventory()[namespace]

        writer.tables = UnscopedPort()
        with self.assertRaisesRegex(NativeWriterError, "registered_peg_unverified"):
            writer._tables(None, BUSINESS, ACTOR)

    def test_explicit_uuid_validation_remains_available(self):
        resolved = resolve_tables_for_write(table_inventory(), PEG_UUID)
        self.assertEqual(len(resolved), 9)

    def test_wrong_function_peg_is_rejected_before_table_reads(self):
        transport = FakeTransport()
        with self.assertRaisesRegex(FunctionTablesError, "function_peg_scope_mismatch"):
            WorkpegFunctionTables(
                function_context(peg="other-peg"), expected_business_id=BUSINESS,
                transport=transport)
        self.assertEqual(transport.calls, [])

    def test_wrong_business_context_is_rejected_before_table_reads(self):
        transport = FakeTransport()
        with self.assertRaisesRegex(FunctionTablesError, "function_business_scope_mismatch"):
            WorkpegFunctionTables(
                function_context(business=OTHER_BUSINESS), expected_business_id=BUSINESS,
                transport=transport)
        self.assertEqual(transport.calls, [])

    def test_browser_header_or_untrusted_scope_cannot_replace_function_token(self):
        with self.assertRaisesRegex(FunctionTablesError, "function_token_missing"):
            WorkpegFunctionTables(
                {"business": BUSINESS, "staff": {"email": ACTOR},
                 "Peg-Namespace": "roomay"}, expected_business_id=BUSINESS,
                transport=FakeTransport())
        grouped = table_inventory()
        with self.assertRaisesRegex(AdapterError, "peg_scope_untrusted"):
            resolve_tables_for_function_scope(
                grouped, {"business_id": BUSINESS, "peg_namespace": "roomay"},
                business_id=BUSINESS, actor_id=ACTOR)

    def test_caller_constructed_scope_claim_is_not_an_adapter_attestation(self):
        grouped = table_inventory()
        forged = FunctionPegScopeAttestation(
            business_id=BUSINESS,
            peg_namespace="roomay",
            actor_id=ACTOR,
            inventory_fingerprint="0" * 64,
            _issuer=object(),
        )
        with self.assertRaisesRegex(AdapterError, "peg_scope_untrusted"):
            resolve_tables_for_function_scope(
                grouped, forged, business_id=BUSINESS, actor_id=ACTOR)

    def test_scope_cannot_be_replayed_for_other_business_actor_or_inventory(self):
        client, grouped, _ = self.client_and_inventory()
        attestation = client.attest_inventory(
            grouped, business_id=BUSINESS, actor_id=ACTOR)
        for business, actor, inventory in (
            (OTHER_BUSINESS, ACTOR, grouped),
            (BUSINESS, "unauthorized@example.invalid", grouped),
            (BUSINESS, ACTOR, {"roomay_hotel_v1": [], "roomay_requests_v1": []}),
        ):
            with self.subTest(business=business, actor=actor):
                with self.assertRaises(AdapterError):
                    resolve_tables_for_function_scope(
                        inventory, attestation,
                        business_id=business, actor_id=actor)

    def test_missing_contract_metadata_is_rejected_in_scoped_mode(self):
        transport = FakeTransport()
        transport.tables["roomay_hotel_v1"][0]["metadata"] = {}
        client, grouped, _ = self.client_and_inventory(transport=transport)
        attestation = client.attest_inventory(
            grouped, business_id=BUSINESS, actor_id=ACTOR)
        with self.assertRaisesRegex(AdapterError, "schema_table_metadata_mismatch"):
            resolve_tables_for_write(
                grouped, None, scope_attestation=attestation,
                business_id=BUSINESS, actor_id=ACTOR)

    def test_workpeg_permission_denial_is_fail_closed_and_sanitized(self):
        transport = FakeTransport(status=403, body={"detail": "private provider text"})
        client = WorkpegFunctionTables(
            function_context(), expected_business_id=BUSINESS, transport=transport)
        with self.assertRaises(FunctionTablesError) as raised:
            client.get_tables("roomay_hotel_v1")
        self.assertEqual(raised.exception.code, "workpeg_actor_or_business_forbidden")
        self.assertNotIn("private provider text", str(raised.exception))

    def test_missing_function_identity_and_malformed_token_fail_closed(self):
        for context in (
            {"business": BUSINESS, "token": token(), "staff": {}},
            {"business": BUSINESS, "token": "not-a-token", "staff": {"email": ACTOR}},
        ):
            with self.subTest(context_keys=tuple(context)):
                with self.assertRaises(FunctionTablesError):
                    WorkpegFunctionTables(context, expected_business_id=BUSINESS,
                                          transport=FakeTransport())


if __name__ == "__main__":
    unittest.main()
