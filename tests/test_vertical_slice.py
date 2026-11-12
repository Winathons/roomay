"""Offline WOR-60 contract tests; all Workpeg rows are fictional envelopes."""
from copy import deepcopy
import unittest
from datetime import timedelta, timezone
from unittest.mock import patch

from domain.fixtures import uid
from domain.schema_migration import ordered_contracts
from domain.vertical_slice import (
    ROOM_TYPE_CAPACITY, ROOM_TYPE_NAME, WRITE_ORDER, VerticalSliceRejected,
    prepare_vertical_slice,
)
from domain.workpeg_adapter import normalize_snapshot


BUSINESS = uid("wor60-test-business")
TYPE_ID = uid("wor60-existing-room-type")
DATE = "2030-02-03"
NOW = "2030-02-03T12:00:00+01:00"
ZONE = "Africa/Lagos"
ZONE_STUB = timezone(timedelta(hours=1), name="synthetic Africa/Lagos")


def schema_inventory():
    result = {"roomay_hotel_v1": [], "roomay_requests_v1": []}
    for index, contract in enumerate(ordered_contracts(), 1):
        table = deepcopy(contract)
        table.pop("alias", None)
        table["uuid"] = "00000000-0000-4000-8000-" + str(index).zfill(12)
        for column in table["columns"]:
            column.setdefault("options", {})
            column.setdefault("metadata", {})
        result[table["namespace"]].append(table)
    return result


def rows_inventory():
    result = {contract["name"]: [] for contract in ordered_contracts()}
    result["room_types"] = [{
        "id": 1, "fingerprint": "type-fingerprint-1",
        "data": {"business_id": BUSINESS, "entity_id": TYPE_ID,
                 "name": ROOM_TYPE_NAME, "capacity": ROOM_TYPE_CAPACITY},
    }]
    return result


def add_expected_prefix(rows, plan, count):
    values = deepcopy(rows)
    next_row_id = 2
    for key in WRITE_ORDER[:count]:
        table_name = {
            "service_requests": "Roomay Service Requests",
            "service_request_audit": "Roomay Service Request Audit",
        }.get(key, key)
        record = deepcopy(plan["records"][key][0])
        data = {"business_id": BUSINESS, **record}
        values[table_name].append({
            "id": next_row_id, "fingerprint": "row-fingerprint-" + str(next_row_id),
            "data": data,
        })
        next_row_id += 1
    return values


def prepare(rows=None, **overrides):
    with patch("domain.vertical_slice.ZoneInfo", return_value=ZONE_STUB):
        return prepare_vertical_slice(
            BUSINESS, schema_inventory(), rows if rows is not None else rows_inventory(),
            operational_date=overrides.get("operational_date", DATE),
            hotel_timezone=overrides.get("hotel_timezone", ZONE),
            authoritative_now=overrides.get("authoritative_now", NOW),
        )


