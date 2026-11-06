"""Offline receptionist dashboard compiled by the Workpeg UI compiler.

The literal projection below is intentionally pinned by tests to
``domain.reception_demo``. Workpeg's compiler parses this module's AST and does
not execute the Python domain package, so the UI needs compiler-safe literals.
No Workpeg data helper is imported or called from this route.
"""
from workpeg.ui import App, State, Button, Column, Container, Divider, Row, Tab, Tabs, Tag, Text, Wrap


DEMO_LABEL = "DEMO DATA \N{EM DASH} NOT CONNECTED TO LIVE WORKPEG"
DATE_LABEL = "Friday, 6 November 2026"

METRICS = [
    {"label": "In house", "value": 1, "helper": "Physical active stays", "tone": "accent"},
    {"label": "Arrivals", "value": 1, "helper": "Confirmed, not checked in", "tone": "info"},
    {"label": "Departures", "value": 0, "helper": "Planned for today", "tone": "neutral"},
    {"label": "Ready for check-in", "value": 1, "helper": "Eligible confirmed arrivals", "tone": "success"},
    {"label": "Needs cleaning", "value": 1, "helper": "Housekeeping action", "tone": "warning"},
    {"label": "Maintenance blocks", "value": 1, "helper": "Out of assignment", "tone": "critical"},
    {"label": "Open requests", "value": 3, "helper": "Across departments", "tone": "purple"},
]

ROOMS = [
    {"number": "201", "room_type": "Standard", "occupancy": "Reserved", "housekeeping": "Ready", "maintenance": "Clear", "filters": ["Reserved"], "guest": "Fictional Guest A", "stay_note": "Future arrival 2026-11-13 \N{MIDDLE DOT} not in house", "accent": "info"},
    {"number": "202", "room_type": "Standard", "occupancy": "Arriving today", "housekeeping": "Ready", "maintenance": "Clear", "filters": ["Arriving today", "Ready for arrival"], "guest": "Fictional Guest B", "stay_note": "Confirmed arrival \N{MIDDLE DOT} not checked in", "accent": "success"},
    {"number": "203", "room_type": "Standard", "occupancy": "Vacant", "housekeeping": "Dirty", "maintenance": "Clear", "filters": ["Vacant", "Needs cleaning"], "guest": "No guest linked", "stay_note": "No active stay or confirmed arrival", "accent": "warning"},
    {"number": "204", "room_type": "Standard", "occupancy": "Vacant", "housekeeping": "Ready", "maintenance": "Clear", "filters": ["Vacant"], "guest": "No guest linked", "stay_note": "No active stay or confirmed arrival", "accent": "neutral"},
    {"number": "205", "room_type": "Standard", "occupancy": "In house", "housekeeping": "Ready", "maintenance": "Blocked", "filters": ["In house", "Blocked"], "guest": "Fictional Guest C", "stay_note": "Checked in \N{MIDDLE DOT} planned departure 2026-11-08", "accent": "critical"},
    {"number": "206", "room_type": "Standard", "occupancy": "Vacant", "housekeeping": "Ready", "maintenance": "Clear", "filters": ["Vacant"], "guest": "No guest linked", "stay_note": "No active stay or confirmed arrival", "accent": "neutral"},
    {"number": "207", "room_type": "Suite", "occupancy": "Vacant", "housekeeping": "Ready", "maintenance": "Clear", "filters": ["Vacant"], "guest": "No guest linked", "stay_note": "No active stay or confirmed arrival", "accent": "neutral"},
    {"number": "208", "room_type": "Suite", "occupancy": "Vacant", "housekeeping": "Ready", "maintenance": "Clear", "filters": ["Vacant"], "guest": "No guest linked", "stay_note": "No active stay or confirmed arrival", "accent": "neutral"},
    {"number": "209", "room_type": "Suite", "occupancy": "Vacant", "housekeeping": "Ready", "maintenance": "Clear", "filters": ["Vacant"], "guest": "No guest linked", "stay_note": "No active stay or confirmed arrival", "accent": "neutral"},
    {"number": "210", "room_type": "Suite", "occupancy": "Vacant", "housekeeping": "Ready", "maintenance": "Clear", "filters": ["Vacant"], "guest": "No guest linked", "stay_note": "No active stay or confirmed arrival", "accent": "neutral"},
]

