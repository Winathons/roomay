import copy
import unittest
from uuid import uuid4

from domain.fixtures import synthetic_hotel, uid
from domain.guest_mvp_contract import (
    ContractValidationError,
    TrustedPersistenceReadback,
    map_reception_transition,
    map_request_persistence_outcome,
    validate_hotel_information,
    validate_request_outcome,
    validate_rfc3339,
)
from domain.service_requests import create_request


class GuestMvpContractRuntimeTests(unittest.TestCase):
    @staticmethod
    def trusted_readback():
        hotel = synthetic_hotel()
        hotel_id = uid("request-hotel")
        guest = {
            "actor_id": "guest-session-c", "hotel_id": hotel_id,
            "kind": "guest", "guest_id": uid("Guest C"),
        }
        draft = {
            "hotel_id": hotel_id, "stay_id": uid("stay"),
            "room_id": uid("205"), "guest_id": uid("Guest C"),
            "origin": "guest", "category": "extra_towels",
            "description": "Please bring two additional towels.",
            "urgency": "normal", "idempotency_key": "idem-1",
            "sensitive": False,
        }
        staff = [{"actor_id": "front", "hotel_id": hotel_id,
                  "department": "reception", "roles": [], "active": True}]
        planned = create_request(
            hotel, draft, guest, staff, [],
            at="2026-11-06T12:00:00+01:00", request_id=uid("request"),
        )
        request = planned["request"]
        event = dict(planned["plan"]["event"], commit_state="committed")
        trusted = TrustedPersistenceReadback.from_reconciled_result(
            planned, request, [event], idempotency_key="idem-1")
        return trusted, request, event

    def test_rfc3339_requires_timezone_and_strict_datetime_shape(self):
        self.assertEqual(validate_rfc3339("2026-11-14T18:00:00Z"),
                         "2026-11-14T18:00:00Z")
        self.assertEqual(validate_rfc3339("2026-11-14T19:00:00.123+01:00"),
                         "2026-11-14T19:00:00.123+01:00")
        for value in (
            "2026-11-14",
            "2026-11-14T18:00:00",
            "2026-02-30T18:00:00Z",
            "2026-11-14 18:00:00Z",
        ):
            with self.subTest(value=value), self.assertRaises(ContractValidationError):
                validate_rfc3339(value)

    def test_hotel_information_is_a_tagged_success_or_failure_union(self):
        validate_hotel_information({
            "question": "Where is breakfast?",
            "answer_state": "answered",
            "answer": "Breakfast is served in the lobby.",
        })
        validate_hotel_information({
            "question": "Is the pool open?",
            "answer_state": "handoff",
            "answer": "Please ask reception to confirm the current status.",
        })
        validate_hotel_information({
            "question": "Where is breakfast?",
            "answer_state": "unavailable",
            "failure": {"code": "workpeg_unavailable", "retryable": True},
        })
        invalid = (
            {"question": "Q", "answer_state": "answered"},
            {"question": "Q", "answer_state": "answered",
             "answer": "A", "failure": {"code": "not_found", "retryable": False}},
            {"question": "Q", "answer_state": "unavailable"},
            {"question": "Q", "answer_state": "unavailable", "answer": "A",
             "failure": {"code": "workpeg_unavailable", "retryable": True}},
            {"question": "Q", "answer_state": "handoff",
             "failure": {"code": "not_found", "retryable": False}},
        )
        for payload in invalid:
            with self.subTest(payload=payload), self.assertRaises(ContractValidationError):
                validate_hotel_information(payload)

    def test_request_outcome_requires_matching_verified_audit_evidence(self):
        trusted, _, _ = self.trusted_readback()
        success = {
            "state": "created",
            "persisted": True,
            "idempotency_key": "idem-1",
            "request_reference": trusted.request_reference,
            "audit_evidence": {
                "reference": trusted.audit_reference,
                "request_reference": trusted.request_reference,
                "verified": True,
            },
        }
        validate_request_outcome(success, trusted_readback=trusted)
        with self.assertRaisesRegex(ContractValidationError, "trusted_readback"):
            validate_request_outcome(success)

        mismatch = copy.deepcopy(success)
        mismatch["audit_evidence"]["request_reference"] = str(uuid4())
        with self.assertRaisesRegex(ContractValidationError, "reference"):
            validate_request_outcome(mismatch, trusted_readback=trusted)

        for state, persisted, extra in (
            ("pending", True, {}),
            ("rejected", False, {"request_reference": "request-1"}),
            ("uncertain", False, {
                "failure": {"code": "persistence_uncertain", "retryable": True},
                "retry_with_same_idempotency_key": True,
            }),
        ):
            payload = {"state": state, "persisted": persisted,
                       "idempotency_key": "idem-1", **extra}
            with self.subTest(state=state), self.assertRaises(ContractValidationError):
                validate_request_outcome(payload)

    def test_persistence_mapping_never_reports_partial_write_as_success(self):
        trusted, request, event = self.trusted_readback()

        created = map_request_persistence_outcome(
            {"kind": "created"}, idempotency_key="idem-1",
            reconciliation="complete", trusted_readback=trusted,
        )
        self.assertEqual(created["state"], "created")
        self.assertTrue(created["persisted"])
        self.assertEqual(created["request_reference"], trusted.request_reference)
        self.assertEqual(created["audit_evidence"]["request_reference"],
                         trusted.request_reference)

        uncertain = map_request_persistence_outcome(
            {"kind": "created"}, idempotency_key="idem-1",
            reconciliation="commit_event",
        )
        self.assertEqual(uncertain, {
            "state": "uncertain",
            "persisted": "unknown",
            "idempotency_key": "idem-1",
            "failure": {"code": "persistence_uncertain", "retryable": True},
            "retry_with_same_idempotency_key": True,
        })

        with self.assertRaises(ContractValidationError):
            TrustedPersistenceReadback.from_reconciled_result(
                {"kind": "created", "plan": {
                    "base_request": request,
                    "target_request": request,
                    "event": event,
                }}, request, [{**event, "request_id": str(uuid4())}],
                idempotency_key="idem-1")

        with self.assertRaises(ContractValidationError):
            TrustedPersistenceReadback.from_reconciled_result(
                {"kind": "duplicate", "request": request}, request,
                [{**event, "sequence": event["sequence"] + 1}],
                idempotency_key="idem-1")

        unavailable = map_request_persistence_outcome(
            {"kind": "created"}, idempotency_key="idem-1",
            reconciliation="unavailable",
        )
        self.assertEqual(unavailable["persisted"], "unknown")

        with self.assertRaisesRegex(ContractValidationError, "trusted_readback"):
            validate_request_outcome({
                "state": "created", "persisted": True,
                "idempotency_key": "idem-1",
                "request_reference": trusted.request_reference,
                "audit_evidence": {
                    "reference": trusted.audit_reference,
                    "request_reference": trusted.request_reference,
                    "verified": True,
                },
            })

    def test_reception_transition_maps_to_trusted_gateway_command(self):
        request_id = str(uuid4())
        payload = {
            "request_reference": request_id,
            "operation_id": "operation-1",
            "expected_version": 2,
            "action": "assign",
            "from_status": "received",
            "target_status": "assigned",
            "assignee_reference": "staff-1",
        }
        command = map_reception_transition(payload,
                                            expected_fingerprint="fp-1")
        self.assertEqual(command, {
            "request_id": request_id,
            "action": "assign",
            "operation_key": "operation-1",
            "expected_version": 2,
            "expected_fingerprint": "fp-1",
            "assignee_id": "staff-1",
        })

        with self.assertRaises(ContractValidationError):
            map_reception_transition(payload, expected_fingerprint="")
        with self.assertRaises(ContractValidationError):
            map_reception_transition({
                **payload, "from_status": "resolved", "target_status": "assigned",
            }, expected_fingerprint="fp-1")
        with self.assertRaises(ContractValidationError):
            map_reception_transition({**payload, "actor_id": "forged"},
                                     expected_fingerprint="fp-1")


if __name__ == "__main__":
    unittest.main()