class VerticalSliceTests(unittest.TestCase):
    def test_preview_is_complete_deterministic_unpersisted_and_preserves_type(self):
        rows = rows_inventory()
        before = deepcopy(rows)
        first = prepare(rows)
        second = prepare(rows)
        self.assertEqual(rows, before)
        self.assertEqual(first, second)
        self.assertFalse(first["persisted"])
        self.assertEqual(first["next_step"], "rooms")
        self.assertEqual(first["room_type_entity_id"], TYPE_ID)
        self.assertEqual(first["records"]["rooms"][0]["number"], "205")
        self.assertEqual(first["records"]["rooms"][0]["room_type_id"], TYPE_ID)
        self.assertEqual(first["records"]["guests"][0]["display_name"],
                         "WOR-60 Fictional Guest (Synthetic)")
        self.assertEqual(first["records"]["reservations"][0]["status"], "confirmed")
        self.assertEqual(first["records"]["stays"][0]["status"], "checked_in")
        self.assertEqual(first["records"]["service_requests"][0]["category"], "extra_towels")
        self.assertEqual(first["records"]["service_requests"][0]["department"], "housekeeping")
        self.assertEqual(first["records"]["service_requests"][0]["status"], "received")
        self.assertEqual(first["records"]["service_request_audit"][0]["request_id"],
                         first["request_id"])
        self.assertEqual(first["dates"]["arrival"], DATE)
        self.assertEqual(first["dates"]["departure"], "2030-02-05")

    def test_each_partial_prefix_resumes_one_next_row_and_only_after_stay_for_request(self):
        base = rows_inventory()
        target = prepare(base)
        expected_steps = list(WRITE_ORDER) + ["complete"]
        for count, expected in enumerate(expected_steps):
            current = add_expected_prefix(base, target, count)
            with self.subTest(count=count):
                self.assertEqual(prepare(current)["next_step"], expected)
                self.assertFalse(prepare(current)["persisted"])

    def test_complete_fixture_passes_the_existing_read_adapter(self):
        base = rows_inventory()
        target = prepare(base)
        complete = add_expected_prefix(base, target, len(WRITE_ORDER))
        normalized = normalize_snapshot(BUSINESS, {
            "room_types": complete["room_types"], "rooms": complete["rooms"],
            "guests": complete["guests"], "reservations": complete["reservations"],
            "stays": complete["stays"], "stay_guests": complete["stay_guests"],
            "room_blocks": complete["room_blocks"],
            "service_requests": complete["Roomay Service Requests"],
            "service_request_audit": complete["Roomay Service Request Audit"],
        })
        self.assertEqual(len(normalized["hotel"]["stays"]), 1)
        self.assertEqual(normalized["hotel"]["rooms"][0]["number"], "205")
        self.assertEqual(normalized["service_requests"][0]["department"], "housekeeping")
        self.assertEqual(normalized["service_requests"][0]["status"], "received")
        self.assertEqual(len(normalized["service_request_audit"]), 1)

    def test_wrong_business_malformed_rows_and_invalid_native_reference_fail_closed(self):
        rows = rows_inventory()
        rows["room_types"][0]["data"]["business_id"] = uid("different-business")
        with self.assertRaises(VerticalSliceRejected):
            prepare(rows)
        rows = rows_inventory()
        rows["rooms"].append({"id": 0, "fingerprint": "", "data": {}})
        with self.assertRaises(VerticalSliceRejected):
            prepare(rows)

    def test_duplicate_or_incompatible_preserved_room_type_is_never_repaired(self):
        rows = rows_inventory()
        rows["room_types"].append(deepcopy(rows["room_types"][0]))
        with self.assertRaises(VerticalSliceRejected):
            prepare(rows)
        rows = rows_inventory()
        rows["room_types"][0]["data"]["capacity"] = 2
        with self.assertRaises(VerticalSliceRejected):
            prepare(rows)

    def test_unexpected_existing_data_duplicate_ids_and_out_of_order_partial_block(self):
        rows = rows_inventory()
        rows["guests"].append({
            "id": 2, "fingerprint": "foreign", "data": {
                "business_id": BUSINESS, "entity_id": uid("other-guest"),
                "display_name": "Unrelated test record",
            },
        })
        with self.assertRaises(VerticalSliceRejected):
            prepare(rows)

        rows = rows_inventory()
        target = prepare(rows)
        out_of_order = rows_inventory()
        out_of_order["guests"].append({
            "id": 3, "fingerprint": "guest-before-room", "data": {
                "business_id": BUSINESS, **target["records"]["guests"][0],
            },
        })
        with self.assertRaises(VerticalSliceRejected):
            prepare(out_of_order)

    def test_date_timezone_boundaries_and_bad_clock_fail_closed(self):
        # UTC late evening is already the next day in Africa/Lagos.
        with self.assertRaisesRegex(VerticalSliceRejected,
                                   "operational_date_does_not_match_hotel_local_now"):
            prepare(operational_date="2030-02-02",
                    authoritative_now="2030-02-02T23:30:00+00:00")
        valid = prepare(operational_date="2030-02-03",
                        authoritative_now="2030-02-02T23:30:00+00:00")
        self.assertEqual(valid["dates"]["arrival"], "2030-02-03")
        for values in [
            {"operational_date": "2030-02-30"},
            {"authoritative_now": "2030-02-03T12:00:00"},
            {"hotel_timezone": ""},
        ]:
            with self.subTest(values=values), self.assertRaises(VerticalSliceRejected):
                prepare(**values)
        with self.assertRaisesRegex(VerticalSliceRejected, "iana_hotel_timezone_unavailable"):
            prepare_vertical_slice(BUSINESS, schema_inventory(), rows_inventory(),
                                   operational_date=DATE, hotel_timezone="Not/A_Zone",
                                   authoritative_now=NOW)

    def test_service_request_is_blocked_without_complete_persisted_stay(self):
        base = rows_inventory()
        target = prepare(base)
        for prefix in range(5):
            with self.subTest(prefix=prefix), self.assertRaises(VerticalSliceRejected):
                # Inject service row early, leaving the stay/occupant sequence incomplete.
                early = add_expected_prefix(base, target, prefix)
                early["Roomay Service Requests"].append({
                    "id": 100, "fingerprint": "early", "data": {
                        "business_id": BUSINESS, **target["records"]["service_requests"][0],
                    },
                })
                prepare(early)

    def test_partial_request_audit_and_final_adapter_consistency(self):
        base = rows_inventory()
        target = prepare(base)
        request_only = add_expected_prefix(base, target, 6)
        self.assertEqual(prepare(request_only)["next_step"], "service_request_audit")
        complete = add_expected_prefix(base, target, 7)
        self.assertTrue(prepare(complete)["complete"])
        request = target["records"]["service_requests"][0]
        audit = target["records"]["service_request_audit"][0]
        self.assertEqual(request["last_event_id"], audit["event_id"])
        self.assertEqual(audit["commit_state"], "pending")


if __name__ == "__main__":
    unittest.main()
