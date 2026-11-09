"""Offline planner for a single, synthetic WOR-60 hotel-to-request slice.

This module only prepares validated row intents. It makes no Workpeg calls and
never claims that a row or operation was persisted. The development UI mirrors
its output because the pinned Workpeg UI compiler cannot call imported domain
functions; compiled parity tests guard that boundary.
"""
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .hotel import validate_snapshot
from .reservation_commands import prepare_booking_request, prepare_room_confirmation
from .schema import proposed_tables
from .service_request_schema import proposed_service_request_tables
from .service_requests import create_request, request_row_payload, event_row_payload
from .workpeg_adapter import (
    AdapterError, contract_by_key, decode_rows, normalize_snapshot,
    resolve_tables, table_contracts,
)


ROOM_TYPE_NAME = "Roomay TEST Room Type (Fictional)"
ROOM_TYPE_CAPACITY = 3
ROOM_NUMBER = "205"
SYNTHETIC_HOTEL_ID = str(uuid5(NAMESPACE_URL, "roomay:wor60:fictional-hotel:v1"))
SYNTHETIC_RECEPTION_ID = "WOR-60-SYNTHETIC-RECEPTION"
BOOKING_IDEMPOTENCY_KEY = "wor60-booking-v1"
STAY_ID = str(uuid5(NAMESPACE_URL, "roomay:synthetic:v1:wor60-stay"))
OCCUPANT_ID = str(uuid5(NAMESPACE_URL, "roomay:synthetic:v1:wor60-stay-guest"))
REQUEST_ID = str(uuid5(NAMESPACE_URL, "roomay:synthetic:v1:wor60-extra-towels-request"))
REQUEST_IDEMPOTENCY_KEY = "wor60-extra-towels-v1"
WRITE_ORDER = (
    "rooms", "guests", "reservations", "stays", "stay_guests",
    "service_requests", "service_request_audit",
)
TABLE_NAME_BY_KEY = {
    "room_types": "room_types", "rooms": "rooms", "guests": "guests",
    "reservations": "reservations", "stays": "stays",
    "stay_guests": "stay_guests", "room_blocks": "room_blocks",
    "service_requests": "Roomay Service Requests",
    "service_request_audit": "Roomay Service Request Audit",
}
TABLE_KEY_BY_NAME = {value: key for key, value in TABLE_NAME_BY_KEY.items()}
IDENTITY_BY_KEY = {
    "room_types": "entity_id", "rooms": "entity_id", "guests": "entity_id",
    "reservations": "entity_id", "stays": "entity_id", "stay_guests": "entity_id",
    "room_blocks": "entity_id", "service_requests": "request_id",
    "service_request_audit": "event_id",
}


class VerticalSliceRejected(ValueError):
    """Sanitized planner refusal code."""

    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _uid(label):
    return str(uuid5(NAMESPACE_URL, "roomay:synthetic:v1:" + label))


def _business_uuid(value):
    try:
        from uuid import UUID
        if not isinstance(value, str) or str(UUID(value)) != value:
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise VerticalSliceRejected("invalid_business_context") from None
    return value


def _local_checkin(operational_date, hotel_timezone, authoritative_now):
    try:
        day = date.fromisoformat(operational_date)
        if day.isoformat() != operational_date:
            raise ValueError
    except (ValueError, TypeError, OverflowError):
        raise VerticalSliceRejected("invalid_operational_date") from None
    try:
        now = datetime.fromisoformat(authoritative_now)
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError
    except (ValueError, TypeError, OverflowError):
        raise VerticalSliceRejected("authoritative_time_required") from None
    if not isinstance(hotel_timezone, str) or not hotel_timezone.strip():
        raise VerticalSliceRejected("iana_hotel_timezone_required")
    try:
        local_now = now.astimezone(ZoneInfo(hotel_timezone))
    except ZoneInfoNotFoundError:
        raise VerticalSliceRejected("iana_hotel_timezone_unavailable") from None
    except (ValueError, TypeError, OverflowError):
        raise VerticalSliceRejected("invalid_authoritative_time") from None
    if local_now.date() != day:
        raise VerticalSliceRejected("operational_date_does_not_match_hotel_local_now")
    # Persist an unambiguous UTC instant after deriving the hotel-local date
    # from the verified IANA zone. This avoids treating a supplied offset as
    # the hotel's time zone.
    utc_now = now.astimezone(timezone.utc).isoformat(timespec="seconds")
    try:
        departure = (day + timedelta(days=2)).isoformat()
    except OverflowError:
        raise VerticalSliceRejected("invalid_departure_date") from None
    return day.isoformat(), utc_now, departure


