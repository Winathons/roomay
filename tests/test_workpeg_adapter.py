import unittest
from copy import deepcopy
from uuid import NAMESPACE_URL, uuid5

from domain.fixtures import synthetic_hotel
from domain.service_requests import create_request
from domain.workpeg_adapter import (
    AdapterError, PAGE_SIZE, collect_pages, contract_by_key, decode_rows,
    full_row_update, normalize_snapshot, reconcile_write, resolve_tables,
    table_contracts, validate_table_response,
)
from ui.hotel_data import HotelData


BUSINESS_ID = "00000000-0000-4000-8000-000000000029"


def uid(label):
    return str(uuid5(NAMESPACE_URL, "workpeg-adapter-test:" + label))


def remote_table(key):
    contract = contract_by_key()[key]
    return {
        "uuid": uid("table:" + key),
        "name": contract["name"],
        "namespace": contract["namespace"],
        "permission": "700",
        "columns": deepcopy(contract["columns"]),
    }


def remote_row(key, record, number):
    return {
        "id": number,
        "fingerprint": uid("fingerprint:" + key + ":" + str(number)),
        "data": {"business_id": BUSINESS_ID, **deepcopy(record)},
    }


def remote_snapshot():
    hotel = synthetic_hotel()
    rows = {}
    number = 1
    for key, records in hotel.items():
        rows[key] = []
        for record in records:
            rows[key].append(remote_row(key, record, number))
            number += 1
    rows["service_requests"] = []
    rows["service_request_audit"] = []
    return rows


def service_request_plan(hotel):
    hotel_id = uid("hotel")
    guest_id = hotel["stay_guests"][0]["guest_id"]
    stay_id = hotel["stays"][0]["entity_id"]
    room_id = hotel["stays"][0]["room_id"]
    actor = {"actor_id": "guest-test", "hotel_id": hotel_id,
             "kind": "guest", "guest_id": guest_id}
    draft = {
        "hotel_id": hotel_id, "stay_id": stay_id, "room_id": room_id,
        "guest_id": guest_id, "origin": "guest", "category": "extra_towels",
        "description": "Please bring two towels.", "urgency": "normal",
        "idempotency_key": "guest-test:one", "sensitive": False,
    }
    return create_request(
        hotel, draft, actor, [], [], at="2026-11-06T12:00:00+01:00",
        request_id=uid("request"),
    )["plan"]


