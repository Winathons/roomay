"""Pure, fail-closed planner for the canonical Roomay Workpeg tables.

This module compares readable inventory only. It never calls Workpeg and it
never treats an absent readable table as proof that an inaccessible table does
not exist.
"""
from copy import deepcopy
from uuid import UUID

from .workpeg_adapter import AdapterError, contract_by_key, table_contracts, validate_table_response


HOTEL_NAMESPACE = "roomay_hotel_v1"
REQUEST_NAMESPACE = "roomay_requests_v1"
NAMESPACES = (HOTEL_NAMESPACE, REQUEST_NAMESPACE)
MIGRATION_ORDER = (
    "room_types",
    "rooms",
    "guests",
    "reservations",
    "stays",
    "stay_guests",
    "room_blocks",
    "Roomay Service Requests",
    "Roomay Service Request Audit",
)
ROOM_TYPES_NAME = "room_types"


def ordered_contracts():
    """Return canonical contract payloads in the reviewed creation order."""
    by_name = {item["name"]: item for item in table_contracts()}
    return [deepcopy(by_name[name]) for name in MIGRATION_ORDER]


def contract_for_name(name):
    for contract in table_contracts():
        if contract["name"] == name:
            return deepcopy(contract)
    return None


def validate_contract_table(name, table):
    """Return a sanitized exact contract check for one Workpeg table object."""
    contract = contract_for_name(name)
    if contract is None:
        return {"valid": False, "uuid": "", "error": "unknown_contract"}
    try:
        table_uuid = validate_table_response(contract, table)
    except AdapterError as error:
        return {"valid": False, "uuid": "", "error": error.code}
    return {"valid": True, "uuid": table_uuid, "error": ""}


def _issue_group(error):
    if error == "unsafe_table_permission":
        return "incorrect_permissions"
    if error == "schema_column_metadata_mismatch" or error == "schema_table_metadata_mismatch":
        return "incorrect_metadata"
    if error.startswith("schema_column") or error.startswith("schema_name") or error.startswith("schema_type"):
        return "incorrect_columns"
    if error.startswith("schema_required") or error.startswith("schema_position") or error.startswith("schema_options"):
        return "incorrect_columns"
    return "incompatible_table"


