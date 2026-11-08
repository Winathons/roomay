"""Isolated, owner-operated first-table setup; never registered in ui/main.py."""
from workpeg.ui import (
    App, Button, Column, Route, Router, State, Text, TextInput, route,
    set_interval, workpeg,
)


PEG_NAMESPACE = "roomay"
TABLE_NAMESPACE = "roomay_hotel_v1"
REQUEST_NAMESPACE = "roomay_requests_v1"
OWNER_ATTESTATION = "I VERIFIED ROOMAY AI OWNER CONTEXT"
CREATE_CONFIRMATION = "CREATE room_types ONLY"
INVENTORY_ATTESTATION = "OWNER VERIFIED NO room_types TABLE"
SDK_RETRY_ACK = "I UNDERSTAND SDK 401/403 REFRESH RETRY"


class DevTableSetup(App):
    expected_business = State("")
    owner_attestation = State("")
    inventory_attestation = State("")
    sdk_retry_ack = State("")
    create_confirmation = State("")
    busy = State(False)
    preflight_ready = State(False)
    preflight_lines = State([])
    timed_out = State(False)
    uncertain = State(False)
    ticks = State(0)
    context_status = State("Not checked; authentication and owner role are unknown.")
    inventory_status = State("Not checked")
    inventory_lines = State([])
    failure = State("")
    last_success = State("None")
    table_uuid = State("")

    def on_mount(self):
        set_interval(self.watch_timeout, 1000)

    def set_business(self, value):
        if not self.busy:
            self.expected_business = value.strip()

    def set_owner_attestation(self, value):
        if not self.busy:
            self.owner_attestation = value

    def set_inventory_attestation(self, value):
        if not self.busy:
            self.inventory_attestation = value

    def set_sdk_retry_ack(self, value):
        if not self.busy:
            self.sdk_retry_ack = value

    def set_create_confirmation(self, value):
        if not self.busy:
            self.create_confirmation = value

    def valid_uuid(self, value):
        if str(value) != value or len(value) != 36:
            return False
        for index in range(36):
            if index in [8, 13, 18, 23]:
                if value[index] != "-":
                    return False
            elif value[index] not in "0123456789abcdef":
                return False
        return True

    def context_is_confirmed(self):
        active_business = route.business_id
        if (not self.valid_uuid(active_business)
                or self.expected_business != active_business):
            self.failure = "Business mismatch. Enter the owner-verified Roomay AI business UUID matching this page URL."
            return False
        if self.owner_attestation != OWNER_ATTESTATION:
            self.failure = "Owner context is not verified by the SDK. Verify the signed-in owner and Roomay AI business in Workpeg, then enter the exact attestation."
            return False
        return True

    def valid_table(self, table):
        if (table.get("name") != "room_types"
                or table.get("namespace") != TABLE_NAMESPACE
                or str(table.get("permission")) != "700"
                or not self.valid_uuid(table.get("uuid", ""))):
            return False
        metadata = table.get("metadata", {})
        extra = metadata.get("extra", {})
        if (len(metadata) != 1 or len(extra) != 1
                or extra.get("contract") != "roomay.hotel.v1"):
            return False
        columns = table.get("columns")
        if not isinstance(columns, list) or len(columns) != 4:
            return False
        expected = [
            ["business_id", "uuid", 500],
            ["entity_id", "uuid", 1000],
            ["name", "text", 2000],
            ["capacity", "number", 3000],
        ]
        for index in range(4):
            column = columns[index]
            if (column.get("id") != expected[index][0]
                    or column.get("name") != expected[index][0]
                    or column.get("type") != expected[index][1]
                    or column.get("position") != expected[index][2]
                    or column.get("required") != True
                    or len(column.get("options", {})) != 0
                    or len(column.get("metadata", {})) != 0):
                return False
        return True

    def owner_summary(self, table):
        owner = table.get("owner")
        if owner is not None and owner.get("id") is not None:
            return "owner id " + str(owner.get("id"))
        return "owner not returned"

    async def fetch_inventory(self):
        hotel_tables = await workpeg.get_tables(TABLE_NAMESPACE)
        if self.timed_out:
            return None
        request_tables = await workpeg.get_tables(REQUEST_NAMESPACE)
        if self.timed_out:
            return None
        if not isinstance(hotel_tables, list) or not isinstance(request_tables, list):
            self.failure = "Malformed table-list response. Inventory is unknown; no create was attempted."
            return None
        lines = []
        all_tables = []
        groups = [[TABLE_NAMESPACE, hotel_tables], [REQUEST_NAMESPACE, request_tables]]
        for group in groups:
            namespace = group[0]
            tables = group[1]
            for table in tables:
                if table.get("namespace") != namespace:
                    self.failure = "Returned table namespace mismatch. Inventory is unsafe; no create was attempted."
                    return None
                name = table.get("name")
                table_uuid = table.get("uuid")
                if (not name or not self.valid_uuid(table_uuid)
                        or table.get("permission") is None):
                    self.failure = "Malformed table identity or permission. Inventory is unknown; no create was attempted."
                    return None
                lines.append(namespace + " / " + name + " / UUID " + table_uuid
                             + " / permission " + str(table.get("permission"))
                             + " / " + self.owner_summary(table))
                all_tables.append(table)
        self.inventory_lines = lines
        return all_tables

    def classify_existing(self, tables):
        room_types = []
        for table in tables:
            if table.get("name") == "room_types" and table.get("namespace") == TABLE_NAMESPACE:
                room_types.append(table)
        if len(room_types) > 1:
            self.failure = "Duplicate room_types tables are visible. Stop for owner reconciliation; no create was attempted."
            return "blocked"
        if len(tables) > len(room_types):
            names = []
            for table in tables:
                if table.get("name") != "room_types":
                    names.append(table.get("name", "unknown"))
            self.failure = "Other Roomay namespace tables are visible (" + ", ".join(names) + "). Stop for full schema review; this procedure creates only the first table."
            return "blocked"
        if room_types:
            if not self.valid_table(room_types[0]):
                self.failure = "Existing room_types schema, permission, metadata, or identity is incompatible. No create was attempted."
                return "blocked"
            self.table_uuid = room_types[0].get("uuid", "")
            return "exists"
        # This is deliberately a first-table-only procedure. Any existing table
        # in either Roomay namespace requires the full inventory planner/review.
        return "absent"

    def same_inventory(self, current_lines):
        if len(current_lines) != len(self.preflight_lines):
            return False
        for index in range(len(current_lines)):
            if current_lines[index] != self.preflight_lines[index]:
                return False
        return True

    def room_types_payload(self):
        return {
            "name": "room_types",
            "alias": "roomay-hotel-v1-room-types",
            "namespace": TABLE_NAMESPACE,
            "permission": "700",
            "metadata": {"extra": {"contract": "roomay.hotel.v1"}},
            "columns": [
                {"id": "business_id", "name": "business_id", "type": "uuid", "required": True, "position": 500},
                {"id": "entity_id", "name": "entity_id", "type": "uuid", "required": True, "position": 1000},
                {"id": "name", "name": "name", "type": "text", "required": True, "position": 2000},
                {"id": "capacity", "name": "capacity", "type": "number", "required": True, "position": 3000},
            ],
        }

    async def inspect(self):
        await self.run_operation("inspect")

    async def create_first_table(self):
        await self.run_operation("create_room_types")

    async def run_operation(self, operation):
        if self.busy or self.uncertain:
            return
        if not self.context_is_confirmed():
            return
        if operation == "create_room_types" and not self.preflight_ready:
            self.failure = "Inspect both namespaces and review the fresh inventory before the separate create confirmation."
            return
        if operation == "create_room_types" and self.create_confirmation != CREATE_CONFIRMATION:
            self.failure = "Type the exact one-table confirmation before the create action."
            return
        if (operation == "create_room_types"
                and self.inventory_attestation != INVENTORY_ATTESTATION):
            self.failure = "Owner must verify that no inaccessible room_types table already exists before creation."
            return
        if operation == "create_room_types" and self.sdk_retry_ack != SDK_RETRY_ACK:
            self.failure = "Acknowledge that the pinned protected helper may refresh and retry once after 401/403 before any create."
            return
        self.busy = True
        self.ticks = 0
        self.timed_out = False
        self.failure = ""
        self.inventory_status = "Refreshing both readable namespaces"
        self.context_status = "Checking protected Workpeg table access for the URL business; owner role remains a manual verification."
        write_started = False
        try:
            tables = await self.fetch_inventory()
            if tables is None or self.timed_out:
                return
            self.context_status = "Protected table reads succeeded for URL business " + route.business_id + "; owner identity is not exposed by this UI helper."
            self.inventory_status = "Readable inventory fetched; inaccessible tables may be hidden by Workpeg."
            disposition = self.classify_existing(tables)
            if disposition == "blocked":
                self.preflight_ready = False
                return
            if operation == "inspect":
                if disposition == "exists":
                    self.preflight_ready = False
                    self.last_success = "Read-only inventory inspected; room_types UUID " + self.table_uuid
                else:
                    self.preflight_lines = []
                    for line in self.inventory_lines:
                        self.preflight_lines.append(line)
                    self.preflight_ready = True
                    self.last_success = "Read-only inventory inspected; no visible tables in the two Roomay namespaces (not proof of inaccessible-table absence)"
                return
            if not self.same_inventory(self.inventory_lines):
                self.preflight_ready = False
                self.failure = "Fresh inventory differs from the reviewed preflight. Inspect again and review before any create."
                return
            if disposition == "exists":
                self.preflight_ready = False
                self.last_success = "room_types already exists with the expected visible schema; no create sent"
                return
            if disposition != "absent":
                self.failure = "Inventory does not authorize the first-table operation."
                return
            payload = self.room_types_payload()
            self.preflight_ready = False
            write_started = True
            created = await workpeg.create_table(payload)
            if self.timed_out:
                return
            if not self.valid_table(created):
                self.failure = "Create response is malformed or differs from the reviewed room_types contract. Outcome is uncertain; do not retry."
                return
            created_uuid = created.get("uuid")
            owner_display = self.owner_summary(created)
            direct = await workpeg.get_table(created_uuid)
            if self.timed_out:
                return
            if not self.valid_table(direct) or direct.get("uuid") != created_uuid:
                self.failure = "Direct table read-back did not match the create response. Outcome is uncertain; do not retry."
                return
            listed = await self.fetch_inventory()
            if listed is None or self.timed_out:
                return
            disposition = self.classify_existing(listed)
            if disposition != "exists" or self.table_uuid != created_uuid:
                self.failure = "Fresh namespace listing did not show exactly the created room_types UUID. Outcome is uncertain; do not retry."
                return
            self.last_success = "One room_types table created and matched create, direct GET, and fresh namespace listing; owner " + owner_display
            self.inventory_status = "Verified by response and read-back; reload verification remains outstanding."
        except Exception as error:
            if not self.timed_out:
                message = str(error)
                if "HTTP 401" in message:
                    self.failure = "Authentication failed (401). No success claimed."
                elif "HTTP 403" in message:
                    self.failure = "Access denied (403). Verify business membership and table permissions."
                else:
                    self.failure = "Workpeg operation failed or response was malformed. No success claimed; inspect with the owner."
                self.context_status = "Access not currently verified."
        finally:
            if write_started and (self.failure or self.timed_out):
                self.uncertain = True
                self.inventory_status = "Write outcome unknown; no automatic retry."
            if not self.timed_out:
                self.busy = False

    def watch_timeout(self):
        if self.busy and not self.timed_out:
            self.ticks += 1
            if self.ticks >= 30:
                self.timed_out = True
                self.uncertain = True
                self.failure = "Operation timed out. Outcome is unknown; stop and reconcile with the owner. No retry or rollback is available here."

    def build(self):
        return Column(
            Text("Roomay / isolated development schema check"),
            Text("Development-only artifact. No guest data. Not registered in ui/main.py or the release router."),
            Text("Peg namespace: roomay (compiled). Table namespaces: roomay_hotel_v1 and roomay_requests_v1."),
            Text("Enter the exact business UUID from the selected Roomay AI development business in Workpeg."),
            TextInput(value=self.expected_business, on_change=self.set_business, placeholder="Owner-verified Roomay AI business UUID"),
            Text("The SDK helper does not expose the signed-in person's role. Verify owner identity and business name in Workpeg before attesting."),
            TextInput(value=self.owner_attestation, on_change=self.set_owner_attestation, placeholder="Type: I VERIFIED ROOMAY AI OWNER CONTEXT"),
            Text("get_tables lists readable tables only. Separately verify in the owner dashboard that no hidden/inaccessible room_types table already exists."),
            TextInput(value=self.inventory_attestation, on_change=self.set_inventory_attestation, placeholder="Type: OWNER VERIFIED NO room_types TABLE"),
            Text("Workpeg 0.152.0 protected requests may refresh and retry once after 401/403; this controller cannot disable SDK behavior."),
            TextInput(value=self.sdk_retry_ack, on_change=self.set_sdk_retry_ack, placeholder="Type: I UNDERSTAND SDK 401/403 REFRESH RETRY"),
            Text("Active URL business ID: " + route.business_id),
            Text("Exact schema preview: name room_types; alias roomay-hotel-v1-room-types; namespace roomay_hotel_v1; permission 700; metadata extra.contract roomay.hotel.v1; columns at positions 500/1000/2000/3000: business_id uuid, entity_id uuid, name text, capacity number (all required)."),
            TextInput(value=self.create_confirmation, on_change=self.set_create_confirmation, placeholder="Type: CREATE room_types ONLY"),
            Text("Authenticated context: " + self.context_status),
            Text("Inventory: " + self.inventory_status),
            Text("Fresh preflight reviewed for one-table creation: " + str(self.preflight_ready)),
            Text("Tables: " + str(self.inventory_lines)),
            Text("Last successful operation: " + self.last_success),
            Text("Failure: " + self.failure),
            Text("Write outcome uncertain: " + str(self.uncertain)),
            Button("Inspect both namespaces (read only)", on_click=self.inspect) if not self.busy else Text("Operation running"),
            Button("Create room_types only (owner approval required)", on_click=self.create_first_table) if not self.busy and not self.uncertain and self.preflight_ready else Text("Inspect and review a fresh inventory before create"),
            Text("Create action repeats the complete inventory read and creates only if no Roomay namespace tables are visible. This cannot prove inaccessible tables are absent. No row create/update/delete controls exist."),
            gap=12,
        )


class DevTableSetupRouter(Router):
    routes = [Route("/b/[business_id]/dev-table-setup", DevTableSetup)]
