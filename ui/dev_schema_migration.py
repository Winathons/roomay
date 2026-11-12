"""Isolated, one-table-at-a-time owner migration UI; never release-routed."""
from workpeg.ui import App, Button, Column, Route, Router, Select, State, Text, TextInput, route, set_interval, workpeg


OWNER_ATTESTATION = "I VERIFIED ROOMAY AI OWNER CONTEXT"
SDK_RETRY_ACK = "I UNDERSTAND SDK 401/403 REFRESH RETRY"
CREATE_PREFIX = "CREATE ONLY: "
MISSING_PREFIX = "I VERIFIED THIS TABLE IS ABSENT: "
# The pinned UI compiler cannot invoke imported domain functions. The compiled
# contract mirror below is kept in sync by parity tests against the domain source.

class DevSchemaMigration(App):
    expected_business = State("")
    owner_attestation = State("")
    missing_attestation = State("")
    create_confirmation = State("")
    sdk_retry_ack = State("")
    selected_table = State("")
    selected_contract = State("")
    busy = State(False)
    uncertain = State(False)
    timed_out = State(False)
    ticks = State(0)
    reviewed_signature = State("")
    prepared_signature = State("")
    prepared_table = State("")
    prepared = State(False)
    owner_verified_missing = State([])
    plan_status = State("Not inspected; no Workpeg calls have been made.")
    table_lines = State([])
    unexpected_lines = State([])
    failure = State("")
    last_success = State("None")
    operation_status = State("Idle")

    def table_names(self):
        return ["room_types", "rooms", "guests", "reservations", "stays", "stay_guests", "room_blocks", "Roomay Service Requests", "Roomay Service Request Audit"]

    def creatable_names(self):
        return ["rooms", "guests", "reservations", "stays", "stay_guests", "room_blocks", "Roomay Service Requests", "Roomay Service Request Audit"]

    def alias_for(self, name):
        if name == "room_types": return "roomay-hotel-v1-room-types"
        if name == "rooms": return "roomay-hotel-v1-rooms"
        if name == "guests": return "roomay-hotel-v1-guests"
        if name == "reservations": return "roomay-hotel-v1-reservations"
        if name == "stays": return "roomay-hotel-v1-stays"
        if name == "stay_guests": return "roomay-hotel-v1-stay-guests"
        if name == "room_blocks": return "roomay-hotel-v1-room-blocks"
        if name == "Roomay Service Requests": return "roomay-service-requests-v1"
        if name == "Roomay Service Request Audit": return "roomay-service-request-audit-v1"
        return ""

    def fields_for(self, name):
        if name == "room_types": return [["entity_id", "uuid", True, [], {}], ["name", "text", True, [], {}], ["capacity", "number", True, [], {}]]
        if name == "rooms": return [["entity_id", "uuid", True, [], {}], ["number", "text", True, [], {}], ["room_type_id", "uuid", True, [], {}], ["enabled", "boolean", True, [], {}], ["housekeeping", "mutable_select", True, ["ready", "dirty", "cleaning", "inspection"], {}]]
        if name == "guests": return [["entity_id", "uuid", True, [], {}], ["display_name", "text", True, [], {}]]
        if name == "reservations": return [["entity_id", "uuid", True, [], {}], ["guest_id", "uuid", True, [], {}], ["room_type_id", "uuid", True, [], {}], ["room_id", "uuid", False, [], {}], ["arrival", "datetime", True, [], {"type": "date"}], ["departure", "datetime", True, [], {"type": "date"}], ["party_size", "number", True, [], {}], ["source", "mutable_select", True, ["advance", "walk_in"], {}], ["status", "mutable_select", True, ["pending_confirmation", "confirmed", "cancelled"], {}]]
        if name == "stays": return [["entity_id", "uuid", True, [], {}], ["reservation_id", "uuid", True, [], {}], ["room_id", "uuid", True, [], {}], ["checked_in_at", "datetime", True, [], {"type": "datetime"}], ["checked_out_at", "datetime", False, [], {"type": "datetime"}], ["status", "mutable_select", True, ["checked_in", "checked_out"], {}]]
        if name == "stay_guests": return [["entity_id", "uuid", True, [], {}], ["stay_id", "uuid", True, [], {}], ["guest_id", "uuid", True, [], {}], ["joined_at", "datetime", True, [], {"type": "datetime"}], ["left_at", "datetime", False, [], {"type": "datetime"}]]
        if name == "room_blocks": return [["entity_id", "uuid", True, [], {}], ["room_id", "uuid", True, [], {}], ["start", "datetime", True, [], {"type": "date"}], ["end", "datetime", True, [], {"type": "date"}], ["reason", "text", True, [], {}], ["status", "mutable_select", True, ["active", "released"], {}]]
        if name == "Roomay Service Requests": return [["request_id", "uuid", True, [], {}], ["idempotency_key", "text", True, [], {}], ["hotel_id", "uuid", True, [], {}], ["stay_id", "uuid", True, [], {}], ["room_id", "uuid", True, [], {}], ["guest_id", "uuid", True, [], {}], ["origin", "mutable_select", True, ["guest", "reception_desk", "phone", "staff"], {}], ["category", "mutable_select", True, ["unknown", "extra_towels", "linen", "room_cleaning", "toiletries", "plumbing", "electrical", "air_conditioning", "room_equipment", "room_service", "dining", "minibar", "transport", "wake_up_call", "billing_question", "general_help"], {}], ["category_detail", "text", True, [], {}], ["department", "mutable_select", True, ["housekeeping", "maintenance", "food_and_beverage", "reception"], {}], ["description", "text", True, [], {}], ["urgency", "mutable_select", True, ["low", "normal", "high", "urgent"], {}], ["status", "mutable_select", True, ["received", "assigned", "acknowledged", "in_progress", "resolved", "reopened", "cancelled", "escalated"], {}], ["assigned_staff_id", "text", False, [], {}], ["triage_required", "boolean", True, [], {}], ["sensitive", "boolean", True, [], {}], ["created_at", "datetime", True, [], {"type": "datetime"}], ["updated_at", "datetime", True, [], {"type": "datetime"}], ["received_at", "datetime", True, [], {"type": "datetime"}], ["acknowledge_by", "datetime", True, [], {"type": "datetime"}], ["due_at", "datetime", True, [], {"type": "datetime"}], ["assigned_at", "datetime", False, [], {"type": "datetime"}], ["acknowledged_at", "datetime", False, [], {"type": "datetime"}], ["in_progress_at", "datetime", False, [], {"type": "datetime"}], ["resolved_at", "datetime", False, [], {"type": "datetime"}], ["reopened_at", "datetime", False, [], {"type": "datetime"}], ["cancelled_at", "datetime", False, [], {"type": "datetime"}], ["escalated_at", "datetime", False, [], {"type": "datetime"}], ["version", "number", True, [], {}], ["last_event_id", "uuid", True, [], {}], ["last_operation_signature", "text", True, [], {}]]
        return [["event_id", "uuid", True, [], {}], ["operation_id", "uuid", True, [], {}], ["operation_signature", "text", True, [], {}], ["request_id", "uuid", True, [], {}], ["hotel_id", "uuid", True, [], {}], ["sequence", "number", True, [], {}], ["event_type", "mutable_select", True, ["created", "status_changed", "triaged"], {}], ["from_status", "text", False, [], {}], ["to_status", "mutable_select", True, ["received", "assigned", "acknowledged", "in_progress", "resolved", "reopened", "cancelled", "escalated"], {}], ["actor_id", "text", True, [], {}], ["actor_kind", "mutable_select", True, ["guest", "staff"], {}], ["actor_department", "mutable_select", False, ["housekeeping", "maintenance", "food_and_beverage", "reception"], {}], ["occurred_at", "datetime", True, [], {"type": "datetime"}], ["reason", "text", False, [], {}], ["commit_state", "mutable_select", True, ["pending", "committed"], {}]]

    def on_mount(self):
        # Timeout watcher only. Inventory inspection is always user initiated.
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
                self.missing_attestation = ""
                self.create_confirmation = ""
                self.prepared = False

    def set_owner_attestation(self, value):
        if not self.busy:
            self.owner_attestation = value

    def set_missing_attestation(self, value):
        if not self.busy:
            self.missing_attestation = value

    def set_create_confirmation(self, value):
        if not self.busy:
            self.create_confirmation = value

    def set_sdk_retry_ack(self, value):
        if not self.busy:
            self.sdk_retry_ack = value

    def set_selected_table(self, value):
        if not self.busy:
            self.selected_table = value
            self.selected_contract = ""
            self.prepared = False
            self.missing_attestation = ""
            self.create_confirmation = ""

    def context_ok(self):
        active_business = route.business_id
        if not self.valid_uuid(active_business) or self.expected_business != active_business:
            self.failure = "Business mismatch. Verify the Roomay AI development business UUID and its URL before continuing."
            return False
        if self.owner_attestation != OWNER_ATTESTATION:
            self.failure = "Owner context is not verified by this SDK UI. Verify the signed-in owner and Roomay AI business in Workpeg."
            return False
        return True

    def contract_payload(self, name):
        namespace = "roomay_requests_v1" if name in ["Roomay Service Requests", "Roomay Service Request Audit"] else "roomay_hotel_v1"
        contract_name = "roomay.service_requests.v1" if namespace == "roomay_requests_v1" else "roomay.hotel.v1"
        columns = [{"id": "business_id", "name": "business_id", "type": "uuid",
                    "required": True, "position": 500}]
        fields = self.fields_for(name)
        for index in range(len(fields)):
            spec = fields[index]
            column = {"id": spec[0], "name": spec[0], "type": spec[1],
                      "required": spec[2], "position": (index + 1) * 1000}
            if len(spec[3]) > 0:
                choices = []
                for value in spec[3]:
                    choices.append({"ref": value, "tag": value})
                column["options"] = {"choices": choices}
            if len(spec[4]) > 0:
                column["metadata"] = spec[4]
            columns.append(column)
        return {"name": name, "alias": self.alias_for(name), "namespace": namespace,
                "permission": "700", "metadata": {"extra": {"contract": contract_name}},
                "columns": columns}

    def schema_summary(self, name):
        contract = self.contract_payload(name)
        summary = (contract["name"] + " | alias " + contract["alias"]
                   + " | namespace " + contract["namespace"]
                   + " | permission " + contract["permission"]
                   + " | metadata extra.contract=" + contract["metadata"]["extra"]["contract"])
        for column in contract["columns"]:
            line = "\n" + column["id"] + " / " + column["type"]
            line = line + " / required=" + str(column["required"])
            line = line + " / position=" + str(column["position"])
            options = column.get("options", {})
            if len(options) > 0:
                refs = []
                for choice in options.get("choices", []):
                    refs.append(choice["ref"] + " (" + choice["tag"] + ")")
                line = line + " / choices=" + ",".join(refs)
            metadata = column.get("metadata", {})
            if len(metadata) > 0:
                line = line + " / metadata type=" + metadata.get("type", "unknown")
            summary = summary + line
        return summary

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

    def valid_table(self, name, table):
        contract = self.contract_payload(name)
        if table.get("name") != name or table.get("namespace") != contract["namespace"]:
            return {"valid": False, "uuid": "", "error": "table_identity_mismatch"}
        if str(table.get("permission")) != "700":
            return {"valid": False, "uuid": "", "error": "unsafe_table_permission"}
        if not self.valid_uuid(table.get("uuid")):
            return {"valid": False, "uuid": "", "error": "malformed_table_uuid"}
        metadata = table.get("metadata", {})
        extra = metadata.get("extra", {})
        if (len(metadata) != 1 or len(extra) != 1
                or extra.get("contract") != contract["metadata"]["extra"]["contract"]):
            return {"valid": False, "uuid": "", "error": "metadata"}
        columns = table.get("columns")
        expected = contract["columns"]
        if not isinstance(columns, list) or len(columns) != len(expected):
            return {"valid": False, "uuid": "", "error": "columns"}
        seen = []
        for column in columns:
            column_id = column.get("id")
            if column_id in seen:
                return {"valid": False, "uuid": "", "error": "columns"}
            seen.append(column_id)
        for wanted in expected:
            found = None
            for column in columns:
                if column.get("id") == wanted["id"]:
                    found = column
            if (found is None or found.get("name") != wanted["name"]
                    or found.get("type") != wanted["type"]
                    or found.get("required") != wanted["required"]
                    or found.get("position") != wanted["position"]):
                return {"valid": False, "uuid": "", "error": "columns"}
            wanted_options = wanted.get("options", {})
            found_options = found.get("options", {})
            if len(wanted_options) != len(found_options):
                return {"valid": False, "uuid": "", "error": "columns"}
            if len(wanted_options) > 0:
                left = wanted_options.get("choices", [])
                right = found_options.get("choices", [])
                if len(left) != len(right):
                    return {"valid": False, "uuid": "", "error": "columns"}
                for choice_index in range(len(left)):
                    if (left[choice_index].get("ref") != right[choice_index].get("ref")
                            or left[choice_index].get("tag") != right[choice_index].get("tag")):
                        return {"valid": False, "uuid": "", "error": "columns"}
            wanted_meta = wanted.get("metadata", {})
            found_meta = found.get("metadata", {})
            if len(wanted_meta) != len(found_meta):
                return {"valid": False, "uuid": "", "error": "columns"}
            if len(wanted_meta) > 0 and found_meta.get("type") != wanted_meta.get("type"):
                return {"valid": False, "uuid": "", "error": "columns"}
        return {"valid": True, "uuid": table.get("uuid"), "error": ""}

    def build_plan(self, hotel, requests):
        blockers = []
        unexpected = []
        all_tables = []
        ids = []
        if not isinstance(hotel, list) or not isinstance(requests, list):
            return {"valid_inventory": False, "blockers": ["malformed_or_inaccessible_namespace"],
                    "unexpected": [], "tables": [], "eligible": [], "signature": "malformed"}
        groups = [["roomay_hotel_v1", hotel], ["roomay_requests_v1", requests]]
        for group in groups:
            namespace = group[0]
            for table in group[1]:
                name = table.get("name")
                table_uuid = table.get("uuid")
                if (not name or table.get("namespace") != namespace
                        or not self.valid_uuid(table_uuid) or table.get("permission") is None
                        or not isinstance(table.get("columns"), list)):
                    blockers.append("malformed_table_inventory")
                else:
                    if table_uuid in ids:
                        blockers.append("duplicate_native_uuid")
                    ids.append(table_uuid)
                    all_tables.append(table)
                    known = False
                    for expected_name in self.table_names():
                        expected_contract = self.contract_payload(expected_name)
                        if expected_contract["namespace"] == namespace and expected_name == name:
                            known = True
                    if not known:
                        unexpected.append({"namespace": namespace, "name": name, "uuid": table_uuid})
        if len(unexpected) > 0:
            blockers.append("unexpected_tables_present")
        items = []
        signature_parts = []
        eligible = []
        for name in self.table_names():
            contract = self.contract_payload(name)
            matches = []
            for table in all_tables:
                if table.get("name") == name and table.get("namespace") == contract["namespace"]:
                    matches.append(table)
            state = "missing_or_unreadable"
            table_uuid = ""
            error = ""
            if len(matches) > 1:
                state = "duplicate"
                error = "duplicate_table"
                blockers.append("duplicate_table:" + name)
            elif len(matches) == 1:
                validation = self.valid_table(name, matches[0])
                table_uuid = matches[0].get("uuid", "")
                if validation["valid"]:
                    state = "existing_compatible"
                else:
                    error = validation["error"]
                    if error == "unsafe_table_permission":
                        state = "incorrect_permissions"
                    elif error == "metadata":
                        state = "incorrect_metadata"
                    elif error == "columns":
                        state = "incorrect_columns"
                    else:
                        state = "incompatible_table"
                    blockers.append(state + ":" + name)
            if name == "room_types" and state == "missing_or_unreadable":
                state = "required_existing_table_missing"
                blockers.append("required_room_types_missing_or_unreadable")
            is_eligible = (name != "room_types" and state == "missing_or_unreadable"
                           and name in self.owner_verified_missing)
            items.append({"name": name, "namespace": contract["namespace"], "alias": contract["alias"],
                          "permission": "700", "status": state, "uuid": table_uuid,
                          "error": error, "eligible": is_eligible, "contract": contract})
            signature_parts.append(name + "=" + state + "=" + table_uuid + "=" + error)
        if len(blockers) == 0:
            for item in items:
                if item["eligible"]:
                    eligible.append(item["name"])
        for item in unexpected:
            signature_parts.append("unexpected=" + item["namespace"] + "/" + item["name"] + "/" + item["uuid"])
        return {"valid_inventory": len(blockers) == 0, "blockers": blockers,
                "unexpected": unexpected, "tables": items, "eligible": eligible,
                "signature": "\n".join(signature_parts)}

    async def read_plan(self):
        hotel = await workpeg.get_tables("roomay_hotel_v1")
        if self.timed_out:
            return None
        requests = await workpeg.get_tables("roomay_requests_v1")
        if self.timed_out:
            return None
        plan = self.build_plan(hotel, requests)
        if plan.get("valid_inventory"):
            for item in plan["tables"]:
                if item["status"] == "existing_compatible":
                    direct = await workpeg.get_table(item["uuid"])
                    if self.timed_out:
                        return None
                    verified = self.valid_table(item["name"], direct)
                    if not verified["valid"] or verified["uuid"] != item["uuid"]:
                        plan["blockers"].append("direct_readback_mismatch:" + item["name"])
                        plan["valid_inventory"] = False
                        plan["eligible"] = []
                        item["status"] = "incompatible_table"
                        item["error"] = "direct_readback_mismatch"
            # A direct GET failure changes the fresh signature as well as the
            # eligibility state, so a create prepared against older state stops.
            plan["signature"] = plan["signature"] + "\nDIRECT=" + str(plan["valid_inventory"])
        return plan

    def show_plan(self, plan):
        lines = []
        for item in plan["tables"]:
            line = item["namespace"] + " / " + item["name"] + " / " + item["status"]
            if item["uuid"]:
                line = line + " / native UUID " + item["uuid"]
            if item["eligible"]:
                line = line + " / eligible after owner attestation"
            lines.append(line)
        self.table_lines = lines
        self.unexpected_lines = [item["namespace"] + " / " + item["name"]
                                 + " / native UUID " + item["uuid"]
                                 for item in plan["unexpected"]]
        if plan["blockers"]:
            self.plan_status = "Inventory has blockers: " + str(plan["blockers"])
        else:
            self.plan_status = "Both readable namespace inventories validated. Missing tables are still potentially inaccessible; owner dashboard review is required per table."

    async def inspect(self):
        await self.run("inspect")

    async def prepare_selected(self):
        await self.run("prepare")

    async def create_selected(self):
        await self.run("create")

    async def run(self, operation):
        if self.busy or self.uncertain:
            return
        self.failure = ""
        if not self.context_ok():
            return
        if operation in ["prepare", "create"]:
            if self.selected_table not in self.creatable_names():
                self.failure = "Select exactly one of the eight remaining canonical tables. room_types is intentionally not selectable."
                return
            if self.missing_attestation != MISSING_PREFIX + self.selected_table:
                self.failure = "Owner must independently verify this exact table is absent before preparation or creation."
                return
        if operation == "create":
            if not self.prepared or self.prepared_table != self.selected_table:
                self.failure = "Prepare and review one missing table before its separate create action."
                return
            if self.create_confirmation != CREATE_PREFIX + self.selected_table:
                self.failure = "Type the exact one-table creation confirmation."
                return
            if self.sdk_retry_ack != SDK_RETRY_ACK:
                self.failure = "Acknowledge the SDK 0.152.0 authentication refresh/retry caveat before creating."
                return
        self.busy = True
        self.ticks = 0
        self.timed_out = False
        self.operation_status = "Inspecting authenticated Workpeg inventory" if operation != "create" else "Rechecking inventory before one create"
        self.owner_verified_missing = [self.selected_table] if operation in ["prepare", "create"] else []
        self.failure = ""
        write_started = False
        try:
            plan = await self.read_plan()
            if plan is None or self.timed_out:
                return
            self.show_plan(plan)
            if operation == "inspect":
                self.prepared = False
                if not plan["valid_inventory"]:
                    # A readable response can still have missing/duplicate or
                    # incompatible tables. Never label that a validation success
                    # or retain an earlier approved inspection baseline.
                    self.reviewed_signature = ""
                    self.last_success = "None"
                    self.failure = "Inventory has blockers or missing required room_types. No table was validated for migration; no change was attempted."
                    self.operation_status = "Read-only inspection blocked; owner review required"
                    return
                self.reviewed_signature = plan["signature"]
                self.last_success = "Both namespaces inspected; existing room_types validated and never modified"
                self.operation_status = "Read-only inspection complete"
                return
            if not plan["valid_inventory"]:
                self.prepared = False
                self.failure = "Inventory is ambiguous or incompatible. No schema was changed. Review blockers and existing tables with the owner."
                return
            if operation == "prepare":
                if plan["signature"] != self.reviewed_signature:
                    self.prepared = False
                    self.failure = "Fresh inventory differs from the inspected baseline. Inspect again before preparing."
                    return
                if self.selected_table not in plan["eligible"]:
                    self.prepared = False
                    self.failure = "This table is not missing and owner-verified for creation. No write is allowed."
                    return
                selected = None
                for item in plan["tables"]:
                    if item["name"] == self.selected_table:
                        selected = item
                self.prepared_signature = plan["signature"]
                self.prepared_table = self.selected_table
                self.selected_contract = self.schema_summary(self.selected_table)
                self.prepared = True
                self.last_success = "One table schema prepared for review only; no write sent"
                self.operation_status = "Prepared, not created"
                return
            if operation == "create":
                if (plan["signature"] != self.prepared_signature
                        or self.selected_table not in plan["eligible"]):
                    self.prepared = False
                    self.failure = "Fresh inventory differs from the reviewed preparation or table eligibility. No create sent."
                    return
                selected = None
                for item in plan["tables"]:
                    if item["name"] == self.selected_table:
                        selected = item
                payload = selected["contract"]
                # Lock before the await: the SDK request may outlive the UI
                # timeout. This controller never sends a second create.
                self.prepared = False
                self.create_confirmation = ""
                self.missing_attestation = ""
                self.sdk_retry_ack = ""
                write_started = True
                self.operation_status = "One create request in flight; do not repeat"
                created = await workpeg.create_table(payload)
                if self.timed_out:
                    return
                created_check = self.valid_table(self.selected_table, created)
                if not created_check["valid"]:
                    self.failure = "Create response did not match the canonical schema or UUID contract. Outcome uncertain; do not retry."
                    return
                created_uuid = created_check["uuid"]
                direct = await workpeg.get_table(created_uuid)
                if self.timed_out:
                    return
                direct_check = self.valid_table(self.selected_table, direct)
                if not direct_check["valid"] or direct_check["uuid"] != created_uuid:
                    self.failure = "Direct GET did not match create response, native UUID, and exact schema. Outcome uncertain; do not retry."
                    return
                self.owner_verified_missing = []
                verified = await self.read_plan()
                if self.timed_out or verified is None:
                    return
                self.show_plan(verified)
                result = None
                for item in verified["tables"]:
                    if item["name"] == self.selected_table:
                        result = item
                if (not verified["valid_inventory"] or result is None
                        or result["status"] != "existing_compatible"
                        or result["uuid"] != created_uuid):
                    self.failure = "Fresh namespace list did not verify exactly the created table UUID and schema. Outcome uncertain; do not retry."
                    return
                self.reviewed_signature = verified["signature"]
                self.last_success = "One table created and verified by response, direct GET, and fresh namespace lists; native UUID " + created_uuid
                self.operation_status = "Verified. Reload manually, then inspect both namespaces again."
                return
        except Exception as error:
            if not self.timed_out:
                message = str(error)
                if "HTTP 401" in message:
                    self.failure = "Authentication failed (401). No success claimed."
                elif "HTTP 403" in message:
                    self.failure = "Access denied (403). Verify development business membership and owner permissions."
                elif write_started:
                    self.failure = "Create failed, timed out, or disconnected. Outcome uncertain; do not retry."
                else:
                    self.failure = "Inventory read failed or was malformed. No change was attempted."
        finally:
            if write_started and (self.failure or self.timed_out):
                self.uncertain = True
                self.operation_status = "Uncertain write outcome — locked; owner reconciliation required"
            if not self.timed_out:
                self.busy = False

    def watch_timeout(self):
        if self.busy and not self.timed_out:
            self.ticks += 1
            if self.ticks >= 30:
                self.timed_out = True
                self.uncertain = True
                self.failure = "Operation timed out. It may still be in flight; this screen is locked. Do not retry. Reconcile with the owner."
                self.operation_status = "Timed out — request may still be running"

    def build(self):
        return Column(
            Text("Roomay — owner-reviewed schema migration planner"),
            Text("DEVELOPMENT ONLY. Offline implementation; no provisioning runs on load, refresh, navigation, compilation, or CI."),
            Text("This isolated source is not registered in the production receptionist router. It never creates rows and never changes an existing schema."),
            Text("Workpeg SDK 0.152.0 protected helpers may refresh and retry after 401/403. No per-call disable switch was verified; owner acknowledgement is required for each future create."),
            Text("Verify the signed-in owner, Roomay AI business, and Peg installation in Workpeg before using any control. Typed confirmation is not authorization."),
            TextInput(value=self.expected_business, on_change=self.set_business, placeholder="Owner-verified Roomay AI development business UUID"),
            TextInput(value=self.owner_attestation, on_change=self.set_owner_attestation, placeholder="I VERIFIED ROOMAY AI OWNER CONTEXT"),
            Text("Active business UUID from Workpeg route: " + route.business_id),
            Button("Inspect both namespaces (read only)", on_click=self.inspect) if not self.busy else Text("Reading both namespaces"),
            Text("Planner status: " + self.plan_status),
            Text("All canonical tables: " + str(self.table_lines)),
            Text("Unexpected tables requiring owner review: " + str(self.unexpected_lines)),
            Select(options=["rooms", "guests", "reservations", "stays", "stay_guests", "room_blocks", "Roomay Service Requests", "Roomay Service Request Audit"], value=self.selected_table, on_change=self.set_selected_table,
                   label="Select one remaining table", placeholder="Choose exactly one missing table"),
            Text("Before preparation, review Workpeg owner inventory for the selected name, then type: " + MISSING_PREFIX + self.selected_table),
            TextInput(value=self.missing_attestation, on_change=self.set_missing_attestation,
                      placeholder="I VERIFIED THIS TABLE IS ABSENT: <exact selected name>"),
            Button("Prepare selected schema (read only)", on_click=self.prepare_selected) if not self.busy and not self.uncertain else Text("Preparation locked while operation is active or uncertain"),
            Text("Selected canonical schema and permission 700: " + self.selected_contract),
            TextInput(value=self.sdk_retry_ack, on_change=self.set_sdk_retry_ack,
                      placeholder="I UNDERSTAND SDK 401/403 REFRESH RETRY"),
            TextInput(value=self.create_confirmation, on_change=self.set_create_confirmation,
                      placeholder="CREATE ONLY: <exact selected name>"),
            Button("Create this one table (separate owner approval)", on_click=self.create_selected)
            if not self.busy and not self.uncertain and self.prepared else Text("Inspect, attest, and prepare one eligible table before creation"),
            Text("Operation status: " + self.operation_status),
            Text("Last successful operation: " + self.last_success),
            Text("Failure: " + self.failure),
            Text("Uncertain outcome / no-retry lock: " + str(self.uncertain)),
            Text("After a verified create, manually reload the browser and inspect both namespaces again before preparing another table."),
            gap=12,
        )


class DevSchemaMigrationRouter(Router):
    routes = [Route("/b/[business_id]/dev-schema-migration", DevSchemaMigration)]
