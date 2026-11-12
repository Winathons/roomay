"""Read-only receptionist projections over a validated Roomay snapshot.

The projection is deliberately separate from persistence.  It reuses the
canonical hotel validator and eligibility rules and never authorizes a write.
"""
from .hotel import parse_day, room_eligibility, validate_snapshot


OPEN_REQUEST_STATUSES = {
    "received", "assigned", "acknowledged", "in_progress", "reopened", "escalated",
}


def _request_audit_projection(request, events):
    """Project safe audit fields without implying delivery or acknowledgement."""
    ordered = sorted(events, key=lambda item: item["sequence"])
    latest = next((event for event in ordered
                   if event["event_id"] == request["last_event_id"]), None)
    if not ordered:
        audit_status = "No audit event visible"
    elif latest is None:
        audit_status = "Audit history incomplete; latest request event is not visible"
    elif latest["to_status"] != request["status"]:
        audit_status = "Audit history does not match the current request status"
    elif latest["commit_state"] == "pending":
        audit_status = "Latest audit event is pending commit; delivery is not represented"
    else:
        audit_status = "Latest event is marked committed; delivery is not represented"
    return audit_status, [{
        "sequence": event["sequence"], "event_type": event["event_type"],
        "from_status": event["from_status"], "to_status": event["to_status"],
        "actor_kind": event["actor_kind"],
        "actor_department": event["actor_department"],
        "occurred_at": event["occurred_at"],
        "commit_state": event["commit_state"],
    } for event in ordered]


def build_reception_snapshot(hotel, service_requests, today, service_request_audit=None):
    """Return a read-only receptionist view for an explicit hotel-local day.

    ``service_request_audit`` is optional for existing callers. Only allowlisted
    timeline fields are projected; operation signatures, actor identifiers and
    free-text audit reasons are not exposed by this read model.
    """
    indexes = validate_snapshot(hotel)
    current = parse_day(today)
    room_types = indexes["room_types"]
    guests = indexes["guests"]
    reservations = indexes["reservations"]
    active_stays = {
        stay["room_id"]: stay for stay in hotel["stays"]
        if stay["status"] == "checked_in"
    }
    occupants_by_stay = {}
    for occupant in hotel["stay_guests"]:
        occupants_by_stay.setdefault(occupant["stay_id"], []).append(
            guests[occupant["guest_id"]]["display_name"])
    active_blocks = {}
    for block in hotel["room_blocks"]:
        if (block["status"] == "active"
                and parse_day(block["start"]) <= current < parse_day(block["end"])):
            active_blocks.setdefault(block["room_id"], []).append(block)

    arrivals, departures, overdue_departures, in_house, room_cards = [], [], [], [], []
    ready_for_check_in = 0
    for room in hotel["rooms"]:
        stay = active_stays.get(room["entity_id"])
        assigned = [
            booking for booking in hotel["reservations"]
            if booking.get("room_id") == room["entity_id"]
            and booking["status"] == "confirmed"
            and parse_day(booking["arrival"]) <= current < parse_day(booking["departure"])
        ]
        booking = reservations[stay["reservation_id"]] if stay else (
            assigned[0] if assigned else None)
        guest = guests[booking["guest_id"]] if booking else None
        if stay:
            occupancy = "In house"
            departure_status = "Scheduled"
            if parse_day(booking["departure"]) < current:
                departure_status = "OVERDUE"
                overdue_departures.append({
                    "guest": guest["display_name"], "room": room["number"],
                    "departure": booking["departure"],
                })
            elif booking["departure"] == today:
                departure_status = "Due today"
            in_house.append({
                "guest": ", ".join(occupants_by_stay.get(stay["entity_id"], [])),
                "room": room["number"],
                "departure": booking["departure"],
                "departure_status": departure_status,
            })
            if booking["departure"] == today:
                departures.append({
                    "guest": guest["display_name"], "room": room["number"],
                    "departure": booking["departure"],
                })
        elif booking and booking["arrival"] == today:
            occupancy = "Arriving today"
            arrivals.append({
                "reservation_id": booking["entity_id"],
                "guest": guest["display_name"], "room": room["number"],
                "arrival": booking["arrival"],
            })
            if not room_eligibility(
                    hotel, booking["entity_id"], room["entity_id"], check_in=True,
                    today=today, staff_approved=True):
                ready_for_check_in += 1
        elif booking:
            occupancy = "Reserved"
        else:
            occupancy = "Vacant"
        block = active_blocks.get(room["entity_id"], [])
        room_cards.append({
            "room_id": room["entity_id"], "number": room["number"],
            "room_type": room_types[room["room_type_id"]]["name"],
            "occupancy": occupancy,
            "housekeeping": room["housekeeping"],
            "maintenance": "Blocked" if block else "Clear",
            "maintenance_reason": block[0]["reason"] if block else "",
            "guest": (", ".join(occupants_by_stay.get(stay["entity_id"], []))
                      if stay else guest["display_name"] if guest else ""),
            "reservation_status": booking["status"] if booking else "",
            "stay_status": stay["status"] if stay else "",
            "enabled": room["enabled"],
        })

    room_numbers = {room["entity_id"]: room["number"] for room in hotel["rooms"]}
    audit_by_request = {}
    requests_by_id = {request["request_id"]: request for request in service_requests}
    for event in service_request_audit or []:
        request = requests_by_id.get(event["request_id"])
        if request is None or event["hotel_id"] != request["hotel_id"]:
            raise ValueError("service request audit relationship is invalid")
        events = audit_by_request.setdefault(event["request_id"], [])
        if any(existing["sequence"] == event["sequence"] for existing in events):
            raise ValueError("service request audit sequence is duplicated")
        events.append(event)
    requests = []
    for request in service_requests:
        audit_status, audit_history = _request_audit_projection(
            request, audit_by_request.get(request["request_id"], []))
        guest = guests.get(request["guest_id"])
        requests.append({
            "request_id": request["request_id"],
            "description": request["description"],
            "category": request["category"],
            "department": request["department"],
            "urgency": request["urgency"],
            "status": request["status"],
            "room": room_numbers.get(request["room_id"], "Unknown"),
            "guest": guest["display_name"] if guest else "Unknown",
            "audit_status": audit_status,
            "audit_history": audit_history,
        })

    return {
        "date": today,
        "metrics": {
            "in_house": len(in_house), "arrivals": len(arrivals),
            "departures": len(departures), "ready_for_check_in": ready_for_check_in,
            "overdue_active_stays": len(overdue_departures),
            "needs_cleaning": sum(room["housekeeping"] != "ready" for room in hotel["rooms"]),
            "maintenance_blocked_rooms": len(active_blocks),
            "open_requests": sum(
                request["status"] in OPEN_REQUEST_STATUSES for request in service_requests),
        },
        "arrivals": arrivals, "departures": departures,
        "overdue_departures": overdue_departures, "in_house": in_house,
        "rooms": room_cards, "requests": requests,
    }
