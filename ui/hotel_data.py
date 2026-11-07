"""Authenticated, read-only Workpeg transport for the Roomay hotel model.

No request is made on mount.  This route intentionally has no create, seed,
reservation-confirmation, or update action while WOR-28 blocks live validation.
"""
from workpeg.ui import App, State, Button, Column, Text, TextInput, route, set_interval, workpeg


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

    def on_mount(self):
        set_interval(self.watch_timeout, 1000)

    def watch_timeout(self):
        if self.busy and not self.timed_out:
            self.ticks += 1
            if self.ticks >= 30:
                self.timed_out = True
                self.failure = "Read timed out. No complete snapshot is available; reload before retrying."
                self.status = "Access not verified"
                self.freshness = "Unknown after timeout"

    def set_business(self, value):
        if not self.busy:
            self.expected_business = value.strip()

    def set_confirmation(self, value):
        if not self.busy:
            self.confirmation = value

    def fail(self, message):
        self.failure = message
        self.freshness = "No complete snapshot"
        return False

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

    async def load_snapshot(self):
        if self.busy:
            return
        if not route.business_id or self.expected_business != route.business_id:
            self.fail("Business context mismatch. Enter the exact owner-verified business ID from this URL.")
            return
        if self.confirmation != "Read Roomay hotel data":
            self.fail("Confirm this read-only operation before loading hotel records.")
            return
        self.busy = True
        self.timed_out = False
        self.ticks = 0
        self.failure = ""
        self.status = "Checking authenticated Workpeg access"
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
            self.room_types = loaded["room_types"]
            self.rooms = loaded["rooms"]
            self.reservations = loaded["reservations"]
            self.active_stays = [stay for stay in loaded["stays"] if stay.get("status") == "checked_in"]
            self.room_blocks = [block for block in loaded["room_blocks"] if block.get("status") == "active"]
            self.service_requests = loaded["Roomay Service Requests"]
            if len(self.room_types) == 0 or len(self.rooms) == 0:
                self.status = "Authenticated transport read succeeded; hotel inventory is empty"
            else:
                self.status = "Authenticated transport read succeeded; domain validation required"
            self.freshness = "Complete transport snapshot; not a reservation lock or write authorization"
        except Exception as error:
            if not self.timed_out:
                message = str(error)
                if "HTTP 400" in message:
                    self.failure = "Workpeg rejected the Peg namespace (400). WOR-28 remains blocking."
                elif "HTTP 401" in message:
                    self.failure = "Authentication failed or expired (401). Sign in through the authorized business context."
                elif "HTTP 403" in message:
                    self.failure = "Authorization denied (403). Verify installation, staff membership and table permissions."
                elif "HTTP 404" in message:
                    self.failure = "A scoped Workpeg resource was not found (404). No cross-business fallback was attempted."
                else:
                    self.failure = "Workpeg read failed: network, service, timeout or malformed response."
                self.status = "Access not verified"
                self.freshness = "No complete snapshot"
        finally:
            if not self.timed_out:
                self.busy = False

    def mark_stale(self):
        self.freshness = "Stale: reload before any decision or mutation"

    def build(self):
        return Column(
            Text("Roomay / Workpeg hotel data adapter"),
            Text("READ ONLY — no tables, records, reservations or stays are created from this route."),
            Text(f"URL business: {route.business_id} | Peg namespace: roomay"),
            TextInput(value=self.expected_business, on_change=self.set_business,
                      placeholder="Exact owner-verified business ID"),
            TextInput(value=self.confirmation, on_change=self.set_confirmation,
                      placeholder="Type: Read Roomay hotel data"),
            Text(f"Status: {self.status}"),
            Text(f"Tables: {self.table_status}"),
            Text(f"Freshness: {self.freshness}"),
            Text(f"Failure: {self.failure}"),
            Text(f"Room types: {len(self.room_types)} | Rooms: {len(self.rooms)} | Reservations: {len(self.reservations)}"),
            Text(f"Active stays: {len(self.active_stays)} | Active blocks: {len(self.room_blocks)} | Service requests: {len(self.service_requests)}"),
            Button("Load authorized Workpeg records", on_click=self.load_snapshot) if not self.busy else Text("Loading authenticated pages…"),
            Button("Mark snapshot stale", on_click=self.mark_stale) if not self.busy else Text("Wait for current read"),
            Text("Local eligibility is advisory. Confirmation requires a trusted concurrency-safe writer not yet verified by Workpeg."),
            gap=12,
        )
