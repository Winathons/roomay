"""Isolated owner-operated WOR-60 row workflow; never release-routed."""
from workpeg.ui import App, Button, Column, Route, Router, State, Text, TextInput, dates, route, set_interval, workpeg


HOTEL_NS = "roomay_hotel_v1"
REQUEST_NS = "roomay_requests_v1"
OWNER_ATTESTATION = "I VERIFIED ROOMAY AI OWNER CONTEXT"
ROW_PERMISSION_ATTESTATION = "I VERIFIED OWNER-ONLY ROW ACCESS"
RETRY_ACK = "I UNDERSTAND SDK 401/403 REFRESH RETRY"
RECONCILIATION_ATTESTATION = "I RECONCILED ALL PRIOR WRITE OUTCOMES"
STAY_RELOAD_ATTESTATION = "I RELOADED AND VERIFIED THE ACTIVE STAY"
CONFIRM_PREFIX = "CREATE ONE WOR60 ROW: "
PAGE_SIZE = 100
MAX_PAGES = 100
ROOM_TYPE_NAME = "Roomay TEST Room Type (Fictional)"
ROOM_TYPE_CAPACITY = 3
ROOM_ID = "12e40a43-8cbf-5c29-8255-bba848bb7227"
GUEST_ID = "d9b8d2ce-cff7-5712-946d-24ae87c21f03"
RESERVATION_ID = "dbd2a533-a583-52e2-a4cb-fe5b24bd160f"
STAY_ID = "e19f6692-a7fd-50c5-ab5c-fc68fc58abe4"
OCCUPANT_ID = "cce2c93c-2db2-568d-bfb2-127dd4aae125"
HOTEL_ID = "0b2c132e-0582-5a75-9ddd-f9e0c72064cb"
REQUEST_ID = "be879138-ca76-54dd-9e97-893a30d4cb04"
AUDIT_ID = "a148307b-a836-524d-bd7b-30b41631a79f"
OPERATION_ID = "aedffe18-95d0-545c-a75c-dabb191a0a93"
REQUEST_SIGNATURE = "d12478556e0e5a38bbcace460642b1fb2fb51c0463f95e3b520c0d6202fa71e6"
class DevVerticalSlice(App):
    expected_business = State("")
    owner_attestation = State("")
    row_permission_attestation = State("")
    retry_ack = State("")
    reconciliation_attestation = State("")
    stay_reload_attestation = State("")
    confirmation = State("")
    operational_date = State("")
    hotel_timezone = State("")
    authoritative_local_now = State("")
    busy = State(False)
    timed_out = State(False)
    uncertain = State(False)
    write_started = State(False)
    write_started_this_page = State(False)
    ticks = State(0)
    table_ids = State({})
    inventory_rows = State({})
    inventory_signature = State("")
    selected_step = State("")
    selected_payload = State({})
    selected_preview = State("")
    stay_reload_verified = State(False)
    table_summary = State([])
    row_summary = State([])
    room_type_entity_id = State("")
    status = State("Not inspected. No Workpeg calls have been made.")
    error = State("")
    last_success = State("None")

    def on_mount(self):
        # The timer only bounds an explicitly started operation.
        set_interval(self.watch_timeout, 1000)

    def table_definitions(self):
        return [
            ["room_types", "roomay_hotel_v1", "roomay-hotel-v1-room-types", "hotel", "entity_id"],
            ["rooms", "roomay_hotel_v1", "roomay-hotel-v1-rooms", "hotel", "entity_id"],
            ["guests", "roomay_hotel_v1", "roomay-hotel-v1-guests", "hotel", "entity_id"],
            ["reservations", "roomay_hotel_v1", "roomay-hotel-v1-reservations", "hotel", "entity_id"],
            ["stays", "roomay_hotel_v1", "roomay-hotel-v1-stays", "hotel", "entity_id"],
            ["stay_guests", "roomay_hotel_v1", "roomay-hotel-v1-stay-guests", "hotel", "entity_id"],
            ["room_blocks", "roomay_hotel_v1", "roomay-hotel-v1-room-blocks", "hotel", "entity_id"],
            ["Roomay Service Requests", "roomay_requests_v1", "roomay-service-requests-v1", "requests", "request_id"],
            ["Roomay Service Request Audit", "roomay_requests_v1", "roomay-service-request-audit-v1", "requests", "event_id"],
        ]

    def record_order(self):
        return ["rooms", "guests", "reservations", "stays", "stay_guests",
                "service_requests", "service_request_audit"]

    def table_key(self, name):
        if name == "Roomay Service Requests": return "service_requests"
        if name == "Roomay Service Request Audit": return "service_request_audit"
        return name

    def table_names(self):
        names = []
        for item in self.table_definitions(): names.append(item[0])
        return names

    def alias_for(self, name):
        for item in self.table_definitions():
            if item[0] == name: return item[2]
        return ""

    def fields_for(self, name):
        if name == "room_types": return [["entity_id", "uuid", True, [], {}], ["name", "text", True, [], {}], ["capacity", "number", True, [], {}]]
        if name == "rooms": return [["entity_id", "uuid", True, [], {}], ["number", "text", True, [], {}], ["room_type_id", "uuid", True, [], {}], ["enabled", "boolean", True, [], {}], ["housekeeping", "mutable_select", True, ["ready", "dirty", "cleaning", "inspection"], {}]]
        if name == "guests": return [["entity_id", "uuid", True, [], {}], ["display_name", "text", True, [], {}]]
        if name == "reservations": return [["entity_id", "uuid", True, [], {}], ["guest_id", "uuid", True, [], {}], ["room_type_id", "uuid", True, [], {}], ["room_id", "uuid", False, [], {}], ["arrival", "datetime", True, [], {"type": "date"}], ["departure", "datetime", True, [], {"type": "date"}], ["party_size", "number", True, [], {}], ["source", "mutable_select", True, ["advance", "walk_in"], {}], ["status", "mutable_select", True, ["pending_confirmation", "confirmed", "cancelled"], {}]]
        if name == "stays": return [["entity_id", "uuid", True, [], {}], ["reservation_id", "uuid", True, [], {}], ["room_id", "uuid", True, [], {}], ["checked_in_at", "datetime", True, [], {"type": "datetime"}], ["checked_out_at", "datetime", False, [], {"type": "datetime"}], ["status", "mutable_select", True, ["checked_in", "checked_out"], {}]]
        if name == "stay_guests": return [["entity_id", "uuid", True, [], {}], ["stay_id", "uuid", True, [], {}], ["guest_id", "uuid", True, [], {}], ["joined_at", "datetime", True, [], {"type": "datetime"}], ["left_at", "datetime", False, [], {"type": "datetime"}]]
        if name == "room_blocks": return [["entity_id", "uuid", True, [], {}], ["room_id", "uuid", True, [], {}], ["start", "datetime", True, [], {"type": "date"}], ["end", "datetime", True, [], {"type": "date"}], ["reason", "text", True, [], {}], ["status", "mutable_select", True, ["active", "released"], []]]
        if name == "Roomay Service Requests": return [["request_id", "uuid", True, [], {}], ["idempotency_key", "text", True, [], {}], ["hotel_id", "uuid", True, [], {}], ["stay_id", "uuid", True, [], {}], ["room_id", "uuid", True, [], {}], ["guest_id", "uuid", True, [], {}], ["origin", "mutable_select", True, ["guest", "reception_desk", "phone", "staff"], {}], ["category", "mutable_select", True, ["unknown", "extra_towels", "linen", "room_cleaning", "toiletries", "plumbing", "electrical", "air_conditioning", "room_equipment", "room_service", "dining", "minibar", "transport", "wake_up_call", "billing_question", "general_help"], {}], ["category_detail", "text", True, [], {}], ["department", "mutable_select", True, ["housekeeping", "maintenance", "food_and_beverage", "reception"], {}], ["description", "text", True, [], {}], ["urgency", "mutable_select", True, ["low", "normal", "high", "urgent"], {}], ["status", "mutable_select", True, ["received", "assigned", "acknowledged", "in_progress", "resolved", "reopened", "cancelled", "escalated"], {}], ["assigned_staff_id", "text", False, [], {}], ["triage_required", "boolean", True, [], {}], ["sensitive", "boolean", True, [], {}], ["created_at", "datetime", True, [], {"type": "datetime"}], ["updated_at", "datetime", True, [], {"type": "datetime"}], ["received_at", "datetime", True, [], {"type": "datetime"}], ["acknowledge_by", "datetime", True, [], {"type": "datetime"}], ["due_at", "datetime", True, [], {"type": "datetime"}], ["assigned_at", "datetime", False, [], {"type": "datetime"}], ["acknowledged_at", "datetime", False, [], {"type": "datetime"}], ["in_progress_at", "datetime", False, [], {"type": "datetime"}], ["resolved_at", "datetime", False, [], {"type": "datetime"}], ["reopened_at", "datetime", False, [], {"type": "datetime"}], ["cancelled_at", "datetime", False, [], {"type": "datetime"}], ["escalated_at", "datetime", False, [], {"type": "datetime"}], ["version", "number", True, [], {}], ["last_event_id", "uuid", True, [], {}], ["last_operation_signature", "text", True, [], {}]]
        return [["event_id", "uuid", True, [], {}], ["operation_id", "uuid", True, [], {}], ["operation_signature", "text", True, [], {}], ["request_id", "uuid", True, [], {}], ["hotel_id", "uuid", True, [], {}], ["sequence", "number", True, [], {}], ["event_type", "mutable_select", True, ["created", "status_changed", "triaged"], {}], ["from_status", "text", False, [], {}], ["to_status", "mutable_select", True, ["received", "assigned", "acknowledged", "in_progress", "resolved", "reopened", "cancelled", "escalated"], {}], ["actor_id", "text", True, [], {}], ["actor_kind", "mutable_select", True, ["guest", "staff"], {}], ["actor_department", "mutable_select", False, ["housekeeping", "maintenance", "food_and_beverage", "reception"], {}], ["occurred_at", "datetime", True, [], {"type": "datetime"}], ["reason", "text", False, [], {}], ["commit_state", "mutable_select", True, ["pending", "committed"], {}]]

    def contract(self, name):
        namespace = REQUEST_NS if name in ["Roomay Service Requests", "Roomay Service Request Audit"] else HOTEL_NS
        contract_type = "roomay.service_requests.v1" if namespace == REQUEST_NS else "roomay.hotel.v1"
        columns = [{"id": "business_id", "name": "business_id", "type": "uuid", "required": True, "position": 500}]
        fields = self.fields_for(name)
        for index in range(len(fields)):
            spec = fields[index]
            column = {"id": spec[0], "name": spec[0], "type": spec[1], "required": spec[2], "position": (index + 1) * 1000}
            if len(spec[3]) > 0:
                choices = []
                for value in spec[3]: choices.append({"ref": value, "tag": value})
                column["options"] = {"choices": choices}
            if len(spec[4]) > 0: column["metadata"] = spec[4]
            columns.append(column)
        return {"name": name, "alias": self.alias_for(name), "namespace": namespace,
                "permission": "700", "metadata": {"extra": {"contract": contract_type}}, "columns": columns}

    def valid_uuid(self, value):
        if value is None: return False
        clean = str(value)
        if value != clean or len(clean) != 36: return False
        for index in range(36):
            if index in [8, 13, 18, 23]:
                if clean[index] != "-": return False
            elif clean[index] not in "0123456789abcdef": return False
        return True

    def context_ok(self):
        active_business = route.business_id
        if not self.valid_uuid(active_business) or self.expected_business != active_business:
            self.error = "Business URL mismatch. Verify the active Roomay AI development business."
            return False
        if self.owner_attestation != OWNER_ATTESTATION:
            self.error = "Verify the signed-in owner and Roomay AI business in Workpeg; typed text is not authentication."
            return False
        if self.row_permission_attestation != ROW_PERMISSION_ATTESTATION:
            self.error = "Owner must verify owner-only row access and no row-level grants in Workpeg."
            return False
        return True

    def on_set_business(self, value):
        if not self.busy:
            self.expected_business = value.strip()
            self.owner_attestation = ""
            self.row_permission_attestation = ""
            self.clear_preparation()

    def clear_preparation(self):
        self.selected_step = ""
        self.selected_payload = {}
        self.selected_preview = ""
        self.confirmation = ""

    def table_valid(self, name, table):
        expected = self.contract(name)
        if (table.get("name") != name or table.get("namespace") != expected["namespace"]
                or str(table.get("permission")) != "700" or not self.valid_uuid(table.get("uuid"))): self.error = "table identity or permission mismatch"; return False
        metadata = table.get("metadata", {})
        extra = metadata.get("extra", {})
        if (len(metadata) != 1 or len(extra) != 1
                or extra.get("contract") != expected["metadata"]["extra"]["contract"]):
            self.error = "table metadata mismatch"
            return False
        actual = table.get("columns")
        wanted = expected["columns"]
        if not isinstance(actual, list) or len(actual) != len(wanted): self.error = "table columns shape mismatch"; return False
        for expected_column in wanted:
            found = None
            for column in actual:
                if column.get("id") == expected_column["id"]: found = column
            if found is None: self.error = "table column is missing"; return False
            if (found.get("name") != expected_column["name"]
                    or found.get("type") != expected_column["type"]
                    or found.get("required") != expected_column["required"]
                    or found.get("position") != expected_column["position"]):
                self.error = "table column definition mismatch: " + expected_column["id"]
                return False
            found_options = found.get("options", {})
            expected_options = expected_column.get("options", {})
            if len(found_options) != len(expected_options):
                self.error = "table column options mismatch: " + expected_column["id"]
                return False
            if len(expected_options) > 0:
                found_choices = found_options.get("choices", [])
                expected_choices = expected_options.get("choices", [])
                if len(found_choices) != len(expected_choices):
                    self.error = "table column choices mismatch: " + expected_column["id"]
                    return False
                for choice_index in range(len(expected_choices)):
                    if (found_choices[choice_index].get("ref") != expected_choices[choice_index].get("ref")
                            or found_choices[choice_index].get("tag") != expected_choices[choice_index].get("tag")):
                        self.error = "table column choices mismatch: " + expected_column["id"]
                        return False
            found_metadata = found.get("metadata", {})
            expected_metadata = expected_column.get("metadata", {})
            if len(found_metadata) != len(expected_metadata):
                self.error = "table column metadata mismatch: " + expected_column["id"]
                return False
            if len(expected_metadata) > 0 and found_metadata.get("type", "") != expected_metadata.get("type", ""):
                self.error = "table column metadata mismatch: " + expected_column["id"]
                return False
        return True

    def valid_field(self, field, value):
        if value is None: return False
        kind = field[1]
        if kind in ["text", "uuid", "datetime", "mutable_select"]:
            if value is None or len(value.strip()) == 0: return False
            if kind == "uuid" and not self.valid_uuid(value): return False
            if kind == "mutable_select" and value not in field[3]: return False
            if kind == "datetime":
                if field[4].get("type") == "date": return dates.is_date(value)
                if self.instant_epoch(value) is None: return False
            return True
        if kind in ["number", "boolean"]: return True
        return False

    def instant_epoch(self, value):
        if str(value) != value: return None
        if len(value) == 20 and value[19] == "Z":
            local_value = value[:19]
            if dates.is_datetime(local_value): return dates.to_epoch(local_value, "UTC")
            return None
        if len(value) != 25 or value[19] not in ["+", "-"] or value[22] != ":": return None
        digits = value[20:22] + value[23:25]
        for character in digits:
            if character not in "0123456789": return None
        local_value = value[:19]
        if not dates.is_datetime(local_value): return None
        hours = int(value[20:22])
        minutes = int(value[23:25])
        if hours > 23 or minutes > 59: return None
        offset = (hours * 60 + minutes) * 60000
        epoch = dates.to_epoch(local_value, "UTC")
        if value[19] == "+": return epoch - offset
        return epoch + offset

    def validate_row(self, name, business, row, seen_ids, seen_entities, seen_fingerprints):
        if row.get("id") != int(row.get("id")) or row["id"] < 1:
            return "malformed native row identity"
        if row["id"] in seen_ids: return "duplicate native row ID"
        if row.get("fingerprint") != str(row.get("fingerprint")) or len(row["fingerprint"]) == 0:
            return "missing row fingerprint"
        if row["fingerprint"] in seen_fingerprints: return "duplicate row fingerprint"
        if str(row.get("permission")) != "700": return "non-owner-only row permission"
        if row.get("inherit_individual_permissions") != False: return "unexpected row-level permission inheritance"
        data = row.get("data")
        if data is None or data.get("business_id") != business:
            return "wrong-business or malformed row"
        fields = self.fields_for(name)
        allowed = ["business_id"]
        for field in fields: allowed.append(field[0])
        for key in data:
            if key not in allowed: return "unexpected data column"
        if "business_id" not in data: return "missing business scope"
        for field in fields:
            value = data.get(field[0])
            if value is None:
                if field[2]: return "missing required field " + field[0]
            elif not self.valid_field(field, value): return "invalid field " + field[0]
        identity = "entity_id"
        if name == "Roomay Service Requests": identity = "request_id"
        if name == "Roomay Service Request Audit": identity = "event_id"
        entity = data.get(identity)
        if not self.valid_uuid(entity) or entity in seen_entities: return "invalid or duplicate Roomay identity"
        seen_ids.append(row["id"])
        seen_entities.append(entity)
        return ""

    async def read_table_rows(self, name, table_id, business):
        rows = []
        offset = 0
        for page_number in range(MAX_PAGES):
            page = await workpeg.get_rows(table_id, limit=PAGE_SIZE, offset=offset)
            if self.timed_out: return None
            if not isinstance(page, list) or len(page) > PAGE_SIZE:
                self.error = "Malformed row page. Complete inventory is not established; no write was attempted."
                return None
            for row in page:
                reason = self.validate_row(name, business, row,
                                           [item["id"] for item in rows],
                                           [item["data"].get(self.identity_for(name)) for item in rows],
                                           [item["fingerprint"] for item in rows])
                if reason:
                    self.error = "Inventory in " + name + " contains " + reason + ". No write was attempted."
                    return None
                rows.append(row)
            if len(page) < PAGE_SIZE:
                return rows
            offset += PAGE_SIZE
        self.error = "Pagination safety limit reached. Complete inventory is unknown; no write was attempted."
        return None

    def identity_for(self, name):
        if name == "Roomay Service Requests": return "request_id"
        if name == "Roomay Service Request Audit": return "event_id"
        return "entity_id"

    async def fresh_inventory(self):
        hotel = await workpeg.get_tables(HOTEL_NS)
        if self.timed_out: return None
        requests = await workpeg.get_tables(REQUEST_NS)
        if self.timed_out: return None
        if not isinstance(hotel, list) or not isinstance(requests, list):
            self.error = "Malformed namespace inventory. No write was attempted."
            return None
        listings = {HOTEL_NS: hotel, REQUEST_NS: requests}
        for candidate in hotel:
            if candidate.get("name") not in ["room_types", "rooms", "guests", "reservations", "stays", "stay_guests", "room_blocks"]:
                self.error = "Unexpected table in hotel namespace. Owner reconciliation is required before any row write."
                return None
        for candidate in requests:
            if candidate.get("name") not in ["Roomay Service Requests", "Roomay Service Request Audit"]:
                self.error = "Unexpected table in request namespace. Owner reconciliation is required before any row write."
                return None
        ids = {}
        summaries = []
        rows = {}
        for item in self.table_definitions():
            name = item[0]
            namespace = item[1]
            matches = []
            for candidate in listings[namespace]:
                if candidate.get("name") == name: matches.append(candidate)
            if len(matches) != 1:
                self.error = "Canonical table missing, unreadable, or duplicated: " + name + ". No write was attempted."
                return None
            listed = matches[0]
            if not self.table_valid(name, listed):
                self.error = "Incompatible canonical table schema or permission: " + name + ". No write was attempted."
                return None
            direct = await workpeg.get_table(listed["uuid"])
            if self.timed_out: return None
            if not self.table_valid(name, direct) or direct.get("uuid") != listed["uuid"]:
                self.error = "Direct table read-back mismatch: " + name + ". No write was attempted."
                return None
            ids[self.table_key(name)] = listed["uuid"]
            values = await self.read_table_rows(name, listed["uuid"], route.business_id)
            if values is None or self.timed_out: return None
            rows[self.table_key(name)] = values
            summaries.append(name + " / UUID " + listed["uuid"] + " / permission 700")
        return {"ids": ids, "rows": rows, "summaries": summaries,
                "signature": self.inventory_signature_for(ids, rows)}

    def inventory_signature_for(self, ids, rows):
        parts = []
        for item in self.table_definitions():
            name = item[0]
            key = self.table_key(name)
            parts.append(name + "=" + str(ids.get(key, "")))
            for row in rows.get(key, []):
                part = str(row.get("id")) + "|" + str(row.get("fingerprint"))
                part = part + "|business_id=" + str(row["data"].get("business_id"))
                for field in self.fields_for(name):
                    part = part + "|" + field[0] + "=" + str(row["data"].get(field[0]))
                parts.append(part)
        return "\n".join(parts)

    def local_utc(self):
        if not dates.is_date(self.operational_date) or not dates.is_datetime(self.authoritative_local_now):
            return None
        if dates.date_of(self.authoritative_local_now) != self.operational_date:
            return None
        if self.hotel_timezone != "Africa/Lagos":
            return None
        epoch = dates.to_epoch(self.authoritative_local_now, self.hotel_timezone)
        if epoch is None: return None
        roundtrip = dates.from_epoch(epoch, self.hotel_timezone)
        if roundtrip != self.authoritative_local_now: return None
        utc_wall = dates.from_epoch(epoch, "UTC")
        if utc_wall is None: return None
        return utc_wall + "+00:00"

    def build_records(self, room_type_id):
        now = self.local_utc()
        if now is None: return None
        departure = dates.add_days(self.operational_date, 2)
        if departure is None or departure <= self.operational_date: return None
        arrival = self.operational_date
        signature = REQUEST_SIGNATURE
        records = {
            "rooms": [{"entity_id": ROOM_ID, "number": "205", "room_type_id": room_type_id, "enabled": True, "housekeeping": "ready"}],
            "guests": [{"entity_id": GUEST_ID, "display_name": "WOR-60 Fictional Guest (Synthetic)"}],
            "reservations": [{"entity_id": RESERVATION_ID, "guest_id": GUEST_ID, "room_type_id": room_type_id, "room_id": ROOM_ID, "arrival": arrival, "departure": departure, "party_size": 1, "source": "advance", "status": "confirmed"}],
            "stays": [{"entity_id": STAY_ID, "reservation_id": RESERVATION_ID, "room_id": ROOM_ID, "checked_in_at": now, "status": "checked_in"}],
            "stay_guests": [{"entity_id": OCCUPANT_ID, "stay_id": STAY_ID, "guest_id": GUEST_ID, "joined_at": now}],
            "room_blocks": [],
            "service_requests": [{"request_id": REQUEST_ID, "idempotency_key": "wor60-extra-towels-v1", "hotel_id": HOTEL_ID, "stay_id": STAY_ID, "room_id": ROOM_ID, "guest_id": GUEST_ID, "origin": "reception_desk", "category": "extra_towels", "category_detail": "extra_towels", "department": "housekeeping", "description": "Synthetic WOR-60 extra-towels request for Room 205.", "urgency": "normal", "status": "received", "assigned_staff_id": None, "triage_required": False, "sensitive": False, "created_at": now, "updated_at": now, "received_at": now, "acknowledge_by": self.utc_after(now, 30), "due_at": self.utc_after(now, 240), "version": 1, "last_event_id": AUDIT_ID, "last_operation_signature": signature}],
            "service_request_audit": [{"event_id": AUDIT_ID, "operation_id": OPERATION_ID, "operation_signature": signature, "request_id": REQUEST_ID, "hotel_id": HOTEL_ID, "sequence": 1, "event_type": "created", "from_status": None, "to_status": "received", "actor_id": "WOR-60-SYNTHETIC-RECEPTION", "actor_kind": "staff", "actor_department": "reception", "occurred_at": now, "reason": None, "commit_state": "pending"}],
        }
        return records

    def utc_after(self, now, minutes):
        epoch = dates.to_epoch(now[:19], "UTC")
        if epoch is None: return None
        utc_wall = dates.from_epoch(epoch + minutes * 60000, "UTC")
        if utc_wall is None: return None
        return utc_wall + "+00:00"

    def normalized_data(self, name, data):
        result = {}
        for field in self.fields_for(name):
            key = field[0]
            result[key] = data.get(key)
        return result

    def data_equal(self, name, current, expected):
        left = self.normalized_data(name, current)
        right = self.normalized_data(name, expected)
        for key in left:
            if left[key] != right[key]: return False
        allowed = ["business_id"]
        for field in self.fields_for(name): allowed.append(field[0])
        for key in current:
            if key not in allowed: return False
        return True

    def payload_equal(self, name, left, right):
        if (left.get("position") != right.get("position")
                or left.get("namespace") != right.get("namespace")
                or left.get("inherit_business_permission") != right.get("inherit_business_permission")
                or left.get("inherit_individual_permissions") != right.get("inherit_individual_permissions")):
            return False
        return self.data_equal(name, left.get("data", {}), right.get("data", {}))

    def validate_model(self, inventory, records, room_type):
        existing = inventory["rows"]
        expected_by_key = {key: values for key, values in records.items()}
        expected_by_key["room_blocks"] = []
        expected_by_key["room_types"] = [{"entity_id": room_type["entity_id"],
                                            "name": room_type["name"],
                                            "capacity": room_type["capacity"]}]
        present = []
        if existing.get("room_blocks", []):
            self.error = "A maintenance block exists for this inventory. No room or stay rows will be created."
            return None
        for key in ["room_types"] + self.record_order():
            name = "Roomay Service Requests" if key == "service_requests" else ("Roomay Service Request Audit" if key == "service_request_audit" else key)
            identity = "request_id" if key == "service_requests" else ("event_id" if key == "service_request_audit" else "entity_id")
            expected = expected_by_key[key]
            if len(expected) != 1: return None
            found = []
            for row in existing.get(key, []):
                matches = []
                for candidate in expected:
                    if row["data"].get(identity) == candidate.get(identity): matches.append(candidate)
                if len(matches) != 1 or not self.data_equal(name, row["data"], matches[0]):
                    self.error = "Unexpected or conflicting existing row in " + name + ". No row was changed. Owner reconciliation is required."
                    return None
                found.append(row)
            if len(found) > 1:
                self.error = "Duplicate synthetic identity in " + name + ". No row was changed."
                return None
            present.append(len(found) == 1)
        missing_seen = False
        for found in present[1:]:
            if not found: missing_seen = True
            elif missing_seen:
                self.error = "Rows are not a valid dependency prefix. Reconcile partial completion before continuing."
                return None
        next_index = present[1:].index(False) if False in present[1:] else len(self.record_order())
        step = self.record_order()[next_index] if next_index < len(self.record_order()) else "complete"
        # The first table record is a preserved existing room_type, not part of writes.
        return {"step": step, "present": present[1:], "expected": expected_by_key}

    def payload_for(self, step, record):
        name = "Roomay Service Requests" if step == "service_requests" else ("Roomay Service Request Audit" if step == "service_request_audit" else step)
        data = {"business_id": route.business_id}
        for key in record:
            if record[key] is not None: data[key] = record[key]
        if step in ["service_requests", "service_request_audit"]:
            namespace = "audit" if step == "service_request_audit" else "active"
            return {"data": data, "position": 1000, "namespace": namespace,
                    "inherit_business_permission": False,
                    "inherit_individual_permissions": False}
        return {"data": data, "position": 1000, "namespace": "active",
                "inherit_business_permission": True,
                "inherit_individual_permissions": False}

    def record_for_step(self, records, step):
        for key in records:
            if key == step: return records[key][0]
        return None

    def type_record(self, rows):
        matches = []
        for row in rows.get("room_types", []):
            if row["data"].get("name") == ROOM_TYPE_NAME:
                matches.append(row)
        if len(matches) != 1: return None
        data = matches[0]["data"]
        if data.get("capacity") != ROOM_TYPE_CAPACITY or not self.valid_uuid(data.get("entity_id")):
            return None
        if len(rows.get("room_types", [])) != 1: return None
        return {"entity_id": data["entity_id"], "name": data["name"], "capacity": data["capacity"]}

    def summary_for(self, inventory):
        rows = inventory["rows"]
        lines = []
        for item in self.table_definitions():
            name = item[0]
            lines.append(name + ": " + str(len(rows[self.table_key(name)]) ) + " rows read")
        return lines

    def rows_signature(self, inventory):
        return self.inventory_signature_for(inventory["ids"], inventory["rows"])

    def full_readback_valid(self, inventory, records, room_type):
        state = self.validate_model(inventory, records, room_type)
        if state is None: return None
        # Before the request and audit steps, the hotel snapshot is complete;
        # once all seven rows exist, the existing adapter contract is mirrored
        # by exact record and relationship checks above.
        return state

    async def inspect(self):
        await self.run("inspect")

    async def prepare_next(self):
        await self.run("prepare")

    async def create_prepared(self):
        await self.run("create")

    async def run(self, operation):
        if self.busy or (self.uncertain and operation != "inspect"):
            return
        self.error = ""
        if not self.context_ok(): return
        if operation == "create" and self.retry_ack != RETRY_ACK:
            self.error = "Acknowledge the SDK 401/403 refresh/retry behavior before each row write."
            return
        if operation == "create" and self.reconciliation_attestation != RECONCILIATION_ATTESTATION:
            self.error = "Owner must reconcile every prior write outcome before continuing."
            return
        if operation == "create":
            if not self.selected_step or self.confirmation != CONFIRM_PREFIX + self.selected_step:
                self.error = "Type the exact one-row confirmation before creating."
                return
        self.busy = True
        self.timed_out = False
        self.ticks = 0
        self.status = "Reading all nine schemas and complete row inventories"
        try:
            inventory = await self.fresh_inventory()
            if inventory is None or self.timed_out: return
            room_type = self.type_record(inventory["rows"])
            if room_type is None:
                self.error = "The unique Roomay TEST Room Type (Fictional), capacity 3, was not found. It will not be created or changed."
                return
            records = self.build_records(room_type["entity_id"])
            if records is None:
                self.error = "Invalid IANA time zone, hotel-local date, or authoritative local timestamp. No writes are allowed."
                return
            check = self.validate_model(inventory, records, room_type)
            if check is None: return
            self.table_ids = inventory["ids"]
            self.inventory_rows = inventory["rows"]
            self.inventory_signature = self.rows_signature(inventory)
            self.table_summary = inventory["summaries"]
            self.row_summary = self.summary_for(inventory)
            self.room_type_entity_id = room_type["entity_id"]
            self.status = "All nine schemas and complete paginated inventories validated"
            if operation == "inspect":
                self.clear_preparation()
                self.selected_step = check["step"]
                self.last_success = "Read-only inspection complete; next eligible row: " + check["step"]
                self.status = "All nine schemas and inventories validated. No row was written. Fresh-page verification: " + str(self.stay_reload_verified)
                return
            if operation == "prepare":
                if self.write_started_this_page:
                    self.error = "A row was written in this page session. Reload, inspect the complete inventory, and verify the saved native row before preparing another operation."
                    return
                self.selected_step = check["step"]
                if check["step"] in ["service_requests", "service_request_audit", "complete"]:
                    if self.write_started_this_page:
                        self.stay_reload_verified = False
                        self.error = "Reload this page after the five hotel rows were written, then inspect and attest before preparing a service request."
                        return
                    if self.stay_reload_attestation != STAY_RELOAD_ATTESTATION:
                        self.error = "Reload the browser, inspect the complete active stay, then enter the exact reload attestation before service-request preparation."
                        return
                    self.stay_reload_verified = True
                if check["step"] == "complete":
                    self.error = "The complete workflow already exists. No row was written. Verify through a fresh page."
                    return
                if check["step"] in ["service_requests", "service_request_audit"] and not self.stay_reload_verified:
                    self.error = "A persisted stay verified after reload is required before service-request operations."
                    return
                record = self.record_for_step(records, check["step"])
                if record is None: self.error = "No safe next row is available."; return
                self.selected_payload = self.payload_for(check["step"], record)
                self.selected_preview = str(self.selected_payload)
                self.confirmation = ""
                self.last_success = "One exact row prepared for review only; no write sent"
                self.status = "Prepared one row: " + check["step"] + ". Inspect payload and confirm separately."
                return
            if operation == "create":
                if check["step"] in ["service_requests", "service_request_audit", "complete"]:
                    if self.write_started_this_page:
                        self.error = "Reload this page after the hotel rows were written before service-request creation."
                        return
                    if self.stay_reload_attestation != STAY_RELOAD_ATTESTATION:
                        self.error = "Owner must verify the active stay after a fresh-page reload before service-request creation."
                        return
                    self.stay_reload_verified = True
                if check["step"] != self.selected_step:
                    self.clear_preparation()
                    self.error = "Fresh inventory changed the next row. Prepare again; no write was sent."
                    return
                if self.rows_signature(inventory) != self.inventory_signature:
                    self.clear_preparation()
                    self.error = "Fresh inventory differs from preparation. Prepare again; no write was sent."
                    return
                record = self.record_for_step(records, self.selected_step)
                expected_payload = self.payload_for(self.selected_step, record)
                step_name = "Roomay Service Requests" if self.selected_step == "service_requests" else ("Roomay Service Request Audit" if self.selected_step == "service_request_audit" else self.selected_step)
                if not self.payload_equal(step_name, expected_payload, self.selected_payload):
                    self.clear_preparation()
                    self.error = "Prepared payload no longer matches the fresh canonical row."
                    return
                name = "Roomay Service Requests" if self.selected_step == "service_requests" else ("Roomay Service Request Audit" if self.selected_step == "service_request_audit" else self.selected_step)
                row_uuid = inventory["ids"][self.table_key(name)]
                self.write_started = True
                self.write_started_this_page = True
                self.uncertain = True
                self.status = "One row creation in flight. Do not repeat."
                saved = await workpeg.add_row(row_uuid, expected_payload)
                if self.timed_out: return
                if not self.row_matches(name, saved, record, route.business_id):
                    self.error = "Create response lacks the expected native identity, fingerprint, business and exact data. Outcome uncertain; do not retry."
                    return
                direct = await workpeg.get_row(row_uuid, saved["id"])
                if self.timed_out: return
                if (not self.row_matches(name, direct, record, route.business_id)
                        or direct["id"] != saved["id"] or direct["fingerprint"] != saved["fingerprint"]):
                    self.error = "Direct row read-back did not match response ID, fingerprint and data. Outcome uncertain; do not retry."
                    return
                after = await self.fresh_inventory()
                if after is None or self.timed_out: return
                after_type = self.type_record(after["rows"])
                if after_type is None: self.error = "Fresh inventory lost the preserved room type; outcome uncertain."; return
                after_records = self.build_records(after_type["entity_id"])
                after_state = self.validate_model(after, after_records, after_type) if after_records else None
                if after_state is None:
                    self.error = "Fresh complete inventory did not verify the operation prefix. Outcome uncertain; do not retry."
                    return
                found = False
                for row in after["rows"][self.table_key(name)]:
                    if row["id"] == saved["id"] and row["fingerprint"] == saved["fingerprint"] and self.row_matches(name, row, record, route.business_id): found = True
                if not found:
                    self.error = "Fresh inventory did not contain the exact saved native row. Outcome uncertain; do not retry."
                    return
                self.uncertain = False
                self.last_success = ("One row created and verified by response, direct GET, and full fresh inventory: "
                                     + self.selected_step + "; native row ID " + str(saved["id"])
                                     + "; fingerprint " + saved["fingerprint"])
                self.status = "Verified one row. Refresh or reload before preparing the next operation."
                self.clear_preparation()
                if after_state["step"] in ["service_requests", "service_request_audit", "complete"]:
                    self.status = "This row is verified. Reload this page and inspect the complete stay before preparing the next workflow step."
                return
        except Exception as exception:
            message = str(exception)
            if self.write_started:
                # An error after add_row began cannot prove whether Workpeg
                # persisted the row, even for HTTP 401/403 or read-back errors.
                self.uncertain = True
                if "HTTP 401" in message or "HTTP 403" in message:
                    self.error = "Authorization error during or after row creation. Outcome uncertain; do not retry. Reconcile as owner."
                else:
                    self.error = "Create or verification failed after write began. Outcome uncertain; do not retry. Reconcile as owner."
            elif "HTTP 401" in message:
                self.error = "Authentication failed or expired (401). No write was attempted."
            elif "HTTP 403" in message:
                self.error = "Access denied (403). No write was attempted."
            else:
                self.error = "Inventory read failed, was malformed, or is incomplete. No write was attempted."
        finally:
            if not self.timed_out: self.busy = False

    def row_matches(self, name, row, record, business):
        if row.get("id") != int(row.get("id")) or row.get("id") < 1:
            return False
        if row.get("fingerprint") != str(row["fingerprint"]) or len(row["fingerprint"]) == 0:
            return False
        data = row.get("data")
        if data is None or data.get("business_id") != business:
            return False
        return self.data_equal(name, data, record)

    def watch_timeout(self):
        if self.busy and not self.timed_out:
            self.ticks += 1
            if self.ticks >= 30:
                self.timed_out = True
                if self.write_started: self.uncertain = True
                self.error = "Operation timed out. It may still be in flight; this page is locked. Reconcile the Workpeg inventory as owner before proceeding."
                self.status = "Timed out — request may still be running"

    def build(self):
        return Column(
            Text("Roomay — synthetic hotel-to-service-request workflow"),
            Text("DEVELOPMENT ONLY — SYNTHETIC DATA. No calls occur on load. Each button is manually triggered; this screen is not in the production router."),
            Text("Preserve the existing Roomay TEST Room Type (Fictional), capacity 3. No table creation, room-type update, deletion, rollback, or bulk write is available."),
            Text("Workpeg 0.152.0 may refresh and retry protected requests after 401/403. Owner acknowledgement is required before each row write."),
            Text("Typed text is not authentication. Verify the signed-in owner, active business, 700 table permissions, and no row-level grants in Workpeg."),
            TextInput(value=self.expected_business, on_change=self.on_set_business, placeholder="Owner-verified Roomay AI development business UUID"),
            Text("Active business from Workpeg route: " + route.business_id),
            TextInput(value=self.owner_attestation, on_change=self.set_owner, placeholder=OWNER_ATTESTATION),
            TextInput(value=self.row_permission_attestation, on_change=self.set_row_permission, placeholder=ROW_PERMISSION_ATTESTATION),
            TextInput(value=self.operational_date, on_change=self.set_operational_date, placeholder="Owner-verified hotel-local date YYYY-MM-DD"),
            TextInput(value=self.hotel_timezone, on_change=self.set_hotel_timezone, placeholder="Owner-verified IANA hotel timezone, e.g. Africa/Lagos"),
            TextInput(value=self.authoritative_local_now, on_change=self.set_authoritative_local_now, placeholder="Owner-verified local timestamp YYYY-MM-DDTHH:MM:SS"),
            Button("Inspect all nine schemas and complete row inventories", on_click=self.inspect) if not self.busy else Text("Reading all nine tables and pages"),
            Text("Schemas: " + str(self.table_summary)),
            Text("Row inventories: " + str(self.row_summary)),
            Text("Preserved room_types entity_id: " + self.room_type_entity_id),
            Text("Next row: " + self.selected_step),
            Text("Step order: Room 205 → fictional guest → confirmed reservation → active stay → registered occupant → reload verification → extra-towels request → audit row."),
            Text("Audit actor is a synthetic reception actor; the request is not sent to or acknowledged by Housekeeping."),
            Button("Prepare exactly the next row (read only)", on_click=self.prepare_next) if not self.busy else Text("Preparation locked during operation"),
            Text("Exact prepared Workpeg row payload: " + self.selected_preview),
            TextInput(value=self.stay_reload_attestation, on_change=self.set_stay_reload, placeholder=STAY_RELOAD_ATTESTATION),
            TextInput(value=self.reconciliation_attestation, on_change=self.set_reconciliation, placeholder=RECONCILIATION_ATTESTATION),
            TextInput(value=self.retry_ack, on_change=self.set_retry_ack, placeholder=RETRY_ACK),
            TextInput(value=self.confirmation, on_change=self.set_confirmation, placeholder=CONFIRM_PREFIX + self.selected_step),
            Button("Create this one reviewed row", on_click=self.create_prepared) if not self.busy and not self.uncertain and self.selected_payload else Text("Review inventory and prepare one row before a separate write"),
            Text("Status: " + self.status),
            Text("Last verified operation: " + self.last_success),
            Text("Failure / uncertainty: " + self.error + " / " + str(self.uncertain)),
            Text("After the first five hotel rows verify, reload this page and inspect before preparing any service request. Reload again after completion to verify persistence."),
            gap=10,
        )

    def set_owner(self, value):
        if not self.busy: self.owner_attestation = value

    def set_row_permission(self, value):
        if not self.busy: self.row_permission_attestation = value

    def set_retry_ack(self, value):
        if not self.busy: self.retry_ack = value

    def set_reconciliation(self, value):
        if not self.busy: self.reconciliation_attestation = value

    def set_stay_reload(self, value):
        if not self.busy: self.stay_reload_attestation = value

    def set_confirmation(self, value):
        if not self.busy: self.confirmation = value

    def set_operational_date(self, value):
        if not self.busy: self.operational_date = value

    def set_hotel_timezone(self, value):
        if not self.busy: self.hotel_timezone = value

    def set_authoritative_local_now(self, value):
        if not self.busy: self.authoritative_local_now = value


class DevVerticalSliceRouter(Router):
    routes = [Route("/b/[business_id]/dev-vertical-slice", DevVerticalSlice)]
