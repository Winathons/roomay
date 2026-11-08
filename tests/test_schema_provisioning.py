"""Offline provisioning contracts with mocked Workpeg responses only."""
import unittest
from copy import deepcopy
from uuid import NAMESPACE_URL, uuid5

from domain.schema_provisioning import (
    ProvisioningError, classify_test_record, first_fictional_room_records,
    prepare_first_room_types_creation, prepare_provisioning_plan,
    verify_created_table,
)
from domain.workpeg_adapter import contract_by_key


BUSINESS = "00000000-0000-4000-8000-000000000029"
OTHER_BUSINESS = "00000000-0000-4000-8000-000000000099"


def uid(label):
    return str(uuid5(NAMESPACE_URL, "roomay-wor29-plan-test:" + label))


def table_response(key):
    contract = contract_by_key()[key]
    return {
        "uuid": uid("table:" + key),
        "name": contract["name"],
        "namespace": contract["namespace"],
        "permission": "700",
        "metadata": deepcopy(contract.get("metadata", {})),
        "columns": deepcopy(contract["columns"]),
    }


def complete_inventory():
    result = {"roomay_hotel_v1": [], "roomay_requests_v1": []}
    for key, contract in contract_by_key().items():
        result[contract["namespace"]].append(table_response(key))
    return result


def context(**overrides):
    values = {
        "target_business_id": BUSINESS,
        "active_business_id": BUSINESS,
        "peg_namespace": "roomay",
    }
    values.update(overrides)
    return values


class MockWorkpeg:
    """Test-only fake for explicit owner-run create/read sequences."""
    def __init__(self, inventory=None, fail_at=None, timeout_after_apply=False):
        self.inventory = deepcopy(inventory or {
            "roomay_hotel_v1": [], "roomay_requests_v1": []
        })
        self.calls = []
        self.fail_at = fail_at
        self.timeout_after_apply = timeout_after_apply

    def create_table(self, table_key):
        self.calls.append(table_key)
        if self.fail_at == table_key:
            raise RuntimeError("synthetic failed table write")
        response = table_response(table_key)
        self.inventory[response["namespace"]].append(response)
        if self.timeout_after_apply:
            raise TimeoutError("synthetic timeout after apply")
        return deepcopy(response)


