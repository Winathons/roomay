"""Typed receptionist view model derived from Roomay's canonical demo snapshot.

This module owns presentation mapping only. It calls the existing hotel validator
and eligibility function instead of duplicating booking/check-in rules.
"""
from typing import TypedDict

from .fixtures import synthetic_hotel, uid
from .hotel import room_eligibility, validate_snapshot


DEMO_DATE = "2026-11-06"
DEMO_LABEL = "DEMO DATA — NOT CONNECTED TO LIVE WORKPEG"


class MetricView(TypedDict):
    label: str
    value: int
    helper: str
    tone: str


class RoomView(TypedDict):
    number: str
    room_type: str
    occupancy: str
    housekeeping: str
    maintenance: str
    filters: list[str]
    guest: str
    stay_note: str
    accent: str


class RequestView(TypedDict):
    reference: str
    description: str
    category: str
    department: str
    priority: str
    status: str
    room: str
    tone: str


class ReceptionDemo(TypedDict):
    date_label: str
    metrics: list[MetricView]
    rooms: list[RoomView]
    requests: list[RequestView]
    arrivals: list[str]
    departures: list[str]
    in_house: list[str]
    pending_enquiries: list[str]


DEMO_REQUESTS: list[RequestView] = [
    {
        "reference": "REQ-104",
        "description": "Extra towels requested before evening turndown",
        "category": "Guest comfort",
        "department": "Housekeeping",
        "priority": "Normal",
        "status": "New",
        "room": "Room 205",
        "tone": "info",
    },
    {
        "reference": "REQ-105",
        "description": "Inspect reported plumbing noise",
        "category": "Room maintenance",
        "department": "Maintenance",
        "priority": "Urgent",
        "status": "Acknowledged",
        "room": "Room 205",
        "tone": "critical",
    },
    {
        "reference": "REQ-106",
        "description": "Confirm airport pickup window",
        "category": "Transport",
        "department": "Front desk",
        "priority": "Normal",
        "status": "In progress",
        "room": "No room assigned",
        "tone": "warning",
    },
    {
        "reference": "REQ-103",
        "description": "Share breakfast hours and location",
        "category": "Hotel information",
        "department": "Front desk",
        "priority": "Low",
        "status": "Resolved",
        "room": "Room 202",
        "tone": "success",
    },
]


def filter_rooms(rooms: list[RoomView], filter_name: str) -> list[RoomView]:
    """Filter the already-derived board; this does not decide room eligibility."""
    if filter_name == "All rooms":
        return list(rooms)
    return [room for room in rooms if filter_name in room["filters"]]


