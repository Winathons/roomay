"""Pure Workpeg table contracts and response normalization for Roomay.

This module performs no I/O.  The compiled UI owns authenticated Workpeg calls;
business rules continue to live in :mod:`domain.hotel`,
:mod:`domain.reservation_commands`, and :mod:`domain.service_requests`.
"""
from copy import deepcopy
from dataclasses import dataclass
from uuid import UUID

from .hotel import validate_snapshot
from .schema import proposed_tables
from .service_request_schema import proposed_service_request_tables
from .service_requests import validate_request


PAGE_SIZE = 100
MAX_PAGES = 100


class AdapterError(ValueError):
    """A fail-closed Workpeg contract or response error."""

    def __init__(self, code):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class RowReference:
    table_key: str
    entity_id: str
    row_id: int
    fingerprint: str


HOTEL_ALIASES = {
    "room_types": "roomay-hotel-v1-room-types",
    "rooms": "roomay-hotel-v1-rooms",
    "guests": "roomay-hotel-v1-guests",
    "reservations": "roomay-hotel-v1-reservations",
    "stays": "roomay-hotel-v1-stays",
    "stay_guests": "roomay-hotel-v1-stay-guests",
    "room_blocks": "roomay-hotel-v1-room-blocks",
}


def _business_column():
    return {
        "id": "business_id", "name": "business_id", "type": "uuid",
        "required": True, "position": 500,
    }


def table_contracts():
    """Return fresh, owner-only contracts; never create tables here.

    ``alias`` is retained solely for a future owner-run migration.  Workpeg does
    not return aliases, so runtime discovery deliberately uses namespace, exact
    name, restrictive permission, and the full column contract.
    """
    contracts = []
    for table in proposed_tables():
        item = deepcopy(table)
        item["permission"] = "700"
        item["alias"] = HOTEL_ALIASES[item["name"]]
        item["metadata"] = {"extra": {"contract": "roomay.hotel.v1"}}
        item["columns"] = [_business_column(), *item["columns"]]
        contracts.append(item)
    for table in proposed_service_request_tables():
        item = deepcopy(table)
        # The request contract already has hotel_id; business_id independently
        # binds every row to the active Workpeg business URL.
        item["columns"] = [_business_column(), *item["columns"]]
        contracts.append(item)
    return contracts


def contract_by_key():
    result = {}
    for contract in table_contracts():
        if contract["namespace"] == "roomay_hotel_v1":
            key = contract["name"]
        elif contract["name"] == "Roomay Service Requests":
            key = "service_requests"
        else:
            key = "service_request_audit"
        result[key] = contract
    return result


def _canonical_uuid(value, code):
    if not isinstance(value, str):
        raise AdapterError(code)
    try:
        parsed = UUID(value)
    except (ValueError, AttributeError, TypeError) as error:
        raise AdapterError(code) from error
    if str(parsed) != value:
        raise AdapterError(code)
    return value


def _choice_refs(column):
    return [choice["ref"] for choice in column.get("options", {}).get("choices", [])]


def validate_table_response(contract, table):
    """Validate one discovered table and return its native UUID."""
    if not isinstance(table, dict):
        raise AdapterError("malformed_table")
    if table.get("name") != contract["name"] or table.get("namespace") != contract["namespace"]:
        raise AdapterError("table_identity_mismatch")
    if str(table.get("permission")) != "700":
        raise AdapterError("unsafe_table_permission")
    table_uuid = _canonical_uuid(table.get("uuid"), "malformed_table_uuid")
    columns = table.get("columns")
    if not isinstance(columns, list):
        raise AdapterError("malformed_columns")
    expected = {column["id"]: column for column in contract["columns"]}
    actual = {}
    for column in columns:
        if not isinstance(column, dict) or not isinstance(column.get("id"), str):
            raise AdapterError("malformed_columns")
        if column["id"] in actual:
            raise AdapterError("duplicate_column")
        actual[column["id"]] = column
    if actual.keys() != expected.keys():
        raise AdapterError("schema_column_mismatch")
    for column_id, wanted in expected.items():
        found = actual[column_id]
        if found.get("name") != wanted["name"]:
            raise AdapterError("schema_name_mismatch")
        if found.get("type") != wanted["type"]:
            raise AdapterError("schema_type_mismatch")
        if bool(found.get("required", False)) != bool(wanted.get("required", False)):
            raise AdapterError("schema_required_mismatch")
        if found.get("position") != wanted.get("position"):
            raise AdapterError("schema_position_mismatch")
        if found.get("options", {}) != wanted.get("options", {}):
            raise AdapterError("schema_options_mismatch")
        if found.get("metadata", {}) != wanted.get("metadata", {}):
            raise AdapterError("schema_column_metadata_mismatch")
    if table.get("metadata", {}) != contract.get("metadata", {}):
        raise AdapterError("schema_table_metadata_mismatch")
    return table_uuid


