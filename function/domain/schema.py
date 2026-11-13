"""Proposed Workpeg column definitions; never provisioned by this module.

UUID columns are application references, NOT platform foreign keys.
"""


def field(name, kind="text", *, required=True, choices=None, metadata=None):
    result = dict(id=name, name=name, type=kind, required=required)
    if choices:
        result["options"] = {"choices": [{"ref": c, "tag": c} for c in choices]}
    if metadata:
        result["metadata"] = metadata
    return result


def choice(name, *values):
    return field(name, "mutable_select", choices=values)


def ref(name, required=True):
    return field(name, "uuid", required=required)


def day(name):
    return field(name, "datetime", metadata={"type": "date"})


def instant(name, required=True):
    return field(name, "datetime", required=required, metadata={"type": "datetime"})


TABLES = {
    "room_types": [field("name"), field("capacity", "number")],
    "rooms": [field("number"), ref("room_type_id"), field("enabled", "boolean"),
              choice("housekeeping", "ready", "dirty", "cleaning", "inspection")],
    "guests": [field("display_name")],
    "reservations": [ref("guest_id"), ref("room_type_id"), ref("room_id", False),
                     day("arrival"), day("departure"), field("party_size", "number"),
                     choice("source", "advance", "walk_in"),
                     choice("status", "pending_confirmation", "confirmed", "cancelled")],
    "stays": [ref("reservation_id"), ref("room_id"), instant("checked_in_at"),
              instant("checked_out_at", False),
              choice("status", "checked_in", "checked_out")],
    "stay_guests": [ref("stay_id"), ref("guest_id"), instant("joined_at"),
                    instant("left_at", False)],
    "room_blocks": [ref("room_id"), day("start"), day("end"), field("reason"),
                    choice("status", "active", "released")],
}


def proposed_tables():
    """Fresh payload-shaped specifications, not a migration or API adapter."""
    from copy import deepcopy
    return [dict(name=name, namespace="roomay_hotel_v1", permission="700",
                 columns=[dict(deepcopy(column), position=(i + 1) * 1000)
                          for i, column in enumerate([ref("entity_id"), *columns])])
            for name, columns in TABLES.items()]