REQUESTS = [
    {"reference": "REQ-104", "description": "Extra towels requested before evening turndown", "category": "Guest comfort", "department": "Housekeeping", "priority": "Normal", "status": "New", "room": "Room 205", "tone": "info"},
    {"reference": "REQ-105", "description": "Inspect reported plumbing noise", "category": "Room maintenance", "department": "Maintenance", "priority": "Urgent", "status": "Acknowledged", "room": "Room 205", "tone": "critical"},
    {"reference": "REQ-106", "description": "Confirm airport pickup window", "category": "Transport", "department": "Front desk", "priority": "Normal", "status": "In progress", "room": "No room assigned", "tone": "warning"},
    {"reference": "REQ-103", "description": "Share breakfast hours and location", "category": "Hotel information", "department": "Front desk", "priority": "Low", "status": "Resolved", "room": "Room 202", "tone": "success"},
]

ARRIVALS = ["Fictional Guest B \N{MIDDLE DOT} Room 202"]
DEPARTURES = []
IN_HOUSE = ["Fictional Guest C \N{MIDDLE DOT} Room 205"]
PENDING_ENQUIRIES = ["Fictional Guest D \N{MIDDLE DOT} enquiry awaiting confirmation \N{MIDDLE DOT} not a stay"]


class ReceptionDemo(App):
    metrics = State([
        {"label": "In house", "value": 1, "helper": "Physical active stays", "tone": "accent"},
        {"label": "Arrivals", "value": 1, "helper": "Confirmed, not checked in", "tone": "info"},
        {"label": "Departures", "value": 0, "helper": "Planned for today", "tone": "neutral"},
        {"label": "Ready for check-in", "value": 1, "helper": "Eligible confirmed arrivals", "tone": "success"},
        {"label": "Needs cleaning", "value": 1, "helper": "Housekeeping action", "tone": "warning"},
        {"label": "Maintenance blocks", "value": 1, "helper": "Out of assignment", "tone": "critical"},
        {"label": "Open requests", "value": 3, "helper": "Across departments", "tone": "purple"},
    ])
    rooms = State([
        {"number": "201", "room_type": "Standard", "occupancy": "Reserved", "housekeeping": "Ready", "maintenance": "Clear", "filters": ["Reserved"], "guest": "Fictional Guest A", "stay_note": "Future arrival 2026-11-13 \N{MIDDLE DOT} not in house", "accent": "info"},
        {"number": "202", "room_type": "Standard", "occupancy": "Arriving today", "housekeeping": "Ready", "maintenance": "Clear", "filters": ["Arriving today", "Ready for arrival"], "guest": "Fictional Guest B", "stay_note": "Confirmed arrival \N{MIDDLE DOT} not checked in", "accent": "success"},
        {"number": "203", "room_type": "Standard", "occupancy": "Vacant", "housekeeping": "Dirty", "maintenance": "Clear", "filters": ["Vacant", "Needs cleaning"], "guest": "No guest linked", "stay_note": "No active stay or confirmed arrival", "accent": "warning"},
        {"number": "204", "room_type": "Standard", "occupancy": "Vacant", "housekeeping": "Ready", "maintenance": "Clear", "filters": ["Vacant"], "guest": "No guest linked", "stay_note": "No active stay or confirmed arrival", "accent": "neutral"},
        {"number": "205", "room_type": "Standard", "occupancy": "In house", "housekeeping": "Ready", "maintenance": "Blocked", "filters": ["In house", "Blocked"], "guest": "Fictional Guest C", "stay_note": "Checked in \N{MIDDLE DOT} planned departure 2026-11-08", "accent": "critical"},
        {"number": "206", "room_type": "Standard", "occupancy": "Vacant", "housekeeping": "Ready", "maintenance": "Clear", "filters": ["Vacant"], "guest": "No guest linked", "stay_note": "No active stay or confirmed arrival", "accent": "neutral"},
        {"number": "207", "room_type": "Suite", "occupancy": "Vacant", "housekeeping": "Ready", "maintenance": "Clear", "filters": ["Vacant"], "guest": "No guest linked", "stay_note": "No active stay or confirmed arrival", "accent": "neutral"},
        {"number": "208", "room_type": "Suite", "occupancy": "Vacant", "housekeeping": "Ready", "maintenance": "Clear", "filters": ["Vacant"], "guest": "No guest linked", "stay_note": "No active stay or confirmed arrival", "accent": "neutral"},
        {"number": "209", "room_type": "Suite", "occupancy": "Vacant", "housekeeping": "Ready", "maintenance": "Clear", "filters": ["Vacant"], "guest": "No guest linked", "stay_note": "No active stay or confirmed arrival", "accent": "neutral"},
        {"number": "210", "room_type": "Suite", "occupancy": "Vacant", "housekeeping": "Ready", "maintenance": "Clear", "filters": ["Vacant"], "guest": "No guest linked", "stay_note": "No active stay or confirmed arrival", "accent": "neutral"},
    ])
    requests = State([
        {"reference": "REQ-104", "description": "Extra towels requested before evening turndown", "category": "Guest comfort", "department": "Housekeeping", "priority": "Normal", "status": "New", "room": "Room 205", "tone": "info"},
        {"reference": "REQ-105", "description": "Inspect reported plumbing noise", "category": "Room maintenance", "department": "Maintenance", "priority": "Urgent", "status": "Acknowledged", "room": "Room 205", "tone": "critical"},
        {"reference": "REQ-106", "description": "Confirm airport pickup window", "category": "Transport", "department": "Front desk", "priority": "Normal", "status": "In progress", "room": "No room assigned", "tone": "warning"},
        {"reference": "REQ-103", "description": "Share breakfast hours and location", "category": "Hotel information", "department": "Front desk", "priority": "Low", "status": "Resolved", "room": "Room 202", "tone": "success"},
    ])
    arrivals = State(["Fictional Guest B \N{MIDDLE DOT} Room 202"])
    in_house = State(["Fictional Guest C \N{MIDDLE DOT} Room 205"])
    pending_enquiries = State(["Fictional Guest D \N{MIDDLE DOT} enquiry awaiting confirmation \N{MIDDLE DOT} not a stay"])
    room_filter = State("All rooms")
    selected_room = State("202")
    feedback = State("Preview mode is ready. No changes can be saved from this screen.")
    failure = State("")

    def set_filter(self, name):
        self.room_filter = name
        self.failure = ""
        self.feedback = f"Showing {name.lower()}. This only filters demo data."

    def select_room(self, number):
        self.selected_room = number
        self.failure = ""
        self.feedback = f"Room {number} selected. Details are read-only demo data."

    def preview_action(self, action):
        self.failure = f"{action} is unavailable in this demo. No Workpeg write was attempted."

    def build(self):
        return Container(
            Column(
                Container(
                    Wrap(
                        Column(
                            Text("Roomay", variant="title", weight="bold", style={"color": "#ffffff"}),
                            Text("Reception workspace", variant="caption", style={"color": "#c9ddd5"}),
                            gap=2,
                        ),
                        Text(DATE_LABEL, variant="label", style={"color": "#e8f2ee"}),
                        spacing=16,
                        cross_alignment="center",
                    ),
                    padding=24,
                    radius=20,
                    color="#12372a",
                    style={"box-shadow": "0 16px 40px rgba(18,55,42,0.18)"},
                ),
                Container(
                    Wrap(
                        Tag("OFFLINE PROTOTYPE", tone="warning", size="sm"),
                        Text(DEMO_LABEL, variant="label", weight="bold", style={"color": "#5f3b00"}),
                        spacing=12,
                        cross_alignment="center",
                    ),
                    padding=16,
                    radius=14,
                    color="#fff2cc",
                    style={"border": "1px solid #e6b84a"},
                ),
                Container(
                    Wrap(
                        Text(self.feedback, variant="body", tone="info", weight="medium"),
                        Text(self.failure, variant="body", tone="danger", weight="semibold", visible=self.failure != ""),
                        Button("Preview walk-in", on_click=lambda: self.preview_action("Walk-in creation"), variant="outline-color", size="sm", aria_label="Preview unavailable walk-in creation"),
                        Button("Preview check-in", on_click=lambda: self.preview_action("Guest check-in"), variant="outline-gray", size="sm", aria_label="Preview unavailable guest check-in"),
                        spacing=12,
                        cross_alignment="center",
                    ),
                    padding=16,
                    radius=14,
                    color="#eef7f3",
                    style={"border": "1px solid #cde4da"},
                ),
                Tabs(
                    Tab("Today", Column(
                        Column(
                            Text("Today at a glance", variant="heading", weight="bold"),
                            Text("Operational signals derived from the canonical fictional hotel snapshot.", tone="muted"),
                            gap=4,
                        ),
                        Wrap(
                            *[
                                Container(
                                    Column(
                                        Text(metric["label"], variant="label", tone="muted", weight="medium"),
                                        Text(metric["value"], variant="display", weight="bold", style={"color": "#12372a"}),
                                        Text(metric["helper"], variant="caption", tone="muted"),
                                        gap=6,
                                    ),
                                    padding=18,
                                    width=210,
                                    radius=16,
                                    color="#ffffff",
                                    style={"border": "1px solid #dce7e2", "min-height": "142px"},
                                ) for metric in self.metrics
                            ],
                            spacing=12,
                            run_spacing=12,
                        ),
                        Wrap(
                            Container(Column(
                                Text("Currently in house", variant="subheading", weight="bold"),
                                Column(*[Text(item, weight="medium") for item in self.in_house], gap=8),
                                Text("A checked-in stay, not merely a reservation.", variant="caption", tone="muted"),
                                gap=12,
                            ), padding=20, width=330, radius=16, color="#ffffff", style={"border": "1px solid #dce7e2", "min-height": "180px"}),
                            Container(Column(
                                Text("Arrivals", variant="subheading", weight="bold"),
                                Column(*[Text(item, weight="medium") for item in self.arrivals], gap=8),
                                Text("Confirmed and eligible; not checked in.", variant="caption", tone="muted"),
                                gap=12,
                            ), padding=20, width=330, radius=16, color="#ffffff", style={"border": "1px solid #dce7e2", "min-height": "180px"}),
                            Container(Column(
                                Text("Departures", variant="subheading", weight="bold"),
                                Text("No departures planned today", tone="muted"),
                                Text("Empty state \N{EM DASH} nothing needs action.", variant="caption", tone="muted"),
                                gap=12,
                            ), padding=20, width=330, radius=16, color="#ffffff", style={"border": "1px solid #dce7e2", "min-height": "180px"}),
                            spacing=12,
                            run_spacing=12,
                        ),
                        Container(Column(
                            Text("Pending enquiry", variant="subheading", weight="bold"),
                            Column(*[Text(item) for item in self.pending_enquiries], gap=8),
                            Text("Pending reservations are not counted as arrivals or active stays.", variant="caption", tone="muted"),
                            gap=10,
                        ), padding=20, radius=16, color="#f8faf9", style={"border": "1px dashed #b8cbc3"}),
                        gap=20,
                    )),
                    Tab("Rooms", Column(
                        Column(
                            Text("Room board", variant="heading", weight="bold"),
                            Text("Occupancy, housekeeping and maintenance are separate signals.", tone="muted"),
                            gap=4,
                        ),
                        Wrap(
                            Button("All rooms", on_click=lambda: self.set_filter("All rooms"), variant="outline-color", size="sm", aria_label="Show all rooms"),
                            Button("In house", on_click=lambda: self.set_filter("In house"), variant="outline-color", size="sm", aria_label="Show in-house rooms"),
                            Button("Ready for arrival", on_click=lambda: self.set_filter("Ready for arrival"), variant="outline-color", size="sm", aria_label="Show rooms ready for arrival"),
                            Button("Needs cleaning", on_click=lambda: self.set_filter("Needs cleaning"), variant="outline-color", size="sm", aria_label="Show rooms needing cleaning"),
                            Button("Blocked", on_click=lambda: self.set_filter("Blocked"), variant="outline-color", size="sm", aria_label="Show maintenance-blocked rooms"),
                            spacing=8,
                            run_spacing=8,
                        ),
                        Text(f"Filter: {self.room_filter}", variant="label", weight="semibold"),
                        Wrap(
                            *[
                                Container(
                                    Column(
                                        Row(Text(f"Room {room['number']}", variant="subheading", weight="bold"), Tag(room["room_type"], tone="neutral", size="sm"), justify="space_between", align="center", gap=8),
                                        Text(room["occupancy"], variant="label", weight="semibold", style={"color": "#156b50"}),
                                        Divider(spacing=4),
                                        Text(f"Housekeeping \N{MIDDLE DOT} {room['housekeeping']}", variant="caption", tone="muted"),
                                        Text(f"Maintenance \N{MIDDLE DOT} {room['maintenance']}", variant="caption", tone="muted"),
                                        Button("View details", on_click=lambda: self.select_room(room["number"]), variant="text", size="sm", aria_label="View room details"),
                                        gap=8,
                                    ),
                                    padding=18,
                                    width=242,
                                    radius=16,
                                    color="#ffffff",
                                    style={"border": "1px solid #dce7e2", "min-height": "210px"},
                                ) for room in self.rooms if self.room_filter == "All rooms" or self.room_filter in room["filters"]
                            ],
                            spacing=12,
                            run_spacing=12,
                        ),
                        Column(*[
                            Container(Column(
                                Row(Text(f"Room {room['number']} details", variant="subheading", weight="bold"), Tag("READ ONLY", tone="info", size="sm"), justify="space_between", align="center", gap=12),
                                Text(f"{room['room_type']} \N{MIDDLE DOT} {room['occupancy']}", weight="semibold"),
                                Text(room["guest"]),
                                Text(room["stay_note"], tone="muted"),
                                Text(f"Housekeeping: {room['housekeeping']} \N{MIDDLE DOT} Maintenance: {room['maintenance']}", variant="caption", tone="muted"),
                                Button("Assign room \N{EM DASH} unavailable", on_click=lambda: self.preview_action("Room assignment"), variant="outline-gray", disabled=True, aria_label="Room assignment unavailable in demo"),
                                gap=10,
                            ), padding=20, radius=16, color="#eef7f3", style={"border": "1px solid #cde4da"})
                            for room in self.rooms if room["number"] == self.selected_room
                        ]),
                        gap=18,
                    )),
                    Tab("Requests", Column(
                        Column(
                            Text("Service requests", variant="heading", weight="bold"),
                            Text("A concise hand-off view across front desk, housekeeping and maintenance.", tone="muted"),
                            gap=4,
                        ),
                        Wrap(
                            *[
                                Container(
                                    Column(
                                        Row(Text(request["reference"], variant="label", weight="bold"), Tag(request["status"], tone="neutral", size="sm"), justify="space_between", align="center", gap=8),
                                        Text(request["description"], variant="subheading", weight="semibold"),
                                        Text(f"{request['category']} \N{MIDDLE DOT} {request['department']}", tone="muted"),
                                        Wrap(Tag(request["priority"], tone="neutral", size="sm"), Text(request["room"], variant="caption", tone="muted"), spacing=8, cross_alignment="center"),
                                        Button("Resolve \N{EM DASH} unavailable", on_click=lambda: self.preview_action("Request resolution"), variant="outline-gray", disabled=True, size="sm", aria_label="Request resolution unavailable in demo"),
                                        gap=10,
                                    ),
                                    padding=20,
                                    width=330,
                                    radius=16,
                                    color="#ffffff",
                                    style={"border": "1px solid #dce7e2", "min-height": "245px"},
                                ) for request in self.requests
                            ],
                            spacing=12,
                            run_spacing=12,
                        ),
                        gap=18,
                    )),
                    variant="secondary",
                    rounded=True,
                ),
                Divider(spacing=4),
                Text("Roomay offline reception prototype \N{MIDDLE DOT} No Workpeg tables, credentials, network requests or writes are used on this route.", variant="caption", tone="muted"),
                gap=18,
            ),
            padding=24,
            color="#f3f7f5",
            style={"min-height": "100vh"},
        )
