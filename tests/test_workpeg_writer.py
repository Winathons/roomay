import unittest
from copy import deepcopy
from uuid import NAMESPACE_URL, uuid5

from domain.fixtures import synthetic_hotel
from domain.service_requests import create_request, transition_request
from domain.workpeg_adapter import contract_by_key, table_contracts
from domain.workpeg_writer import NativeRequestWriter


BUSINESS_ID = "00000000-0000-4000-8000-000000000029"
HOTEL_ID = "00000000-0000-4000-8000-000000000030"
PEG_ID = "4d1ffcbb-f00f-4273-acec-b6463d065881"


def uid(label):
    return str(uuid5(NAMESPACE_URL, "roomay-writer-test:" + label))


def initial_plan():
    hotel = synthetic_hotel()
    guest_id = hotel["stay_guests"][0]["guest_id"]
    stay = hotel["stays"][0]
    actor = {"actor_id": "guest-test-actor", "hotel_id": HOTEL_ID,
             "kind": "guest", "guest_id": guest_id}
    draft = {
        "hotel_id": HOTEL_ID, "stay_id": stay["entity_id"],
        "room_id": stay["room_id"], "guest_id": guest_id,
        "origin": "guest", "category": "extra_towels",
        "description": "Please bring two towels.", "urgency": "normal",
        "idempotency_key": "guest-test:acceptance-001", "sensitive": False,
    }
    result = create_request(
        hotel, draft, actor, [], [], at="2026-11-13T12:00:00+01:00",
        request_id=uid("request"),
    )
    return result["plan"]


def remote_table(key, *, peg=PEG_ID):
    contract = contract_by_key()[key]
    return {
        "uuid": uid("table:" + key), "name": contract["name"],
        "namespace": contract["namespace"], "permission": "700", "peg": peg,
        "metadata": deepcopy(contract.get("metadata", {})),
        "columns": deepcopy(contract["columns"]),
    }


def remote_hotel_rows():
    rows = {}
    number = 1
    for key, records in synthetic_hotel().items():
        rows[key] = []
        for record in records:
            rows[key].append({
                "id": number, "fingerprint": uid("fingerprint:" + str(number)),
                "position": number * 1000,
                "data": {"business_id": BUSINESS_ID, **deepcopy(record)},
            })
            number += 1
    rows["service_requests"] = []
    rows["service_request_audit"] = []
    return rows


def trusted_context(**changes):
    context = {
        "authenticated": True,
        "membership_verified": True,
        "business_binding_verified": True,
        "actor_authorized": True,
        "business_id": BUSINESS_ID,
        "hotel_id": HOTEL_ID,
        "actor_id": "guest-test-actor",
        "registered_peg_id": PEG_ID,
        "request_write_verified": True,
        "audit_write_verified": True,
        "serialization_scope_verified": True,
    }
    context.update(changes)
    return context


class ContextResolver:
    def __init__(self, context=None):
        self.context = context or trusted_context()

    def resolve(self, _proof):
        return deepcopy(self.context)


class PlanFactory:
    def __init__(self, plan=None, error=None):
        self.plan = deepcopy(plan if plan is not None else initial_plan())
        self.error = error

    def prepare(self, _proof, _command):
        if self.error:
            raise self.error
        return deepcopy(self.plan)


class Lease:
    def __init__(self, business_id, request_id, *, allowed=True):
        self.value = {
            "active": allowed,
            "covers_all_writers": allowed,
            "covers_business_idempotency": allowed,
            "business_id": business_id,
            "request_id": request_id,
        }

    def __enter__(self):
        return self.value

    def __exit__(self, *_args):
        return False


class SerializationGuard:
    def __init__(self, allowed=True):
        self.allowed = allowed
        self.calls = []

    def acquire(self, business_id, request_id):
        self.calls.append((business_id, request_id))
        return Lease(business_id, request_id, allowed=self.allowed)