class ProvisioningPlanTests(unittest.TestCase):
    def test_first_table_plan_proposes_only_room_types_and_never_authorizes_write(self):
        inventory = {"roomay_hotel_v1": [], "roomay_requests_v1": []}
        result = prepare_first_room_types_creation(
            **context(), tables_by_namespace=inventory)
        self.assertEqual(result["state"], "ready_for_owner_review")
        self.assertEqual(result["payload"], contract_by_key()["room_types"])
        self.assertEqual(result["payload"]["name"], "room_types")
        self.assertEqual(result["payload"]["namespace"], "roomay_hotel_v1")
        self.assertFalse(result["writes_authorized"])

    def test_first_table_plan_blocks_incomplete_context_and_duplicate_schema(self):
        with self.assertRaises(ProvisioningError):
            prepare_first_room_types_creation(
                **context(peg_namespace="wrong"),
                tables_by_namespace={"roomay_hotel_v1": [], "roomay_requests_v1": []})
        inventory = {"roomay_hotel_v1": [table_response("room_types"),
                                         table_response("room_types")],
                     "roomay_requests_v1": []}
        result = prepare_first_room_types_creation(
            **context(), tables_by_namespace=inventory)
        self.assertEqual(result["state"], "blocked")
        self.assertIsNone(result["payload"])
        self.assertFalse(result["writes_authorized"])

    def test_first_table_plan_reports_valid_existing_table_without_create(self):
        inventory = complete_inventory()
        result = prepare_first_room_types_creation(
            **context(), tables_by_namespace=inventory)
        self.assertEqual(result["state"], "already_exists")
        self.assertEqual(result["table_uuid"], table_response("room_types")["uuid"])
        self.assertIsNone(result["payload"])
        self.assertFalse(result["writes_authorized"])

    def test_exact_nine_contracts_are_owner_only_and_namespace_scoped(self):
        plan = prepare_provisioning_plan(
            **context(), tables_by_namespace=complete_inventory())
        self.assertEqual(plan["state"], "ready_for_owner_review")
        self.assertEqual(len(plan["existing_table_uuids"]), 9)
        self.assertEqual(plan["create_payloads"], [])
        self.assertFalse(plan["writes_authorized"])
        for item in plan["existing_table_uuids"].values():
            self.assertEqual(len(item), 36)
        for contract in contract_by_key().values():
            self.assertEqual(contract["permission"], "700")

    def test_missing_table_proposes_only_that_creation_and_never_calls_sdk(self):
        inventory = complete_inventory()
        inventory["roomay_hotel_v1"] = [
            table for table in inventory["roomay_hotel_v1"]
            if table["name"] != "rooms"
        ]
        fake = MockWorkpeg(inventory)
        plan = prepare_provisioning_plan(
            **context(), tables_by_namespace=fake.inventory)
        self.assertEqual(plan["missing_table_keys"], ["rooms"])
        self.assertEqual([item["table_key"] for item in plan["create_payloads"]], ["rooms"])
        self.assertEqual(fake.calls, [])

    def test_duplicate_table_blocks_every_proposed_creation(self):
        inventory = {"roomay_hotel_v1": [], "roomay_requests_v1": []}
        inventory["roomay_hotel_v1"] = [table_response("rooms"), table_response("rooms")]
        plan = prepare_provisioning_plan(
            **context(), tables_by_namespace=inventory)
        self.assertEqual(plan["state"], "blocked")
        self.assertIn("duplicate_table:rooms", plan["errors"])
        self.assertEqual(plan["create_payloads"], [])

    def test_wrong_namespace_or_business_stops_before_inventory_use(self):
        with self.assertRaisesRegex(ProvisioningError, "peg_namespace_mismatch"):
            prepare_provisioning_plan(
                **context(peg_namespace="personal-roomay"),
                tables_by_namespace=complete_inventory())
        with self.assertRaisesRegex(ProvisioningError, "business_context_mismatch"):
            prepare_provisioning_plan(
                **context(active_business_id=OTHER_BUSINESS),
                tables_by_namespace=complete_inventory())

    def test_unreadable_or_wrong_namespace_table_list_is_not_absence(self):
        for inventory in [
            {"roomay_hotel_v1": None, "roomay_requests_v1": []},
            {"roomay_hotel_v1": [{"name": "rooms", "namespace": "wrong"}],
             "roomay_requests_v1": []},
        ]:
            with self.subTest(inventory=inventory):
                with self.assertRaises(ProvisioningError):
                    prepare_provisioning_plan(
                        **context(), tables_by_namespace=inventory)

    def test_wrong_permissions_and_every_column_contract_mismatch_block(self):
        mutations = [
            (lambda table: table.update(permission="740"), "unsafe_table_permission"),
            (lambda table: table["columns"].pop(), "schema_column_mismatch"),
            (lambda table: table["columns"][0].update(type="text"), "schema_type_mismatch"),
            (lambda table: table["columns"][0].update(name="wrong"), "schema_name_mismatch"),
            (lambda table: table["columns"][0].update(position=42), "schema_position_mismatch"),
            (lambda table: table["metadata"].update(extra={}), "schema_table_metadata_mismatch"),
        ]
        for mutate, reason in mutations:
            inventory = {"roomay_hotel_v1": [], "roomay_requests_v1": []}
            bad = table_response("rooms")
            mutate(bad)
            inventory["roomay_hotel_v1"] = [bad]
            plan = prepare_provisioning_plan(
                **context(), tables_by_namespace=inventory)
            self.assertEqual(plan["state"], "blocked")
            self.assertTrue(any(reason in error for error in plan["errors"]))
            self.assertEqual(plan["create_payloads"], [])

    def test_choice_and_datetime_metadata_mismatches_block(self):
        for key, column_id, mutate, expected_code in [
            ("rooms", "housekeeping",
             lambda column: column["options"]["choices"].pop(), "schema_options_mismatch"),
            ("reservations", "arrival",
             lambda column: column.update(metadata={"type": "datetime"}),
             "schema_column_metadata_mismatch"),
        ]:
            inventory = {"roomay_hotel_v1": [], "roomay_requests_v1": []}
            bad = table_response(key)
            column = next(item for item in bad["columns"] if item["id"] == column_id)
            mutate(column)
            inventory[contract_by_key()[key]["namespace"]] = [bad]
            plan = prepare_provisioning_plan(
                **context(), tables_by_namespace=inventory)
            self.assertEqual(plan["state"], "blocked")
            self.assertTrue(any(expected_code in error for error in plan["errors"]))

    def test_create_uuid_is_accepted_only_after_matching_direct_and_list_readback(self):
        response = table_response("room_types")
        listed = complete_inventory()
        actual_uuid = verify_created_table(
            "room_types", response,
            direct_readback=deepcopy(response), tables_by_namespace=listed)
        self.assertEqual(actual_uuid, response["uuid"])
        with self.assertRaisesRegex(ProvisioningError, "uuid_mismatch"):
            changed = deepcopy(response)
            changed["uuid"] = uid("different-table")
            verify_created_table(
                "room_types", response, direct_readback=changed,
                tables_by_namespace=listed)

    def test_failed_partial_creation_is_not_rolled_back_or_retried(self):
        fake = MockWorkpeg(fail_at="rooms")
        initial = prepare_provisioning_plan(
            **context(), tables_by_namespace=fake.inventory)
        self.assertGreater(len(initial["create_payloads"]), 1)
        first = initial["create_payloads"][0]["table_key"]
        self.assertEqual(first, "room_types")
        fake.create_table(first)
        with self.assertRaisesRegex(RuntimeError, "synthetic failed"):
            fake.create_table("rooms")
        calls_after_failure = list(fake.calls)
        recovery = prepare_provisioning_plan(
            **context(), tables_by_namespace=fake.inventory)
        self.assertIn("room_types", recovery["existing_table_uuids"])
        self.assertNotIn("room_types", recovery["missing_table_keys"])
        self.assertEqual(fake.calls, calls_after_failure)
        self.assertEqual(len(recovery["create_payloads"]), 8)

    def test_uncertain_create_outcome_stops_even_if_table_appears(self):
        fake = MockWorkpeg(timeout_after_apply=True)
        with self.assertRaises(TimeoutError):
            fake.create_table("room_types")
        response = fake.inventory["roomay_hotel_v1"][0]
        with self.assertRaisesRegex(ProvisioningError, "uncertain_create_outcome"):
            verify_created_table(
                "room_types", None, direct_readback=response,
                tables_by_namespace=fake.inventory)
        self.assertEqual(fake.calls, ["room_types"])

    def test_failed_or_duplicate_readback_never_confirms_creation(self):
        response = table_response("rooms")
        with self.assertRaisesRegex(ProvisioningError, "invalid_direct_readback"):
            verify_created_table("rooms", response, direct_readback=None,
                                 tables_by_namespace=complete_inventory())
        duplicated = complete_inventory()
        duplicated["roomay_hotel_v1"].append(deepcopy(response))
        with self.assertRaisesRegex(ProvisioningError, "not_unique"):
            verify_created_table("rooms", response, direct_readback=response,
                                 tables_by_namespace=duplicated)

    def test_first_fictional_test_rows_are_deterministic_and_not_authorized(self):
        plan = first_fictional_room_records(BUSINESS)
        self.assertFalse(plan["writes_authorized"])
        self.assertEqual(plan, first_fictional_room_records(BUSINESS))
        self.assertEqual(plan["room"]["room_type_id"], plan["room_type"]["entity_id"])
        self.assertEqual(plan["room"]["number"], "WOR29-201")
        self.assertTrue(plan["row_payloads"]["rooms"]["inherit_business_permission"])
        self.assertFalse(plan["row_payloads"]["rooms"]["inherit_individual_permissions"])

    def test_duplicate_test_records_and_collisions_are_refused(self):
        expected = first_fictional_room_records(BUSINESS)["room"]
        row = {"id": 12, "fingerprint": uid("fp"), "data": deepcopy(expected)}
        self.assertEqual(classify_test_record([], expected, unique_field="number"), "absent")
        self.assertEqual(classify_test_record([row], expected, unique_field="number"),
                         "already_present")
        with self.assertRaisesRegex(ProvisioningError, "duplicate_test_record"):
            classify_test_record([row, {**deepcopy(row), "id": 13}], expected,
                                 unique_field="number")
        collision = deepcopy(row)
        collision["data"]["entity_id"] = uid("other-room")
        self.assertEqual(classify_test_record([collision], expected, unique_field="number"),
                         "identity_collision")
        wrong = deepcopy(row)
        wrong["data"]["business_id"] = OTHER_BUSINESS
        with self.assertRaisesRegex(ProvisioningError, "cross_business_test_row"):
            classify_test_record([wrong], expected, unique_field="number")


if __name__ == "__main__":
    unittest.main()
