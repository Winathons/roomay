"""Versioned guest MVP contract shape and fail-closed vocabulary checks."""
import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator, FormatChecker

from domain.guest_mvp_contract import ContractValidationError, validate_rfc3339
from domain.service_requests import DEPARTMENTS, STATUSES, TRANSITIONS
from domain.staff_actions import ACTION_TARGETS


SCHEMA_PATH = (Path(__file__).resolve().parents[1]
               / "docs/contracts/roomay.guest-mvp.v1.schema.json")


class GuestMvpContractV1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        cls.defs = cls.schema["$defs"]
        Draft202012Validator.check_schema(cls.schema)
        cls.format_checker = FormatChecker()
        cls.format_checker.checks("date-time", raises=ContractValidationError)(
            validate_rfc3339)
        cls.validator = Draft202012Validator(
            cls.schema, format_checker=cls.format_checker)

    def envelope(self, message_type, payload, **overrides):
        message = {
            "contract_version": "roomay.guest-mvp.v1",
            "message_type": message_type,
            "correlation_id": "corr-1",
            "payload": payload,
        }
        message.update(overrides)
        return message

    def assert_valid_message(self, message):
        self.assertEqual(self._message_errors(message), [])

    def assert_invalid_message(self, message):
        self.assertTrue(self._message_errors(message))

    def _message_errors(self, message):
        errors = list(self.validator.iter_errors(message))
        if (message.get("message_type") == "request_outcome"
                and message.get("payload", {}).get("state") in {"created", "duplicate"}):
            payload = message["payload"]
            evidence = payload.get("audit_evidence", {})
            # JSON Schema cannot express equality between sibling values; the
            # adapter contract must verify that the audit row links to the
            # canonical request before returning success.
            if payload.get("request_reference") != evidence.get("request_reference"):
                errors.append("audit evidence references a different request")
        return errors

    def test_contract_is_versioned_and_has_all_consumer_messages(self):
        self.assertEqual(self.schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertEqual(self.schema["$id"], "urn:roomay:contracts:guest-mvp:v1")
        self.assertEqual(self.schema["properties"]["contract_version"]["const"], "roomay.guest-mvp.v1")
        self.assertEqual(set(self.schema["properties"]["message_type"]["enum"]), {
            "guest_context", "hotel_information", "conversation_action",
            "request_draft", "request_outcome", "reception_transition",
            "guest_status_readback",
        })

    def test_public_shapes_reject_unspecified_fields_and_require_identity_scope(self):
        for name in self.schema["properties"]["message_type"]["enum"]:
            with self.subTest(name=name):
                definition = self.defs[name]
                self.assertEqual(definition["type"], "object")
                self.assertTrue(definition["additionalProperties"] is False)
                if name in {"conversation_action", "guest_context", "request_outcome"}:
                    self.assertTrue(definition["oneOf"])
                    for operation in definition["oneOf"]:
                        self.assertTrue(set(operation["required"]) <= set(definition["properties"]))
                else:
                    self.assertTrue(definition["required"])
                    self.assertTrue(set(definition["required"]) <= set(definition["properties"]))
        context = self.defs["guest_context"]["properties"]["stay"]
        self.assertIn("room_id", context["required"])
        self.assertIn("verified", context["required"])
        self.assertEqual(context["properties"]["verified"]["const"], True)

    def test_confirmation_and_mutation_are_distinct_explicit_operations(self):
        action = self.defs["conversation_action"]["properties"]
        self.assertEqual(set(action["operation"]["enum"]), {"message", "confirm", "cancel"})
        draft = self.defs["request_draft"]
        self.assertIn("confirmation_required", draft["required"])
        self.assertEqual(draft["properties"]["confirmation_required"]["const"], True)
        self.assertIn("confirmation_handle", draft["required"])

    def test_hotel_information_has_exclusive_success_failure_states(self):
        self.assert_valid_message(self.envelope("hotel_information", {
            "question": "Where is breakfast?",
            "answer_state": "answered",
            "answer": "In the lobby.",
        }))
        self.assert_valid_message(self.envelope("hotel_information", {
            "question": "Is the pool open?",
            "answer_state": "handoff",
            "answer": "Reception can confirm the current status.",
        }))
        self.assert_valid_message(self.envelope("hotel_information", {
            "question": "Where is breakfast?",
            "answer_state": "unavailable",
            "failure": {"code": "workpeg_unavailable", "retryable": True},
        }))
        self.assert_invalid_message(self.envelope("hotel_information", {
            "question": "Q", "answer_state": "answered",
        }))
        self.assert_invalid_message(self.envelope("hotel_information", {
            "question": "Q", "answer_state": "unavailable", "answer": "A",
            "failure": {"code": "workpeg_unavailable", "retryable": True},
        }))

    def test_failure_and_persistence_states_are_explicitly_distinguished(self):
        failures = set(self.defs["failure_code"]["enum"])
        self.assertTrue({
            "unauthenticated", "wrong_business", "wrong_room", "stay_revoked",
            "stay_expired", "duplicate_operation", "workpeg_unavailable",
            "persistence_uncertain",
        } <= failures)
        outcomes = set(self.defs["request_outcome"]["properties"]["state"]["enum"])
        self.assertTrue({"created", "duplicate", "rejected", "unavailable", "uncertain"} <= outcomes)
        self.assertEqual(self.defs["guest_status_readback"]["properties"]["status"]["enum"],
                         list(STATUSES))

    def test_guest_projection_excludes_internal_identity_and_audit_fields(self):
        fields = set(self.defs["guest_status_readback"]["properties"])
        self.assertFalse({"guest_id", "business_id", "stay_id", "room_id", "audit_events"} & fields)

    def test_contract_vocabulary_does_not_drift_from_request_domain(self):
        self.assertEqual(set(self.defs["request_draft"]["properties"]["department"]["enum"]),
                         set(DEPARTMENTS))
        self.assertEqual(set(self.defs["guest_status_readback"]["properties"]["status"]["enum"]),
                         set(STATUSES))
        transition = self.defs["reception_transition"]
        self.assertEqual(set(transition["properties"]["action"]["enum"]),
                         set(ACTION_TARGETS))
        contract_edges = {
            (item["properties"]["action"]["const"],
             item["properties"]["from_status"]["const"],
             item["properties"]["target_status"]["const"])
            for item in transition["oneOf"]
        }
        expected_edges = {
            (action, source, target)
            for action, target in ACTION_TARGETS.items()
            for source, targets in TRANSITIONS.items()
            if target in targets
        }
        self.assertEqual(contract_edges, expected_edges)

    def test_draft_2020_12_validates_fail_closed_guest_context_variants(self):
        verified = {
            "state": "verified",
            "stay": {"verified": True, "status": "checked_in", "room_id": "room-1",
                     "valid_until": "2026-11-14T18:00:00Z"},
            "authorized_hotel": {"display_name": "Hotel"},
            "authorized_room": {"display_label": "101"},
        }
        failure = {"state": "unauthenticated", "failure": {"code": "unauthenticated",
                                                               "retryable": False}}
        self.assert_valid_message(self.envelope("guest_context", verified))
        self.assert_valid_message(self.envelope("guest_context", failure))
        self.assert_invalid_message(self.envelope("guest_context", {
            **failure, "stay": verified["stay"], "authorized_hotel": verified["authorized_hotel"],
            "authorized_room": verified["authorized_room"],
        }))
        self.assert_invalid_message(self.envelope("guest_context", {**verified, "failure": failure["failure"]}))

    def test_date_time_formats_are_strict_rfc3339(self):
        valid = self.envelope("guest_context", {
            "state": "verified",
            "stay": {"verified": True, "status": "checked_in", "room_id": "room-1",
                     "valid_until": "2026-11-14T18:00:00Z"},
            "authorized_hotel": {"display_name": "Hotel"},
            "authorized_room": {"display_label": "101"},
        })
        self.assert_valid_message(valid)
        for timestamp in (
            "2026-11-14",
            "2026-11-14T18:00:00",
            "2026-02-30T18:00:00Z",
        ):
            with self.subTest(timestamp=timestamp):
                invalid = json.loads(json.dumps(valid))
                invalid["payload"]["stay"]["valid_until"] = timestamp
                self.assert_invalid_message(invalid)

    def test_draft_2020_12_validates_confirmation_and_versioned_envelopes(self):
        self.assert_valid_message(self.envelope("conversation_action", {
            "operation": "confirm", "interaction_id": "i-1", "confirmation_handle": "confirm-1",
        }))
        self.assert_invalid_message(self.envelope("conversation_action", {
            "operation": "confirm", "interaction_id": "i-1", "confirmation_handle": "confirm-1",
            "text": "also send a message",
        }))
        self.assert_invalid_message(self.envelope("guest_status_readback", {
            "state": "available", "request_reference": "req-1", "status": "received",
            "updated_at": "2026-11-14T12:00:00Z", "guest_id": "private-id",
        }))
        self.assert_invalid_message(self.envelope("guest_status_readback", {
            "state": "available", "request_reference": "req-1", "status": "received",
            "updated_at": "2026-11-14T12:00:00Z",
        }, contract_version="roomay.guest-mvp.v2"))
        self.assert_invalid_message(self.envelope("unknown", {}))

    def test_draft_2020_12_validates_outcomes_and_reconciliation(self):
        success = {
            "state": "created", "persisted": True, "request_reference": "req-1",
            "idempotency_key": "idem-1",
            "audit_evidence": {"reference": "audit-1", "request_reference": "req-1", "verified": True},
        }
        uncertain = {
            "state": "uncertain", "persisted": "unknown", "idempotency_key": "idem-1",
            "retry_with_same_idempotency_key": True,
            "failure": {"code": "persistence_uncertain", "retryable": True},
        }
        self.assert_valid_message(self.envelope("request_outcome", success))
        self.assert_valid_message(self.envelope("request_outcome", uncertain))
        self.assert_invalid_message(self.envelope("request_outcome", {
            "state": "created", "persisted": True, "idempotency_key": "idem-1",
        }))
        self.assert_invalid_message(self.envelope("request_outcome", {
            **uncertain, "persisted": False,
        }))
        self.assert_invalid_message(self.envelope("request_outcome", {
            **success, "audit_evidence": {**success["audit_evidence"], "request_reference": "other"},
        }))

    def test_draft_2020_12_validates_supported_transition_edges_and_readback_failures(self):
        valid_transition = {
            "request_reference": "req-1", "operation_id": "op-1", "expected_version": 1,
            "action": "assign", "from_status": "received", "target_status": "assigned",
            "assignee_reference": "staff-1",
        }
        self.assert_valid_message(self.envelope("reception_transition", valid_transition))
        self.assert_invalid_message(self.envelope("reception_transition", {
            **valid_transition, "target_status": "resolved",
        }))
        self.assert_invalid_message(self.envelope("reception_transition", {
            **valid_transition, "from_status": "resolved",
        }))
        self.assert_invalid_message(self.envelope("reception_transition", {
            **valid_transition, "action": "cancel", "target_status": "cancelled",
        }))
        self.assert_valid_message(self.envelope("guest_status_readback", {
            "state": "unavailable", "failure": {"code": "workpeg_unavailable", "retryable": True},
        }))
        self.assert_valid_message(self.envelope("guest_status_readback", {
            "state": "not_found", "failure": {"code": "not_found", "retryable": False},
        }))
        self.assert_invalid_message(self.envelope("guest_status_readback", {
            "state": "unavailable", "failure": {"code": "workpeg_unavailable", "retryable": True},
            "request_reference": "invented", "status": "received",
            "updated_at": "2026-11-14T12:00:00Z",
        }))


if __name__ == "__main__":
    unittest.main()