class MockTables:
    """Mock only the documented Workpeg helper surface; never makes network calls."""

    def __init__(self, rows=None, *, peg=PEG_ID, timeout_after_add=False):
        self.tables = {"roomay_hotel_v1": [], "roomay_requests_v1": []}
        for key, contract in contract_by_key().items():
            self.tables[contract["namespace"]].append(remote_table(key, peg=peg))
        self.rows = deepcopy(rows or remote_hotel_rows())
        self.calls = []
        self.timeout_after_add = timeout_after_add
        self._next_id = 1000

    def get_tables(self, namespace):
        self.calls.append(("get_tables", namespace))
        return deepcopy(self.tables[namespace])

    def get_rows(self, table_uuid, limit=100, offset=0):
        self.calls.append(("get_rows", table_uuid, limit, offset))
        table = self._table_by_uuid(table_uuid)
        return deepcopy(self.rows[table["name_key"]][offset:offset + limit])

    def add_row(self, table_uuid, payload):
        table = self._table_by_uuid(table_uuid)
        self.calls.append(("add_row", table["name_key"]))
        row = {
            "id": self._next_id,
            "fingerprint": uid("fingerprint:" + str(self._next_id)),
            "position": payload["position"], "data": deepcopy(payload["data"]),
        }
        self._next_id += 1
        self.rows[table["name_key"]].append(row)
        if self.timeout_after_add:
            self.timeout_after_add = False
            raise TimeoutError("simulated ambiguous response")
        return {"ignored": "write response is not verification"}

    def update_row(self, table_uuid, row_id, patch):
        table = self._table_by_uuid(table_uuid)
        self.calls.append(("update_row", table["name_key"], row_id))
        row = next(item for item in self.rows[table["name_key"]]
                   if item["id"] == row_id)
        if "data" in patch:
            row["data"] = deepcopy(patch["data"])
        row["fingerprint"] = uid("updated:" + str(row_id) + ":" + str(len(self.calls)))
        return None

    def _table_by_uuid(self, table_uuid):
        for group in self.tables.values():
            for table in group:
                if table["uuid"] == table_uuid:
                    key = next(key for key, contract in contract_by_key().items()
                               if contract["name"] == table["name"])
                    return {**table, "name_key": key}
        raise AssertionError("unknown mock table UUID")


def writer(*, enabled=True, context=None, plan=None, tables=None,
           serialization_allowed=True, plan_error=None):
    plan = plan if plan is not None else initial_plan()
    command = {"request_id": plan["target_request"]["request_id"]}
    store = tables or MockTables()
    guard = SerializationGuard(serialization_allowed)
    coordinator = NativeRequestWriter(
        enabled=enabled, tables=store,
        context_resolver=ContextResolver(context),
        plan_factory=PlanFactory(plan, plan_error),
        serialization_guard=guard,
    )
    return coordinator, store, guard, command