def _table_records(business_id, rows_by_table):
    if not isinstance(rows_by_table, dict) or set(rows_by_table) != set(TABLE_KEY_BY_NAME):
        raise VerticalSliceRejected("incomplete_row_inventory")
    records = {}
    references = []
    for key in TABLE_NAME_BY_KEY:
        try:
            values, refs = decode_rows(key, business_id, rows_by_table[TABLE_NAME_BY_KEY[key]])
        except AdapterError as error:
            raise VerticalSliceRejected("invalid_inventory:" + error.code) from None
        records[key] = values
        references.extend(refs)
    return records, references


def _adapter_rows(rows_by_table):
    return {key: rows_by_table[TABLE_NAME_BY_KEY[key]] for key in TABLE_NAME_BY_KEY}


def _normalize_record(key, record):
    columns = {column["id"] for column in contract_by_key()[key]["columns"]}
    return {column: record.get(column) for column in columns if column != "business_id"}


def validate_inventory(business_id, tables_by_namespace, rows_by_table):
    """Validate schemas, all row pages, and the preserved room-type record.

    ``tables_by_namespace`` and ``rows_by_table`` must be complete results of
    explicit authenticated reads. This function performs no I/O.
    """
    business_id = _business_uuid(business_id)
    try:
        if (not isinstance(tables_by_namespace, dict)
                or set(tables_by_namespace) != {"roomay_hotel_v1", "roomay_requests_v1"}):
            raise VerticalSliceRejected("incomplete_namespace_inventory")
        allowed = {"roomay_hotel_v1": set(), "roomay_requests_v1": set()}
        for contract in table_contracts():
            allowed[contract["namespace"]].add(contract["name"])
        for namespace in allowed:
            if not isinstance(tables_by_namespace[namespace], list):
                raise VerticalSliceRejected("malformed_namespace_inventory")
            seen_names = set()
            for table in tables_by_namespace[namespace]:
                if not isinstance(table, dict) or table.get("name") not in allowed[namespace]:
                    raise VerticalSliceRejected("unexpected_table_inventory")
                if table["name"] in seen_names:
                    raise VerticalSliceRejected("duplicate_table_inventory")
                seen_names.add(table["name"])
        resolved = resolve_tables(tables_by_namespace)
    except VerticalSliceRejected:
        raise
    except AdapterError as error:
        raise VerticalSliceRejected("invalid_inventory:" + error.code) from None
    records, references = _table_records(business_id, rows_by_table)
    room_types = records["room_types"]
    target = [row for row in room_types if row.get("name") == ROOM_TYPE_NAME]
    if len(target) != 1 or target[0].get("capacity") != ROOM_TYPE_CAPACITY:
        raise VerticalSliceRejected("preserved_room_type_missing_duplicate_or_incompatible")
    if len(room_types) != 1:
        raise VerticalSliceRejected("unexpected_room_type_records_require_owner_review")
    # Validate the immutable base row through the canonical hotel validator.
    # Subsequent reads may contain an intentional verified prefix of this
    # multi-row workflow, so full referential validation is done against the
    # prepared target (and again after completion), not against an incomplete
    # intermediate snapshot.
    base = {table["name"]: [] for table in proposed_tables()}
    base["room_types"] = deepcopy(room_types)
    try:
        validate_snapshot(base)
    except (ValueError, TypeError, KeyError):
        raise VerticalSliceRejected("invalid_room_type_inventory") from None
    return {"resolved_tables": resolved, "records": records,
            "room_type": deepcopy(target[0]), "references": references}


