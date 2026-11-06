"""Deterministic fictional records, returned fresh; no seed writes."""
from uuid import NAMESPACE_URL, uuid5


def uid(label):
    return str(uuid5(NAMESPACE_URL, "roomay:synthetic:v1:" + label))


def synthetic_hotel():
    data = {
        "room_types": [dict(entity_id=uid(t), name=t, capacity=c)
                       for t, c in [("standard", 2), ("suite", 4)]],
        "rooms": [dict(entity_id=uid(str(n)), number=str(n),
                       room_type_id=uid("standard" if n <= 206 else "suite"),
                       enabled=True, housekeeping="dirty" if n == 203 else "ready")
                  for n in range(201, 211)],
        "guests": [dict(entity_id=uid(g), display_name="Fictional " + g)
                   for g in ["Guest A", "Guest B", "Guest C"]],
        "reservations": [], "stays": [], "stay_guests": [], "room_blocks": [],
    }
    for label, guest, room, arrival, departure, source in [
        ("future", "Guest A", "201", "2026-11-13", "2026-11-15", "advance"),
        ("walk-in", "Guest B", "202", "2026-11-06", "2026-11-07", "walk_in"),
        ("in-house", "Guest C", "205", "2026-11-05", "2026-11-08", "advance"),
    ]:
        data["reservations"].append(dict(
            entity_id=uid(label), guest_id=uid(guest), room_type_id=uid("standard"),
            room_id=uid(room), arrival=arrival, departure=departure, party_size=1,
            source=source, status="confirmed"))
    data["stays"].append(dict(entity_id=uid("stay"), reservation_id=uid("in-house"),
                              room_id=uid("205"), status="checked_in",
                              checked_in_at="2026-11-05T15:00:00+01:00"))
    data["stay_guests"].append(dict(entity_id=uid("occupant"), stay_id=uid("stay"),
                                    guest_id=uid("Guest C"),
                                    joined_at="2026-11-05T15:00:00+01:00"))
    data["room_blocks"].append(dict(entity_id=uid("block"), room_id=uid("205"),
                                     start="2026-11-06", end="2026-11-09",
                                     reason="Fictional plumbing inspection",
                                     status="active"))
    return data