def resolve_tables(tables_by_namespace):
    """Resolve every contract without treating an unreadable table as absent."""
    if not isinstance(tables_by_namespace, dict):
        raise AdapterError("malformed_table_lists")
    resolved = {}
    for key, contract in contract_by_key().items():
        tables = tables_by_namespace.get(contract["namespace"])
        if not isinstance(tables, list):
            raise AdapterError("malformed_table_list")
        matches = [table for table in tables
                   if isinstance(table, dict) and table.get("name") == contract["name"]]
        if not matches:
            raise AdapterError("missing_table:" + key)
        if len(matches) != 1:
            raise AdapterError("duplicate_table:" + key)
        resolved[key] = validate_table_response(contract, matches[0])
    return resolved


def validate_table_ownership(table, registered_peg_id):
    """Require exact, typed Peg ownership evidence for write readiness.

    Workpeg's current Tables reference describes ``peg`` as ``number | null``,
    while Roomay's owner-observed development metadata has returned a UUID
    string.  Do not coerce either representation: the trusted registered Peg
    identity and every table's returned value must match exactly.  This check
    is deliberately separate from :func:`validate_table_response`, so an
    unknown ownership field does not break otherwise-valid read-only use.
    """
    if not isinstance(table, dict):
        raise AdapterError("malformed_table")
    if type(registered_peg_id) is str:
        try:
            if str(UUID(registered_peg_id)) != registered_peg_id:
                raise ValueError
        except (ValueError, TypeError, AttributeError) as error:
            raise AdapterError("invalid_registered_peg_id") from error
    elif type(registered_peg_id) is int:
        if registered_peg_id <= 0:
            raise AdapterError("invalid_registered_peg_id")
    else:
        raise AdapterError("invalid_registered_peg_id")

    if "peg" not in table:
        raise AdapterError("peg_ownership_missing")
    actual = table["peg"]
    if type(actual) is not type(registered_peg_id):
        raise AdapterError("peg_ownership_type_mismatch")
    if actual != registered_peg_id:
        raise AdapterError("peg_ownership_mismatch")
    return actual


def resolve_tables_for_write(tables_by_namespace, registered_peg_id):
    """Resolve canonical tables and prove exact Peg ownership for each.

    This does not prove actor authorization, row permission, or serialization;
    those are separate mandatory gates in the writer coordinator.
    """
    resolved = resolve_tables(tables_by_namespace)
    for key, contract in contract_by_key().items():
        tables = tables_by_namespace[contract["namespace"]]
        table = next(item for item in tables if item.get("name") == contract["name"])
        validate_table_ownership(table, registered_peg_id)
    return resolved


def collect_pages(pages, *, page_size=PAGE_SIZE, max_pages=MAX_PAGES):
    """Validate already-fetched Workpeg windows and return a single row list."""
    if not isinstance(pages, list) or not pages:
        raise AdapterError("malformed_pages")
    rows = []
    ended = False
    for index, page in enumerate(pages):
        if ended:
            raise AdapterError("page_after_end")
        if index >= max_pages:
            raise AdapterError("pagination_limit")
        if not isinstance(page, list) or len(page) > page_size:
            raise AdapterError("malformed_page")
        rows.extend(page)
        if len(page) < page_size:
            ended = True
    if not ended:
        raise AdapterError("pagination_incomplete")
    return rows


def _validate_value(column, value):
    kind = column["type"]
    if kind in {"text", "datetime", "mutable_select"}:
        if not isinstance(value, str) or not value.strip():
            raise AdapterError("invalid_field:" + column["id"])
    elif kind == "uuid":
        _canonical_uuid(value, "invalid_field:" + column["id"])
    elif kind == "number":
        if type(value) not in (int, float):
            raise AdapterError("invalid_field:" + column["id"])
    elif kind == "boolean":
        if type(value) is not bool:
            raise AdapterError("invalid_field:" + column["id"])
    else:
        raise AdapterError("unsupported_column_type:" + kind)
    if kind == "mutable_select" and value not in _choice_refs(column):
        raise AdapterError("invalid_choice:" + column["id"])


def decode_rows(table_key, business_id, rows):
    """Normalize native rows and retain the row-id/fingerprint mapping."""
    _canonical_uuid(business_id, "invalid_business_id")
    contract = contract_by_key().get(table_key)
    if contract is None:
        raise AdapterError("unknown_table_contract")
    if not isinstance(rows, list):
        raise AdapterError("malformed_row_list")
    columns = {column["id"]: column for column in contract["columns"]}
    identity = "entity_id"
    if table_key == "service_requests":
        identity = "request_id"
    elif table_key == "service_request_audit":
        identity = "event_id"
    records, references, row_ids, entity_ids = [], [], set(), set()
    for row in rows:
        if not isinstance(row, dict):
            raise AdapterError("malformed_row")
        row_id = row.get("id")
        if type(row_id) is not int or row_id <= 0 or row_id in row_ids:
            raise AdapterError("invalid_or_duplicate_row_id")
        fingerprint = row.get("fingerprint")
        if not isinstance(fingerprint, str) or not fingerprint:
            raise AdapterError("missing_fingerprint")
        data = row.get("data")
        if not isinstance(data, dict) or data.keys() - columns.keys():
            raise AdapterError("malformed_row_data")
        for column_id, column in columns.items():
            value = data.get(column_id)
            if value is None:
                if column.get("required", False):
                    raise AdapterError("missing_field:" + column_id)
                continue
            _validate_value(column, value)
        if data["business_id"] != business_id:
            raise AdapterError("cross_business_row")
        entity_id = data.get(identity)
        if entity_id in entity_ids:
            raise AdapterError("duplicate_entity_id")
        row_ids.add(row_id)
        entity_ids.add(entity_id)
        # Workpeg documents missing column values as null. Preserve optional
        # nulls so canonical records with an exact field set remain valid.
        normalized = {key: data.get(key) for key in columns if key != "business_id"}
        records.append(normalized)
        references.append(RowReference(table_key, entity_id, row_id, fingerprint))
    return records, references


