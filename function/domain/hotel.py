"""Pure checks over a complete, single-business snapshot of plain records.

ValueError means invalid/inconsistent input. Eligibility returns reason codes.
Passing checks is advisory: it neither authorizes nor commits a booking/check-in.
"""
from datetime import date, datetime
from uuid import UUID

from .schema import proposed_tables


def parse_day(value):
    if not isinstance(value, str):
        raise ValueError("date must be YYYY-MM-DD")
    parsed = date.fromisoformat(value)
    if parsed.isoformat() != value:
        raise ValueError("date must be YYYY-MM-DD")
    return parsed


def parse_instant(value):
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must include UTC offset")
    return parsed


def interval(start, end):
    start, end = parse_day(start), parse_day(end)
    if start >= end:
        raise ValueError("arrival/start must precede departure/end")
    return start, end


def overlaps(a_start, a_end, b_start, b_end):
    a, b = interval(a_start, a_end), interval(b_start, b_end)
    return a[0] < b[1] and b[0] < a[1]


def validate_snapshot(data):
    """Validate local shape, references and record invariants; no remote claims."""
    indexes = {}
    expected = {table["name"] for table in proposed_tables()}
    if not isinstance(data, dict) or data.keys() != expected:
        raise ValueError("snapshot must contain exactly the model tables")
    for table in proposed_tables():
        name = table["name"]
        indexes[name] = {}
        columns = {c["id"]: c for c in table["columns"]}
        if not isinstance(data[name], list):
            raise ValueError("table records must be a list")
        for row in data[name]:
            if not isinstance(row, dict):
                raise ValueError("record must be a dictionary")
            if row.keys() - columns.keys():
                raise ValueError("unknown fields: " + name)
            for key, column in columns.items():
                value = row.get(key)
                if value is None:
                    if column["required"]:
                        raise ValueError("missing " + key)
                    continue
                kind = column["type"]
                if kind in ("text", "uuid", "datetime", "mutable_select"):
                    if not isinstance(value, str) or not value.strip():
                        raise ValueError("expected nonempty string: " + key)
                if kind == "uuid" and str(UUID(value)) != value:
                    raise ValueError("noncanonical UUID")
                if kind == "number" and (type(value) is not int or value < 1):
                    raise ValueError("expected positive integer: " + key)
                if kind == "boolean" and type(value) is not bool:
                    raise ValueError("expected boolean")
                if kind == "mutable_select" and value not in {
                        c["ref"] for c in column["options"]["choices"]}:
                    raise ValueError("invalid status/choice")
                if kind == "datetime":
                    (parse_day if column["metadata"]["type"] == "date"
                     else parse_instant)(value)
            key = row["entity_id"]
            if key in indexes[name]:
                raise ValueError("duplicate entity_id")
            indexes[name][key] = row

    def linked(table, key):
        if key not in indexes[table]:
            raise ValueError("missing reference: " + table)
        return indexes[table][key]

    numbers = set()
    for room in data["rooms"]:
        linked("room_types", room["room_type_id"])
        if room["number"] in numbers:
            raise ValueError("duplicate room number")
        numbers.add(room["number"])
    for booking in data["reservations"]:
        interval(booking["arrival"], booking["departure"])
        linked("guests", booking["guest_id"])
        room_type = linked("room_types", booking["room_type_id"])
        if booking["party_size"] > room_type["capacity"]:
            raise ValueError("party exceeds capacity")
        if booking.get("room_id"):
            room = linked("rooms", booking["room_id"])
            if room["room_type_id"] != room_type["entity_id"]:
                raise ValueError("room type mismatch")
        elif booking["status"] == "confirmed":
            raise ValueError("Phase A confirmation requires assigned room")
    active_rooms, used_bookings = set(), set()
    for stay in data["stays"]:
        booking = linked("reservations", stay["reservation_id"])
        linked("rooms", stay["room_id"])
        if booking["status"] != "confirmed" or booking.get("room_id") != stay["room_id"]:
            raise ValueError("stay requires matching confirmed reservation")
        if stay["reservation_id"] in used_bookings:
            raise ValueError("one stay per reservation in Phase A")
        used_bookings.add(stay["reservation_id"])
        out = stay.get("checked_out_at")
        if (stay["status"] == "checked_out") != (out is not None):
            raise ValueError("checkout status/timestamp mismatch")
        if out and parse_instant(out) < parse_instant(stay["checked_in_at"]):
            raise ValueError("checkout before check-in")
        if stay["status"] == "checked_in":
            if stay["room_id"] in active_rooms:
                raise ValueError("multiple active stays in room")
            active_rooms.add(stay["room_id"])
    pairs = set()
    counts = {}
    for occupant in data["stay_guests"]:
        stay = linked("stays", occupant["stay_id"])
        linked("guests", occupant["guest_id"])
        pair = (occupant["stay_id"], occupant["guest_id"])
        if pair in pairs:
            raise ValueError("duplicate registered occupant")
        pairs.add(pair)
        joined = parse_instant(occupant["joined_at"])
        left = occupant.get("left_at")
        if joined < parse_instant(stay["checked_in_at"]):
            raise ValueError("occupant arrived before stay")
        if left and parse_instant(left) < joined:
            raise ValueError("occupant left before arrival")
        if stay.get("checked_out_at") and (
                not left or parse_instant(left) > parse_instant(stay["checked_out_at"])):
            raise ValueError("occupant exceeds stay")
        counts[stay["entity_id"]] = counts.get(stay["entity_id"], 0) + 1
    for stay in data["stays"]:
        booking = linked("reservations", stay["reservation_id"])
        if not 1 <= counts.get(stay["entity_id"], 0) <= booking["party_size"]:
            raise ValueError("stay needs registered occupants within party size")
    for block in data["room_blocks"]:
        linked("rooms", block["room_id"])
        interval(block["start"], block["end"])
    confirmed = [r for r in data["reservations"] if r["status"] == "confirmed"]
    for i, a in enumerate(confirmed):
        for b in confirmed[i + 1:]:
            if a["room_id"] == b["room_id"] and overlaps(
                    a["arrival"], a["departure"], b["arrival"], b["departure"]):
                raise ValueError("conflicting confirmed reservations")
    return indexes


