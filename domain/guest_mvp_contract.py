"""Pure compatibility seams for the merged ``roomay.guest-mvp.v1`` wire contract.

This module does not authenticate a caller, authorize a hotel operation, or
write Workpeg rows.  JSON Schema validation remains the transport shape
authority.  These functions enforce the cross-field invariants that JSON
Schema cannot express and map public fields into the existing Python domain
gateways without copying their policy.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
from uuid import UUID

from .service_requests import (
    RequestError,
    TRANSITIONS,
    creation_event_identity,
    event_row_payload,
    reconcile_write,
    validate_request,
)
from .staff_actions import ACTION_TARGETS, audit_history_is_consistent


CONTRACT_VERSION = "roomay.guest-mvp.v1"

_RFC3339 = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
    r"(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)

_PENDING_RECONCILIATIONS = frozenset({
    "append_pending_event",
    "apply_request",
    "commit_event",
    "manual_reconciliation_duplicate_events",
    "manual_reconciliation_event_conflict",
    "manual_reconciliation_request_conflict",
    "manual_reconciliation_request_without_event",
    "manual_reconciliation_committed_mismatch",
})

_FAILURE_CODES = frozenset({
    "unauthenticated", "membership_unverified", "wrong_business",
    "wrong_hotel", "wrong_room", "stay_revoked", "stay_expired",
    "stay_not_active", "duplicate_operation", "idempotency_conflict",
    "workpeg_unavailable", "persistence_uncertain", "not_found",
    "forbidden", "invalid_contract", "stale_version",
})

_READBACK_TOKEN = object()


class ContractValidationError(ValueError):
    """Safe contract refusal; never contains provider or record contents."""

    def __init__(self, code: str, field: str | None = None):
        self.code = code
        self.field = field
        super().__init__(code if field is None else f"{code}:{field}")


@dataclass(frozen=True, init=False)
class TrustedPersistenceReadback:
    """Domain-validated evidence bound to one result and authorized read scope."""

    result_kind: str
    operation_id: str
    operation_signature: str
    request_reference: str
    audit_reference: str
    idempotency_key: str
    hotel_id: str
    stay_id: str
    room_id: str
    guest_id: str
    commit_state: str

    def __init__(self, binding, audit_event, idempotency_key, *, _token=None):
        if _token is not _READBACK_TOKEN:
            raise TypeError("trusted_readback_must_come_from_domain_rows")
        request = binding["request"]
        object.__setattr__(self, "result_kind", binding["result_kind"])
        object.__setattr__(self, "operation_id", binding["operation_id"])
        object.__setattr__(self, "operation_signature", binding["operation_signature"])
        object.__setattr__(self, "request_reference", request["request_id"])
        object.__setattr__(self, "audit_reference", audit_event["event_id"])
        object.__setattr__(self, "idempotency_key", idempotency_key)
        for field in ("hotel_id", "stay_id", "room_id", "guest_id"):
            object.__setattr__(self, field, request[field])
        object.__setattr__(self, "commit_state", audit_event["commit_state"])

    @classmethod
    def from_reconciled_result(cls, result, persisted_request,
                               persisted_events, *, idempotency_key):
        """Validate canonical read rows against this result and its operation.

        The caller must obtain rows and the scope binding from its authorized
        server-side reader. This pure check validates consistency; it cannot
        establish platform provenance for arbitrary dictionaries.
        """
        key = _required_text(idempotency_key, "idempotency_key")
        try:
            binding = _persistence_result_binding(result, key)
            expected_request = binding["request"]
            if persisted_request != expected_request:
                raise ContractValidationError("persistence_readback_mismatch")
            validate_request(persisted_request)
            if binding["result_kind"] == "created":
                state = reconcile_write(
                    result["plan"], persisted_request, persisted_events)
                if state != "complete":
                    raise ContractValidationError("persistence_not_complete")
                expected_event = result["plan"]["event"]
                matches = [event for event in persisted_events
                           if event.get("operation_id") == expected_event["operation_id"]]
            else:
                if not audit_history_is_consistent(persisted_request, persisted_events):
                    raise ContractValidationError("audit_history_inconsistent")
                identity = binding["creation_event_identity"]
                matches = [event for event in persisted_events
                           if event.get("event_id") == identity["event_id"]
                           and event.get("operation_id") == identity["operation_id"]]
            if len(matches) != 1:
                raise ContractValidationError("invalid_persistence_readback")
            persisted_event = matches[0]
            event_row_payload(persisted_event, 0)
        except (RequestError, TypeError, KeyError, AttributeError):
            raise ContractValidationError(
                "invalid_persistence_readback") from None
        expected_event = binding["creation_event_identity"]
        if (persisted_event.get("event_id") != expected_event["event_id"]
                or persisted_event.get("operation_id") != expected_event["operation_id"]
                or persisted_event.get("operation_signature")
                != expected_event["operation_signature"]
                or persisted_event.get("request_id") != expected_event["request_id"]
                or persisted_event.get("hotel_id") != expected_event["hotel_id"]
                or persisted_event.get("event_type") != "created"
                or persisted_event.get("sequence") != 1
                or persisted_event.get("from_status") is not None
                or persisted_event.get("to_status") != "received"
                or persisted_event.get("commit_state") != "committed"):
            raise ContractValidationError("request_audit_reference_mismatch")
        return cls(
            binding,
            persisted_event,
            key,
            _token=_READBACK_TOKEN,
        )


def _required_text(value, field: str, *, limit: int = 200) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ContractValidationError("invalid_contract", field)
    return value


def _canonical_uuid(value, field: str) -> str:
    if not isinstance(value, str):
        raise ContractValidationError("invalid_contract", field)
    try:
        if str(UUID(value)) != value:
            raise ValueError
    except (AttributeError, TypeError, ValueError):
        raise ContractValidationError("invalid_contract", field) from None
    return value


def _persistence_result_binding(result: dict, idempotency_key: str) -> dict:
    """Return the domain operation and complete stay scope being reported."""
    if not isinstance(result, dict) or result.get("kind") not in {
            "created", "duplicate"}:
        raise ContractValidationError("invalid_request_result")
    request = result.get("request")
    try:
        validate_request(request)
        if request.get("idempotency_key") != idempotency_key:
            raise ContractValidationError("idempotency_conflict")
        identity = creation_event_identity(request)
        if result["kind"] == "created":
            plan = result.get("plan")
            if (not isinstance(plan, dict)
                    or set(plan) != {"base_request", "target_request", "event"}
                    or plan["base_request"] is not None
                    or plan["target_request"] != request):
                raise ContractValidationError("invalid_request_result")
            event = plan["event"]
            if (not isinstance(event, dict)
                    or any(event.get(key) != value
                           for key, value in identity.items())
                    or event.get("event_type") != "created"
                    or event.get("sequence") != 1
                    or event.get("from_status") is not None
                    or event.get("to_status") != "received"):
                raise ContractValidationError("invalid_request_operation")
        else:
            if result.get("plan") is not None:
                raise ContractValidationError("invalid_request_result")
            supplied_identity = result.get("creation_event_identity")
            if supplied_identity != identity:
                raise ContractValidationError("invalid_request_operation")
        return {
            "result_kind": result["kind"],
            "request": request,
            "creation_event_identity": identity,
            **identity,
        }
    except (RequestError, TypeError, KeyError, AttributeError):
        raise ContractValidationError("invalid_request_result") from None


def _validate_readback_binding(binding, idempotency_key, trusted_readback):
    if not isinstance(trusted_readback, TrustedPersistenceReadback):
        raise ContractValidationError("trusted_readback_required")
    expected = {
        "result_kind": binding["result_kind"],
        "operation_id": binding["operation_id"],
        "operation_signature": binding["operation_signature"],
        "request_reference": binding["request_id"],
        "audit_reference": binding["event_id"],
        "idempotency_key": idempotency_key,
        "hotel_id": binding["hotel_id"],
        "stay_id": binding["request"]["stay_id"],
        "room_id": binding["request"]["room_id"],
        "guest_id": binding["request"]["guest_id"],
    }
    if any(getattr(trusted_readback, field) != value
           for field, value in expected.items()):
        raise ContractValidationError("trusted_readback_mismatch")


def _require_failure(value, field: str = "failure") -> dict:
    if not isinstance(value, dict):
        raise ContractValidationError("invalid_contract", field)
    if set(value) - {"code", "retryable", "message"}:
        raise ContractValidationError("invalid_contract", field)
    if not isinstance(value.get("code"), str) or not value["code"].strip():
        raise ContractValidationError("invalid_contract", field + ".code")
    if value["code"] not in _FAILURE_CODES:
        raise ContractValidationError("invalid_contract", field + ".code")
    if type(value.get("retryable")) is not bool:
        raise ContractValidationError("invalid_contract", field + ".retryable")
    if "message" in value and (
            not isinstance(value["message"], str) or len(value["message"]) > 240):
        raise ContractValidationError("invalid_contract", field + ".message")
    return value


def validate_rfc3339(value: str, field: str = "timestamp") -> str:
    """Require an RFC3339 date-time with an explicit UTC offset.

    ``datetime.fromisoformat`` alone accepts date-only values and timestamps
    without an offset.  The wire contract does not, so the grammar check and
    timezone check are deliberately both required.
    """
    if not isinstance(value, str) or _RFC3339.fullmatch(value) is None:
        raise ContractValidationError("invalid_rfc3339", field)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ContractValidationError("invalid_rfc3339", field) from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ContractValidationError("invalid_rfc3339", field)
    return value


def validate_hotel_information(payload: dict) -> dict:
    """Validate the complete hotel-information payload without schema bypass."""
    if not isinstance(payload, dict):
        raise ContractValidationError("invalid_contract", "payload")
    if set(payload) - {"question", "answer_state", "answer", "failure"}:
        raise ContractValidationError("invalid_contract", "payload")
    question = payload.get("question")
    if not isinstance(question, str) or not question.strip() or len(question) > 1000:
        raise ContractValidationError("invalid_hotel_information", "question")
    state = payload.get("answer_state")
    answer = payload.get("answer")
    has_answer = isinstance(answer, str) and bool(answer.strip())
    if "answer" in payload and (
            not isinstance(answer, str) or not has_answer or len(answer) > 1200):
        raise ContractValidationError("invalid_hotel_information", "answer")
    has_failure = "failure" in payload
    if state == "answered":
        if not has_answer or has_failure:
            raise ContractValidationError("invalid_hotel_information", "answer_state")
    elif state == "handoff":
        if not has_answer or has_failure:
            raise ContractValidationError("invalid_hotel_information", "answer_state")
    elif state == "unavailable":
        if "answer" in payload or not has_failure:
            raise ContractValidationError("invalid_hotel_information", "answer_state")
        _require_failure(payload["failure"])
    else:
        raise ContractValidationError("invalid_hotel_information", "answer_state")
    return payload


def validate_request_outcome(
        payload: dict, *, result: dict | None = None,
        trusted_readback: TrustedPersistenceReadback | None = None) -> dict:
    """Enforce persistence truth using domain-validated evidence."""
    if not isinstance(payload, dict):
        raise ContractValidationError("invalid_contract", "payload")
    state = payload.get("state")
    _required_text(payload.get("idempotency_key"), "idempotency_key")
    if state in {"created", "duplicate"}:
        if not isinstance(trusted_readback, TrustedPersistenceReadback):
            raise ContractValidationError("trusted_readback_required")
        binding = _persistence_result_binding(result, payload["idempotency_key"])
        if binding["result_kind"] != state:
            raise ContractValidationError("trusted_readback_mismatch")
        _validate_readback_binding(
            binding, payload["idempotency_key"], trusted_readback)
        if payload.get("persisted") is not True:
            raise ContractValidationError("invalid_persistence_outcome", "persisted")
        request_reference = _required_text(
            payload.get("request_reference"), "request_reference")
        evidence = payload.get("audit_evidence")
        if not isinstance(evidence, dict) or evidence.get("verified") is not True:
            raise ContractValidationError("audit_evidence_unverified", "audit_evidence")
        evidence_reference = _required_text(
            evidence.get("request_reference"),
            "audit_evidence.request_reference",
        )
        _required_text(evidence.get("reference"), "audit_evidence.reference")
        if evidence_reference != request_reference:
            raise ContractValidationError("request_audit_reference_mismatch")
        if (trusted_readback.commit_state != "committed"
                or trusted_readback.idempotency_key != payload["idempotency_key"]
                or trusted_readback.request_reference != request_reference
                or trusted_readback.audit_reference != evidence["reference"]):
            raise ContractValidationError("trusted_readback_mismatch")
        if "failure" in payload or "retry_with_same_idempotency_key" in payload:
            raise ContractValidationError("invalid_persistence_outcome")
    elif state in {"rejected", "unavailable"}:
        if payload.get("persisted") is not False:
            raise ContractValidationError("invalid_persistence_outcome", "persisted")
        _require_failure(payload.get("failure"))
        if any(field in payload for field in (
                "request_reference", "audit_evidence",
                "retry_with_same_idempotency_key")):
            raise ContractValidationError("invalid_persistence_outcome")
    elif state == "uncertain":
        if payload.get("persisted") != "unknown":
            raise ContractValidationError("invalid_persistence_outcome", "persisted")
        failure = _require_failure(payload.get("failure"))
        if failure.get("code") != "persistence_uncertain":
            raise ContractValidationError("invalid_persistence_outcome", "failure.code")
        if payload.get("retry_with_same_idempotency_key") is not True:
            raise ContractValidationError(
                "invalid_persistence_outcome",
                "retry_with_same_idempotency_key",
            )
        if any(field in payload for field in ("request_reference", "audit_evidence")):
            raise ContractValidationError("invalid_persistence_outcome")
    else:
        raise ContractValidationError("invalid_persistence_outcome", "state")
    return payload


def _uncertain_outcome(idempotency_key: str) -> dict:
    return {
        "state": "uncertain",
        "persisted": "unknown",
        "idempotency_key": idempotency_key,
        "failure": {"code": "persistence_uncertain", "retryable": True},
        "retry_with_same_idempotency_key": True,
    }


def map_request_persistence_outcome(
        result: dict, *, idempotency_key: str, reconciliation: str,
        trusted_readback: TrustedPersistenceReadback | None = None) -> dict:
    """Map a domain plan and reconciliation step to a truthful public outcome.

    ``reconciliation == "complete"`` is the only path that can produce a
    created/duplicate success.  The caller must supply independent,
    domain-validated readback of both canonical rows.  All partial or
    ambiguous steps become ``uncertain``;
    they must be reconciled with the original idempotency key.
    """
    key = _required_text(idempotency_key, "idempotency_key")
    binding = _persistence_result_binding(result, key)
    if trusted_readback is not None:
        _validate_readback_binding(binding, key, trusted_readback)
    if reconciliation == "complete":
        if not isinstance(trusted_readback, TrustedPersistenceReadback):
            return _uncertain_outcome(key)
        if trusted_readback.commit_state != "committed":
            return _uncertain_outcome(key)
        outcome = {
            "state": binding["result_kind"],
            "persisted": True,
            "idempotency_key": key,
            "request_reference": trusted_readback.request_reference,
            "audit_evidence": {
                "reference": trusted_readback.audit_reference,
                "request_reference": trusted_readback.request_reference,
                "verified": True,
            },
        }
        return validate_request_outcome(
            outcome, result=result, trusted_readback=trusted_readback)
    if reconciliation in _PENDING_RECONCILIATIONS or reconciliation is None:
        return _uncertain_outcome(key)
    if reconciliation == "unavailable":
        # A provider outage does not prove that a preceding write did not
        # commit.  Only an explicit pre-write refusal may be reported as
        # persisted=False; this seam conservatively returns unknown.
        return _uncertain_outcome(key)
    if reconciliation == "rejected":
        return validate_request_outcome({
            "state": "rejected",
            "persisted": False,
            "idempotency_key": key,
            "failure": {"code": "invalid_contract", "retryable": False},
        })
    raise ContractValidationError("unknown_reconciliation_state", "reconciliation")


def map_reception_transition(payload: dict, *, expected_fingerprint: str) -> dict:
    """Map a public transition into ``StaffActionGateway.prepare`` input.

    The public contract deliberately omits actor identity and fingerprint.
    Actor identity and the fingerprint must come from trusted server-side
    adapters; the gateway then performs membership, department, version and
    lifecycle checks.
    """
    if not isinstance(payload, dict):
        raise ContractValidationError("invalid_contract", "payload")
    allowed = {
        "request_reference", "operation_id", "expected_version", "action",
        "from_status", "target_status", "assignee_reference", "reason",
    }
    if set(payload) - allowed:
        raise ContractValidationError("invalid_contract")
    request_id = _canonical_uuid(payload.get("request_reference"), "request_reference")
    operation_key = _required_text(payload.get("operation_id"), "operation_id")
    if type(payload.get("expected_version")) is not int or payload["expected_version"] < 1:
        raise ContractValidationError("invalid_contract", "expected_version")
    action = payload.get("action")
    source = payload.get("from_status")
    target = payload.get("target_status")
    if action not in ACTION_TARGETS or source not in TRANSITIONS or target not in TRANSITIONS:
        raise ContractValidationError("invalid_status_transition")
    if ACTION_TARGETS[action] != target or target not in TRANSITIONS[source]:
        raise ContractValidationError("invalid_status_transition")
    if not isinstance(expected_fingerprint, str) or not expected_fingerprint.strip():
        raise ContractValidationError("trusted_fingerprint_required")
    is_assignment = action == "assign"
    has_assignee = "assignee_reference" in payload
    if is_assignment != has_assignee:
        raise ContractValidationError("invalid_transition_fields")
    is_escalation = action == "escalate"
    has_reason = "reason" in payload
    if is_escalation != has_reason:
        raise ContractValidationError("invalid_transition_fields")
    command = {
        "request_id": request_id,
        "action": action,
        "operation_key": operation_key,
        "expected_version": payload["expected_version"],
        "expected_fingerprint": expected_fingerprint,
    }
    if has_assignee:
        command["assignee_id"] = _required_text(
            payload["assignee_reference"], "assignee_reference")
    if has_reason:
        command["reason"] = _required_text(payload["reason"], "reason", limit=1000)
    return command


__all__ = [
    "CONTRACT_VERSION",
    "ContractValidationError",
    "TrustedPersistenceReadback",
    "map_reception_transition",
    "map_request_persistence_outcome",
    "validate_hotel_information",
    "validate_request_outcome",
    "validate_rfc3339",
]
