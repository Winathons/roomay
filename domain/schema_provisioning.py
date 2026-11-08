"""Offline planning and read-back contracts for future Workpeg provisioning.

This module does not import the SDK, make network calls, or execute writes.
An owner must separately authorize any hosted provisioning operation.
"""
from copy import deepcopy
from uuid import NAMESPACE_URL, UUID, uuid5

from .workpeg_adapter import AdapterError, contract_by_key, validate_table_response


EXPECTED_PEG_NAMESPACE = "roomay"
SCHEMA_NAMESPACES = ("roomay_hotel_v1", "roomay_requests_v1")


class ProvisioningError(ValueError):
    """A fail-closed preflight, creation-response, or read-back error."""

    def __init__(self, code):
        super().__init__(code)
        self.code = code


def _canonical_business_id(value):
    if not isinstance(value, str):
        raise ProvisioningError("invalid_business_id")
    try:
        parsed = UUID(value)
    except (ValueError, TypeError, AttributeError) as error:
        raise ProvisioningError("invalid_business_id") from error
    if str(parsed) != value:
        raise ProvisioningError("invalid_business_id")
    return value


def prepare_provisioning_plan(*, target_business_id, active_business_id,
                              peg_namespace, tables_by_namespace):
    """Return a read-only table inventory and proposed missing-table payloads.

    Context values are explicit owner/operator inputs, not authentication
    proofs. The Workpeg UI's protected call and selected business session must
    be independently confirmed before this plan is used for hosted writes.
    """
    target = _canonical_business_id(target_business_id)
    active = _canonical_business_id(active_business_id)
    if target != active:
        raise ProvisioningError("business_context_mismatch")
    if peg_namespace != EXPECTED_PEG_NAMESPACE:
        raise ProvisioningError("peg_namespace_mismatch")
    if not isinstance(tables_by_namespace, dict):
        raise ProvisioningError("malformed_table_inventory")

    contracts = contract_by_key()
    existing = {}
    missing = []
    errors = []
    for namespace in SCHEMA_NAMESPACES:
        tables = tables_by_namespace.get(namespace)
        if not isinstance(tables, list):
            raise ProvisioningError("table_list_unreadable:" + namespace)
        for table in tables:
            if (not isinstance(table, dict)
                    or not isinstance(table.get("name"), str)
                    or table.get("namespace") != namespace):
                raise ProvisioningError("malformed_or_wrong_namespace_table:" + namespace)

    for key, contract in contracts.items():
        tables = tables_by_namespace[contract["namespace"]]
        matches = [table for table in tables if table["name"] == contract["name"]]
        if not matches:
            missing.append(key)
            continue
        if len(matches) != 1:
            errors.append("duplicate_table:" + key)
            continue
        try:
            table_uuid = validate_table_response(contract, matches[0])
        except AdapterError as error:
            errors.append("incompatible_table:" + key + ":" + error.code)
            continue
        existing[key] = table_uuid

    blocked = bool(errors)
    payloads = [] if blocked else [
        {"table_key": key, "payload": deepcopy(contracts[key])}
        for key in missing
    ]
    return {
        "target_business_id": target,
        "peg_namespace": EXPECTED_PEG_NAMESPACE,
        "state": "blocked" if blocked else "ready_for_owner_review",
        "existing_table_uuids": existing,
        "missing_table_keys": [] if blocked else missing,
        "create_payloads": payloads,
        "errors": errors,
        "writes_authorized": False,
    }


def verify_created_table(table_key, create_response, *, direct_readback,
                         tables_by_namespace):
    """Require complete matching create, get_table and fresh list responses.

    A missing/malformed create response is an uncertain write. This function
    never treats a later listing as permission to retry or to report success.
    """
    if create_response is None:
        raise ProvisioningError("uncertain_create_outcome")
    contract = contract_by_key().get(table_key)
    if contract is None:
        raise ProvisioningError("unknown_table_contract")
    try:
        created_uuid = validate_table_response(contract, create_response)
    except AdapterError as error:
        raise ProvisioningError("invalid_create_response:" + error.code) from error
    try:
        readback_uuid = validate_table_response(contract, direct_readback)
    except AdapterError as error:
        raise ProvisioningError("invalid_direct_readback:" + error.code) from error
    if created_uuid != readback_uuid:
        raise ProvisioningError("create_readback_uuid_mismatch")
    if not isinstance(tables_by_namespace, dict):
        raise ProvisioningError("create_list_readback_failed")
    listed = tables_by_namespace.get(contract["namespace"])
    if not isinstance(listed, list):
        raise ProvisioningError("create_list_readback_failed")
    matches = [table for table in listed
               if isinstance(table, dict) and table.get("name") == contract["name"]]
    if len(matches) != 1:
        raise ProvisioningError("create_list_readback_not_unique")
    try:
        listed_uuid = validate_table_response(contract, matches[0])
    except AdapterError as error:
        raise ProvisioningError("invalid_list_readback:" + error.code) from error
    if listed_uuid != created_uuid:
        raise ProvisioningError("create_list_uuid_mismatch")
    return created_uuid


def first_fictional_room_records(business_id):
    """Build, but never write, the proposed first two test-row payloads."""
    business = _canonical_business_id(business_id)
    type_id = str(uuid5(NAMESPACE_URL, "roomay:wor-29:fictional-room-type"))
    room_id = str(uuid5(NAMESPACE_URL, "roomay:wor-29:fictional-room"))
    room_type = {
        "business_id": business,
        "entity_id": type_id,
        "name": "Roomay WOR-29 Fictional Single",
        "capacity": 1,
    }
    room = {
        "business_id": business,
        "entity_id": room_id,
        "number": "WOR29-201",
        "room_type_id": type_id,
        "enabled": True,
        "housekeeping": "ready",
    }
    return {
        "room_type": room_type,
        "room": room,
        "row_payloads": {
            "room_types": {"data": room_type, "position": 1000,
                           "inherit_business_permission": True,
                           "inherit_individual_permissions": False},
            "rooms": {"data": room, "position": 1000,
                      "inherit_business_permission": True,
                      "inherit_individual_permissions": False},
        },
        "writes_authorized": False,
    }


def classify_test_record(rows, expected_data, *, unique_field):
    """Classify an existing native-row list before a future test insert."""
    if not isinstance(rows, list) or not isinstance(expected_data, dict):
        raise ProvisioningError("malformed_test_record_list")
    business = _canonical_business_id(expected_data.get("business_id"))
    identity = expected_data.get("entity_id")
    if not isinstance(identity, str) or not isinstance(unique_field, str):
        raise ProvisioningError("invalid_test_record_identity")
    matches = []
    seen_row_ids = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ProvisioningError("malformed_test_row")
        row_id = row.get("id")
        fingerprint = row.get("fingerprint")
        data = row.get("data")
        if type(row_id) is not int or row_id <= 0 or row_id in seen_row_ids:
            raise ProvisioningError("invalid_test_row_id")
        if not isinstance(fingerprint, str) or not fingerprint:
            raise ProvisioningError("missing_test_row_fingerprint")
        if not isinstance(data, dict):
            raise ProvisioningError("malformed_test_row_data")
        if data.get("business_id") != business:
            raise ProvisioningError("cross_business_test_row")
        seen_row_ids.add(row_id)
        if data.get("entity_id") == identity or data.get(unique_field) == expected_data.get(unique_field):
            matches.append(data)
    if len(matches) > 1:
        raise ProvisioningError("duplicate_test_record")
    if not matches:
        return "absent"
    return "already_present" if matches[0] == expected_data else "identity_collision"
