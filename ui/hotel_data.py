"""Authenticated, read-only receptionist application over Workpeg tables.

The UI compiles with Workpeg 0.149.1. It never provisions, seeds, or mutates
records and fails closed when the complete owner-only table contract cannot be
read. Browser-local ``dates.today()`` is exposed rather than mislabelled as a
persisted hotel timezone.
"""
from workpeg.ui import (
    App, Authenticated, Button, Column, Container, Divider, Row, State, Tab,
    Tabs, Tag, Text, TextInput, Wrap, dates, route, set_interval, workpeg,
)


class HotelData(App):
    expected_business = State("")
    confirmation = State("")
    busy = State(False)
    timed_out = State(False)
    ticks = State(0)
    status = State("Not loaded")
    failure = State("")
    freshness = State("No snapshot")
    table_status = State("Not checked")
    room_types = State([])
    rooms = State([])
    reservations = State([])
    active_stays = State([])
    room_blocks = State([])
    service_requests = State([])
    row_references = State([])
    guests = State([])
    stays = State([])
    stay_guests = State([])
    request_audit = State([])
    operational_date = State("")
    view_state = State("loading")
    metrics = State([])
    arrival_cards = State([])
    departure_cards = State([])
    in_house_cards = State([])
    room_cards = State([])
    request_cards = State([])
    room_filter = State("All rooms")
    selected_room = State("")

    async def on_mount(self):
        set_interval(self.watch_timeout, 1000)
        self.operational_date = dates.today()
        await self.load_snapshot()

    def watch_timeout(self):
        if self.busy and not self.timed_out:
            self.ticks += 1
            if self.ticks >= 30:
                self.timed_out = True
                self.failure = "Read timed out. No complete snapshot is available; reload before retrying."
                self.status = "Access not verified"
                self.freshness = "Unknown after timeout"
                self.view_state = "connection_unavailable"

    def set_business(self, value):
        if not self.busy:
            self.expected_business = value.strip()

    def set_confirmation(self, value):
        if not self.busy:
            self.confirmation = value

    def fail(self, message):
        self.failure = message
        self.freshness = "No complete snapshot"
        self.view_state = "connection_unavailable"
        return False

    def set_operational_date(self, value):
        self.operational_date = value.strip()
        if dates.is_date(self.operational_date):
            self.failure = ""
            if self.view_state == "loaded":
                self.project_records()
        else:
            self.failure = "Operational date must be a valid YYYY-MM-DD date."

    def set_filter(self, value):
        self.room_filter = value

    def select_room(self, value):
        self.selected_room = value

    def valid_uuid(self, value):
        if str(value) != value or len(value) != 36:
            return False
        for position in range(36):
            if position in [8, 13, 18, 23]:
                if value[position] != "-":
                    return False
            elif value[position] not in "0123456789abcdef":
                return False
        return True

    def expected_names(self, namespace):
        if namespace == "roomay_hotel_v1":
            return ["room_types", "rooms", "guests", "reservations", "stays", "stay_guests", "room_blocks"]
        return ["Roomay Service Requests", "Roomay Service Request Audit"]

    def allowed_fields(self, table_name):
        if table_name == "room_types":
            return ["business_id", "entity_id", "name", "capacity"]
        if table_name == "rooms":
            return ["business_id", "entity_id", "number", "room_type_id", "enabled", "housekeeping"]
        if table_name == "guests":
            return ["business_id", "entity_id", "display_name"]
        if table_name == "reservations":
            return ["business_id", "entity_id", "guest_id", "room_type_id", "room_id", "arrival", "departure", "party_size", "source", "status"]
        if table_name == "stays":
            return ["business_id", "entity_id", "reservation_id", "room_id", "checked_in_at", "checked_out_at", "status"]
        if table_name == "stay_guests":
            return ["business_id", "entity_id", "stay_id", "guest_id", "joined_at", "left_at"]
        if table_name == "room_blocks":
            return ["business_id", "entity_id", "room_id", "start", "end", "reason", "status"]
        if table_name == "Roomay Service Requests":
            return ["business_id", "request_id", "idempotency_key", "hotel_id", "stay_id", "room_id", "guest_id", "origin", "category", "category_detail", "department", "description", "urgency", "status", "assigned_staff_id", "triage_required", "sensitive", "created_at", "updated_at", "received_at", "acknowledge_by", "due_at", "assigned_at", "acknowledged_at", "in_progress_at", "resolved_at", "reopened_at", "cancelled_at", "escalated_at", "version", "last_event_id", "last_operation_signature"]
        return ["business_id", "event_id", "operation_id", "operation_signature", "request_id", "hotel_id", "sequence", "event_type", "from_status", "to_status", "actor_id", "actor_kind", "actor_department", "occurred_at", "reason", "commit_state"]

    def optional_fields(self, table_name):
        if table_name == "reservations":
            return ["room_id"]
        if table_name == "stays":
            return ["checked_out_at"]
        if table_name == "stay_guests":
            return ["left_at"]
        if table_name == "Roomay Service Requests":
            return ["assigned_staff_id", "assigned_at", "acknowledged_at", "in_progress_at", "resolved_at", "reopened_at", "cancelled_at", "escalated_at"]
        if table_name == "Roomay Service Request Audit":
            return ["from_status", "actor_department", "reason"]
        return []

    def field_type(self, field):
        if field in ["business_id", "entity_id", "room_type_id", "guest_id", "room_id", "reservation_id", "stay_id", "request_id", "hotel_id", "last_event_id", "event_id", "operation_id"]:
            return "uuid"
        if field in ["capacity", "party_size", "version", "sequence"]:
            return "number"
        if field in ["enabled", "triage_required", "sensitive"]:
            return "boolean"
        if field in ["arrival", "departure", "checked_in_at", "checked_out_at", "joined_at", "left_at", "start", "end", "created_at", "updated_at", "received_at", "acknowledge_by", "due_at", "assigned_at", "acknowledged_at", "in_progress_at", "resolved_at", "reopened_at", "cancelled_at", "escalated_at", "occurred_at"]:
            return "datetime"
        if field in ["housekeeping", "source", "status", "origin", "category", "department", "urgency", "event_type", "to_status", "actor_kind", "actor_department", "commit_state"]:
            return "mutable_select"
        return "text"

    async def find_tables(self, namespace):
        tables = await workpeg.get_tables(namespace)
        if self.timed_out:
            return None
        if not isinstance(tables, list):
            self.fail("Malformed table-list response. Missing tables have not been established.")
            return None
        found = {}
        for name in self.expected_names(namespace):
            matches = []
            for table in tables:
                if table.get("name") == name:
                    matches.append(table)
            if len(matches) == 0:
                self.fail("Required table is missing or unreadable: " + name + ". No provisioning was attempted.")
                return None
            if len(matches) > 1:
                self.fail("Duplicate table identity: " + name + ". Owner reconciliation is required.")
                return None
            table = matches[0]
            if table.get("namespace") != namespace or str(table.get("permission")) != "700":
                self.fail("Unsafe namespace or permissions for table: " + name + ".")
                return None
            table_id = table.get("uuid", "")
            if not self.valid_uuid(table_id) or not isinstance(table.get("columns"), list):
                self.fail("Malformed table identifier or columns for: " + name + ".")
                return None
            expected_fields = self.allowed_fields(name)
            optional_fields = self.optional_fields(name)
            if len(table["columns"]) != len(expected_fields):
                self.fail("Column count mismatch for: " + name + ".")
                return None
            business_columns = 0
            for column in table["columns"]:
                field = column.get("id", "")
                if field not in expected_fields or column.get("type") != self.field_type(field):
                    self.fail("Column identity or type mismatch for: " + name + ".")
                    return None
                if column.get("required", False) != (field not in optional_fields):
                    self.fail("Required-column mismatch for: " + name + ".")
                    return None
                if column.get("id") == "business_id" and column.get("type") == "uuid" and column.get("required"):
                    business_columns += 1
            if business_columns != 1:
                self.fail("Business identity column mismatch for: " + name + ".")
                return None
            found[name] = table_id
        return found

    async def fetch_rows(self, table_name, table_id):
        rows = []
        for page_number in range(100):
            page = await workpeg.get_rows(table_id, limit=100, offset=page_number * 100)
            if self.timed_out:
                return None
            if not isinstance(page, list) or len(page) > 100:
                self.fail("Malformed row page for: " + table_name + ".")
                return None
            for row in page:
                row_id = row.get("id", 0)
                fingerprint = row.get("fingerprint", "")
                data = row.get("data")
                if row_id != int(row_id) or row_id <= 0 or not fingerprint or data is None:
                    self.fail("Missing native row identity for: " + table_name + ".")
                    return None
                if data.get("business_id") != route.business_id:
                    self.fail("Cross-business or missing business identity in: " + table_name + ".")
                    return None
                for existing in rows:
                    if existing["id"] == row_id:
                        self.fail("Duplicate native row ID in: " + table_name + ".")
                        return None
                rows.append(row)
            if len(page) < 100:
                return rows
        self.fail("Pagination safety limit reached for: " + table_name + ".")
        return None

    def records(self, table_name, rows):
        result = []
        references = [item for item in self.row_references]
        identity = "entity_id"
        if table_name == "Roomay Service Requests":
            identity = "request_id"
        if table_name == "Roomay Service Request Audit":
            identity = "event_id"
        seen = []
        allowed = self.allowed_fields(table_name)
        optional = self.optional_fields(table_name)
        for row in rows:
            for key in row["data"]:
                if key not in allowed:
                    self.fail("Unexpected field in: " + table_name + ".")
                    return None
            for key in allowed:
                if key not in optional and row["data"].get(key) is None:
                    self.fail("Incomplete record in: " + table_name + ".")
                    return None
            entity_id = row["data"].get(identity, "")
            if not self.valid_uuid(entity_id) or entity_id in seen:
                self.fail("Invalid or duplicate Roomay identity in: " + table_name + ".")
                return None
            seen.append(entity_id)
            record = {key: value for key, value in row["data"].items() if key != "business_id"}
            result.append(record)
            references.append({"table": table_name, "entity_id": entity_id,
                               "row_id": row["id"], "fingerprint": row["fingerprint"]})
        self.row_references = references
        return result

    def validate_relationships(self, loaded):
        room_types = [item["entity_id"] for item in loaded["room_types"]]
        rooms = [item["entity_id"] for item in loaded["rooms"]]
        guests = [item["entity_id"] for item in loaded["guests"]]
        reservations = [item["entity_id"] for item in loaded["reservations"]]
        stays = [item["entity_id"] for item in loaded["stays"]]
        numbers = []
        active_rooms = []
        used_reservations = []
        for room in loaded["rooms"]:
            if room["room_type_id"] not in room_types or room["number"] in numbers:
                return self.fail("Invalid room type reference or duplicate room number.")
            numbers.append(room["number"])
        for booking in loaded["reservations"]:
            if (booking["guest_id"] not in guests
                    or booking["room_type_id"] not in room_types
                    or booking["arrival"] >= booking["departure"]):
                return self.fail("Invalid reservation reference or date interval.")
            if booking.get("room_id"):
                if booking["room_id"] not in rooms:
                    return self.fail("Reservation references an unknown room.")
                matched_room = [room for room in loaded["rooms"]
                                if room["entity_id"] == booking["room_id"]][0]
                if matched_room["room_type_id"] != booking["room_type_id"]:
                    return self.fail("Reservation room type does not match its assigned room.")
            elif booking["status"] == "confirmed":
                return self.fail("Confirmed reservation is missing its assigned room.")
            room_type = [item for item in loaded["room_types"]
                         if item["entity_id"] == booking["room_type_id"]][0]
            if booking["party_size"] > room_type["capacity"]:
                return self.fail("Reservation party exceeds room type capacity.")
        confirmed = [booking for booking in loaded["reservations"]
                     if booking["status"] == "confirmed"]
        for left_index in range(len(confirmed)):
            for right_index in range(left_index + 1, len(confirmed)):
                left = confirmed[left_index]
                right = confirmed[right_index]
                if (left["room_id"] == right["room_id"]
                        and self.intervals_overlap(left["arrival"], left["departure"],
                                                   right["arrival"], right["departure"])):
                    return self.fail("Confirmed reservations overlap for the same room.")
        for stay in loaded["stays"]:
            if stay["reservation_id"] not in reservations or stay["room_id"] not in rooms:
                return self.fail("Stay references an unknown reservation or room.")
            booking = [item for item in loaded["reservations"]
                       if item["entity_id"] == stay["reservation_id"]][0]
            if booking["status"] != "confirmed" or booking.get("room_id") != stay["room_id"]:
                return self.fail("Stay does not match a confirmed room assignment.")
            if stay["reservation_id"] in used_reservations:
                return self.fail("Reservation has more than one stay.")
            used_reservations.append(stay["reservation_id"])
            if stay["status"] == "checked_in":
                if stay["room_id"] in active_rooms:
                    return self.fail("Room has more than one active stay.")
                active_rooms.append(stay["room_id"])
        occupant_pairs = []
        occupant_counts = {}
        for occupant in loaded["stay_guests"]:
            if occupant["stay_id"] not in stays or occupant["guest_id"] not in guests:
                return self.fail("Registered occupant references an unknown stay or guest.")
            pair = occupant["stay_id"] + ":" + occupant["guest_id"]
            if pair in occupant_pairs:
                return self.fail("Duplicate registered occupant.")
            occupant_pairs.append(pair)
            occupant_counts[occupant["stay_id"]] = occupant_counts.get(occupant["stay_id"], 0) + 1
        for stay in loaded["stays"]:
            booking = [item for item in loaded["reservations"]
                       if item["entity_id"] == stay["reservation_id"]][0]
            count = occupant_counts.get(stay["entity_id"], 0)
            if count < 1 or count > booking["party_size"]:
                return self.fail("Stay occupant count is outside the reservation party size.")
        for block in loaded["room_blocks"]:
            if block["room_id"] not in rooms or block["start"] >= block["end"]:
                return self.fail("Maintenance block has an invalid room or date interval.")
        request_ids = []
        for request in loaded["Roomay Service Requests"]:
            if request["request_id"] in request_ids:
                return self.fail("Duplicate service request identity.")
            request_ids.append(request["request_id"])
            if (request["stay_id"] not in stays or request["room_id"] not in rooms
                    or request["guest_id"] not in guests):
                return self.fail("Service request references unknown hotel records.")
            stay = [item for item in loaded["stays"]
                    if item["entity_id"] == request["stay_id"]][0]
            if stay["room_id"] != request["room_id"]:
                return self.fail("Service request room does not match its stay.")
            if request["stay_id"] + ":" + request["guest_id"] not in occupant_pairs:
                return self.fail("Service request guest is not a registered occupant.")
        for event in loaded["Roomay Service Request Audit"]:
            if event["request_id"] not in request_ids:
                return self.fail("Service request audit references an unknown request.")
        return True

    def intervals_overlap(self, a_start, a_end, b_start, b_end):
        return a_start < b_end and b_start < a_end

    def readiness_reasons(self, booking, room):
        reasons = []
        if booking["status"] != "confirmed":
            reasons.append("not_confirmed")
        if booking.get("room_id") != room["entity_id"]:
            reasons.append("room_not_assigned")
        if not room["enabled"]:
            reasons.append("room_disabled")
        if room["room_type_id"] != booking["room_type_id"]:
            reasons.append("wrong_room_type")
        if not booking["arrival"] <= self.operational_date < booking["departure"]:
            reasons.append("outside_booking_dates")
        if room["housekeeping"] != "ready":
            reasons.append("housekeeping_not_ready")
        if any(stay["room_id"] == room["entity_id"] and stay["status"] == "checked_in"
               for stay in self.stays):
            reasons.append("occupied")
        if any(stay["reservation_id"] == booking["entity_id"] for stay in self.stays):
            reasons.append("reservation_already_used")
        if any(other["entity_id"] != booking["entity_id"]
               and other.get("room_id") == room["entity_id"]
               and other["status"] == "confirmed"
               and self.intervals_overlap(booking["arrival"], booking["departure"],
                                          other["arrival"], other["departure"])
               for other in self.reservations):
            reasons.append("reservation_overlap")
        if any(block["room_id"] == room["entity_id"] and block["status"] == "active"
               and self.intervals_overlap(booking["arrival"], booking["departure"],
                                          block["start"], block["end"])
               for block in self.room_blocks):
            reasons.append("maintenance_block")
        return reasons

    def project_records(self):
        if not dates.is_date(self.operational_date):
            self.failure = "Operational date must be a valid YYYY-MM-DD date."
            return
        room_cards = []
        arrivals = []
        departures = []
        in_house = []
        ready = 0
        active_blocks = 0
        for room in self.rooms:
            room_type = [item for item in self.room_types
                         if item["entity_id"] == room["room_type_id"]][0]
            current_stays = [stay for stay in self.stays
                             if stay["room_id"] == room["entity_id"]
                             and stay["status"] == "checked_in"]
            current_bookings = [booking for booking in self.reservations
                                if booking.get("room_id") == room["entity_id"]
                                and booking["status"] == "confirmed"
                                and booking["arrival"] <= self.operational_date
                                and self.operational_date < booking["departure"]]
            stay = current_stays[0] if current_stays else None
            booking = None
            if stay:
                booking = [item for item in self.reservations
                           if item["entity_id"] == stay["reservation_id"]][0]
            elif current_bookings:
                booking = current_bookings[0]
            guest = None
            if booking:
                guest = [item for item in self.guests
                         if item["entity_id"] == booking["guest_id"]][0]
            blocks = [block for block in self.room_blocks
                      if block["room_id"] == room["entity_id"]
                      and block["status"] == "active"
                      and block["start"] <= self.operational_date
                      and self.operational_date < block["end"]]
            if blocks:
                active_blocks += 1
            occupancy = "Vacant"
            if stay:
                occupancy = "In house"
                in_house.append({"guest": guest["display_name"], "room": room["number"],
                                 "departure": booking["departure"]})
                if booking["departure"] == self.operational_date:
                    departures.append({"guest": guest["display_name"],
                                       "room": room["number"]})
            elif booking and booking["arrival"] == self.operational_date:
                occupancy = "Arriving today"
                arrivals.append({"guest": guest["display_name"], "room": room["number"],
                                 "reservation_id": booking["entity_id"]})
                if len(self.readiness_reasons(booking, room)) == 0:
                    ready += 1
            elif booking:
                occupancy = "Reserved"
            room_cards.append({
                "room_id": room["entity_id"], "number": room["number"],
                "room_type": room_type["name"], "occupancy": occupancy,
                "housekeeping": room["housekeeping"],
                "maintenance": "Blocked" if blocks else "Clear",
                "maintenance_reason": blocks[0]["reason"] if blocks else "",
                "guest": guest["display_name"] if guest else "",
                "enabled": room["enabled"],
            })
        room_numbers = {room["entity_id"]: room["number"] for room in self.rooms}
        request_cards = [{
            "request_id": request["request_id"], "description": request["description"],
            "category": request["category"], "department": request["department"],
            "urgency": request["urgency"], "status": request["status"],
            "room": room_numbers.get(request["room_id"], "Unknown"),
        } for request in self.service_requests]
        open_statuses = ["received", "assigned", "acknowledged", "in_progress",
                         "reopened", "escalated"]
        self.metrics = [
            {"label": "In house", "value": len(in_house), "helper": "Physical active stays"},
            {"label": "Arrivals", "value": len(arrivals), "helper": "Confirmed, not checked in"},
            {"label": "Departures", "value": len(departures), "helper": "Active stays due today"},
            {"label": "Ready for check-in", "value": ready, "helper": "Canonical eligibility rules"},
            {"label": "Needs cleaning", "value": len([room for room in self.rooms if room["housekeeping"] != "ready"]), "helper": "Not marked ready"},
            {"label": "Maintenance blocks", "value": active_blocks, "helper": "Active on operational date"},
            {"label": "Open requests", "value": len([request for request in self.service_requests if request["status"] in open_statuses]), "helper": "Unresolved guest requests"},
        ]
        self.arrival_cards = arrivals
        self.departure_cards = departures
        self.in_house_cards = in_house
        self.room_cards = room_cards
        self.request_cards = request_cards
        if not self.selected_room and room_cards:
            self.selected_room = room_cards[0]["number"]

    async def load_snapshot(self):
        if self.busy:
            return
        if not self.valid_uuid(route.business_id):
            self.fail("Business context is missing or malformed. Open this route inside an authorized Workpeg business.")
            return
        self.busy = True
        self.timed_out = False
        self.ticks = 0
        self.failure = ""
        self.status = "Checking authenticated Workpeg access"
        self.view_state = "loading"
        self.table_status = "Checking required tables"
        self.freshness = "Loading; not usable"
        self.row_references = []
        try:
            hotel_tables = await self.find_tables("roomay_hotel_v1")
            if hotel_tables is None or self.timed_out:
                return
            request_tables = await self.find_tables("roomay_requests_v1")
            if request_tables is None or self.timed_out:
                return
            table_ids = {key: value for key, value in hotel_tables.items()}
            for key, value in request_tables.items():
                table_ids[key] = value
            self.table_status = "All 9 owner-only contracts found"
            loaded = {}
            for table_name, table_id in table_ids.items():
                rows = await self.fetch_rows(table_name, table_id)
                if rows is None or self.timed_out:
                    return
                values = self.records(table_name, rows)
                if values is None:
                    return
                loaded[table_name] = values
            if not self.validate_relationships(loaded):
                return
            self.room_types = loaded["room_types"]
            self.rooms = loaded["rooms"]
            self.reservations = loaded["reservations"]
            self.guests = loaded["guests"]
            self.stays = loaded["stays"]
            self.stay_guests = loaded["stay_guests"]
            self.active_stays = [stay for stay in loaded["stays"] if stay.get("status") == "checked_in"]
            self.room_blocks = [block for block in loaded["room_blocks"] if block.get("status") == "active"]
            self.service_requests = loaded["Roomay Service Requests"]
            self.request_audit = loaded["Roomay Service Request Audit"]
            if len(self.room_types) == 0 or len(self.rooms) == 0:
                self.status = "Records loaded; no rooms configured"
                self.view_state = "empty_inventory"
            else:
                self.status = "Records loaded successfully"
                self.view_state = "loaded"
                self.project_records()
            self.freshness = "Complete read-only snapshot; not a reservation lock or write authorization"
        except Exception as error:
            if not self.timed_out:
                message = str(error)
                if "HTTP 400" in message:
                    self.failure = "Workpeg rejected the Peg namespace (400). WOR-28 remains blocking."
                    self.view_state = "connection_unavailable"
                elif "HTTP 401" in message:
                    self.failure = "Authentication failed or expired (401). Sign in through the authorized business context."
                    self.view_state = "authentication_required"
                elif "HTTP 403" in message:
                    self.failure = "Access denied (403). This release accepts only the owner-only table contract."
                    self.view_state = "access_denied"
                elif "HTTP 404" in message:
                    self.failure = "A scoped Workpeg resource was not found (404). No cross-business fallback was attempted."
                    self.view_state = "connection_unavailable"
                else:
                    self.failure = "Workpeg read failed: network, service, timeout or malformed response."
                    self.view_state = "connection_unavailable"
                self.status = "Access not verified"
                self.freshness = "No complete snapshot"
        finally:
            if not self.timed_out:
                self.busy = False

    def mark_stale(self):
        self.freshness = "Stale: reload before any decision or mutation"

    def build(self):
        return Authenticated(Container(
            Column(
                Container(
                    Wrap(
                        Column(
                            Text("Roomay", variant="title", weight="bold", style={"color": "#ffffff"}),
                            Text("Reception workspace", variant="caption", style={"color": "#c9ddd5"}),
                            gap=2,
                        ),
                        Column(
                            Tag("WORKPEG RECORDS", tone="success", size="sm"),
                            Text(f"Business {route.business_id}", variant="caption", style={"color": "#e8f2ee"}),
                            gap=6,
                        ),
                        spacing=16,
                        cross_alignment="center",
                    ),
                    padding=24, radius=20, color="#12372a",
                    style={"box-shadow": "0 16px 40px rgba(18,55,42,0.18)"},
                ),
                Container(
                    Wrap(
                        Column(
                            Text(self.status, variant="label", weight="bold"),
                            Text(self.freshness, variant="caption", tone="muted"),
                            gap=3,
                        ),
                        TextInput(value=self.operational_date, on_change=self.set_operational_date,
                                  placeholder="Operational date YYYY-MM-DD"),
                        Button("Refresh records", on_click=self.load_snapshot,
                               variant="outline-color") if not self.busy else Text("Refreshing..."),
                        spacing=12, cross_alignment="center",
                    ),
                    padding=16, radius=14, color="#eef7f3",
                    style={"border": "1px solid #cde4da"},
                ),
                Container(
                    Column(
                        Text("Loading authenticated Workpeg records...", variant="subheading", weight="bold"),
                        Text("No cached or fictional hotel records are shown while the snapshot is incomplete.", tone="muted"),
                        gap=6,
                    ),
                    padding=24, radius=16, color="#ffffff",
                    style={"border": "1px solid #dce7e2"}, visible=self.view_state == "loading",
                ),
                Container(
                    Column(
                        Text("No rooms configured", variant="heading", weight="bold"),
                        Text("The authenticated read succeeded, but the Roomay room inventory is empty. No records were seeded."),
                        Text("An authorized owner must provision and populate the reviewed table contract outside this read-only route.", tone="muted"),
                        gap=8,
                    ),
                    padding=24, radius=16, color="#fffaf0",
                    style={"border": "1px solid #ecd6a4"}, visible=self.view_state == "empty_inventory",
                ),
                Container(
                    Column(
                        Text("Authentication required", variant="heading", weight="bold"),
                        Text(self.failure),
                        Text("Use the Workpeg sign-in flow for this business; credentials are never accepted by Roomay UI fields.", tone="muted"),
                        gap=8,
                    ),
                    padding=24, radius=16, color="#fff4f4",
                    style={"border": "1px solid #e6b8b8"}, visible=self.view_state == "authentication_required",
                ),
                Container(
                    Column(
                        Text("Access denied", variant="heading", weight="bold"),
                        Text(self.failure),
                        Text("No fallback business, public table, or alternate data store was queried.", tone="muted"),
                        gap=8,
                    ),
                    padding=24, radius=16, color="#fff4f4",
                    style={"border": "1px solid #e6b8b8"}, visible=self.view_state == "access_denied",
                ),
                Container(
                    Column(
                        Text("Connection unavailable", variant="heading", weight="bold"),
                        Text(self.failure),
                        Text("The receptionist snapshot is unavailable until every required page passes validation.", tone="muted"),
                        gap=8,
                    ),
                    padding=24, radius=16, color="#fff4f4",
                    style={"border": "1px solid #e6b8b8"}, visible=self.view_state == "connection_unavailable",
                ),
                Container(
                    Column(
                        Wrap(
                            Tag("READ ONLY", tone="info", size="sm"),
                            Text(f"Operational date: {self.operational_date}", variant="label", weight="semibold"),
                            Text("Browser-local date; hotel timezone is not yet persisted", variant="caption", tone="muted"),
                            spacing=10, cross_alignment="center",
                        ),
                        Tabs(
                            Tab("Today", Column(
                                Column(
                                    Text("Today at a glance", variant="heading", weight="bold"),
                                    Text("Counts are derived from the same validated Workpeg snapshot shown below.", tone="muted"),
                                    gap=4,
                                ),
                                Wrap(*[
                                    Container(Column(
                                        Text(metric["label"], variant="label", tone="muted", weight="medium"),
                                        Text(metric["value"], variant="display", weight="bold", style={"color": "#12372a"}),
                                        Text(metric["helper"], variant="caption", tone="muted"),
                                        gap=6,
                                    ), padding=18, width=210, radius=16, color="#ffffff",
                                    style={"border": "1px solid #dce7e2", "min-height": "138px"})
                                    for metric in self.metrics
                                ], spacing=12, run_spacing=12),
                                Wrap(
                                    Container(Column(
                                        Text("Currently in house", variant="subheading", weight="bold"),
                                        Text("No active stays", tone="muted", visible=len(self.in_house_cards) == 0),
                                        Column(*[Text(f"{item['guest']} - Room {item['room']} - departs {item['departure']}") for item in self.in_house_cards], gap=8),
                                        Text("Physical checked-in stays only.", variant="caption", tone="muted"),
                                        gap=10,
                                    ), padding=20, width=330, radius=16, color="#ffffff", style={"border": "1px solid #dce7e2"}),
                                    Container(Column(
                                        Text("Arrivals", variant="subheading", weight="bold"),
                                        Text("No confirmed arrivals", tone="muted", visible=len(self.arrival_cards) == 0),
                                        Column(*[Text(f"{item['guest']} - Room {item['room']}") for item in self.arrival_cards], gap=8),
                                        Text("Reservations are not treated as checked-in guests.", variant="caption", tone="muted"),
                                        gap=10,
                                    ), padding=20, width=330, radius=16, color="#ffffff", style={"border": "1px solid #dce7e2"}),
                                    Container(Column(
                                        Text("Departures", variant="subheading", weight="bold"),
                                        Text("No departures planned", tone="muted", visible=len(self.departure_cards) == 0),
                                        Column(*[Text(f"{item['guest']} - Room {item['room']}") for item in self.departure_cards], gap=8),
                                        Text("Derived from active stays and reservation departure dates.", variant="caption", tone="muted"),
                                        gap=10,
                                    ), padding=20, width=330, radius=16, color="#ffffff", style={"border": "1px solid #dce7e2"}),
                                    spacing=12, run_spacing=12,
                                ),
                                gap=20,
                            )),
                            Tab("Rooms", Column(
                                Column(Text("Room board", variant="heading", weight="bold"),
                                       Text("Occupancy, housekeeping, and maintenance remain separate persisted signals.", tone="muted"), gap=4),
                                Wrap(
                                    Button("All rooms", on_click=lambda: self.set_filter("All rooms"), variant="outline-color", size="sm"),
                                    Button("In house", on_click=lambda: self.set_filter("In house"), variant="outline-color", size="sm"),
                                    Button("Arriving today", on_click=lambda: self.set_filter("Arriving today"), variant="outline-color", size="sm"),
                                    Button("Needs cleaning", on_click=lambda: self.set_filter("Needs cleaning"), variant="outline-color", size="sm"),
                                    Button("Blocked", on_click=lambda: self.set_filter("Blocked"), variant="outline-color", size="sm"),
                                    spacing=8, run_spacing=8,
                                ),
                                Text(f"Filter: {self.room_filter}", variant="label", weight="semibold"),
                                Wrap(*[
                                    Container(Column(
                                        Row(Text(f"Room {room['number']}", variant="subheading", weight="bold"), Tag(room["room_type"], tone="neutral", size="sm"), justify="space_between", align="center", gap=8),
                                        Text(room["occupancy"], variant="label", weight="semibold", style={"color": "#156b50"}),
                                        Divider(spacing=4),
                                        Text(f"Housekeeping - {room['housekeeping']}", variant="caption", tone="muted"),
                                        Text(f"Maintenance - {room['maintenance']}", variant="caption", tone="muted"),
                                        Button("View details", on_click=lambda: self.select_room(room["number"]), variant="text", size="sm"),
                                        gap=8,
                                    ), padding=18, width=242, radius=16, color="#ffffff",
                                    style={"border": "1px solid #dce7e2", "min-height": "205px"})
                                    for room in self.room_cards
                                    if self.room_filter == "All rooms"
                                    or self.room_filter == room["occupancy"]
                                    or (self.room_filter == "Needs cleaning" and room["housekeeping"] != "ready")
                                    or (self.room_filter == "Blocked" and room["maintenance"] == "Blocked")
                                ], spacing=12, run_spacing=12),
                                Column(*[
                                    Container(Column(
                                        Row(Text(f"Room {room['number']} details", variant="subheading", weight="bold"), Tag("READ ONLY", tone="info", size="sm"), justify="space_between", align="center", gap=12),
                                        Text(f"{room['room_type']} - {room['occupancy']}", weight="semibold"),
                                        Text(room["guest"] if room["guest"] else "No guest linked"),
                                        Text(f"Housekeeping: {room['housekeeping']} - Maintenance: {room['maintenance']}", variant="caption", tone="muted"),
                                        Text(room["maintenance_reason"], tone="warning", visible=room["maintenance_reason"] != ""),
                                        Text("Booking, assignment, and check-in writes are disabled until a protected writer is verified.", variant="caption", tone="muted"),
                                        gap=9,
                                    ), padding=20, radius=16, color="#eef7f3", style={"border": "1px solid #cde4da"})
                                    for room in self.room_cards if room["number"] == self.selected_room
                                ]),
                                gap=18,
                            )),
                            Tab("Requests", Column(
                                Column(Text("Guest service requests", variant="heading", weight="bold"),
                                       Text("Persisted requests are read only; lifecycle actions remain governed by WOR-14 authorization rules.", tone="muted"), gap=4),
                                Text("No service requests", tone="muted", visible=len(self.request_cards) == 0),
                                Wrap(*[
                                    Container(Column(
                                        Row(Tag(request["urgency"], tone="warning", size="sm"), Tag(request["status"], tone="info", size="sm"), justify="space_between", align="center", gap=8),
                                        Text(request["description"], weight="semibold"),
                                        Text(f"{request['category']} - {request['department']}", variant="caption", tone="muted"),
                                        Text(f"Room {request['room']}", variant="caption", tone="muted"),
                                        gap=9,
                                    ), padding=18, width=320, radius=16, color="#ffffff", style={"border": "1px solid #dce7e2"})
                                    for request in self.request_cards
                                ], spacing=12, run_spacing=12),
                                gap=18,
                            )),
                        ),
                        Container(Text("No mutation controls are enabled. Local eligibility is advisory; confirmation requires a trusted concurrency-safe writer.", variant="caption", tone="muted"), padding=14, radius=12, color="#f5f7f6"),
                        gap=18,
                    ),
                    visible=self.view_state == "loaded",
                ),
                gap=18,
            ),
            padding=24, color="#f4f7f5",
            style={"min-height": "100vh", "max-width": "1440px", "margin": "0 auto"},
        ))