def _make_plan(business_id, room_type, operational_date, hotel_timezone, authoritative_now):
    arrival, checked_in_at, departure = _local_checkin(
        operational_date, hotel_timezone, authoritative_now)
    room_id = _uid("wor60-room-205")
    guest_id = _uid("wor60-fictional-guest")
    snapshot = {table["name"]: [] for table in proposed_tables()}
    snapshot["room_types"] = [deepcopy(room_type)]
    room = {"entity_id": room_id, "number": ROOM_NUMBER,
            "room_type_id": room_type["entity_id"], "enabled": True,
            "housekeeping": "ready"}
    guest = {"entity_id": guest_id,
             "display_name": "WOR-60 Fictional Guest (Synthetic)"}
    snapshot["rooms"].append(room)
    snapshot["guests"].append(guest)
    try:
        booking = prepare_booking_request(
            snapshot, idempotency_key=BOOKING_IDEMPOTENCY_KEY,
            guest_id=guest_id, room_type_id=room_type["entity_id"],
            arrival=arrival, departure=departure, party_size=1, source="advance",
        )
        snapshot["reservations"].append(deepcopy(booking.record))
        confirmation = prepare_room_confirmation(
            snapshot, reservation_id=booking.reservation_id, room_id=room_id,
            staff_authorized=True,
        )
        snapshot["reservations"][0] = deepcopy(confirmation.record)
    except (ValueError, TypeError, KeyError):
        raise VerticalSliceRejected("reservation_rules_rejected_preview") from None

    # This is a synthetic test record, not an authorized check-in command.
    # The canonical snapshot validator remains the authority for its structure,
    # references, active occupancy and departure/arrival invariants.
    stay = {"entity_id": STAY_ID, "reservation_id": booking.reservation_id,
            "room_id": room_id, "status": "checked_in", "checked_in_at": checked_in_at}
    occupant = {"entity_id": OCCUPANT_ID, "stay_id": STAY_ID,
                "guest_id": guest_id, "joined_at": checked_in_at}
    snapshot["stays"].append(stay)
    snapshot["stay_guests"].append(occupant)
    try:
        validate_snapshot(snapshot)
    except (ValueError, TypeError, KeyError):
        raise VerticalSliceRejected("hotel_invariants_rejected_preview") from None

    staff_actor = {"actor_id": SYNTHETIC_RECEPTION_ID,
                   "hotel_id": SYNTHETIC_HOTEL_ID, "kind": "staff"}
    staff_directory = [{"actor_id": SYNTHETIC_RECEPTION_ID,
                        "hotel_id": SYNTHETIC_HOTEL_ID,
                        "department": "reception", "roles": [], "active": True}]
    draft = {
        "hotel_id": SYNTHETIC_HOTEL_ID, "stay_id": STAY_ID,
        "room_id": room_id, "guest_id": guest_id,
        "origin": "reception_desk", "category": "extra_towels",
        "description": "Synthetic WOR-60 extra-towels request for Room 205.",
        "urgency": "normal", "idempotency_key": REQUEST_IDEMPOTENCY_KEY,
        "sensitive": False,
    }
    try:
        request_result = create_request(
            snapshot, draft, staff_actor, staff_directory, [],
            at=checked_in_at, request_id=REQUEST_ID,
        )
    except (ValueError, TypeError, KeyError):
        raise VerticalSliceRejected("service_request_rules_rejected_preview") from None
    request = request_result["request"]
    event = request_result["plan"]["event"]
    if (request["category"] != "extra_towels" or request["department"] != "housekeeping"
            or request["status"] != "received"):
        raise VerticalSliceRejected("service_request_routing_mismatch")

    records = {
        "rooms": [room], "guests": [guest], "reservations": [confirmation.record],
        "stays": [stay], "stay_guests": [occupant],
        "service_requests": [request], "service_request_audit": [event],
    }
    return {"business_id": business_id, "hotel_id": SYNTHETIC_HOTEL_ID,
            "room_type": deepcopy(room_type), "records": deepcopy(records),
            "arrival": arrival, "departure": departure,
            "checked_in_at": checked_in_at, "persisted": False}


def _row_payload(key, record, business_id):
    data = deepcopy(record)
    data["business_id"] = business_id
    if key == "service_requests":
        payload = request_row_payload(record, 1000)
    elif key == "service_request_audit":
        payload = event_row_payload(record, 1000)
    else:
        contract = contract_by_key()[key]
        payload = {"data": data, "position": 1000, "namespace": "active",
                   "inherit_business_permission": True,
                   "inherit_individual_permissions": False}
        return payload
    payload["data"]["business_id"] = business_id
    return payload


