"""Isolated WOR-58 manual row test; never imported by the release UI."""
from workpeg.ui import App, Button, Column, Route, Router, State, Text, TextInput, route, set_interval, workpeg


TABLE_NAMESPACE = "roomay_hotel_v1"
OWNER_ATTESTATION = "I VERIFIED ROOMAY AI OWNER CONTEXT"
SDK_RETRY_ACK = "I UNDERSTAND SDK 401/403 REFRESH RETRY"
ROW_PERMISSION_ATTESTATION = "I VERIFIED NO ROW-LEVEL GRANTS"
INSERT_CONFIRMATION = "INSERT ROOMAY TEST ROOM TYPE"
UPDATE_CONFIRMATION = "UPDATE ROOMAY TEST CAPACITY ONLY"
ENTITY_ID = "4a3e15b4-2df4-5a22-93c5-720d4eaa5801"
PAGE_SIZE = 100
MAX_PAGES = 10


class DevRoomTypesRows(App):
    expected_business = State("")
    owner_attestation = State("")
    permission_attestation = State("")
    sdk_retry_ack = State("")
    insert_confirmation = State("")
    update_confirmation = State("")
    busy = State(False)
    uncertain = State(False)
    ticks = State(0)
    timed_out = State(False)
    table_uuid = State("")
    table_status = State("Not inspected")
    row_status = State("Not read")
    rows_summary = State([])
    failure = State("")
    last_success = State("None")
    insert_prepared = State(False)
    update_prepared = State(False)
    prepared_signature = State("")
    prepared_business = State("")
    prepared_row_id = State(0)
    prepared_fingerprint = State("")

    def on_mount(self):
        # Timer only: no table or row access happens on mount.
        set_interval(self.watch_timeout, 1000)

    def valid_uuid(self, value):
        if value is None or len(value) != 36:
            return False
        for index in range(36):
            if index in [8, 13, 18, 23]:
                if value[index] != "-":
                    return False
            elif value[index] not in "0123456789abcdef":
                return False
        return True

    def set_business(self, value):
        if not self.busy:
            cleaned = value.strip()
            if cleaned != self.expected_business:
                self.expected_business = cleaned
                self.owner_attestation = ""
                self.permission_attestation = ""
                self.insert_prepared = False
                self.update_prepared = False
                self.insert_confirmation = ""
                self.update_confirmation = ""

    def set_owner_attestation(self, value):
        if not self.busy:
            self.owner_attestation = value

    def set_permission_attestation(self, value):
        if not self.busy:
            self.permission_attestation = value

    def set_retry_ack(self, value):
        if not self.busy:
            self.sdk_retry_ack = value

    def set_insert_confirmation(self, value):
        if not self.busy:
            self.insert_confirmation = value

    def set_update_confirmation(self, value):
        if not self.busy:
            self.update_confirmation = value

    def context_ok(self):
        business = route.business_id
        if not self.valid_uuid(business) or self.expected_business != business:
            self.failure = "Business mismatch. Verify the Roomay AI development business URL and enter its exact UUID."
            return False
        if self.owner_attestation != OWNER_ATTESTATION:
            self.failure = "Owner context is not verified by this UI. Verify the signed-in owner and Roomay AI business in Workpeg."
            return False
        return True

    def table_valid(self, table):
        if (table.get("name") != "room_types" or table.get("namespace") != TABLE_NAMESPACE
                or str(table.get("permission")) != "700" or not self.valid_uuid(table.get("uuid"))):
            return False
        metadata = table.get("metadata", {})
        extra = metadata.get("extra", {})
        if (len(metadata) != 1 or len(extra) != 1
                or extra.get("contract") != "roomay.hotel.v1"):
            return False
        columns = table.get("columns")
        expected = [["business_id", "uuid", 500], ["entity_id", "uuid", 1000],
                    ["name", "text", 2000], ["capacity", "number", 3000]]
        if not isinstance(columns, list) or len(columns) != len(expected):
            return False
        for index in range(len(expected)):
            column = columns[index]
            item = expected[index]
            if (column.get("id") != item[0]
                    or column.get("name") != item[0] or column.get("type") != item[1]
                    or column.get("position") != item[2] or column.get("required") != True
                    or len(column.get("options", {})) != 0
                    or len(column.get("metadata", {})) != 0):
                return False
        return True

    async def find_table(self):
        tables = await workpeg.get_tables(TABLE_NAMESPACE)
        if self.timed_out:
            return None
        if not isinstance(tables, list):
            self.failure = "Malformed table listing; table state is unknown."
            return None
        matches = []
        for item in tables:
            if item.get("name") == "room_types":
                matches.append(item)
        if len(matches) != 1 or not self.table_valid(matches[0]):
            self.failure = "room_types is missing, duplicated, inaccessible, or differs from the canonical owner-only schema. No write is allowed."
            self.table_uuid = ""
            return None
        found = matches[0]
        direct = await workpeg.get_table(found["uuid"])
        if self.timed_out:
            return None
        if not self.table_valid(direct) or direct.get("uuid") != found["uuid"]:
            self.failure = "Direct table read-back mismatched the namespace listing. No write is allowed."
            return None
        self.table_uuid = found["uuid"]
        self.table_status = "Existing room_types table verified by listing and direct GET; permission 700"
        return self.table_uuid

    def row_valid(self, row, business):
        row_id = row.get("id")
        fingerprint = row.get("fingerprint")
        data = row.get("data")
        return (row_id > 0 and len(fingerprint) > 0
                and str(row.get("permission")) == "700"
                and row.get("inherit_business_permission") == True
                and row.get("inherit_individual_permissions") == False
                and data.get("business_id") == business and self.valid_uuid(data.get("entity_id"))
                and len(data.get("name")) > 0 and data.get("capacity") >= 0)

    async def read_inventory(self):
        rows = []
        offset = 0
        ended = False
        for page_index in range(MAX_PAGES):
            if not ended:
                page = await workpeg.get_rows(self.table_uuid, limit=PAGE_SIZE, offset=offset)
                if self.timed_out:
                    return None
                if not isinstance(page, list) or len(page) > PAGE_SIZE:
                    self.failure = "Malformed row page; complete inventory is not established."
                    return None
                if len(page) < PAGE_SIZE:
                    ended = True
                for row in page:
                    if not self.row_valid(row, route.business_id):
                        self.failure = "Malformed, incomplete, or cross-business row. Inventory is unsafe; no write is allowed."
                        return None
                    rows.append(row)
                offset += PAGE_SIZE
        if not ended:
            self.failure = "Row inventory exceeded the safety page limit; no write is allowed."
            return None
        ids = []
        fingerprints = []
        entities = []
        for row in rows:
            if row["id"] in ids or row["fingerprint"] in fingerprints or row["data"]["entity_id"] in entities:
                self.failure = "Duplicate native row identity, fingerprint, or entity ID. Stop for owner reconciliation."
                return None
            ids.append(row["id"])
            fingerprints.append(row["fingerprint"])
            entities.append(row["data"]["entity_id"])
        self.rows_summary = ["row " + str(row["id"]) + " / fingerprint " + row["fingerprint"]
                             + " / " + row["data"]["name"] + " / capacity " + str(row["data"]["capacity"])
                             for row in rows]
        return rows

    def row_signature(self, rows):
        # Canonical selected values used to detect stale preparation.
        parts = []
        for row in rows:
            data = row["data"]
            encoded = ""
            for key in data:
                encoded = encoded + "|" + key + "=" + str(data[key])
            parts.append(str(row["id"]) + "|" + row["fingerprint"] + encoded)
        return "\n".join(parts)

    def data_equal(self, left, right):
        if len(left) != len(right):
            return False
        for key in left:
            if key not in right or left[key] != right[key]:
                return False
        return True

    def synthetic_matches(self, row):
        data = row["data"]
        return (data.get("entity_id") == ENTITY_ID
                and data.get("name") == "Roomay TEST Room Type (Fictional)"
                and data.get("capacity") in [2, 3])

    async def inspect_table(self):
        await self.run("inspect")

    async def read_rows(self):
        await self.run("read")

    async def prepare_insert(self):
        await self.run("prepare_insert")

    async def insert_row(self):
        await self.run("insert")

    async def prepare_update(self):
        await self.run("prepare_update")

    async def update_row(self):
        await self.run("update")

    async def run(self, operation):
        if self.busy:
            return
        if self.uncertain and operation in ["prepare_insert", "insert", "prepare_update", "update"]:
            self.failure = "A prior write is uncertain. This page session remains write-locked; reconcile with the owner before any new session."
            return
        self.failure = ""
        if not self.context_ok():
            return
        if operation == "insert" and (not self.insert_prepared or self.insert_confirmation != INSERT_CONFIRMATION):
            self.failure = "Prepare the insert, then type its separate exact owner confirmation."
            return
        if operation == "update" and (not self.update_prepared or self.update_confirmation != UPDATE_CONFIRMATION):
            self.failure = "Prepare the update, then type its separate exact owner confirmation."
            return
        if operation in ["insert", "update"] and self.sdk_retry_ack != SDK_RETRY_ACK:
            self.failure = "Acknowledge the documented SDK 401/403 refresh-and-retry caveat before writing."
            return
        if operation in ["prepare_insert", "insert", "prepare_update", "update"] and self.permission_attestation != ROW_PERMISSION_ATTESTATION:
            self.failure = "Owner must verify there are no row-level permission grants before preparing or writing."
            return
        self.busy = True
        self.ticks = 0
        self.timed_out = False
        write_started = False
        try:
            table_id = await self.find_table()
            if not table_id or self.timed_out:
                return
            if operation == "inspect":
                self.last_success = "Existing table schema and owner-only permission inspected"
                return
            rows = await self.read_inventory()
            if rows is None or self.timed_out:
                return
            self.row_status = "Complete readable inventory: " + str(len(rows)) + " rows"
            signature = self.row_signature(rows)
            matching = [row for row in rows if self.synthetic_matches(row)]
            synthetic_identity = [row for row in rows if row["data"]["entity_id"] == ENTITY_ID]
            if operation == "read":
                self.insert_prepared = False
                self.update_prepared = False
                self.last_success = "Rows read from the existing Workpeg table"
                return
            if operation == "prepare_insert":
                self.insert_prepared = False
                self.update_prepared = False
                if rows:
                    self.failure = "Table is not empty. No insert prepared; this test requires a completely reviewed inventory with no unexpected rows."
                    return
                self.prepared_signature = signature
                self.prepared_business = route.business_id
                self.insert_prepared = True
                self.last_success = "Fictional row insert prepared only; no write sent"
                return
            if operation == "insert":
                if (signature != self.prepared_signature or rows
                        or self.prepared_business != route.business_id):
                    self.insert_prepared = False
                    self.failure = "Fresh inventory differs from the prepared empty inventory. Prepare again; no insert sent."
                    return
                self.insert_prepared = False
                self.insert_confirmation = ""
                self.permission_attestation = ""
                self.sdk_retry_ack = ""
                write_started = True
                saved = await workpeg.add_row(table_id, {
                    "data": {"business_id": route.business_id, "entity_id": ENTITY_ID,
                             "name": "Roomay TEST Room Type (Fictional)", "capacity": 2},
                    "position": 1000, "inherit_business_permission": True,
                    "inherit_individual_permissions": False,
                })
                if self.timed_out:
                    return
                if not self.row_valid(saved, route.business_id) or not self.synthetic_matches(saved):
                    self.failure = "Insert response lacks a valid native ID, fingerprint, or expected values. Outcome uncertain; do not retry."
                    return
                verify = await self.read_inventory()
                if verify is None or self.timed_out:
                    return
                found = [row for row in verify if row.get("id") == saved["id"]]
                if (len(found) != 1 or found[0].get("fingerprint") != saved["fingerprint"]
                        or not self.data_equal(found[0].get("data"), saved.get("data")) or len(verify) != 1):
                    self.failure = "Insert read-back did not exactly match native ID, fingerprint, values, and complete inventory. Outcome uncertain; do not retry."
                    return
                self.last_success = "Fictional row inserted and verified by fresh read; reload verification remains manual"
                self.row_status = "Verified one fictional row; reload the browser, then explicitly read again"
                return
            if operation == "prepare_update":
                self.insert_prepared = False
                self.update_prepared = False
                if len(rows) != 1 or len(matching) != 1 or len(synthetic_identity) != 1:
                    self.failure = "Update preparation requires exactly one recognized fictional row and no other rows."
                    return
                row = matching[0]
                if row["data"]["capacity"] != 2:
                    self.failure = "Fictional row is not in the expected ready-to-update state (capacity 2)."
                    return
                self.prepared_signature = signature
                self.prepared_business = route.business_id
                self.prepared_row_id = row["id"]
                self.prepared_fingerprint = row["fingerprint"]
                self.update_prepared = True
                self.last_success = "Capacity update prepared only; no write sent"
                return
            if operation == "update":
                if (signature != self.prepared_signature or len(rows) != 1 or len(matching) != 1
                        or self.prepared_business != route.business_id):
                    self.update_prepared = False
                    self.failure = "Fresh row inventory differs from update preparation. Prepare again; no update sent."
                    return
                row = matching[0]
                if (row["id"] != self.prepared_row_id or row["fingerprint"] != self.prepared_fingerprint
                        or row["data"]["capacity"] != 2):
                    self.update_prepared = False
                    self.failure = "Native row ID, fingerprint, or value changed since preparation. No update sent."
                    return
                data = {key: value for key, value in row["data"].items()}
                data["capacity"] = 3
                self.update_prepared = False
                self.update_confirmation = ""
                self.permission_attestation = ""
                self.sdk_retry_ack = ""
                write_started = True
                saved = await workpeg.update_row(table_id, row["id"], {"data": data})
                if self.timed_out:
                    return
                if (not self.row_valid(saved, route.business_id)
                        or saved.get("id") != row["id"] or saved.get("fingerprint") == row["fingerprint"]
                        or not self.data_equal(saved.get("data"), data)):
                    self.failure = "Update response did not confirm the same native ID, changed fingerprint, and full data. Outcome uncertain; do not retry."
                    return
                verify = await self.read_inventory()
                if verify is None or self.timed_out:
                    return
                found = [item for item in verify if item.get("id") == row["id"]]
                if (len(found) != 1 or found[0].get("fingerprint") != saved["fingerprint"]
                        or not self.data_equal(found[0].get("data"), data) or len(verify) != 1):
                    self.failure = "Update read-back mismatch. Outcome uncertain; do not retry."
                    return
                self.last_success = "Fictional row updated with unrelated fields preserved and verified by fresh read; reload verification remains manual"
                self.row_status = "Updated row verified; reload the browser, then explicitly read again"
        except Exception as error:
            if not self.timed_out:
                message = str(error)
                if "HTTP 401" in message:
                    self.failure = "Authentication failed (401). No success claimed."
                elif "HTTP 403" in message:
                    self.failure = "Access denied (403). Owner must verify business membership and owner-only permission."
                elif write_started:
                    self.failure = "Write failed or disconnected. Outcome uncertain; do not retry."
                else:
                    self.failure = "Read failed or response was malformed. No success claimed."
        finally:
            if write_started and (self.failure or self.timed_out):
                self.uncertain = True
            if not self.timed_out:
                self.busy = False

    def watch_timeout(self):
        if self.busy and not self.timed_out:
            self.ticks += 1
            if self.ticks >= 30:
                self.timed_out = True
                self.busy = False
                self.failure = "Operation timed out. Stop and have the owner reconcile; no automatic retry is available."

    def build(self):
        return Column(
            Text("Roomay — isolated room type row test"),
            Text("DEVELOPMENT ONLY. The existing room_types table is preserved; this screen never creates tables or deletes rows."),
            Text("Workpeg 0.152.0 may refresh and retry protected requests after 401/403. The SDK helper has no per-call switch to disable that behavior."),
            Text("Verify the signed-in owner and Roomay AI development business in Workpeg. The SDK UI does not expose an owner-role assertion."),
            TextInput(value=self.expected_business, on_change=self.set_business, placeholder="Owner-verified active business UUID"),
            TextInput(value=self.owner_attestation, on_change=self.set_owner_attestation, placeholder="I VERIFIED ROOMAY AI OWNER CONTEXT"),
            Text("Row helper responses do not enumerate individual row grants. Check them in Workpeg's owner UI before each prepare/write."),
            TextInput(value=self.permission_attestation, on_change=self.set_permission_attestation, placeholder="I VERIFIED NO ROW-LEVEL GRANTS"),
            TextInput(value=self.sdk_retry_ack, on_change=self.set_retry_ack, placeholder="Acknowledge SDK retry caveat before each write"),
            Text("Active URL business: " + route.business_id),
            Text("Synthetic row: stable entity ID; Roomay TEST Room Type (Fictional); capacity 2; business_id is taken from the active URL."),
            Text("Table: " + self.table_status), Text("Rows: " + self.row_status),
            Text("Visible fictional-safe row summary: " + str(self.rows_summary)),
            Text("Last successful operation: " + self.last_success), Text("Failure: " + self.failure),
            Text("Write outcome uncertain / write controls locked: " + str(self.uncertain)),
            Button("Inspect existing table", on_click=self.inspect_table) if not self.busy else Text("Loading table"),
            Button("Read current rows", on_click=self.read_rows) if not self.busy else Text("Loading rows"),
            Button("Prepare fictional insert", on_click=self.prepare_insert) if not self.busy and not self.uncertain else Text("Preparation unavailable until any uncertain write is reconciled"),
            TextInput(value=self.insert_confirmation, on_change=self.set_insert_confirmation, placeholder="INSERT ROOMAY TEST ROOM TYPE"),
            Button("Insert fictional row (owner approval required)", on_click=self.insert_row) if not self.busy and not self.uncertain and self.insert_prepared else Text("Prepare and review before insert"),
            Button("Prepare controlled capacity update", on_click=self.prepare_update) if not self.busy and not self.uncertain else Text("Preparation unavailable until any uncertain write is reconciled"),
            TextInput(value=self.update_confirmation, on_change=self.set_update_confirmation, placeholder="UPDATE ROOMAY TEST CAPACITY ONLY"),
            Button("Update fictional row (separate owner approval)", on_click=self.update_row) if not self.busy and not self.uncertain and self.update_prepared else Text("Prepare and review before update"),
            Text("After any verified write, manually reload the browser and click Read current rows. A successful API response alone is not persistence verification."),
            gap=12,
        )


class DevRoomTypesRowsRouter(Router):
    routes = [Route("/b/[business_id]/dev-room-types-rows", DevRoomTypesRows)]