class ContractTests(unittest.TestCase):
    def test_contracts_are_owner_only_business_bound_and_use_supported_types(self):
        allowed = {"text", "number", "boolean", "uuid", "datetime", "mutable_select"}
        contracts = table_contracts()
        self.assertEqual(len(contracts), 9)
        for contract in contracts:
            self.assertEqual(contract["permission"], "700")
            self.assertRegex(contract["alias"], r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
            self.assertEqual(contract["columns"][0]["id"], "business_id")
            self.assertTrue({column["type"] for column in contract["columns"]} <= allowed)

    def test_table_resolution_uses_namespace_name_schema_and_uuid(self):
        grouped = {"roomay_hotel_v1": [], "roomay_requests_v1": []}
        for key, contract in contract_by_key().items():
            grouped[contract["namespace"]].append(remote_table(key))
        resolved = resolve_tables(grouped)
        self.assertEqual(set(resolved), set(contract_by_key()))

    def test_missing_duplicate_unsafe_and_malformed_tables_fail_closed(self):
        contract = contract_by_key()["rooms"]
        table = remote_table("rooms")
        bad_tables = [
            {**table, "permission": "770"},
            {**table, "uuid": "not-a-uuid"},
            {**table, "columns": table["columns"][:-1]},
            {**table, "columns": [*table["columns"], deepcopy(table["columns"][0])]},
        ]
        for bad in bad_tables:
            with self.subTest(bad=bad):
                with self.assertRaises(AdapterError):
                    validate_table_response(contract, bad)
        grouped = {"roomay_hotel_v1": [], "roomay_requests_v1": []}
        with self.assertRaisesRegex(AdapterError, "missing_table"):
            resolve_tables(grouped)

    def test_alias_is_not_used_as_a_runtime_identifier(self):
        table = remote_table("rooms")
        self.assertNotIn("alias", table)
        self.assertEqual(validate_table_response(contract_by_key()["rooms"], table),
                         table["uuid"])

    def test_compiled_transport_literals_match_the_pure_contract(self):
        transport = HotelData()
        for key, contract in contract_by_key().items():
            name = contract["name"]
            fields = transport.allowed_fields(name)
            self.assertEqual(fields, [column["id"] for column in contract["columns"]])
            optional = transport.optional_fields(name)
            for column in contract["columns"]:
                self.assertEqual(transport.field_type(column["id"]), column["type"])
                self.assertEqual(column["id"] in optional,
                                 not column.get("required", False))


class PaginationAndRowTests(unittest.TestCase):
    def test_plain_list_pages_are_combined_until_short_page(self):
        first = [{"id": number} for number in range(PAGE_SIZE)]
        last = [{"id": PAGE_SIZE}]
        self.assertEqual(len(collect_pages([first, last])), PAGE_SIZE + 1)
        with self.assertRaisesRegex(AdapterError, "pagination_incomplete"):
            collect_pages([first])
        with self.assertRaisesRegex(AdapterError, "malformed_page"):
            collect_pages([{"results": []}])

    def test_rows_map_native_ids_and_fingerprints_without_leaking_business_id(self):
        room = synthetic_hotel()["rooms"][0]
        records, refs = decode_rows("rooms", BUSINESS_ID, [remote_row("rooms", room, 91)])
        self.assertEqual(records, [room])
        self.assertEqual(refs[0].row_id, 91)
        self.assertEqual(refs[0].entity_id, room["entity_id"])
        self.assertNotIn("business_id", records[0])

    def test_wrong_business_duplicate_and_incomplete_records_fail(self):
        room = synthetic_hotel()["rooms"][0]
        row = remote_row("rooms", room, 1)
        wrong = deepcopy(row)
        wrong["data"]["business_id"] = uid("other-business")
        for rows, code in [
            ([wrong], "cross_business_row"),
            ([row, {**deepcopy(row), "id": 2}], "duplicate_entity_id"),
            ([{**row, "fingerprint": ""}], "missing_fingerprint"),
        ]:
            with self.subTest(code=code):
                with self.assertRaisesRegex(AdapterError, code):
                    decode_rows("rooms", BUSINESS_ID, rows)
        missing = deepcopy(row)
        del missing["data"]["number"]
        with self.assertRaisesRegex(AdapterError, "missing_field:number"):
            decode_rows("rooms", BUSINESS_ID, [missing])

    def test_malformed_and_unexpected_data_fail(self):
        room = synthetic_hotel()["rooms"][0]
        row = remote_row("rooms", room, 1)
        for bad in [None, {}, "bad", [None]]:
            with self.subTest(bad=bad):
                with self.assertRaises(AdapterError):
                    decode_rows("rooms", BUSINESS_ID, bad)
        row["data"]["server_surprise"] = "ignored on writes but unsafe on read"
        with self.assertRaisesRegex(AdapterError, "malformed_row_data"):
            decode_rows("rooms", BUSINESS_ID, [row])


class SnapshotAndWriteContractTests(unittest.TestCase):
    def test_complete_synthetic_snapshot_normalizes_through_domain_rules(self):
        result = normalize_snapshot(BUSINESS_ID, remote_snapshot())
        self.assertFalse(result["empty_inventory"])
        self.assertEqual(len(result["hotel"]["rooms"]), 10)
        self.assertEqual(len(result["references"]), 21)

    def test_empty_inventory_is_explicit_not_fabricated(self):
        rows = {key: [] for key in contract_by_key()}
        result = normalize_snapshot(BUSINESS_ID, rows)
        self.assertTrue(result["empty_inventory"])
        self.assertEqual(result["hotel"]["rooms"], [])

    def test_invalid_cross_table_snapshot_is_rejected(self):
        rows = remote_snapshot()
        rows["rooms"][0]["data"]["room_type_id"] = uid("missing-room-type")
        with self.assertRaisesRegex(AdapterError, "invalid_hotel_snapshot"):
            normalize_snapshot(BUSINESS_ID, rows)

    def test_service_request_and_audit_are_bound_to_hotel_stay(self):
        rows = remote_snapshot()
        plan = service_request_plan(synthetic_hotel())
        rows["service_requests"] = [remote_row(
            "service_requests", plan["target_request"], 90)]
        rows["service_request_audit"] = [remote_row(
            "service_request_audit", plan["event"], 91)]
        result = normalize_snapshot(BUSINESS_ID, rows)
        self.assertEqual(result["service_requests"][0]["room_id"],
                         synthetic_hotel()["stays"][0]["room_id"])
        broken = deepcopy(rows)
        broken["service_requests"][0]["data"]["room_id"] = uid("wrong-room")
        with self.assertRaisesRegex(AdapterError, "invalid_service_request"):
            normalize_snapshot(BUSINESS_ID, broken)

    def test_orphan_audit_event_is_rejected(self):
        rows = remote_snapshot()
        plan = service_request_plan(synthetic_hotel())
        rows["service_request_audit"] = [remote_row(
            "service_request_audit", plan["event"], 91)]
        with self.assertRaisesRegex(AdapterError, "orphan_service_request_audit"):
            normalize_snapshot(BUSINESS_ID, rows)

    def test_full_data_patch_preserves_unrelated_fields_and_identity(self):
        existing = {"data": {"business_id": BUSINESS_ID, "entity_id": uid("room"),
                               "status": "ready", "future_field": {"keep": True}}}
        patch = full_row_update(existing, {"status": "dirty"},
                                immutable=("business_id", "entity_id"))
        self.assertEqual(patch["data"]["future_field"], {"keep": True})
        with self.assertRaisesRegex(AdapterError, "immutable_field_change"):
            full_row_update(existing, {"business_id": uid("other")},
                            immutable=("business_id",))

    def test_failed_write_reconciliation_never_blindly_retries(self):
        before = uid("before")
        expected = {"status": "confirmed"}
        self.assertEqual(reconcile_write(expected, before, {
            "fingerprint": uid("after"), "data": expected}), "confirmed")
        self.assertEqual(reconcile_write(expected, before, {
            "fingerprint": before, "data": {"status": "pending_confirmation"}}),
            "not_applied")
        self.assertEqual(reconcile_write(expected, before, {
            "fingerprint": uid("other"), "data": {"status": "cancelled"}}),
            "conflict_manual_reconciliation")
        self.assertEqual(reconcile_write(expected, before, None),
                         "not_found_manual_reconciliation")


if __name__ == "__main__":
    unittest.main()