def build_reception_demo() -> ReceptionDemo:
    snapshot = synthetic_hotel()
    indexes = validate_snapshot(snapshot)
    stays = [stay for stay in snapshot["stays"] if stay["status"] == "checked_in"]
    active_by_room = {stay["room_id"]: stay for stay in stays}
    stay_reservations = {stay["reservation_id"] for stay in stays}
    active_blocks = {
        block["room_id"] for block in snapshot["room_blocks"]
        if block["status"] == "active"
    }
    arrivals = [
        booking for booking in snapshot["reservations"]
        if booking["status"] == "confirmed"
        and booking["arrival"] == DEMO_DATE
        and booking["entity_id"] not in stay_reservations
    ]
    departures = [
        stay for stay in stays
        if indexes["reservations"][stay["reservation_id"]]["departure"] == DEMO_DATE
    ]
    ready_arrival_rooms = {
        booking["room_id"] for booking in arrivals
        if room_eligibility(
            snapshot, booking["entity_id"], booking["room_id"],
            check_in=True, today=DEMO_DATE, staff_approved=True,
        ) == ()
    }

    type_names = {
        room_type["entity_id"]: room_type["name"].title()
        for room_type in snapshot["room_types"]
    }
    arrival_by_room = {booking["room_id"]: booking for booking in arrivals}
    confirmed_by_room = {
        booking["room_id"]: booking for booking in snapshot["reservations"]
        if booking["status"] == "confirmed" and booking.get("room_id")
    }
    rooms: list[RoomView] = []
    for room in snapshot["rooms"]:
        room_id = room["entity_id"]
        active_stay = active_by_room.get(room_id)
        arrival = arrival_by_room.get(room_id)
        reservation = confirmed_by_room.get(room_id)
        if active_stay:
            booking = indexes["reservations"][active_stay["reservation_id"]]
            guest = indexes["guests"][booking["guest_id"]]["display_name"]
            occupancy = "In house"
            stay_note = f"Checked in · planned departure {booking['departure']}"
            filters = ["In house"]
            accent = "critical" if room_id in active_blocks else "accent"
        elif arrival:
            guest = indexes["guests"][arrival["guest_id"]]["display_name"]
            occupancy = "Arriving today"
            stay_note = "Confirmed arrival · not checked in"
            filters = ["Arriving today"]
            if room_id in ready_arrival_rooms:
                filters.append("Ready for arrival")
            accent = "success" if room_id in ready_arrival_rooms else "warning"
        elif reservation:
            guest = indexes["guests"][reservation["guest_id"]]["display_name"]
            occupancy = "Reserved"
            stay_note = f"Future arrival {reservation['arrival']} · not in house"
            filters = ["Reserved"]
            accent = "info"
        else:
            guest = "No guest linked"
            occupancy = "Vacant"
            stay_note = "No active stay or confirmed arrival"
            filters = ["Vacant"]
            accent = "neutral"
        housekeeping = room["housekeeping"].title()
        maintenance = "Blocked" if room_id in active_blocks else "Clear"
        if housekeeping == "Dirty" and not active_stay:
            filters.append("Needs cleaning")
            accent = "warning"
        if maintenance == "Blocked":
            filters.append("Blocked")
            accent = "critical"
        rooms.append({
            "number": room["number"],
            "room_type": type_names[room["room_type_id"]],
            "occupancy": occupancy,
            "housekeeping": housekeeping,
            "maintenance": maintenance,
            "filters": filters,
            "guest": guest,
            "stay_note": stay_note,
            "accent": accent,
        })

    in_house_guests = []
    for stay in stays:
        booking = indexes["reservations"][stay["reservation_id"]]
        guest = indexes["guests"][booking["guest_id"]]
        room = indexes["rooms"][stay["room_id"]]
        in_house_guests.append(f"{guest['display_name']} · Room {room['number']}")
    arrival_labels = [
        f"{indexes['guests'][booking['guest_id']]['display_name']} · Room {indexes['rooms'][booking['room_id']]['number']}"
        for booking in arrivals
    ]
    departure_labels = [
        f"Room {indexes['rooms'][stay['room_id']]['number']}"
        for stay in departures
    ]
    outstanding = [request for request in DEMO_REQUESTS if request["status"] != "Resolved"]
    metrics: list[MetricView] = [
        {"label": "In house", "value": len(stays), "helper": "Physical active stays", "tone": "accent"},
        {"label": "Arrivals", "value": len(arrivals), "helper": "Confirmed, not checked in", "tone": "info"},
        {"label": "Departures", "value": len(departures), "helper": "Planned for today", "tone": "neutral"},
        {"label": "Ready for check-in", "value": len(ready_arrival_rooms), "helper": "Eligible confirmed arrivals", "tone": "success"},
        {"label": "Needs cleaning", "value": len([room for room in rooms if room["housekeeping"] == "Dirty"]), "helper": "Housekeeping action", "tone": "warning"},
        {"label": "Maintenance blocks", "value": len(active_blocks), "helper": "Out of assignment", "tone": "critical"},
        {"label": "Open requests", "value": len(outstanding), "helper": "Across departments", "tone": "purple"},
    ]
    return {
        "date_label": "Friday, 6 November 2026",
        "metrics": metrics,
        "rooms": rooms,
        "requests": [dict(request) for request in DEMO_REQUESTS],
        "arrivals": arrival_labels,
        "departures": departure_labels,
        "in_house": in_house_guests,
        "pending_enquiries": ["Fictional Guest D · enquiry awaiting confirmation · not a stay"],
    }