def room_eligibility(data, reservation_id, room_id, *, check_in=False,
                     today=None, staff_approved=False):
    """Check a proposed allocation or arrival against a complete local snapshot.

    today is an explicit hotel-local date, never the machine clock. No mutation.
    Occupied rooms conservatively fail even for future allocation until checkout.
    Confirmed assignments cannot change through this check, in either mode.
    """
    index = validate_snapshot(data)
    if reservation_id not in index["reservations"] or room_id not in index["rooms"]:
        raise ValueError("unknown reservation or room")
    booking = index["reservations"][reservation_id]
    room = index["rooms"][room_id]
    reasons = []
    if booking["status"] == "cancelled":
        reasons.append("cancelled")
    if booking["status"] == "confirmed" and booking["room_id"] != room_id:
        reasons.append("confirmed_reservation_assigned_elsewhere")
    if not room["enabled"]:
        reasons.append("room_disabled")
    if room["room_type_id"] != booking["room_type_id"]:
        reasons.append("wrong_room_type")
    if any(s["room_id"] == room_id and s["status"] == "checked_in"
           for s in data["stays"]):
        reasons.append("occupied")
    if any(s["reservation_id"] == reservation_id for s in data["stays"]):
        reasons.append("reservation_already_used")
    if any(r["entity_id"] != reservation_id and r.get("room_id") == room_id
           and r["status"] == "confirmed" and overlaps(
               booking["arrival"], booking["departure"], r["arrival"], r["departure"])
           for r in data["reservations"]):
        reasons.append("reservation_overlap")
    # An active maintenance block has a *planned* end, not automatic repair
    # approval. Once started, it keeps the room unsafe until explicitly
    # released; a booking ending before the block begins remains unaffected.
    if any(b["room_id"] == room_id and b["status"] == "active"
           and parse_day(b["start"]) < parse_day(booking["departure"])
           for b in data["room_blocks"]):
        reasons.append("maintenance_block")
    if check_in:
        current = parse_day(today)
        if not parse_day(booking["arrival"]) <= current < parse_day(booking["departure"]):
            reasons.append("outside_booking_dates")
        if booking["status"] != "confirmed":
            reasons.append("not_confirmed")
        if booking.get("room_id") != room_id:
            reasons.append("room_not_assigned")
        if room["housekeeping"] != "ready":
            reasons.append("housekeeping_not_ready")
        if not staff_approved:
            reasons.append("staff_approval_required")
    return tuple(reasons)
