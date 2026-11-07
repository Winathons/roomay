"""Read-only receptionist projections over a validated Roomay snapshot.

The projection is deliberately separate from persistence.  It reuses the
canonical hotel validator and eligibility rules and never authorizes a write.
"""
from .hotel import parse_day, room_eligibility, validate_snapshot


OPEN_REQUEST_STATUSES = {
    "received", "assigned", "acknowledged", "in_progress", "reopened", "escalated",
}


def build_reception_snapshot(hotel, service_requests, today):
    """Return the read-only receptionist view for an explicit hotel-local day."""
    indexes = validate_snapshot(hotel)
    current = parse_day(today)
    room_types = indexes["room_types"]
    guests = indexes["guests"]
    reservations = indexes["reservations"]
    active_stays = {
        stay["room_id"]: stay for stay in hotel["stays"]
        if stay["status"] == "checked_in"
    }
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
                "guest": guest["display_name"], "room": room["number"],
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
            "guest": guest["display_name"] if guest else "",
            "enabled": room["enabled"],
        })

    room_numbers = {room["entity_id"]: room["number"] for room in hotel["rooms"]}
    requests = []
    for request in service_requests:
        requests.append({
            "request_id": request["request_id"],
            "description": request["description"],
            "category": request["category"],
            "department": request["department"],
            "urgency": request["urgency"],
            "status": request["status"],
            "room": room_numbers.get(request["room_id"], "Unknown"),
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
