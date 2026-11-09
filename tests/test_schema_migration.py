"""Pure migration-planner tests using fictional Workpeg table metadata."""
from copy import deepcopy
import unittest

from domain.schema_migration import MIGRATION_ORDER, ordered_contracts, plan_migration


def table_response(contract, number):
    item = deepcopy(contract)
    item.pop("alias", None)  # Workpeg aliases are write-only.
    item["uuid"] = "00000000-0000-4000-8000-" + str(number).zfill(12)
    for column in item["columns"]:
        column.setdefault("options", {})
        column.setdefault("metadata", {})
    item["owner"] = {"id": 900}
    return item


def inventory(names=None):
    selected = set(names or ["room_types"])
    hotel = []
    requests = []
    for index, contract in enumerate(ordered_contracts(), start=1):
        if contract["name"] in selected:
            (hotel if contract["namespace"] == "roomay_hotel_v1" else requests).append(
                table_response(contract, index))
    return {"roomay_hotel_v1": hotel, "roomay_requests_v1": requests}


class SchemaMigrationPlannerTests(unittest.TestCase):
    def test_all_nine_canonical_contracts_have_business_column_owner_permission_and_alias(self):
        contracts = ordered_contracts()
        self.assertEqual([item["name"] for item in contracts], list(MIGRATION_ORDER))
        self.assertEqual(len(contracts), 9)
        for contract in contracts:
            self.assertEqual(contract["permission"], "700")
            self.assertTrue(contract["alias"])
            self.assertEqual(contract["columns"][0], {
                "id": "business_id", "name": "business_id", "type": "uuid",
                "required": True, "position": 500,
            })

    def test_existing_room_types_is_preserved_and_only_remaining_eight_are_eligible(self):
        result = plan_migration(inventory(), owner_verified_missing=MIGRATION_ORDER[1:])
        self.assertTrue(result["valid_inventory"])
        self.assertEqual(result["eligible"], list(MIGRATION_ORDER[1:]))
        room_types = result["tables"][0]
        self.assertEqual(room_types["status"], "existing_compatible")
        self.assertEqual(room_types["uuid"], inventory()["roomay_hotel_v1"][0]["uuid"])
        self.assertNotIn("room_types", result["eligible"])

    def test_missing_or_unreadable_needs_individual_owner_attestation(self):
        result = plan_migration(inventory())
        self.assertEqual(result["eligible"], [])
        self.assertEqual(result["tables"][1]["status"], "missing_or_unreadable")
        self.assertEqual(result["tables"][1]["eligible"], False)
        verified = plan_migration(inventory(), owner_verified_missing=["rooms"])
        self.assertEqual(verified["eligible"], ["rooms"])

    def test_room_types_is_never_recreated_and_blocks_migration_if_missing(self):
        empty = {"roomay_hotel_v1": [], "roomay_requests_v1": []}
        result = plan_migration(empty, owner_verified_missing=MIGRATION_ORDER[1:])
        self.assertFalse(result["valid_inventory"])
        self.assertIn("required_room_types_missing_or_unreadable", result["blockers"])
        self.assertEqual(result["tables"][0]["status"], "required_existing_table_missing")
        self.assertEqual(result["eligible"], [])

    def test_duplicate_matching_table_blocks_every_creation(self):
        value = inventory()
        value["roomay_hotel_v1"].append(deepcopy(value["roomay_hotel_v1"][0]))
        result = plan_migration(value, owner_verified_missing=MIGRATION_ORDER[1:])
        self.assertFalse(result["valid_inventory"])
        self.assertEqual(result["tables"][0]["status"], "duplicate")
        self.assertEqual(result["eligible"], [])

    def test_incorrect_permission_columns_metadata_and_unexpected_tables_block(self):
        cases = []
        wrong_permission = inventory(); wrong_permission["roomay_hotel_v1"][0]["permission"] = "740"
        cases.append((wrong_permission, "incorrect_permissions"))
        wrong_columns = inventory(); wrong_columns["roomay_hotel_v1"][0]["columns"].pop()
        cases.append((wrong_columns, "incorrect_columns"))
        wrong_metadata = inventory(); wrong_metadata["roomay_hotel_v1"][0]["metadata"] = {"extra": {"contract": "wrong"}}
        cases.append((wrong_metadata, "incorrect_metadata"))
        unexpected = inventory(); unexpected["roomay_hotel_v1"].append({
            "name": "legacy_table", "namespace": "roomay_hotel_v1",
            "uuid": "00000000-0000-4000-8000-000000000099", "permission": "700", "columns": [],
        })
        cases.append((unexpected, "unexpected_tables_present"))
        for value, blocker in cases:
            with self.subTest(blocker=blocker):
                result = plan_migration(value, owner_verified_missing=MIGRATION_ORDER[1:])
                self.assertFalse(result["valid_inventory"])
                self.assertTrue(any(blocker in issue for issue in result["blockers"]))
                self.assertEqual(result["eligible"], [])

    def test_malformed_or_missing_namespace_responses_are_not_empty_inventory(self):
        for value in [None, {"roomay_hotel_v1": [], "roomay_requests_v1": {"results": []}},
                      {"roomay_hotel_v1": []}]:
            result = plan_migration(value)
            self.assertFalse(result["valid_inventory"])
            self.assertEqual(result["eligible"], [])
            self.assertTrue(all(item["status"] == "inventory_unknown" for item in result["tables"]))

    def test_mutable_select_choices_and_datetime_metadata_remain_canonical(self):
        contracts = {item["name"]: item for item in ordered_contracts()}
        by_id = {column["id"]: column for column in contracts["rooms"]["columns"]}
        self.assertEqual(by_id["housekeeping"]["type"], "mutable_select")
        self.assertEqual([choice["ref"] for choice in by_id["housekeeping"]["options"]["choices"]],
                         ["ready", "dirty", "cleaning", "inspection"])
        reservations = {column["id"]: column for column in contracts["reservations"]["columns"]}
        self.assertEqual(reservations["arrival"]["metadata"], {"type": "date"})
        self.assertEqual(reservations["room_id"]["required"], False)
        requests = {column["id"]: column for column in contracts["Roomay Service Requests"]["columns"]}
        self.assertEqual(requests["status"]["options"]["choices"][-1]["ref"], "escalated")
        audit = {column["id"]: column for column in contracts["Roomay Service Request Audit"]["columns"]}
        self.assertEqual(audit["occurred_at"]["metadata"], {"type": "datetime"})


if __name__ == "__main__":
    unittest.main()
