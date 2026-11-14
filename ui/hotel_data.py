"""Authenticated, read-only Workpeg reception and housekeeping views.

The UI compiles with Workpeg 0.152.0. It never provisions, seeds, or mutates
records and fails closed when the complete owner-only table contract cannot be
read. Housekeeping is an owner-only, department-filtered preview until trusted
staff membership and table access are verified. Browser-local ``dates.today()``
is exposed rather than mislabelled as a persisted hotel timezone.
"""
from workpeg.ui import (
    App, Authenticated, Button, Column, Container, Divider, Row, State, Tab,
    Table, TableCell, TableHeader, TableRow, Tabs, Tag, Text, TextInput, Wrap,
    dates, route, set_interval, workpeg,
    navigate,
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
    request_summary = State([])
    selected_request_card = State({})
    overdue_departure_cards = State([])
    housekeeping_room_cards = State([])
    housekeeping_request_cards = State([])
    housekeeping_metrics = State([])
    room_filter = State("All rooms")
    request_filter = State("All requests")
    selected_room = State("")
    selected_request = State("")
    active_view = State("Today")
    date_error = State("")
    show_business_id = State(False)

    async def on_mount(self):
        if route.workspace not in ["", "housekeeping"]:
            self.status = "Workspace unavailable"
            self.failure = "This Roomay staff workspace is not available."
            self.freshness = "No records read"
            self.view_state = "connection_unavailable"
            return
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
        proposed = value.strip()
        if not dates.is_date(proposed):
            self.date_error = "Enter a valid YYYY-MM-DD date. Counts still use the last valid operational date."
            return
        self.date_error = ""
        self.operational_date = proposed
        if self.view_state == "loaded":
            self.project_records()

    def set_filter(self, value):
        self.room_filter = value

    def set_request_filter(self, value):
        if value in ["All requests", "New"]:
            self.request_filter = value

    def set_view(self, value):
        if value in ["Today", "Rooms", "Requests"]:
            self.active_view = value

    def toggle_business_id(self):
        self.show_business_id = not self.show_business_id

    def _nav_button(self, label, view):
        if view == "Today":
            return self._nav_button_for(label, view, "layout-dashboard")
        if view == "Rooms":
            return self._nav_button_for(label, view, "bed")
        return self._nav_button_for(label, view, "clipboard-list")

    def _nav_button_for(self, label, view, icon):
        if self.active_view == view:
            return Button(label, on_click=lambda: self.set_view(view),
                          variant="ghost-gray", full_width=True, icon=icon,
                          icon_position="left",
                          style={"justify-content": "flex-start", "text-align": "left",
                                 "border-radius": "8px", "font-weight": "700",
                                 ":rest": {"color": "#181a1a", "background-color": "#f0f1ef"},
                                 ":hover": {"color": "#181a1a", "background-color": "#e8eae7"},
                                 ":focus-visible": {"color": "#181a1a",
                                                    "background-color": "#e8eae7",
                                                    "outline": "2px solid #181a1a",
                                                    "outline-offset": "2px"},
                                 ":active": {"color": "#181a1a",
                                             "background-color": "#e0e2df"}})
        return Button(label, on_click=lambda: self.set_view(view),
                      variant="ghost-gray", full_width=True, icon=icon,
                      icon_position="left",
                      style={"justify-content": "flex-start", "text-align": "left",
                             "border-radius": "8px", "font-weight": "600",
                             ":rest": {"color": "#515653", "background-color": "transparent"},
                             ":hover": {"color": "#181a1a", "background-color": "#f0f1ef"},
                             ":focus-visible": {"color": "#181a1a",
                                                "background-color": "#f0f1ef",
                                                "outline": "2px solid #181a1a",
                                                "outline-offset": "2px"},
                             ":active": {"color": "#181a1a",
                                         "background-color": "#e8eae7"}})

    def _filter_button(self, label, value):
        if self.room_filter == value:
            return Button(label, on_click=lambda: self.set_filter(value),
                          variant="primary", size="sm")
        return Button(label, on_click=lambda: self.set_filter(value),
                      variant="outline-gray", size="sm")

    def _request_filter_button(self, label, value):
        if self.request_filter == value:
            return Button(label, on_click=lambda: self.set_request_filter(value),
                          variant="primary", size="sm")
        return Button(label, on_click=lambda: self.set_request_filter(value),
                      variant="outline-gray", size="sm")

    def select_room(self, value):
        self.selected_room = value

    def select_request(self, value):
        self.selected_request = value
        self.selected_request_card = next((request for request in self.request_cards
                                            if request["request_id"] == value), {})

    def clear_selected_request(self):
        self.selected_request = ""
        self.selected_request_card = {}

    def open_request_detail(self, value):
        self.select_request(value)
        self.active_view = "Requests"

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

    def instant_epoch(self, value):
        if str(value) != value:
            return None
        if len(value) == 20 and value[19] == "Z":
            local_value = value[:19]
            if dates.is_datetime(local_value):
                return dates.to_epoch(local_value, "UTC")
            return None
        if (len(value) != 25 or value[19] not in ["+", "-"]
                or value[22] != ":"):
            return None
        digits = value[20:22] + value[23:25]
        for character in digits:
            if character not in "0123456789":
                return None
        local_value = value[:19]
        if not dates.is_datetime(local_value):
            return None
        hours = int(value[20:22])
        minutes = int(value[23:25])
        if hours > 23 or minutes > 59:
            return None
        offset = (hours * 60 + minutes) * 60000
        epoch = dates.to_epoch(local_value, "UTC")
        if value[19] == "+":
            return epoch - offset
        return epoch + offset

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

    def field_metadata(self, field):
        if field in ["arrival", "departure", "start", "end"]:
            return {"type": "date"}
        if field in ["checked_in_at", "checked_out_at", "joined_at", "left_at", "created_at", "updated_at", "received_at", "acknowledge_by", "due_at", "assigned_at", "acknowledged_at", "in_progress_at", "resolved_at", "reopened_at", "cancelled_at", "escalated_at", "occurred_at"]:
            return {"type": "datetime"}
        return {}

    def field_choices(self, table_name, field):
        if table_name == "rooms" and field == "housekeeping":
            return ["ready", "dirty", "cleaning", "inspection"]
        if table_name == "reservations" and field == "source":
            return ["advance", "walk_in"]
        if table_name == "reservations" and field == "status":
            return ["pending_confirmation", "confirmed", "cancelled"]
        if table_name == "stays" and field == "status":
            return ["checked_in", "checked_out"]
        if table_name == "room_blocks" and field == "status":
            return ["active", "released"]
        if field == "origin":
            return ["guest", "reception_desk", "phone", "staff"]
        if field == "category":
            return ["unknown", "extra_towels", "linen", "room_cleaning", "toiletries", "plumbing", "electrical", "air_conditioning", "room_equipment", "room_service", "dining", "minibar", "transport", "wake_up_call", "billing_question", "general_help"]
        if field == "department" or field == "actor_department":
            return ["housekeeping", "maintenance", "food_and_beverage", "reception"]
        if field == "urgency":
            return ["low", "normal", "high", "urgent"]
        if field == "status" or field == "to_status":
            return ["received", "assigned", "acknowledged", "in_progress", "resolved", "reopened", "cancelled", "escalated"]
        if field == "event_type":
            return ["created", "status_changed", "triaged"]
        if field == "actor_kind":
            return ["guest", "staff"]
        if field == "commit_state":
            return ["pending", "committed"]
        return []

    def expected_table_metadata(self, namespace):
        if namespace == "roomay_hotel_v1":
            return {"extra": {"contract": "roomay.hotel.v1"}}
        return {"extra": {"contract": "roomay.service_requests.v1"}}

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
            table_metadata = table.get("metadata", {})
            extra_metadata = table_metadata.get("extra", {})
            if (len(table_metadata) != 1 or len(extra_metadata) != 1
                    or extra_metadata.get("contract") != self.expected_table_metadata(namespace)["extra"]["contract"]):
                self.fail("Table contract metadata mismatch for: " + name + ".")
                return None
            table_id = table.get("uuid", "")
            if not self.valid_uuid(table_id) or not isinstance(table.get("columns"), list):
                self.fail("Malformed table identifier or columns for: " + name + ".")
                return None
            expected_fields = self.allowed_fields(name)
            optional_fields = self.optional_fields(name)
            seen_fields = []
            if len(table["columns"]) != len(expected_fields):
                self.fail("Column count mismatch for: " + name + ".")
                return None
            business_columns = 0
            for column in table["columns"]:
                field = column.get("id", "")
                if (field not in expected_fields or field in seen_fields
                        or column.get("name") != field
                        or column.get("type") != self.field_type(field)):
                    self.fail("Column identity or type mismatch for: " + name + ".")
                    return None
                seen_fields.append(field)
                if column.get("required", False) != (field not in optional_fields):
                    self.fail("Required-column mismatch for: " + name + ".")
                    return None
                expected_position = 500 if field == "business_id" else expected_fields.index(field) * 1000
                if column.get("position") != expected_position:
                    self.fail("Column position mismatch for: " + name + ".")
                    return None
                metadata = column.get("metadata", {})
                expected_metadata_type = self.field_metadata(field).get("type", "")
                if (len(metadata) != len(self.field_metadata(field))
                        or metadata.get("type", "") != expected_metadata_type):
                    self.fail("Column metadata mismatch for: " + name + ".")
                    return None
                expected_choices = self.field_choices(name, field)
                options = column.get("options", {})
                choices = options.get("choices", [])
                if len(options) != (1 if expected_choices else 0):
                    self.fail("Column options mismatch for: " + name + ".")
                    return None
                if len(choices) != len(expected_choices):
                    self.fail("Column choices mismatch for: " + name + ".")
                    return None
                for index in range(len(expected_choices)):
                    if (choices[index].get("ref") != expected_choices[index]
                            or choices[index].get("tag") != expected_choices[index]):
                        self.fail("Column choices mismatch for: " + name + ".")
                        return None
                if column.get("id") == "business_id" and column.get("type") == "uuid" and column.get("required"):
                    business_columns += 1
            if business_columns != 1:
                self.fail("Business identity column mismatch for: " + name + ".")
                return None
            if len(seen_fields) != len(expected_fields):
                self.fail("Column set mismatch for: " + name + ".")
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
                    or not dates.is_date(booking["arrival"])
                    or not dates.is_date(booking["departure"])
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
            checked_out_at = stay.get("checked_out_at")
            checked_in_epoch = self.instant_epoch(stay["checked_in_at"])
            if checked_in_epoch is None:
                return self.fail("Stay has an invalid check-in timestamp.")
            if ((stay["status"] == "checked_out" and not checked_out_at)
                    or (stay["status"] != "checked_out" and checked_out_at)):
                return self.fail("Stay checkout status and timestamp do not agree.")
            if checked_out_at:
                checked_out_epoch = self.instant_epoch(checked_out_at)
                if checked_out_epoch is None:
                    return self.fail("Stay has an invalid checkout timestamp.")
                if checked_out_epoch < checked_in_epoch:
                    return self.fail("Stay checkout precedes check-in.")
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
            stay = [item for item in loaded["stays"]
                    if item["entity_id"] == occupant["stay_id"]][0]
            joined_at = self.instant_epoch(occupant["joined_at"])
            if joined_at is None:
                return self.fail("Registered occupant has an invalid arrival timestamp.")
            checked_in_at = self.instant_epoch(stay["checked_in_at"])
            if joined_at < checked_in_at:
                return self.fail("Registered occupant arrived before stay check-in.")
            left_at = occupant.get("left_at")
            left_epoch = None
            if left_at:
                left_epoch = self.instant_epoch(left_at)
                if left_epoch is None:
                    return self.fail("Registered occupant has an invalid departure timestamp.")
                if left_epoch < joined_at:
                    return self.fail("Registered occupant left before arrival.")
            if stay.get("checked_out_at"):
                if not left_at:
                    return self.fail("Checked-out stay has an occupant without a departure timestamp.")
                if left_epoch > self.instant_epoch(stay["checked_out_at"]):
                    return self.fail("Registered occupant left after stay checkout.")
            occupant_counts[occupant["stay_id"]] = occupant_counts.get(occupant["stay_id"], 0) + 1
        for stay in loaded["stays"]:
            booking = [item for item in loaded["reservations"]
                       if item["entity_id"] == stay["reservation_id"]][0]
            count = occupant_counts.get(stay["entity_id"], 0)
            if count < 1 or count > booking["party_size"]:
                return self.fail("Stay occupant count is outside the reservation party size.")
        for block in loaded["room_blocks"]:
            if (block["room_id"] not in rooms
                    or not dates.is_date(block["start"])
                    or not dates.is_date(block["end"])
                    or block["start"] >= block["end"]):
                return self.fail("Maintenance block has an invalid room or date interval.")
        request_ids = []
        requests_by_id = {}
        for request in loaded["Roomay Service Requests"]:
            if request["request_id"] in request_ids:
                return self.fail("Duplicate service request identity.")
            request_ids.append(request["request_id"])
            requests_by_id[request["request_id"]] = request
            category_departments = {
                "extra_towels": "housekeeping", "linen": "housekeeping",
                "room_cleaning": "housekeeping", "toiletries": "housekeeping",
                "plumbing": "maintenance", "electrical": "maintenance",
                "air_conditioning": "maintenance", "room_equipment": "maintenance",
                "room_service": "food_and_beverage", "dining": "food_and_beverage",
                "minibar": "food_and_beverage", "transport": "reception",
                "wake_up_call": "reception", "billing_question": "reception",
                "general_help": "reception",
            }
            expected_department = category_departments.get(request["category"], "reception")
            expected_triage = request["category"] not in category_departments
            if (request["department"] != expected_department
                    or request["triage_required"] != expected_triage):
                return self.fail("Service request category and department routing disagree.")
            if (request["stay_id"] not in stays or request["room_id"] not in rooms
                    or request["guest_id"] not in guests):
                return self.fail("Service request references unknown hotel records.")
            if request["stay_id"] + ":" + request["guest_id"] not in occupant_pairs:
                return self.fail("Service request guest is not a registered occupant.")
        audit_sequences = {}
        for event in loaded["Roomay Service Request Audit"]:
            request = requests_by_id.get(event["request_id"])
            if request is None:
                return self.fail("Service request audit references an unknown request.")
            if event["hotel_id"] != request["hotel_id"]:
                return self.fail("Service request audit hotel does not match its request.")
            if (event["sequence"] != int(event["sequence"])
                    or event["sequence"] < 1):
                return self.fail("Service request audit sequence is invalid.")
            sequences = audit_sequences.get(event["request_id"], [])
            audit_sequences[event["request_id"]] = sequences
            if event["sequence"] in sequences:
                return self.fail("Service request audit sequence is duplicated.")
            sequences.append(event["sequence"])
            if self.instant_epoch(event["occurred_at"]) is None:
                return self.fail("Service request audit timestamp is invalid.")
        return True

    def intervals_overlap(self, a_start, a_end, b_start, b_end):
        return a_start < b_end and b_start < a_end

    def ordered_audit_events(self, audit_items):
        ordered = []
        previous_sequence = 0
        for _index in range(len(audit_items)):
            candidate = None
            for event in audit_items:
                if (event["sequence"] > previous_sequence
                        and (candidate is None
                             or event["sequence"] < candidate["sequence"])):
                    candidate = event
            if candidate is None:
                return ordered
            ordered.append(candidate)
            previous_sequence = candidate["sequence"]
        return ordered

    def audit_history_matches_request(self, request, history):
        """Check the visible audit sequence against its current request row.

        This is a read-projection guard, not a replacement for the canonical
        staff transition validator or a claim that Workpeg writes are atomic.
        """
        version = request.get("version")
        try:
            normalized_version = int(version)
        except (TypeError, ValueError):
            return False
        if (version != normalized_version or str(version) != str(normalized_version)
                or normalized_version < 1 or len(history) != normalized_version):
            return False
        for expected_sequence in range(1, normalized_version + 1):
            event = history[expected_sequence - 1]
            sequence = event.get("sequence")
            try:
                normalized_sequence = int(sequence)
            except (TypeError, ValueError):
                return False
            if (sequence != normalized_sequence
                    or str(sequence) != str(normalized_sequence)
                    or normalized_sequence != expected_sequence
                    or event.get("request_id") != request.get("request_id")
                    or event.get("commit_state") not in {"pending", "committed"}
                    or (expected_sequence < version
                        and event.get("commit_state") != "committed")):
                return False
        latest = history[-1]
        latest_time = self.instant_epoch(latest.get("occurred_at"))
        updated_time = self.instant_epoch(request.get("updated_at"))
        return (latest_time is not None
                and latest_time == updated_time
                and latest.get("event_id") == request.get("last_event_id")
                and latest.get("sequence") == normalized_version
                and latest.get("to_status") == request.get("status")
                and latest.get("operation_signature") == request.get("last_operation_signature"))

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
            self.date_error = "Operational date is invalid. Computed receptionist data is hidden."
            self.metrics = []
            self.arrival_cards = []
            self.departure_cards = []
            self.overdue_departure_cards = []
            self.in_house_cards = []
            self.room_cards = []
            self.request_cards = []
            return
        room_cards = []
        arrivals = []
        departures = []
        overdue_departures = []
        in_house = []
        ready = 0
        blocked_rooms = 0
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
            registered_occupants = []
            if stay:
                registered_occupants = [
                    next((item for item in self.guests
                          if item["entity_id"] == occupant["guest_id"]),
                         {"display_name": "Unknown"}).get("display_name", "Unknown")
                    for occupant in self.stay_guests
                    if occupant["stay_id"] == stay["entity_id"]
                ]
            blocks = [block for block in self.room_blocks
                      if block["room_id"] == room["entity_id"]
                      and block["status"] == "active"
                      and block["start"] <= self.operational_date
                      and self.operational_date < block["end"]]
            if blocks:
                blocked_rooms += 1
            occupancy = "Vacant"
            if stay:
                occupancy = "In house"
                departure_status = "Scheduled"
                if booking["departure"] < self.operational_date:
                    departure_status = "OVERDUE"
                    overdue_departures.append({"guest": guest["display_name"],
                                               "room": room["number"],
                                               "departure": booking["departure"]})
                elif booking["departure"] == self.operational_date:
                    departure_status = "Due today"
                in_house.append({"guest": ", ".join(registered_occupants), "room": room["number"],
                                 "departure": booking["departure"],
                                 "departure_status": departure_status,
                                 "reservation_status": booking["status"],
                                 "stay_status": stay["status"]})
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
                "housekeeping_label": {"ready": "Ready", "dirty": "Dirty",
                                       "cleaning": "Cleaning", "inspection": "Inspection"}
                                      .get(room["housekeeping"], "Unknown"),
                "maintenance": "Blocked" if blocks else "Clear",
                "maintenance_reason": blocks[0]["reason"] if blocks else "",
                "guest": (", ".join(registered_occupants) if stay
                          else guest["display_name"] if guest else ""),
                "reservation_status": booking["status"] if booking else "",
                "stay_status": stay["status"] if stay else "",
                "enabled": room["enabled"],
            })
        room_numbers = {room["entity_id"]: room["number"] for room in self.rooms}
        audit_by_request = {}
        for event in self.request_audit:
            audit_items = audit_by_request.get(event["request_id"], [])
            audit_items.append(event)
            audit_by_request[event["request_id"]] = audit_items
        department_display = {
            "housekeeping": "Housekeeping", "maintenance": "Maintenance",
            "food_and_beverage": "Food & beverage", "reception": "Reception",
            "human_triage": "Human triage",
        }
        category_display = {
            "unknown": "Needs triage", "extra_towels": "Extra towels",
            "linen": "Linen", "room_cleaning": "Room cleaning",
            "toiletries": "Toiletries", "plumbing": "Plumbing",
            "electrical": "Electrical", "air_conditioning": "Air conditioning",
            "room_equipment": "Room equipment", "room_service": "Room service",
            "dining": "Dining", "minibar": "Minibar", "transport": "Transport",
            "wake_up_call": "Wake-up call", "billing_question": "Billing question",
            "general_help": "General help",
        }
        status_display = {
            "received": "Received", "assigned": "Assigned",
            "acknowledged": "Acknowledged", "in_progress": "In progress",
            "resolved": "Resolved", "reopened": "Reopened",
            "cancelled": "Cancelled", "escalated": "Escalated",
        }
        urgency_display = {"low": "Low", "normal": "Normal", "high": "High", "urgent": "Urgent"}
        request_cards = []
        for request in self.service_requests:
            audit_history = self.ordered_audit_events(
                audit_by_request.get(request["request_id"], []))
            latest = next((event for event in audit_history
                           if event["event_id"] == request["last_event_id"]), None)
            if not audit_history:
                audit_status = "No audit event visible"
                audit_tone = "warning"
            elif not self.audit_history_matches_request(request, audit_history):
                audit_status = "Audit history is incomplete or mismatched; request status is unverified"
                audit_tone = "warning"
            elif latest is None:
                audit_status = "Audit history incomplete; latest request event is not visible"
                audit_tone = "warning"
            elif latest["to_status"] != request["status"]:
                audit_status = "Audit history does not match the current request status"
                audit_tone = "warning"
            elif latest["commit_state"] == "pending":
                audit_status = "Latest audit event pending commit; delivery is not represented"
                audit_tone = "warning"
            else:
                audit_status = "Latest event marked committed; delivery is not represented"
                audit_tone = "neutral"
            guest = next((item["display_name"] for item in self.guests
                          if item["entity_id"] == request["guest_id"]), "Unknown")
            request_cards.append({
                "request_id": request["request_id"], "description": request["description"],
                "category": request["category"], "department": request["department"],
                "category_label": category_display.get(request["category"], request["category"]),
                "department_label": department_display.get(request["department"], request["department"]),
                "status_label": status_display.get(request["status"], request["status"]),
                "urgency_label": urgency_display.get(request["urgency"], request["urgency"]),
                "urgency": request["urgency"], "status": request["status"],
                "room": room_numbers.get(request["room_id"], "Unknown"),
                "guest": guest, "audit_status": audit_status, "audit_tone": audit_tone,
                "audit_history": [{
                    "sequence": event["sequence"], "event_type": event["event_type"],
                    "from_status": event["from_status"], "to_status": event["to_status"],
                    "actor_kind": event["actor_kind"],
                    "actor_department": event["actor_department"],
                    "occurred_at": event["occurred_at"],
                    "commit_state": event["commit_state"],
                } for event in audit_history],
            })
        open_statuses = ["received", "assigned", "acknowledged", "in_progress",
                         "reopened", "escalated"]
        self.metrics = [
            {"label": "In house", "value": len(in_house), "helper": "Physical active stays"},
            {"label": "Arrivals", "value": len(arrivals), "helper": "Confirmed, not checked in"},
            {"label": "Scheduled departures today", "value": len(departures), "helper": "Checked-in stays due today"},
            {"label": "Overdue active stays", "value": len(overdue_departures), "helper": "Still checked in past departure"},
            {"label": "Ready for check-in", "value": ready, "helper": "Canonical eligibility rules"},
            {"label": "Needs cleaning", "value": len([room for room in self.rooms if room["housekeeping"] != "ready"]), "helper": "Not marked ready"},
            {"label": "Maintenance-blocked rooms", "value": blocked_rooms, "helper": "Rooms with an active block today"},
            {"label": "Open requests", "value": len([request for request in self.service_requests if request["status"] in open_statuses]), "helper": "Unresolved guest requests"},
        ]
        self.arrival_cards = arrivals
        self.departure_cards = departures
        self.overdue_departure_cards = overdue_departures
        self.in_house_cards = in_house
        self.room_cards = room_cards
        self.request_cards = request_cards
        active_requests = [request for request in request_cards
                           if request["status"] in ["received", "assigned", "acknowledged",
                                                     "in_progress", "reopened", "escalated"]]
        resolved_today = [request for request in request_cards
                          if any(event["to_status"] == "resolved"
                                 and event["occurred_at"][:10] == self.operational_date
                                 for event in request["audit_history"])]
        self.request_summary = [
            {"label": "Open requests", "value": len(active_requests), "helper": "All active issues"},
            {"label": "New requests", "value": len([request for request in request_cards
                                                        if request["status"] == "received"]),
             "helper": "Awaiting review"},
            {"label": "In progress", "value": len([request for request in request_cards
                                                       if request["status"] == "in_progress"]),
             "helper": "Being handled"},
            {"label": "Resolved today", "value": len(resolved_today),
             "helper": "Audit events on operational date"},
        ]
        self.housekeeping_room_cards = [room for room in room_cards
                                       if room["housekeeping"] != "ready"]
        self.housekeeping_request_cards = [request for request in request_cards
                                           if request["department"] == "housekeeping"
                                           and request["status"] not in ["resolved", "cancelled"]]
        self.housekeeping_metrics = [
            {"label": "Needs cleaning", "value": len([room for room in self.rooms
                                                        if room["housekeeping"] == "dirty"])},
            {"label": "In progress", "value": len([room for room in self.rooms
                                                      if room["housekeeping"] == "cleaning"])},
            {"label": "Awaiting inspection", "value": len([room for room in self.rooms
                                                               if room["housekeeping"] == "inspection"])},
            {"label": "Open department requests", "value": len(self.housekeeping_request_cards)},
        ]
        if room_cards and not any(room["number"] == self.selected_room for room in room_cards):
            self.selected_room = room_cards[0]["number"]
        if not any(request["request_id"] == self.selected_request for request in request_cards):
            self.selected_request = ""
            self.selected_request_card = {}
        else:
            self.selected_request_card = next((request for request in request_cards
                                               if request["request_id"] == self.selected_request), {})

    async def load_snapshot(self):
        if self.busy:
            return
        if route.workspace not in ["", "housekeeping"]:
            self.fail("This Roomay staff workspace is not available.")
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

    def _metric_card(self, metric):
        return Container(Column(
            Text(metric["label"], variant="label", tone="muted", weight="semibold",
                 style={"letter-spacing": "0.01em"}),
            Text(metric["value"], variant="display", weight="bold",
                 style={"color": "#181a1a", "font-size": "38px",
                        "line-height": "1.02", "letter-spacing": "-1.4px",
                        "font-variant-numeric": "tabular-nums"}),
            Text(metric["helper"], variant="caption", tone="muted",
                 style={"line-height": "1.45"}),
            gap=7,
        ), padding=18, width=248, radius=14, color="#ffffff",
            style={"flex": "1 1 200px", "min-width": "150px",
                   "max-width": "100%", "border": "1px solid #e2e9e4",
                   "min-height": "112px"})

    def _room_card(self, room):
        return Container(Column(
            Text(f"Room {room['number']}", variant="subheading", weight="bold"),
            Text(room["room_type"], variant="caption", tone="muted",
                 style={"overflow-wrap": "anywhere", "word-break": "break-word",
                        "min-width": "0"}),
            Text(room["occupancy"], variant="label", weight="semibold",
                 style={"color": "#1b4332"}),
            Divider(spacing=4),
            Wrap(self._housekeeping_badge(room), self._maintenance_badge(room),
                 spacing=6, run_spacing=6),
            Text(f"Reservation: {room['reservation_status'] or 'None'} - Stay: {room['stay_status'] or 'None'}",
                 variant="caption", tone="muted"),
            Button("View details", on_click=lambda: self.select_room(room["number"]),
                   variant="outline-gray", size="sm", icon="eye",
                   icon_position="left"),
            gap=9,
        ), padding=17, width=228, radius=12, color="#ffffff",
            style={"flex": "1 1 205px", "min-height": "190px",
                   "min-width": "0", "border": "1px solid #e2e9e4",
                   })

    def _housekeeping_badge(self, room):
        if room["housekeeping"] == "ready":
            return Tag(f"Housekeeping - {room['housekeeping']}", tone="success", size="sm")
        return Tag(f"Housekeeping - {room['housekeeping']}", tone="warning", size="sm")

    def _maintenance_badge(self, room):
        if room["maintenance"] == "Blocked":
            return Tag(f"Maintenance - {room['maintenance']}", tone="critical", size="sm")
        return Tag(f"Maintenance - {room['maintenance']}", tone="neutral", size="sm")

    def _room_guest(self, room):
        if room["guest"]:
            return Text(room["guest"])
        return Text("No registered guest linked")

    def _room_detail(self, room):
        return Container(Column(
            Row(Column(Text(f"Room {room['number']}", variant="title", weight="bold"),
                       Text(room["room_type"], variant="caption", tone="muted"), gap=3),
                Tag("READ ONLY", tone="neutral", size="sm"),
                justify="space_between", align="center", gap=12),
            Divider(spacing=5),
            Text("Room status", variant="caption", tone="muted"),
            Text(room["occupancy"], weight="semibold",
                 style={"overflow-wrap": "anywhere", "word-break": "break-word"}),
            Row(Text("Housekeeping", variant="caption", tone="muted"),
                self._housekeeping_badge(room), justify="space_between", align="center", gap=8),
            Row(Text("Maintenance", variant="caption", tone="muted"),
                self._maintenance_badge(room), justify="space_between", align="center", gap=8),
            Divider(spacing=5),
            Text("Reservation", variant="caption", tone="muted"),
            Text(room["reservation_status"] or "No linked reservation", weight="medium"),
            Text("Physical stay", variant="caption", tone="muted"),
            Text(room["stay_status"] or "No active stay", weight="medium"),
            Text("Registered guests", variant="caption", tone="muted",
                 visible=room["guest"] != ""),
            self._room_guest(room),
            Text(room["maintenance_reason"], tone="warning", visible=room["maintenance_reason"] != ""),
            Text("Room guidance is not included in the authorized hotel table contract.",
                 variant="caption", tone="muted"),
            gap=10,
        ), padding=22, width=360, radius=12, color="#ffffff",
            style={"flex": "0 1 360px", "border": "1px solid #e8ebe8",
                   "min-width": "260px", "max-width": "100%"})

    def _room_inspector(self):
        return Column(
            *[self._room_detail(room) for room in self.room_cards
              if room["number"] == self.selected_room],
            Container(Column(
                Text("Room details", variant="subheading", weight="bold"),
                Text("Select a room to inspect its verified operational details.",
                     variant="caption", tone="muted"),
                gap=8,
            ), padding=22, width=360, radius=12, color="#ffffff",
                style={"border": "1px solid #e8ebe8", "max-width": "100%"},
                visible=self.selected_room == ""),
            gap=0,
        )

    def _today_content(self):
        return Column(
            Wrap(*[self._metric_card(metric) for metric in self.request_summary],
                 spacing=12, run_spacing=12),
            Container(Column(
                Row(Column(Text("Guest service requests", variant="subheading", weight="bold"),
                           Text("Requests from the verified WorkPeg snapshot.",
                                variant="caption", tone="muted"), gap=3),
                    Button("Open request workspace", on_click=lambda: self.set_view("Requests"),
                           variant="text", size="sm"),
                    justify="space_between", align="center", gap=10),
                Wrap(self._request_filter_button("All requests", "All requests"),
                     self._request_filter_button("New", "New"),
                     spacing=8, run_spacing=8),
                Text("No service requests are present in the validated snapshot.",
                     tone="muted", visible=len(self.request_cards) == 0),
                Table(
                    TableHeader(TableCell(title="REQUEST"), TableCell(title="ROOM"),
                                TableCell(title="CATEGORY"), TableCell(title="STATUS"),
                                TableCell(title="ASSIGNED TO")),
                    *[self._request_overview_row(request) for request in self.request_cards
                      if self.request_filter == "All requests" or request["status"] == "received"],
                    search="Search requests, rooms or guests",
                    sortable=True, page_size=8, hover=True,
                    key="reception-overview-request-table",
                ),
                gap=12,
            ), padding=18, radius=12, color="#ffffff",
                style={"border": "1px solid #e8ebe8", "max-width": "100%"}),
            Column(
                Text("Hotel operations", variant="subheading", weight="bold"),
                Text("Verified stays, arrivals, departures and room readiness.",
                     variant="caption", tone="muted"),
                Wrap(*[self._metric_card(metric) for metric in self.metrics],
                     spacing=12, run_spacing=12),
            Wrap(
                Container(Column(
                    Row(Text("Currently in house", variant="subheading", weight="bold"),
                        Tag(str(len(self.in_house_cards)), tone="info", size="sm"),
                        justify="space_between", align="center", gap=8),
                    Text("No active stays", tone="muted", visible=len(self.in_house_cards) == 0),
                    Column(*[Text(f"{item['guest']} - Room {item['room']} - departure {item['departure']} - {item['departure_status']}")
                             for item in self.in_house_cards], gap=8),
                    Text("Only physically checked-in stays count as in house.", variant="caption", tone="muted"),
                    gap=10,
                ), padding=20, width=300, radius=18, color="#ffffff",
                    style={"flex": "1 1 270px", "min-height": "190px",
                           "border": "1px solid #e2e9e4",
                           "box-shadow": "0 8px 24px rgba(25, 43, 39, 0.04)"}),
                Container(Column(
                    Row(Text("Arrivals", variant="subheading", weight="bold"),
                        Tag(str(len(self.arrival_cards)), tone="info", size="sm"),
                        justify="space_between", align="center", gap=8),
                    Text("No confirmed arrivals", tone="muted", visible=len(self.arrival_cards) == 0),
                    Column(*[Text(f"{item['guest']} - Room {item['room']}") for item in self.arrival_cards], gap=8),
                    Text("A reservation is not a checked-in stay.", variant="caption", tone="muted"),
                    gap=10,
                ), padding=20, width=300, radius=18, color="#ffffff",
                    style={"flex": "1 1 270px", "min-height": "190px",
                           "border": "1px solid #e2e9e4",
                           "box-shadow": "0 8px 24px rgba(25, 43, 39, 0.04)"}),
                Container(Column(
                    Row(Text("Scheduled departures", variant="subheading", weight="bold"),
                        Tag(str(len(self.departure_cards)), tone="neutral", size="sm"),
                        justify="space_between", align="center", gap=8),
                    Text("No active stays due today", tone="muted", visible=len(self.departure_cards) == 0),
                    Column(*[Text(f"{item['guest']} - Room {item['room']}") for item in self.departure_cards], gap=8),
                    Text("Overdue active stays", variant="label", weight="bold", tone="warning",
                         visible=len(self.overdue_departure_cards) > 0),
                    Column(*[Text(f"OVERDUE - {item['guest']} - Room {item['room']} - scheduled {item['departure']}", tone="warning")
                             for item in self.overdue_departure_cards], gap=8),
                    Text("An overdue guest remains in house until checkout is recorded.", variant="caption", tone="muted"),
                    gap=10,
                ), padding=20, width=300, radius=18, color="#ffffff",
                    style={"flex": "1 1 270px", "min-height": "190px",
                           "border": "1px solid #e2e9e4",
                           "box-shadow": "0 8px 24px rgba(25, 43, 39, 0.04)"}),
                spacing=12, run_spacing=12,
            ),
            Container(Column(
                Text("Operational date", variant="label", weight="bold"),
                Text(f"{self.operational_date} - browser-local date; hotel timezone is not persisted",
                     variant="caption", tone="muted"),
                gap=4,
            ), padding=15, radius=14, color="#edf3ef",
                style={"border": "1px solid #dfe9e1"}),
            gap=16),
            gap=20,
        )

    def _rooms_content(self):
        return Column(
            Column(Text("Room information", variant="heading", weight="bold",
                        style={"color": "#181a1a", "letter-spacing": "-0.025em"}),
                   Text("Verified room inventory, occupancy, readiness and maintenance.", tone="muted"),
                   gap=4),
            Wrap(
                self._filter_button("All rooms", "All rooms"),
                self._filter_button("In house", "In house"),
                self._filter_button("Arriving today", "Arriving today"),
                self._filter_button("Needs cleaning", "Needs cleaning"),
                self._filter_button("Blocked", "Blocked"),
                spacing=8, run_spacing=8,
            ),
            Text(f"Showing: {self.room_filter}", variant="caption", tone="muted"),
            Text("Room board", variant="subheading", weight="bold"),
            Text("Select a room to inspect details.", variant="caption", tone="muted"),
            Wrap(
                Container(Wrap(*[self._room_card(room) for room in self.room_cards
                                 if self.room_filter == "All rooms"
                                 or self.room_filter == room["occupancy"]
                                 or (self.room_filter == "Needs cleaning" and room["housekeeping"] != "ready")
                                 or (self.room_filter == "Blocked" and room["maintenance"] == "Blocked")],
                              spacing=12, run_spacing=12),
                         padding=16, width=610, radius=18, color="#ffffff",
                         style={"flex": "1 1 560px", "min-width": "280px",
                                "max-width": "100%", "box-sizing": "border-box",
                                "border": "1px solid #e2e9e4",
                                "box-shadow": "0 8px 24px rgba(25, 43, 39, 0.035)"}),
                self._room_inspector(), spacing=12, run_spacing=12,
                cross_alignment="start"),
            Text("No rooms match this filter.", tone="muted",
                 visible=len(self.room_cards) == 0 or not any(
                     self.room_filter == "All rooms"
                     or self.room_filter == room["occupancy"]
                     or (self.room_filter == "Needs cleaning" and room["housekeeping"] != "ready")
                     or (self.room_filter == "Blocked" and room["maintenance"] == "Blocked")
                     for room in self.room_cards)),
            gap=18,
        )

    def _requests_content(self):
        return Column(
            Column(Text("Guest service requests", variant="heading", weight="bold",
                        style={"color": "#181a1a", "font-size": "27px",
                               "letter-spacing": "-0.025em"}),
                   Text("A clear view of what needs your attention.", tone="muted"),
                   gap=4),
            Wrap(
                *[self._metric_card(metric) for metric in self.request_summary],
                spacing=12, run_spacing=12,
            ),
            Text("No service requests are present in the validated snapshot.", tone="muted",
                 visible=len(self.request_cards) == 0),
            Wrap(
                Container(Table(
                    TableHeader(TableCell(title="REQUEST"), TableCell(title="ROOM"),
                                TableCell(title="CATEGORY"), TableCell(title="STATUS"),
                                TableCell(title="DEPARTMENT")),
                    *[self._request_table_row(request) for request in self.request_cards],
                    search="Search requests, rooms or guests",
                    sortable=True, page_size=8, hover=True,
                    key="reception-guest-request-table",
                ), padding=0, width=700, radius=12, color="#ffffff",
                    style={"flex": "1 1 620px", "min-width": "0", "max-width": "100%",
                           "border": "1px solid #e8ebe8", "overflow": "hidden"}),
                self._request_detail(self.selected_request_card),
                spacing=12, run_spacing=12, cross_alignment="start",
            ),
            gap=18,
        )

    def _request_overview_row(self, request):
        return TableRow(
            TableCell(Button(request["description"],
                             on_click=lambda: self.open_request_detail(request["request_id"]),
                             variant="text", size="sm",
                             style={"justify-content": "flex-start", "text-align": "left",
                                    "white-space": "normal", "font-weight": "600",
                                    ":focus-visible": {"outline": "2px solid #181a1a",
                                                       "outline-offset": "2px"}}),
                      title="", subtext="Open read-only request details"),
            TableCell(title="Room " + request["room"], subtext=request["guest"]),
            TableCell(title=request["category_label"]),
            TableCell(self._request_status_tag(request)),
            TableCell(title="Unavailable", subtext="Staff assignment is read only"),
        )

    def _request_table_row(self, request):
        return TableRow(
            TableCell(Button(request["description"],
                             on_click=lambda: self.select_request(request["request_id"]),
                             variant="text", size="sm",
                             style={"justify-content": "flex-start", "text-align": "left",
                                    "white-space": "normal", "font-weight": "600",
                                    ":focus-visible": {"outline": "2px solid #181a1a",
                                                       "outline-offset": "2px"}}),
                      title="", subtext="Open read-only request details"),
            TableCell(title="Room " + request["room"], subtext=request["guest"]),
            TableCell(title=request["category_label"]),
            TableCell(self._request_status_tag(request)),
            TableCell(title="Unavailable", subtext="Staff assignment is read only"),
        )

    def _request_status_tag(self, request):
        if request["status"] == "received":
            return Tag(request["status_label"], tone="info", size="sm")
        if request["status"] in ["assigned", "acknowledged", "in_progress", "reopened", "escalated"]:
            return Tag(request["status_label"], tone="warning", size="sm")
        if request["status"] == "resolved":
            return Tag(request["status_label"], tone="success", size="sm")
        return Tag(request["status_label"], tone="neutral", size="sm")

    def _request_detail(self, request):
        if not request:
            return Container(Column(
                Text("Request details", variant="subheading", weight="bold"),
                Text("Select a request to review its verified details and audit history.",
                     variant="caption", tone="muted"),
                Text("Request status and assignment are read-only here.",
                     variant="caption", tone="muted"),
                gap=12,
            ), padding=22, width=360, radius=12, color="#ffffff",
                style={"flex": "0 1 360px", "min-width": "260px", "max-width": "100%",
                       "border": "1px solid #e8ebe8"})

        return Container(Column(
            Row(Text("Request details", variant="subheading", weight="bold"),
                Button("Back to requests", on_click=self.clear_selected_request,
                       variant="text", size="sm"),
                justify="space_between", align="center", gap=8),
            Row(self._request_status_tag(request),
                Tag(request["urgency_label"], tone="warning", size="sm"),
                justify="start", align="center", gap=6),
            Divider(spacing=5),
            Text("Issue details", variant="label", weight="semibold"),
            Text(request["description"], style={"overflow-wrap": "anywhere", "word-break": "break-word"}),
            Row(Column(Text("Room", variant="caption", tone="muted"),
                       Text(request["room"], weight="semibold"), gap=3),
                Column(Text("Category", variant="caption", tone="muted"),
                       Text(request["category_label"], weight="semibold"), gap=3),
                justify="space_between", align="start", gap=12),
            Row(Column(Text("Guest", variant="caption", tone="muted"),
                       Text(request["guest"], weight="medium"), gap=3),
                Column(Text("Department", variant="caption", tone="muted"),
                       Text(request["department_label"], weight="medium"), gap=3),
                justify="space_between", align="start", gap=12),
            self._audit_note(request),
            Text("Audit history", variant="label", weight="semibold"),
            Text("No audit events are visible for this request.", variant="caption", tone="muted",
                 visible=len(request["audit_history"]) == 0),
            Column(*[Text(f"{event['sequence']} · {event['event_type']} · {event['to_status']} · {event['commit_state']} · {event['occurred_at']}",
                          variant="caption", tone="muted",
                          style={"overflow-wrap": "anywhere", "word-break": "break-word"})
                     for event in request["audit_history"]], gap=6),
            Container(Text("Assignment, acknowledgement, status changes and guest messaging are unavailable until authorized persistence is verified.",
                           variant="caption", tone="muted"), padding=12, radius=10,
                      color="#f3f5f2", style={"border": "1px solid #e8ebe8"}),
            gap=12,
        ), padding=22, width=360, radius=12, color="#ffffff",
            style={"flex": "0 1 360px", "min-width": "260px", "max-width": "100%",
                   "border": "1px solid #e8ebe8"})

    def _audit_note(self, request):
        if request["audit_tone"] == "warning":
            return Container(Text("Audit: " + request["audit_status"], variant="caption",
                                  tone="warning"), padding=10, radius=10, color="#fef6ee",
                             style={"border": "1px solid #ecd6a4"})
        return Container(Text("Audit: " + request["audit_status"], variant="caption",
                              tone="muted"), padding=10, radius=10, color="#f0f4f1",
                         style={"border": "1px solid #dce7e2"})

    def _state_panel(self, title, message, detail, color, border, state):
        return Container(Column(
            Text(title, variant="heading", weight="bold"),
            Text(message), Text(detail, tone="muted"), gap=8,
        ), padding=24, radius=16, color=color,
            style={"border": f"1px solid {border}"}, visible=self.view_state == state)

    def _sidebar(self):
        return Container(Column(
            Row(
                Container(Text("H", variant="title", weight="bold",
                               style={"color": "#ffffff"}),
                          width=54, height=54, radius=10, color="#181a1a",
                          style={"display": "grid", "place-items": "center"}),
                       Column(Text("Roomay", variant="title", weight="bold",
                            style={"color": "#181a1a", "letter-spacing": "-0.04em"}),
                       Text("HOTEL OPERATIONS", variant="caption",
                            style={"color": "#737976", "letter-spacing": "0.07em"}),
                       gap=1),
                gap=10, align="center",
            ),
            Divider(spacing=10),
            Text("WORKSPACE", variant="caption", weight="bold",
                 style={"color": "#718178", "letter-spacing": "0.1em"}),
            self._nav_button("Overview", "Today"),
            self._nav_button("Rooms", "Rooms"),
            Divider(spacing=10),
            Text("WORKSPACES", variant="caption", weight="bold",
                 style={"color": "#718178", "letter-spacing": "0.1em"}),
            Button("Housekeeping", on_click=self.open_housekeeping,
                   variant="ghost-gray", full_width=True, icon="brush",
                   icon_position="left",
                   style={"justify-content": "flex-start", "text-align": "left",
                          "border-radius": "10px",
                          ":rest": {"color": "#53675c", "background-color": "transparent"},
                          ":hover": {"color": "#103a30", "background-color": "#eaf2ed"},
                          ":focus-visible": {"color": "#103a30", "background-color": "#eaf2ed",
                                             "outline": "2px solid #174c3d", "outline-offset": "2px"}}),
            Divider(spacing=10),
            Text("DATA SOURCE", variant="caption", weight="bold",
                 style={"color": "#718178", "letter-spacing": "0.1em"},
                 visible=self.view_state == "loaded"),
            Wrap(Tag("WORKPEG SNAPSHOT", tone="success", size="sm"),
                 Tag("READ ONLY", tone="neutral", size="sm"),
                 spacing=6, run_spacing=6, visible=self.view_state == "loaded"),
            Tag("CHECKING ACCESS", tone="warning", size="sm", visible=self.view_state == "loading"),
            Tag("READ NOT VERIFIED", tone="warning", size="sm",
                visible=self.view_state == "connection_unavailable"
                        or self.view_state == "authentication_required"
                        or self.view_state == "access_denied"),
            Text("No sample records are substituted for Workpeg data.", variant="caption",
                 style={"color": "#687972", "line-height": "1.45"},
                 visible=self.view_state != "loaded"),
            gap=12,
            ), padding=24, width=232, radius=14, color="#ffffff",
            style={"min-height": "calc(100vh - 48px)", "border": "1px solid #e8ebe8",
                   "box-sizing": "border-box",
                   "align-self": "stretch"})

    def open_housekeeping(self):
        navigate(f"/b/{route.business_id}/reception/housekeeping")

    def open_reception(self):
        navigate(f"/b/{route.business_id}/reception")

    def _housekeeping_sidebar(self):
        return Container(Column(
            Row(
                Container(Text("R", variant="title", weight="bold",
                               style={"color": "#ffffff"}),
                          width=38, height=38, radius=12, color="#174c3d",
                          style={"display": "grid", "place-items": "center"}),
                Column(Text("roomay.", variant="title", weight="bold",
                            style={"color": "#192b27", "letter-spacing": "-0.06em"}),
                       Text("HOTEL OPERATIONS", variant="caption",
                            style={"color": "#687972", "letter-spacing": "0.07em"}),
                       gap=1),
                gap=10, align="center",
            ),
            Divider(spacing=10),
            Text("HOUSEKEEPING", variant="caption", weight="bold",
                 style={"color": "#718178", "letter-spacing": "0.1em"}),
            Button("Reception workspace", on_click=self.open_reception,
                   variant="ghost-gray", full_width=True, icon="layout-dashboard",
                   icon_position="left",
                   style={"justify-content": "flex-start", "text-align": "left",
                          "border-radius": "10px",
                          ":rest": {"color": "#53675c", "background-color": "transparent"},
                          ":hover": {"color": "#103a30", "background-color": "#eaf2ed"},
                          ":focus-visible": {"color": "#103a30", "background-color": "#eaf2ed",
                                             "outline": "2px solid #174c3d", "outline-offset": "2px"}}),
            Divider(spacing=10),
            Tag("OWNER-ONLY READ", tone="warning", size="sm"),
            Text("Department staff access is not configured. This preview contains no operational actions.",
                 variant="caption", style={"color": "#687972", "line-height": "1.45"}),
            gap=12,
        ), padding=20, width=250, radius=20, color="#fbfcf9",
            style={"min-height": "calc(100vh - 40px)", "border": "1px solid #e2e9e4",
                   "box-shadow": "0 10px 30px rgba(25, 43, 39, 0.045)",
                   "align-self": "stretch"})

    def _housekeeping_room_card(self, room):
        if room["housekeeping"] == "ready":
            return self._housekeeping_room_card_for_tone(room, "success")
        if room["housekeeping"] in ["dirty", "inspection"]:
            return self._housekeeping_room_card_for_tone(room, "warning")
        return self._housekeeping_room_card_for_tone(room, "info")

    def _housekeeping_room_card_for_tone(self, room, tone):
        return Container(Column(
            Row(Text("Room " + room["number"], variant="subheading", weight="bold"),
                Tag(room["housekeeping_label"], tone=tone, size="sm"),
                justify="space_between", align="center", gap=8),
            Text(room["room_type"], variant="caption", tone="muted",
                 style={"overflow-wrap": "anywhere", "word-break": "break-word",
                        "min-width": "0"}),
            Wrap(Tag("Maintenance blocked", tone="critical", size="sm",
                     visible=room["maintenance"] == "Blocked"),
                 Tag("Room in house", tone="neutral", size="sm",
                     visible=room["occupancy"] == "In house"),
                 spacing=6, run_spacing=6),
            Text("Occupancy, readiness and maintenance are separate signals.",
                 variant="caption", tone="muted"),
            gap=9,
        ), padding=17, width=270, radius=17, color="#ffffff",
            style={"flex": "1 1 250px", "border": "1px solid #e2e9e4",
                   "min-width": "0", "min-height": "150px",
                   "box-shadow": "0 8px 22px rgba(25, 43, 39, 0.035)"})

    def _housekeeping_request_card(self, request):
        return Container(Column(
            Wrap(Tag(request["category_label"], tone="info", size="sm"),
                 Tag(request["urgency_label"], tone="warning", size="sm"),
                 Tag(request["status_label"], tone="neutral", size="sm"),
                 spacing=6, run_spacing=6),
            Text("Room " + request["room"], variant="label", weight="semibold"),
            Text("Guest message withheld until department access is authorized.",
                 variant="caption", tone="muted"),
            self._audit_note(request),
            gap=9,
        ), padding=18, width=340, radius=17, color="#ffffff",
            style={"flex": "1 1 320px", "border": "1px solid #e2e9e4",
                   "min-width": "0", "box-shadow": "0 8px 22px rgba(25, 43, 39, 0.035)"})

    def _housekeeping_content(self):
        return Container(Wrap(
            self._housekeeping_sidebar(),
            Container(Column(
                Wrap(Column(Text("HOUSEKEEPING", variant="caption", weight="bold",
                                 style={"color": "#718178", "letter-spacing": "0.1em"}),
                            Text("Room readiness", variant="heading", weight="bold",
                                 style={"color": "#103a30", "font-size": "32px",
                                        "letter-spacing": "-0.035em"}),
                            Text("A read-only view of verified room and department records.",
                                 variant="caption", tone="muted"), gap=3),
                     Tag("READ ONLY", tone="info", size="sm"),
                     spacing=12, cross_alignment="center"),
                Container(Column(
                    Text("Owner-only preview", variant="label", weight="bold"),
                    Text("Housekeeping staff are not authorized to read these owner-only tables. "
                         "This view does not verify department membership and is not available "
                         "for staff operations. No actions are enabled.", tone="muted"),
                    gap=6,
                ), padding=16, radius=14, color="#fff8e8",
                    style={"border": "1px solid #ecd6a4"}),
                self._controls(),
                self._state_panel("Loading authenticated records...",
                    "Room data remains hidden until the complete Workpeg snapshot validates.",
                    "No cached or fictional records are substituted.",
                    "#ffffff", "#dce7e2", "loading"),
                self._state_panel("No rooms configured",
                    "The authenticated hotel snapshot contains no configured rooms.",
                    "No records were added by this workspace.",
                    "#fef6ee", "#ecd6a4", "empty_inventory"),
                self._state_panel("Authentication required", self.failure,
                    "Sign in through the Workpeg business context.",
                    "#fff4f4", "#e6b8b8", "authentication_required"),
                self._state_panel("Access denied", self.failure,
                    "No alternate business or data source was queried.",
                    "#fff4f4", "#e6b8b8", "access_denied"),
                self._state_panel("Connection unavailable", self.failure,
                    "No records are shown until every required read validates.",
                    "#fff4f4", "#e6b8b8", "connection_unavailable"),
                Column(
                    Column(Text("Readiness overview", variant="subheading", weight="bold"),
                           Wrap(*[Container(Column(
                               Text(metric["label"], variant="caption", tone="muted"),
                                Text(metric["value"], variant="display", weight="bold",
                                     style={"color": "#103a30", "font-size": "36px",
                                            "line-height": "1.05", "letter-spacing": "-1px",
                                            "font-variant-numeric": "tabular-nums"}), gap=7),
                                padding=17, width=205, radius=16, color="#ffffff",
                                style={"flex": "1 1 170px", "min-width": "145px",
                                       "border": "1px solid #e2e9e4", "min-height": "112px",
                                       "box-shadow": "0 8px 22px rgba(25, 43, 39, 0.035)"})
                               for metric in self.housekeeping_metrics], spacing=12, run_spacing=12), gap=12),
                    Column(Text("Rooms requiring attention", variant="subheading", weight="bold"),
                           Text("Housekeeping readiness remains separate from occupancy and maintenance.",
                                variant="caption", tone="muted"),
                           Text("No rooms need cleaning.", tone="muted",
                                visible=len(self.housekeeping_room_cards) == 0),
                           Wrap(*[self._housekeeping_room_card(room)
                                  for room in self.housekeeping_room_cards], spacing=12, run_spacing=12),
                           gap=10),
                    Column(Text("Housekeeping request activity", variant="subheading", weight="bold"),
                           Text("Unresolved requests routed to Housekeeping. No assignment, notification or staff action is implied.",
                                variant="caption", tone="muted"),
                           Text("No open Housekeeping requests.", tone="muted",
                                visible=len(self.housekeeping_request_cards) == 0),
                           Wrap(*[self._housekeeping_request_card(request)
                                  for request in self.housekeeping_request_cards], spacing=12, run_spacing=12),
                           gap=10),
                    Container(Text("Acknowledge, start-work and resolve actions are unavailable until "
                                   "trusted department authorization and committed persistence are implemented.",
                                   variant="caption", tone="muted"),
                               padding=16, radius=14, color="#edf3ef",
                               style={"border": "1px solid #dfe9e1"}),
                    gap=20, visible=self.view_state == "loaded"),
                gap=18,
            ), style={"flex": "1 1 600px", "min-width": "280px", "max-width": "100%"}),
            spacing=18, run_spacing=18, cross_alignment="start"),
            padding=24, color="#f7f8f3",
            style={"min-height": "100vh", "max-width": "1600px", "margin": "0 auto"})

    def _loaded_view(self):
        return Column(
            self._active_content(),
            Container(Text("This workspace is read only. No booking, check-in, assignment or service-request writes are enabled.",
                           variant="caption", tone="muted"),
                      padding=15, radius=14, color="#edf3ef",
                      style={"border": "1px solid #dfe9e1"}),
            gap=18,
            visible=self.view_state == "loaded",
        )

    def _controls(self):
        return Container(Wrap(
            Column(Text(self.status, variant="label", weight="bold"),
                   Text(self.freshness, variant="caption", tone="muted"), gap=3),
            self._business_scope(),
            Column(Text("Operational date", variant="caption", tone="muted"),
                   TextInput(value=self.operational_date, on_change=self.set_operational_date,
                             placeholder="YYYY-MM-DD"), gap=2),
            Text(self.date_error, variant="caption", tone="warning", visible=self.date_error != ""),
            self._refresh_control(),
            spacing=14, run_spacing=10, cross_alignment="center",
        ), padding=17, radius=16, color="#ffffff",
             style={"border": "1px solid #e2e9e4",
                    "box-shadow": "0 8px 24px rgba(25, 43, 39, 0.035)"})

    def _main_content(self):
        return Container(Column(
            Wrap(
                Column(Text("RECEPTION / FRONT DESK", variant="caption", weight="bold",
                            style={"color": "#718178", "letter-spacing": "0.1em"}),
                       Text(self._page_title(), variant="heading", weight="bold",
                            style={"color": "#181a1a", "font-size": "46px",
                                   "line-height": "1.08", "letter-spacing": "-0.045em"}),
                       Text("A clear view of verified hotel operations.",
                            variant="caption", tone="muted",
                            style={"font-size": "18px", "line-height": "1.5"}), gap=5),
                Tag("READ ONLY", tone="info", size="sm"),
                spacing=12, cross_alignment="center",
            ),
            self._controls(),
            self._state_panel("Loading authenticated records...",
                "No cached or fictional hotel records are shown while the snapshot is incomplete.",
                "Operational information appears only after all required reads and relationship checks pass.",
                "#ffffff", "#dce7e2", "loading"),
            self._state_panel("No rooms configured",
                "The authenticated read succeeded, but the Roomay room inventory is empty. No records were seeded.",
                "An authorized owner must provision and populate the reviewed table contract outside this read-only route.",
                "#fef6ee", "#ecd6a4", "empty_inventory"),
            self._state_panel("Authentication required", self.failure,
                "Use the Workpeg sign-in flow for this business; Roomay does not accept credentials in UI fields.",
                "#fff4f4", "#e6b8b8", "authentication_required"),
            self._state_panel("Access denied", self.failure,
                "No fallback business, public table or alternate data store was queried.",
                "#fff4f4", "#e6b8b8", "access_denied"),
            self._state_panel("Connection unavailable", self.failure,
                "The receptionist snapshot is unavailable until every required page passes validation.",
                "#fff4f4", "#e6b8b8", "connection_unavailable"),
            self._loaded_view(),
            gap=18,
        ), style={"flex": "1 1 600px", "min-width": "0",
                  "max-width": "100%"})

    def _active_content(self):
        if self.active_view == "Today":
            return self._today_content()
        if self.active_view == "Rooms":
            return self._rooms_content()
        return self._requests_content()

    def _page_title(self):
        if self.view_state == "loaded":
            if self.active_view == "Today":
                return "Good evening, Reception"
            if self.active_view == "Rooms":
                return "Room information"
            return "Guest service requests"
        return "Reception workspace"

    def _refresh_control(self):
        if self.busy:
            return Text("Refreshing records...")
        return Button("Refresh records", on_click=self.load_snapshot, variant="outline-gray",
                      icon="refresh", icon_position="left")

    def _business_scope(self):
        if self.show_business_id:
            return Column(
                Row(Text("Business scope", variant="caption", tone="muted"),
                    Button("Hide ID", on_click=self.toggle_business_id,
                           variant="ghost-gray", size="sm"),
                    align="center", gap=6),
                Text(route.business_id, variant="caption", weight="medium",
                     style={"overflow-wrap": "anywhere", "word-break": "break-all"}),
                gap=2,
            )
        return Row(Text("Business scope", variant="caption", tone="muted"),
                   Button("Show ID", on_click=self.toggle_business_id,
                          variant="ghost-gray", size="sm"),
                   align="center", gap=6)

    def build(self):
        if route.workspace == "housekeeping":
            return Authenticated(self._housekeeping_content())
        return Authenticated(Container(Wrap(self._sidebar(), self._main_content(), spacing=22, run_spacing=18,
                cross_alignment="start"), padding=24, color="#f8f9f7",
                style={"min-height": "100vh", "max-width": "1600px", "margin": "0 auto",
                       "box-sizing": "border-box"}))