def normalize_snapshot(business_id, rows_by_table, *, allow_pending_request_id=None):
    """Decode and validate a complete hotel snapshot and service requests."""
    if not isinstance(rows_by_table, dict):
        raise AdapterError("malformed_snapshot_rows")
    expected = set(contract_by_key())
    if rows_by_table.keys() != expected:
        raise AdapterError("incomplete_snapshot_rows")
    hotel, references = {}, []
    for key in HOTEL_ALIASES:
        hotel[key], refs = decode_rows(key, business_id, rows_by_table[key])
        references.extend(refs)
    try:
        hotel_index = validate_snapshot(hotel)
    except (ValueError, TypeError) as error:
        raise AdapterError("invalid_hotel_snapshot") from error
    requests, refs = decode_rows("service_requests", business_id,
                                 rows_by_table["service_requests"])
    references.extend(refs)
    for request in requests:
        try:
            validate_request(request)
            stay = hotel_index["stays"].get(request["stay_id"])
            if stay is None or stay["room_id"] != request["room_id"]:
                raise ValueError("service request stay/room mismatch")
            occupants = [occupant for occupant in hotel["stay_guests"]
                         if occupant["stay_id"] == request["stay_id"]
                         and occupant["guest_id"] == request["guest_id"]]
            if len(occupants) != 1:
                raise ValueError("service request guest is not a registered occupant")
        except (ValueError, TypeError) as error:
            raise AdapterError("invalid_service_request") from error
    audit, refs = decode_rows("service_request_audit", business_id,
                              rows_by_table["service_request_audit"])
    references.extend(refs)
    requests_by_id = {request["request_id"]: request for request in requests}
    audit_sequences = {}
    for event in audit:
        request = requests_by_id.get(event["request_id"])
        if request is None and not (
                event["request_id"] == allow_pending_request_id
                and event.get("commit_state") == "pending"
                and event.get("sequence") == 1):
            raise AdapterError("orphan_service_request_audit")
        if request is not None and event["hotel_id"] != request["hotel_id"]:
            raise AdapterError("service_request_audit_hotel_mismatch")
        if type(event["sequence"]) is not int or event["sequence"] < 1:
            raise AdapterError("invalid_service_request_audit_sequence")
        sequences = audit_sequences.setdefault(event["request_id"], set())
        if event["sequence"] in sequences:
            raise AdapterError("duplicate_service_request_audit_sequence")
        sequences.add(event["sequence"])
    return {
        "hotel": hotel,
        "service_requests": requests,
        "service_request_audit": audit,
        "references": references,
        "empty_inventory": not hotel["room_types"] or not hotel["rooms"],
    }


def full_row_update(existing_row, changes, *, immutable=()):
    """Build a safe Workpeg PATCH whose ``data`` preserves unrelated fields."""
    if not isinstance(existing_row, dict) or not isinstance(existing_row.get("data"), dict):
        raise AdapterError("malformed_existing_row")
    if not isinstance(changes, dict):
        raise AdapterError("malformed_changes")
    for key in immutable:
        if key in changes and changes[key] != existing_row["data"].get(key):
            raise AdapterError("immutable_field_change:" + key)
    data = deepcopy(existing_row["data"])
    data.update(deepcopy(changes))
    return {"data": data}


def reconcile_write(expected_data, before_fingerprint, readback):
    """Classify a mandatory read-back after a failed, timed-out, or stale write.

    Fingerprints are change markers only; the SDK documents no conditional
    update primitive.  Conflicts therefore require a trusted serialized writer
    or manual reconciliation rather than an automatic retry.
    """
    if not isinstance(expected_data, dict) or not isinstance(before_fingerprint, str):
        raise AdapterError("invalid_reconciliation_input")
    if readback is None:
        return "not_found_manual_reconciliation"
    if not isinstance(readback, dict) or not isinstance(readback.get("data"), dict):
        return "malformed_manual_reconciliation"
    fingerprint = readback.get("fingerprint")
    if not isinstance(fingerprint, str) or not fingerprint:
        return "malformed_manual_reconciliation"
    if readback["data"] == expected_data and fingerprint != before_fingerprint:
        return "confirmed"
    if fingerprint == before_fingerprint:
        return "not_applied"
    return "conflict_manual_reconciliation"
