"""Owner-operated development smoke test. No table requests on mount."""
from workpeg.ui import App, State, Column, Text, Button, TextInput, route, set_interval, workpeg


class DevSmoke(App):
    expected_business = State("")
    consent = State("")
    busy = State(False)
    timed_out = State(False)
    uncertain = State(False)
    ticks = State(0)
    context = State("Authentication and business access not checked.")
    table_status = State("Not checked")
    room_status = State("Not read")
    last_success = State("None")
    failure = State("")
    table_uuid = State("")

    def on_mount(self):
        set_interval(self.watch_timeout, 1000)

    def watch_timeout(self):
        if self.busy and not self.timed_out:
            self.ticks += 1
            if self.ticks >= 30:
                self.timed_out = True
                self.uncertain = True
                self.failure = "Timed out. Outcome unknown; requests cannot be cancelled by this SDK. Stop, reconcile with the owner, then reload and read before any write."
                self.context = "Access not currently verified"
                self.table_status = "Unknown after timeout"
                self.room_status = "Unknown after timeout"

    def set_business(self, value):
        if not self.busy:
            self.expected_business = value.strip()

    def set_consent(self, value):
        if not self.busy:
            self.consent = value

    def fail(self, message):
        self.failure = message
        return False

    def valid_table(self, table):
        if table.get("name") != "Roomay Dev Smoke" or table.get("namespace") != "roomay_smoke":
            return self.fail("Unexpected table identity. No write performed.")
        if str(table.get("permission")) != "700":
            return self.fail("Expected owner-only permission 700. Stop and inspect permissions.")
        table_id = table.get("uuid", "")
        if str(table_id) != table_id or len(table_id) != 36:
            return self.fail("Malformed table UUID.")
        for position in range(36):
            if position in [8, 13, 18, 23]:
                if table_id[position] != "-":
                    return self.fail("Malformed table UUID.")
            elif table_id[position] not in "0123456789abcdef":
                return self.fail("Malformed table UUID.")
        columns = table.get("columns")
        if not isinstance(columns, list):
            return self.fail("Malformed table columns.")
        room_columns = 0
        status_columns = 0
        for column in columns:
            if column.get("id") == "room_number" and column.get("type") == "text":
                room_columns += 1
            if column.get("id") == "status" and column.get("type") == "text":
                status_columns += 1
        if room_columns != 1 or status_columns != 1:
            return self.fail("Unexpected schema. Expected room_number and status text column IDs.")
        self.table_uuid = table_id
        self.table_status = "Found owner-only Roomay Dev Smoke"
        return True

    async def find_table(self):
        tables = await workpeg.get_tables("roomay_smoke")
        if self.timed_out:
            return False
        if not isinstance(tables, list):
            return self.fail("Malformed table list; absence is not established.")
        if len(tables) > 1:
            return self.fail("Multiple smoke tables visible. Stop; owner must resolve duplicates.")
        self.table_uuid = ""
        if len(tables) == 1:
            return self.valid_table(tables[0])
        self.table_status = "No visible smoke table (not proof that another owner has none)"
        return True

    async def read_room(self):
        # This dedicated table must contain at most one row. Two detects overflow;
        # do not silently use a partial page as proof that room 201 is absent.
        rows = await workpeg.get_rows(self.table_uuid, limit=2, offset=0)
        if self.timed_out:
            return None
        if not isinstance(rows, list):
            self.fail("Malformed row list; absence is not established.")
            return None
        if len(rows) > 1:
            self.fail("Multiple rows in smoke table. Stop; owner must resolve duplicates.")
            return None
        if len(rows) == 0:
            self.room_status = "No saved room visible"
            return []
        row = rows[0]
        row_id = row.get("id", 0)
        if row_id != int(row_id) or row_id <= 0:
            self.fail("Malformed row ID.")
            return None
        data = row.get("data")
        if data.get("room_number") != "201" or data.get("status") not in ["ready", "dirty"]:
            self.fail("Unexpected room data. Only fictional Room 201, ready or dirty, is supported.")
            return None
        self.room_status = f"Saved fictional Room 201: {data['status']} (row {row_id})"
        return rows

    async def run_operation(self, operation):
        if self.busy:
            return
        if not route.business_id or self.expected_business != route.business_id:
            self.fail("Business context mismatch. Use the owner-verified Roomay AI business URL and enter its exact business ID.")
            return
        if self.consent != "Roomay AI single operator":
            self.fail("Confirm the isolated development business and single-operator test first.")
            return
        if self.uncertain and operation in ["create_table", "create_room", "dirty"]:
            self.fail("Previous write outcome is unknown. Writes locked; reconcile saved records with the owner before reloading.")
            return
        self.busy = True
        self.ticks = 0
        self.failure = ""
        self.table_uuid = ""
        self.table_status = "Checking"
        self.room_status = "Not read in this operation"
        self.context = "Checking authenticated table access"
        write_started = False
        try:
            found = await self.find_table()
            if not found or self.timed_out:
                return
            self.context = "Authenticated table read succeeded in the URL business; business name is owner-confirmed, not verified by SDK."
            if operation == "check":
                self.last_success = "Connection / table lookup succeeded"
                return
            if operation == "create_table":
                if self.table_uuid:
                    self.last_success = "Table already exists; no create sent"
                    return
                write_started = True
                created = await workpeg.create_table({
                    "name": "Roomay Dev Smoke", "namespace": "roomay_smoke",
                    "alias": "roomay-dev-smoke-v1", "permission": "700",
                    "columns": [
                        {"id": "room_number", "name": "room_number", "type": "text", "position": 1000, "required": True},
                        {"id": "status", "name": "status", "type": "text", "position": 2000, "required": True},
                    ],
                })
                if self.timed_out or not self.valid_table(created):
                    return
                created_id = self.table_uuid
                found = await self.find_table()
                if not found or self.timed_out:
                    return
                if self.table_uuid != created_id:
                    self.fail("Create response did not match table read-back. Outcome unknown.")
                    return
                self.last_success = "Table created and read back; reload verification still required"
                return
            if not self.table_uuid:
                self.fail("No visible smoke table. Create it separately as the designated owner.")
                return
            rows = await self.read_room()
            if rows is None or self.timed_out:
                return
            if operation == "read":
                self.last_success = "Saved records read successfully"
                return
            if operation == "create_room":
                if len(rows) == 1:
                    self.last_success = "Room 201 already exists; no insert sent"
                    return
                write_started = True
                saved = await workpeg.add_row(self.table_uuid, {
                    "data": {"room_number": "201", "status": "ready"},
                    "position": 1000, "inherit_business_permission": True,
                    "inherit_individual_permissions": False,
                })
                expected = "ready"
            elif operation == "dirty":
                if len(rows) != 1:
                    self.fail("Create fictional Room 201 before updating.")
                    return
                row = rows[0]
                if row["data"]["status"] == "dirty":
                    self.last_success = "Room 201 is already dirty; no update sent"
                    return
                # Copy ALL data keys from the fresh read: PATCH replaces data.
                patch = {key: value for key, value in row["data"].items()}
                patch["status"] = "dirty"
                write_started = True
                saved = await workpeg.update_row(self.table_uuid, row["id"], {"data": patch})
                expected = "dirty"
            else:
                self.fail("Unknown operation")
                return
            if self.timed_out:
                return
            saved_id = saved.get("id")
            if operation == "dirty" and saved_id != rows[0]["id"]:
                self.fail("Update returned a different row ID. Outcome unknown.")
                return
            reread = await self.read_room()
            if reread is None or self.timed_out:
                return
            if len(reread) != 1 or reread[0]["id"] != saved_id or reread[0]["data"]["status"] != expected:
                self.fail("Write not confirmed by read-back. Outcome unknown.")
                return
            self.last_success = f"Room 201 {expected} write read back; reload verification still required"
        except Exception as error:
            if not self.timed_out:
                # Never display arbitrary server error text (may contain secrets).
                message = str(error)
                if "HTTP 401" in message:
                    self.failure = "Authentication failed (401). Sign in through the authorized Workpeg business context."
                elif "HTTP 403" in message:
                    self.failure = "Authorization denied (403). Owner must verify staff membership, table permissions and Peg installation."
                else:
                    self.failure = "Operation failed: network, service or malformed response. No success claimed."
                self.context = "Access not currently verified"
        finally:
            if write_started and (self.failure or self.timed_out):
                self.uncertain = True
                self.room_status = "Write outcome unknown; reconcile before retry"
            if not self.timed_out:
                self.busy = False

    async def check_connection(self):
        await self.run_operation("check")

    async def create_table(self):
        await self.run_operation("create_table")

    async def create_room(self):
        await self.run_operation("create_room")

    async def read_saved(self):
        await self.run_operation("read")

    async def mark_dirty(self):
        await self.run_operation("dirty")

    def build(self):
        return Column(
            Text("Roomay / Development persistence test"),
            Text("Fictional Room 201 only. No hotel or guest data. One designated owner, one browser tab; no concurrent operators."),
            Text(f"URL business: {route.business_id} | Peg: roomay | Table namespace: roomay_smoke"),
            Text("Enter the Roomay AI business ID verified by its owner. Approval alone does not prove installation."),
            TextInput(value=self.expected_business, on_change=self.set_business, placeholder="Verified development business ID"),
            TextInput(value=self.consent, on_change=self.set_consent, placeholder="Type: Roomay AI single operator"),
            Text(f"Context: {self.context}"),
            Text(f"Table: {self.table_status}"),
            Text(f"Record: {self.room_status}"),
            Text(f"Last successful operation: {self.last_success}"),
            Text(f"Failure: {self.failure}"),
            Text(f"Operation pending: {self.busy} | Writes locked after uncertain result: {self.uncertain}"),
            Button("1. Check connection / find table", on_click=self.check_connection) if not self.busy else Text("Waiting for operation"),
            Button("2. Create table if absent", on_click=self.create_table) if not self.busy and not self.uncertain else Text("Write action locked"),
            Button("3. Create fictional Room 201 if absent", on_click=self.create_room) if not self.busy and not self.uncertain else Text("Write action locked"),
            Button("4. Read saved records", on_click=self.read_saved) if not self.busy else Text("Waiting for operation"),
            Button("5. Mark Room 201 dirty", on_click=self.mark_dirty) if not self.busy and not self.uncertain else Text("Write action locked"),
            Text("A read-back is not a reload test. Reload, confirm context again, then Check and Read. See docs/dev-smoke.md."),
            gap=12,
        )