class WriterSafetyTests(unittest.TestCase):
    def test_disabled_by_default_performs_no_platform_reads_or_writes(self):
        coordinator, store, _guard, command = writer(enabled=False)
        result = coordinator.execute(object(), command)
        self.assertEqual((result["state"], result["reason"], result["persisted"]),
                         ("unavailable", "native_writer_disabled", False))
        self.assertEqual(store.calls, [])

    def test_denied_authorization_wrong_business_and_missing_serialization_fail_closed(self):
        for context, serialization, reason in (
            (trusted_context(actor_authorized=False), True, "trusted_write_gate_unverified"),
            (trusted_context(business_id=uid("wrong-business")), True,
             "cross_business_row"),
            (trusted_context(), False, "global_serialization_unverified"),
        ):
            with self.subTest(reason=reason):
                coordinator, store, _guard, command = writer(
                    context=context, serialization_allowed=serialization)
                result = coordinator.execute(object(), command)
                self.assertEqual(result["reason"], reason)
                self.assertFalse(result["persisted"])
                if reason == "trusted_write_gate_unverified":
                    self.assertEqual(store.calls, [])
                elif reason == "global_serialization_unverified":
                    self.assertFalse(any(call[0] == "get_tables" for call in store.calls))
                else:
                    self.assertFalse(any(call[0] in {"add_row", "update_row"}
                                         for call in store.calls))

    def test_mismatched_or_missing_peg_and_incomplete_inventory_block_writes(self):
        for store, expected in (
            (MockTables(peg=uid("unrelated-peg")), "peg_ownership_mismatch"),
            (MockTables(peg=None), "peg_ownership_type_mismatch"),
        ):
            coordinator, _store, _guard, command = writer(tables=store)
            result = coordinator.execute(object(), command)
            self.assertEqual(result["reason"], expected)
            self.assertFalse(any(call[0] in {"add_row", "update_row"}
                                 for call in store.calls))

        store = MockTables()
        store.tables["roomay_hotel_v1"] = store.tables["roomay_hotel_v1"][:-1]
        coordinator, _store, _guard, command = writer(tables=store)
        result = coordinator.execute(object(), command)
        self.assertTrue(result["reason"].startswith("missing_table"))
        self.assertFalse(any(call[0] in {"add_row", "update_row"}
                             for call in store.calls))

        store = MockTables()
        store.tables["roomay_hotel_v1"][0]["metadata"] = {"extra": {"contract": "wrong"}}
        coordinator, _store, _guard, command = writer(tables=store)
        result = coordinator.execute(object(), command)
        self.assertEqual(result["reason"], "schema_table_metadata_mismatch")
        self.assertFalse(any(call[0] in {"add_row", "update_row"}
                             for call in store.calls))

        store = MockTables()
        store.rows["rooms"] = []
        coordinator, _store, _guard, command = writer(tables=store)
        result = coordinator.execute(object(), command)
        self.assertEqual(result["reason"], "invalid_hotel_snapshot")
        self.assertFalse(any(call[0] in {"add_row", "update_row"}
                             for call in store.calls))

    def test_wrong_plan_hotel_actor_or_version_is_rejected(self):
        bad_plan = initial_plan()
        bad_plan["target_request"]["version"] = 4
        coordinator, store, _guard, command = writer(plan=bad_plan)
        result = coordinator.execute(object(), command)
        self.assertEqual(result["reason"], "canonical_write_version_mismatch")
        self.assertFalse(any(call[0] in {"add_row", "update_row"} for call in store.calls))

        bad_plan = initial_plan()
        bad_plan["event"]["actor_id"] = "forged-actor"
        coordinator, store, _guard, command = writer(plan=bad_plan)
        result = coordinator.execute(object(), command)
        self.assertEqual(result["reason"], "canonical_write_scope_mismatch")
        self.assertFalse(any(call[0] in {"add_row", "update_row"} for call in store.calls))

    def test_failed_plan_factory_is_sanitized_and_no_platform_mutation_occurs(self):
        coordinator, store, _guard, command = writer(plan_error=RuntimeError("secret raw data"))
        result = coordinator.execute(object(), command)
        self.assertEqual(result["reason"], "authorized_plan_unavailable")
        self.assertNotIn("secret", str(result))
        self.assertFalse(any(call[0] in {"add_row", "update_row"} for call in store.calls))