def plan_migration(tables_by_namespace, *, owner_verified_missing=()):
    """Compare both readable namespace lists to all nine canonical contracts.

    ``owner_verified_missing`` is a list of names independently checked by an
    owner in Workpeg. It is an operator attestation, never authentication. A
    table is creation-eligible only when both namespace responses are valid,
    no ambiguity exists anywhere in the inventory, and the exact missing table
    is attested. ``room_types`` is never eligible for creation.
    """
    contracts = ordered_contracts()
    blockers = []
    unexpected = []
    states = {}
    if not isinstance(owner_verified_missing, (list, tuple, set)):
        return _failed_plan(contracts, "invalid_owner_missing_attestation")
    owner_names = list(owner_verified_missing)
    known_names = [contract["name"] for contract in contracts]
    for name in owner_names:
        if name not in known_names or name == ROOM_TYPES_NAME:
            blockers.append("invalid_owner_missing_attestation")

    if not isinstance(tables_by_namespace, dict):
        return _failed_plan(contracts, "malformed_inventory")
    for namespace in NAMESPACES:
        if not isinstance(tables_by_namespace.get(namespace), list):
            return _failed_plan(contracts, "missing_or_malformed_namespace:" + namespace)

    all_ids = []
    grouped = {}
    expected_by_namespace = {}
    for contract in contracts:
        expected_by_namespace.setdefault(contract["namespace"], []).append(contract["name"])

    for namespace in NAMESPACES:
        for table in tables_by_namespace[namespace]:
            if not isinstance(table, dict):
                blockers.append("malformed_table_entry:" + namespace)
                continue
            name = table.get("name")
            returned_namespace = table.get("namespace")
            table_uuid = table.get("uuid")
            if (not isinstance(name, str) or not name
                    or returned_namespace != namespace
                    or not isinstance(table_uuid, str) or not table_uuid
                    or table.get("permission") is None
                    or not isinstance(table.get("columns"), list)):
                blockers.append("malformed_table_identity_or_schema:" + namespace)
                continue
            try:
                if str(UUID(table_uuid)) != table_uuid:
                    raise ValueError("non-canonical uuid")
            except (ValueError, TypeError, AttributeError):
                blockers.append("malformed_table_uuid:" + namespace)
                continue
            if table_uuid in all_ids:
                blockers.append("duplicate_native_table_uuid")
            all_ids.append(table_uuid)
            grouped.setdefault((namespace, name), []).append(table)
            if name not in expected_by_namespace.get(namespace, []):
                unexpected.append({"namespace": namespace, "name": name, "uuid": table_uuid})

    if unexpected:
        blockers.append("unexpected_tables_present")
    if "room_types" not in [name for (namespace, name) in grouped if namespace == HOTEL_NAMESPACE]:
        blockers.append("required_room_types_missing_or_unreadable")

    for contract in contracts:
        name = contract["name"]
        namespace = contract["namespace"]
        matches = grouped.get((namespace, name), [])
        if not matches:
            states[name] = {
                "name": name, "namespace": namespace, "alias": contract.get("alias", ""),
                "permission": contract["permission"], "status": "missing_or_unreadable",
                "eligible": False, "uuid": "", "error": "",
                "contract": deepcopy(contract),
            }
            continue
        if len(matches) > 1:
            blockers.append("duplicate_table:" + name)
            states[name] = {
                "name": name, "namespace": namespace, "alias": contract.get("alias", ""),
                "permission": contract["permission"], "status": "duplicate",
                "eligible": False, "uuid": "", "error": "duplicate_table",
                "contract": deepcopy(contract),
            }
            continue
        item = matches[0]
        try:
            table_uuid = validate_table_response(contract, item)
            status = "existing_compatible"
            error = ""
        except AdapterError as exception:
            error = exception.code
            status = _issue_group(error)
            blockers.append(status + ":" + name)
            table_uuid = item.get("uuid", "")
        states[name] = {
            "name": name, "namespace": namespace, "alias": contract.get("alias", ""),
            "permission": contract["permission"], "status": status,
            "eligible": False, "uuid": table_uuid, "error": error,
            "contract": deepcopy(contract),
        }

    # Missing/unreadable room_types is never an invitation to recreate it.
    if states.get(ROOM_TYPES_NAME, {}).get("status") == "missing_or_unreadable":
        states[ROOM_TYPES_NAME]["status"] = "required_existing_table_missing"

    if not blockers:
        for name in MIGRATION_ORDER:
            item = states[name]
            if (name != ROOM_TYPES_NAME
                    and item["status"] == "missing_or_unreadable"
                    and name in owner_names):
                item["eligible"] = True
    return {
        "valid_inventory": not blockers,
        "blockers": sorted(set(blockers)),
        "unexpected": unexpected,
        "tables": [states[name] for name in MIGRATION_ORDER],
        "eligible": [name for name in MIGRATION_ORDER if states[name]["eligible"]],
        "signature": _signature(states, unexpected),
    }


def _failed_plan(contracts, reason):
    items = []
    for contract in contracts:
        items.append({
            "name": contract["name"], "namespace": contract["namespace"],
            "alias": contract.get("alias", ""), "permission": contract["permission"],
            "status": "inventory_unknown", "eligible": False, "uuid": "",
            "error": reason, "contract": deepcopy(contract),
        })
    return {
        "valid_inventory": False, "blockers": [reason], "unexpected": [],
        "tables": items, "eligible": [], "signature": "unknown:" + reason,
    }


def _signature(states, unexpected):
    parts = []
    for name in MIGRATION_ORDER:
        item = states[name]
        parts.append(name + "=" + item["status"] + "=" + str(item["uuid"])
                     + "=" + str(item["error"]))
    for item in sorted(unexpected, key=lambda value: (value["namespace"], value["name"], value["uuid"])):
        parts.append("unexpected=" + item["namespace"] + "/" + item["name"] + "/" + item["uuid"])
    return "\n".join(parts)
