"""Disabled-by-default Workpeg request/audit orchestration boundary.

This coordinator is intentionally not wired to a production route or SDK
instance. It accepts only injected trusted identity, authorization, complete
read, serialization, and Workpeg-table ports so the reconciliation contract can
be exercised offline. Workpeg SDK 0.152.0 does not document transactions or
compare-and-swap; callers must provide a guard covering *all* writers before
enabling it. Table fingerprints alone are not a serialization guarantee.
"""
from copy import deepcopy
from uuid import UUID

from .service_requests import (
    OPTIONAL_REQUEST_FIELDS,
    RequestError,
    event_row_payload,
    reconcile_write as reconcile_request_write,
    request_row_payload,
    validate_request,
)
from .staff_actions import _audit_history_is_consistent
from .workpeg_adapter import (
    AdapterError,
    PAGE_SIZE,
    collect_pages,
    contract_by_key,
    decode_rows,
    full_row_update,
    normalize_snapshot,
    resolve_tables_for_write,
)


class NativeWriterError(ValueError):
    """A sanitized, stable-code refusal from the offline writer boundary."""

    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _uuid(value):
    if not isinstance(value, str):
        return False
    try:
        return str(UUID(value)) == value
    except (ValueError, TypeError, AttributeError):
        return False


class NativeRequestWriter:
    """Coordinate one already-authorized canonical request/audit plan.

    Required injected ports:

    * ``context_resolver.resolve(session_proof)`` returns server-verified
      business, Peg, actor, authorization, and table-write capability claims.
    * ``plan_factory.prepare(session_proof, command)`` uses the existing
      GuestActionGateway or StaffActionGateway/domain contracts and returns a
      canonical ``{base_request, target_request, event}`` plan.
    * ``serialization_guard.acquire(business_id, request_id)`` yields a lease
      with ``covers_all_writers is True`` and ``active is True``.
    * ``tables`` exposes only documented helper-equivalent methods:
      ``get_tables(namespace)``, ``get_rows(uuid, limit, offset)``,
      ``add_row(uuid, payload)``, and ``update_row(uuid, row_id, patch)``.

    The writer is off unless explicitly constructed with ``enabled=True``.
    That flag is not sufficient by itself: every trusted gate is revalidated
    for each operation. No production caller currently constructs this class.
    """

    _CONTEXT_FIELDS = {
        "authenticated", "membership_verified", "business_binding_verified",
        "actor_authorized", "business_id", "hotel_id", "actor_id",
        "registered_peg_id", "request_write_verified", "audit_write_verified",
        "serialization_scope_verified",
    }

    def __init__(self, *, tables, context_resolver, plan_factory,
                 serialization_guard, enabled=False):
        self.enabled = enabled is True
        self.tables = tables
        self.context_resolver = context_resolver
        self.plan_factory = plan_factory
        self.serialization_guard = serialization_guard

    @staticmethod
    def _result(state, reason, *, persisted=False, request_id=None,
                event_id=None, next_step=None):
        return {
            "state": state,
            "reason": reason,
            "persisted": persisted,
            "request_id": request_id,
            "event_id": event_id,
            "next_step": next_step,
        }

    def execute(self, session_proof, command):
        """Execute under verified gates; never accept role/business claims.

        ``session_proof`` is opaque and is passed only to the trusted resolver
        and existing plan factory. Browser-supplied identity is never read.
        """
        if not self.enabled:
            return self._result("unavailable", "native_writer_disabled")
        if any(not callable(getattr(port, method, None)) for port, method in (
            (self.context_resolver, "resolve"), (self.plan_factory, "prepare"),
            (self.serialization_guard, "acquire"), (self.tables, "get_tables"),
            (self.tables, "get_rows"), (self.tables, "add_row"),
            (self.tables, "update_row"),
        )):
            return self._result("refused", "writer_capability_unavailable")

        try:
            context = self.context_resolver.resolve(session_proof)
            self._validate_context(context)
            request_id = self._command_request_id(command)
            lease_context = self.serialization_guard.acquire(
                context["business_id"], request_id)
            if not hasattr(lease_context, "__enter__") or not hasattr(lease_context, "__exit__"):
                raise NativeWriterError("serialization_lease_unavailable")
            with lease_context as lease:
                if (not isinstance(lease, dict)
                        or lease.get("active") is not True
                        or lease.get("covers_all_writers") is not True
                        or lease.get("covers_business_idempotency") is not True
                        or lease.get("business_id") != context["business_id"]
                        or lease.get("request_id") != request_id):
                    raise NativeWriterError("global_serialization_unverified")
                return self._execute_locked(session_proof, command, context, request_id)
        except NativeWriterError as error:
            return self._result("refused", error.code)
        except Exception:
            # Never emit provider/SDK exception text, request data, or secrets.
            return self._result("refused", "writer_preflight_failed")

    @classmethod
    def _validate_context(cls, context):
        if not isinstance(context, dict) or set(context) != cls._CONTEXT_FIELDS:
            raise NativeWriterError("trusted_context_invalid")
        for field in (
            "authenticated", "membership_verified", "business_binding_verified",
            "actor_authorized", "request_write_verified", "audit_write_verified",
            "serialization_scope_verified",
        ):
            if context[field] is not True:
                raise NativeWriterError("trusted_write_gate_unverified")
        if (not _uuid(context["business_id"]) or not _uuid(context["hotel_id"])
                or not isinstance(context["actor_id"], str)
                or not context["actor_id"].strip()):
            raise NativeWriterError("trusted_context_invalid")
        peg_id = context["registered_peg_id"]
        if not ((type(peg_id) is str and _uuid(peg_id))
                or (type(peg_id) is int and peg_id > 0)):
            raise NativeWriterError("registered_peg_unverified")

    @staticmethod
    def _command_request_id(command):
        if not isinstance(command, dict) or not _uuid(command.get("request_id")):
            raise NativeWriterError("invalid_operation_reference")
        return command["request_id"]

    def _tables(self, registered_peg_id):
        grouped = {}
        for namespace in ("roomay_hotel_v1", "roomay_requests_v1"):
            result = self.tables.get_tables(namespace)
            if not isinstance(result, list):
                raise NativeWriterError("table_inventory_incomplete")
            grouped[namespace] = result
        try:
            resolved = resolve_tables_for_write(grouped, registered_peg_id)
        except AdapterError as error:
            raise NativeWriterError(error.code) from None
        return resolved

    def _read_snapshot(self, business_id, registered_peg_id, request_id):
        table_ids = self._tables(registered_peg_id)
        rows_by_table, raw_by_entity = {}, {}
        contracts = contract_by_key()
        for key in contracts:
            table_uuid = table_ids[key]
            pages = []
            offset = 0
            for _ in range(100):
                page = self.tables.get_rows(table_uuid, limit=PAGE_SIZE, offset=offset)
                if not isinstance(page, list) or len(page) > PAGE_SIZE:
                    raise NativeWriterError("row_inventory_malformed")
                pages.append(page)
                offset += PAGE_SIZE
                if len(page) < PAGE_SIZE:
                    break
            else:
                raise NativeWriterError("row_inventory_incomplete")
            try:
                rows = collect_pages(pages)
                records, references = decode_rows(key, business_id, rows)
            except AdapterError as error:
                raise NativeWriterError(error.code) from None
            rows_by_table[key] = rows
            raw_by_entity[key] = {
                reference.entity_id: (self._canonical_record(key, record), raw, reference)
                for record, raw, reference in zip(records, rows, references)
            }
        try:
            snapshot = normalize_snapshot(
                business_id, rows_by_table, allow_pending_request_id=request_id)
        except AdapterError as error:
            raise NativeWriterError(error.code) from None
        return table_ids, rows_by_table, raw_by_entity, snapshot

    @staticmethod
    def _canonical_record(table_key, record):
        """Undo Workpeg's null-for-absent representation for optional request fields."""
        normalized = deepcopy(record)
        if table_key == "service_requests":
            # assigned_staff_id is nullable but remains a required key in the
            # canonical request object; only optional timestamp fields may be
            # absent from the domain shape when Workpeg returns nulls.
            for field in OPTIONAL_REQUEST_FIELDS - {"assigned_staff_id"}:
                if normalized.get(field) is None:
                    normalized.pop(field, None)
        return normalized

    def _execute_locked(self, session_proof, command, context, request_id):
        try:
            prepared = self.plan_factory.prepare(session_proof, command)
        except Exception:
            raise NativeWriterError("authorized_plan_unavailable") from None
        prepared_state = (prepared.get("state") if isinstance(prepared, dict)
                          else getattr(prepared, "state", None))
        if prepared_state == "verified_duplicate":
            # Independently re-read the whole canonical snapshot even though
            # the existing gateway also verified its duplicate path.
            prepared_persisted = (prepared.get("persisted") if isinstance(prepared, dict)
                                  else getattr(prepared, "persisted", None))
            if prepared_persisted is not True:
                raise NativeWriterError("duplicate_outcome_uncertain")
            _, _, raw_by_entity, snapshot = self._read_snapshot(
                context["business_id"], context["registered_peg_id"], request_id)
            pair = raw_by_entity["service_requests"].get(request_id)
            if pair is None:
                raise NativeWriterError("duplicate_outcome_uncertain")
            request = pair[0]
            events = [event for event in snapshot["service_request_audit"]
                      if event["request_id"] == request_id]
            if not _audit_history_is_consistent(request, events):
                raise NativeWriterError("duplicate_outcome_uncertain")
            return self._result("duplicate", "independent_committed_readback",
                                persisted=True, request_id=request_id,
                                event_id=request["last_event_id"])
        plan = (prepared.get("plan") if isinstance(prepared, dict)
                else getattr(prepared, "plan", None))
        if plan is None and isinstance(prepared, dict):
            plan = prepared
        self._validate_plan(plan, context, request_id)

        did_write = False
        last_step = None
        try:
            table_ids, rows_by_table, raw_by_entity, snapshot = self._read_snapshot(
                context["business_id"], context["registered_peg_id"], request_id)
            self._check_duplicate_keys(snapshot, plan, request_id)
            for _ in range(4):
                request_pair = raw_by_entity["service_requests"].get(request_id)
                current_request = request_pair[0] if request_pair else None
                events = [event for event in snapshot["service_request_audit"]
                          if event["request_id"] == request_id]
                try:
                    step = reconcile_request_write(plan, current_request, events)
                except RequestError:
                    raise NativeWriterError("request_reconciliation_invalid") from None
                last_step = step
                if step == "complete":
                    return self._result("complete", "verified_canonical_readback",
                                        persisted=True, request_id=request_id,
                                        event_id=plan["event"]["event_id"])
                if step.startswith("manual_reconciliation_"):
                    return self._result("uncertain", step, request_id=request_id,
                                        event_id=plan["event"]["event_id"],
                                        next_step="owner_review_required")

                if step == "append_pending_event":
                    position = self._next_position(rows_by_table["service_request_audit"])
                    payload = event_row_payload(plan["event"], position)
                    payload["data"]["business_id"] = context["business_id"]
                    did_write = True
                    self.tables.add_row(table_ids["service_request_audit"], payload)
                elif step == "apply_request":
                    target = deepcopy(plan["target_request"])
                    target["business_id"] = context["business_id"]
                    if request_pair is None:
                        position = self._next_position(rows_by_table["service_requests"])
                        payload = request_row_payload(plan["target_request"], position)
                        payload["data"]["business_id"] = context["business_id"]
                        did_write = True
                        self.tables.add_row(table_ids["service_requests"], payload)
                    else:
                        existing, raw, reference = request_pair
                        base = plan["base_request"]
                        if existing != base:
                            return self._result("uncertain", "request_base_changed",
                                                request_id=request_id,
                                                next_step="owner_review_required")
                        patch = full_row_update(
                            raw, target,
                            immutable=("business_id", "request_id", "hotel_id"))
                        did_write = True
                        self.tables.update_row(
                            table_ids["service_requests"], reference.row_id, patch)
                elif step == "commit_event":
                    event_id = plan["event"]["event_id"]
                    event_pair = raw_by_entity["service_request_audit"].get(event_id)
                    if event_pair is None or event_pair[0].get("commit_state") != "pending":
                        return self._result("uncertain", "pending_event_unavailable",
                                            request_id=request_id, event_id=event_id,
                                            next_step="owner_review_required")
                    event, raw, reference = event_pair
                    committed = deepcopy(event)
                    committed["commit_state"] = "committed"
                    committed["business_id"] = context["business_id"]
                    patch = full_row_update(
                        raw, committed,
                        immutable=("business_id", "event_id", "operation_id", "request_id"))
                    did_write = True
                    self.tables.update_row(
                        table_ids["service_request_audit"], reference.row_id, patch)
                else:
                    return self._result("uncertain", "manual_reconciliation_required",
                                        request_id=request_id,
                                        event_id=plan["event"]["event_id"],
                                        next_step="owner_review_required")

                # Every successful helper response is followed by an independent
                # complete read. The response body is never treated as proof.
                table_ids, rows_by_table, raw_by_entity, snapshot = self._read_snapshot(
                    context["business_id"], context["registered_peg_id"], request_id)

            return self._result("uncertain", "reconciliation_step_limit",
                                request_id=request_id,
                                event_id=plan["event"]["event_id"],
                                next_step="owner_review_required")
        except NativeWriterError as error:
            if did_write:
                return self._reconcile_after_uncertain(
                    context, plan, request_id, error.code)
            raise
        except Exception:
            if did_write:
                return self._reconcile_after_uncertain(
                    context, plan, request_id, "write_outcome_uncertain")
            raise NativeWriterError("native_write_preflight_failed") from None

    def _reconcile_after_uncertain(self, context, plan, request_id, reason):
        try:
            _, _, raw_by_entity, snapshot = self._read_snapshot(
                context["business_id"], context["registered_peg_id"], request_id)
            request_pair = raw_by_entity["service_requests"].get(request_id)
            request = request_pair[0] if request_pair else None
            events = [event for event in snapshot["service_request_audit"]
                      if event["request_id"] == request_id]
            step = reconcile_request_write(plan, request, events)
            if step == "complete":
                return self._result("complete", "verified_after_uncertain_response",
                                    persisted=True, request_id=request_id,
                                    event_id=plan["event"]["event_id"])
            return self._result("uncertain", reason, request_id=request_id,
                                event_id=plan["event"]["event_id"],
                                next_step=step)
        except Exception:
            return self._result("uncertain", reason, request_id=request_id,
                                event_id=plan["event"]["event_id"],
                                next_step="readback_unavailable_manual_review")

    @staticmethod
    def _next_position(rows):
        positions = [row.get("position") for row in rows]
        if any(type(position) not in (int, float) for position in positions):
            raise NativeWriterError("row_position_malformed")
        return max(positions, default=0) + 1000

    @staticmethod
    def _check_duplicate_keys(snapshot, plan, request_id):
        target = plan["target_request"]
        for existing in snapshot["service_requests"]:
            if (existing["request_id"] != request_id
                    and existing["hotel_id"] == target["hotel_id"]
                    and existing["idempotency_key"] == target["idempotency_key"]):
                raise NativeWriterError("idempotency_conflict_or_duplicate")
        operation_id = plan["event"]["operation_id"]
        if any(event["operation_id"] == operation_id
               and event["request_id"] != request_id
               for event in snapshot["service_request_audit"]):
            raise NativeWriterError("operation_id_conflict")

    @staticmethod
    def _validate_plan(plan, context, request_id):
        if not isinstance(plan, dict) or set(plan) != {
            "base_request", "target_request", "event"
        }:
            raise NativeWriterError("canonical_write_plan_invalid")
        target, event, base = plan["target_request"], plan["event"], plan["base_request"]
        try:
            validate_request(target)
            if base is not None:
                validate_request(base)
            event_row_payload(event, 1000)
        except (RequestError, TypeError, KeyError, AttributeError):
            raise NativeWriterError("canonical_write_plan_invalid") from None
        if (target["request_id"] != request_id
                or target["hotel_id"] != context["hotel_id"]
                or event["request_id"] != request_id
                or event["hotel_id"] != context["hotel_id"]
                or event["actor_id"] != context["actor_id"]
                or event["commit_state"] != "pending"):
            raise NativeWriterError("canonical_write_scope_mismatch")
        if ((base is None and target["version"] != 1)
                or (base is not None and (
                    base["request_id"] != request_id
                    or base["hotel_id"] != context["hotel_id"]
                    or target["version"] != base["version"] + 1
                ))):
            raise NativeWriterError("canonical_write_version_mismatch")