def prepare_vertical_slice(business_id, tables_by_namespace, rows_by_table, *,
                           operational_date, hotel_timezone, authoritative_now):
    """Prepare the next single row after a complete, safe inventory read.

    Existing rows must be the exact preserved room type and an exact prefix of
    this plan. Any unrelated, duplicate, altered or out-of-order row blocks the
    workflow. Repeated calls with the same business/date/time are deterministic.
    """
    inspected = validate_inventory(business_id, tables_by_namespace, rows_by_table)
    business_id = _business_uuid(business_id)
    planned = _make_plan(business_id, inspected["room_type"], operational_date,
                         hotel_timezone, authoritative_now)
    existing, references = _table_records(business_id, rows_by_table)
    expected = {key: [] for key in TABLE_NAME_BY_KEY}
    for key, values in planned["records"].items():
        expected[key] = deepcopy(values)
    expected["room_types"] = [deepcopy(inspected["room_type"])]

    for key in TABLE_NAME_BY_KEY:
        identity = IDENTITY_BY_KEY[key]
        expected_index = {record[identity]: _normalize_record(key, record)
                          for record in expected[key]}
        seen = set()
        for record in existing[key]:
            record_id = record.get(identity)
            if record_id in seen or record_id not in expected_index:
                raise VerticalSliceRejected("unexpected_records_require_owner_reconciliation")
            seen.add(record_id)
            if record != expected_index[record_id]:
                raise VerticalSliceRejected("existing_synthetic_record_mismatch")

    present_steps = []
    for key in WRITE_ORDER:
        identity = IDENTITY_BY_KEY[key]
        target = expected[key][0]
        present_steps.append(any(row.get(identity) == target[identity] for row in existing[key]))
    missing_seen = False
    for present in present_steps:
        if not present:
            missing_seen = True
        elif missing_seen:
            raise VerticalSliceRejected("partial_sequence_requires_owner_reconciliation")
    next_index = present_steps.index(False) if False in present_steps else len(WRITE_ORDER)
    next_step = WRITE_ORDER[next_index] if next_index < len(WRITE_ORDER) else "complete"
    if next_index >= WRITE_ORDER.index("service_requests"):
        # Service work is gated on a complete, independently inspectable stay.
        if not all(present_steps[:5]):
            raise VerticalSliceRejected("persisted_stay_required_before_service_request")
        try:
            persisted_hotel = {table: deepcopy(existing[table])
                               for table in TABLE_NAME_BY_KEY if table in {
                                   "room_types", "rooms", "guests", "reservations",
                                   "stays", "stay_guests", "room_blocks"}}
            hotel_index = validate_snapshot(persisted_hotel)
            if (len(persisted_hotel["stays"]) != 1
                    or len(persisted_hotel["stay_guests"]) != 1
                    or persisted_hotel["stays"][0]["status"] != "checked_in"
                    or planned["records"]["stays"][0]["entity_id"] not in hotel_index["stays"]):
                raise ValueError
        except (AdapterError, ValueError, TypeError, KeyError):
            raise VerticalSliceRejected("persisted_stay_failed_fresh_readback") from None
    if next_step == "complete":
        try:
            normalize_snapshot(business_id, _adapter_rows(rows_by_table))
        except (AdapterError, ValueError, TypeError, KeyError):
            raise VerticalSliceRejected("complete_vertical_slice_failed_adapter_validation") from None
    payload = None
    if next_step != "complete":
        identity = IDENTITY_BY_KEY[next_step]
        payload = _row_payload(next_step, expected[next_step][0], business_id)
    return {
        "valid": True, "next_step": next_step, "payload": payload,
        "records": deepcopy(expected), "dates": {"arrival": planned["arrival"],
            "departure": planned["departure"], "checked_in_at": planned["checked_in_at"]},
        "room_type_entity_id": inspected["room_type"]["entity_id"],
        "room_id": planned["records"]["rooms"][0]["entity_id"],
        "guest_id": planned["records"]["guests"][0]["entity_id"],
        "reservation_id": planned["records"]["reservations"][0]["entity_id"],
        "stay_id": planned["records"]["stays"][0]["entity_id"],
        "request_id": planned["records"]["service_requests"][0]["request_id"],
        "audit_event_id": planned["records"]["service_request_audit"][0]["event_id"],
        "persisted_prefix": [WRITE_ORDER[index] for index, present in enumerate(present_steps) if present],
        "complete": next_step == "complete", "persisted": False,
        "references": references,
    }