class WriterReconciliationTests(unittest.TestCase):
    def test_new_request_and_audit_are_verified_after_each_sequential_write(self):
        coordinator, store, _guard, command = writer()
        result = coordinator.execute(object(), command)
        self.assertEqual(result["state"], "complete")
        self.assertTrue(result["persisted"])
        self.assertEqual(len(store.rows["service_requests"]), 1)
        self.assertEqual(len(store.rows["service_request_audit"]), 1)
        saved_request = store.rows["service_requests"][0]["data"]
        saved_event = store.rows["service_request_audit"][0]["data"]
        self.assertEqual(saved_request["status"], "received")
        self.assertEqual(saved_event["commit_state"], "committed")
        self.assertEqual(saved_request["last_event_id"], saved_event["event_id"])
        mutations = [call[0] for call in store.calls if call[0] in {"add_row", "update_row"}]
        self.assertEqual(mutations, ["add_row", "add_row", "update_row"])
        # There is a full independent namespace+rows read after each write.
        self.assertGreaterEqual(sum(call[0] == "get_tables" for call in store.calls), 8)

    def test_timeout_after_audit_insert_reconciles_without_automatic_retry(self):
        plan = initial_plan()
        store = MockTables(timeout_after_add=True)
        coordinator, store, _guard, command = writer(plan=plan, tables=store)
        result = coordinator.execute(object(), command)
        self.assertEqual(result["state"], "uncertain")
        self.assertFalse(result["persisted"])
        self.assertEqual(result["next_step"], "apply_request")
        self.assertEqual(len(store.rows["service_request_audit"]), 1)
        self.assertEqual(store.rows["service_requests"], [])
        self.assertEqual(sum(call[0] == "add_row" for call in store.calls), 1)

    def test_unreadable_uncertain_outcome_never_claims_success(self):
        plan = initial_plan()
        store = MockTables(timeout_after_add=True)
        original = store.get_rows

        def fail_reads_after_mutation(table_uuid, limit=100, offset=0):
            if any(call[0] == "add_row" for call in store.calls):
                raise TimeoutError("private provider error")
            return original(table_uuid, limit, offset)

        store.get_rows = fail_reads_after_mutation
        coordinator, store, _guard, command = writer(plan=plan, tables=store)
        result = coordinator.execute(object(), command)
        self.assertEqual(result["state"], "uncertain")
        self.assertFalse(result["persisted"])
        self.assertEqual(result["next_step"], "readback_unavailable_manual_review")
        self.assertNotIn("private", str(result))

    def test_transition_preserves_existing_request_fields_and_commits_audit(self):
        hotel = synthetic_hotel()
        guest_id = hotel["stay_guests"][0]["guest_id"]
        stay = hotel["stays"][0]
        guest = {"actor_id": "guest-test-actor", "hotel_id": HOTEL_ID,
                 "kind": "guest", "guest_id": guest_id}
        created = create_request(
            hotel,
            {"hotel_id": HOTEL_ID, "stay_id": stay["entity_id"],
             "room_id": stay["room_id"], "guest_id": guest_id, "origin": "guest",
             "category": "extra_towels", "description": "Please bring towels.",
             "urgency": "normal", "idempotency_key": "guest-test:existing",
             "sensitive": False},
            guest, [], [], at="2026-11-13T12:00:00+01:00", request_id=uid("existing"),
        )
        request = created["request"]
        created_event = deepcopy(created["plan"]["event"])
        created_event["commit_state"] = "committed"
        staff = [
            {"actor_id": "front-desk", "hotel_id": HOTEL_ID,
             "department": "reception", "roles": [], "active": True},
            {"actor_id": "housekeeper", "hotel_id": HOTEL_ID,
             "department": "housekeeping", "roles": [], "active": True},
        ]
        outcome = transition_request(
            request, "assigned",
            {"actor_id": "front-desk", "hotel_id": HOTEL_ID, "kind": "staff"},
            staff, at="2026-11-13T12:05:00+01:00", operation_key="assign-001",
            assignee_id="housekeeper",
        )
        plan = outcome["plan"]
        context = trusted_context(actor_id="front-desk")
        rows = remote_hotel_rows()
        rows["service_requests"] = [{
            "id": 501, "fingerprint": uid("old-request-fingerprint"), "position": 501000,
            "data": {"business_id": BUSINESS_ID, **request},
        }]
        rows["service_request_audit"] = [{
            "id": 502, "fingerprint": uid("old-event-fingerprint"), "position": 502000,
            "data": {"business_id": BUSINESS_ID, **created_event},
        }]
        coordinator, store, _guard, command = writer(context=context, plan=plan,
                                                      tables=MockTables(rows))
        result = coordinator.execute(object(), command)
        self.assertEqual(result["state"], "complete")
        saved = store.rows["service_requests"][0]["data"]
        self.assertEqual(saved["description"], request["description"])
        self.assertEqual(saved["created_at"], request["created_at"])
        self.assertEqual(saved["status"], "assigned")
        self.assertEqual(store.rows["service_request_audit"][-1]["data"]["commit_state"],
                         "committed")

    def test_verified_duplicate_is_idempotent_and_does_not_write(self):
        plan = initial_plan()
        rows = remote_hotel_rows()
        event = deepcopy(plan["event"])
        event["commit_state"] = "committed"
        rows["service_requests"] = [{
            "id": 100, "fingerprint": uid("duplicate-request-fingerprint"),
            "position": 100000, "data": {"business_id": BUSINESS_ID,
                                             **deepcopy(plan["target_request"])},
        }]
        rows["service_request_audit"] = [{
            "id": 101, "fingerprint": uid("duplicate-event-fingerprint"),
            "position": 101000, "data": {"business_id": BUSINESS_ID, **event},
        }]
        store = MockTables(rows)
        guard = SerializationGuard()
        coordinator = NativeRequestWriter(
            enabled=True, tables=store,
            context_resolver=ContextResolver(),
            plan_factory=PlanFactory({"state": "verified_duplicate", "persisted": True}),
            serialization_guard=guard,
        )
        command = {"request_id": plan["target_request"]["request_id"]}
        result = coordinator.execute(object(), command)
        self.assertEqual(result["state"], "duplicate")
        self.assertTrue(result["persisted"])
        self.assertTrue(any(call[0] == "get_tables" for call in store.calls))
        self.assertFalse(any(call[0] in {"add_row", "update_row"} for call in store.calls))


if __name__ == "__main__":
    unittest.main()
