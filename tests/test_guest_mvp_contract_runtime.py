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
from domain.service_requests import create_request, transition_request


class GuestMvpContractRuntimeTests(unittest.TestCase):
    @staticmethod
    def trusted_readback(*, hotel_label="request-hotel", request_label="request"):
        hotel = synthetic_hotel()
        hotel_id = uid(hotel_label)
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
        staff = [
            {"actor_id": "front", "hotel_id": hotel_id,
             "department": "reception", "roles": [], "active": True},
            {"actor_id": "housekeeper", "hotel_id": hotel_id,
             "department": "housekeeping", "roles": [], "active": True},
        ]
        planned = create_request(
            hotel, draft, guest, staff, [],
            at="2026-11-06T12:00:00+01:00", request_id=uid(request_label),
        )
        request = planned["request"]
        event = dict(planned["plan"]["event"], commit_state="committed")
        trusted = TrustedPersistenceReadback.from_reconciled_result(
            planned, request, [event], idempotency_key="idem-1")
        return planned, trusted, request, event, draft, staff, hotel

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
            {"answer_state": "answered", "answer": "A"},
            {"question": "Q", "answer_state": "answered", "answer": "A",
             "extra": "caller supplied"},
            {"question": " ", "answer_state": "answered", "answer": "A"},
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
        _, trusted, _, _, _, _, _ = self.trusted_readback()
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
        result, _, _, _, _, _, _ = self.trusted_readback()
        validate_request_outcome(
            success, result=result, trusted_readback=trusted)
        with self.assertRaisesRegex(ContractValidationError, "trusted_readback"):
            validate_request_outcome(success)
        with self.assertRaisesRegex(ContractValidationError, "trusted_readback"):
            validate_request_outcome(
                {**success, "state": "duplicate"}, result=result,
                trusted_readback=trusted)

        mismatch = copy.deepcopy(success)
        mismatch["audit_evidence"]["request_reference"] = str(uuid4())
        with self.assertRaisesRegex(ContractValidationError, "reference"):
            validate_request_outcome(
                mismatch, result=result, trusted_readback=trusted)

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
        result, trusted, request, event, draft, staff, hotel = self.trusted_readback()

        created = map_request_persistence_outcome(
            result, idempotency_key="idem-1",
            reconciliation="complete", trusted_readback=trusted,
        )
        self.assertEqual(created["state"], "created")
        self.assertTrue(created["persisted"])
        self.assertEqual(created["request_reference"], trusted.request_reference)
        self.assertEqual(created["audit_evidence"]["request_reference"],
                         trusted.request_reference)

        uncertain = map_request_persistence_outcome(
            result, idempotency_key="idem-1",
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
                result, request, [{**event, "request_id": str(uuid4())}],
                idempotency_key="idem-1")

        with self.assertRaises(ContractValidationError):
            TrustedPersistenceReadback.from_reconciled_result(
                {"kind": "duplicate", "request": request,
                 "creation_event_identity": {}}, request,
                [{**event, "sequence": event["sequence"] + 1}],
                idempotency_key="idem-1")

        unavailable = map_request_persistence_outcome(
            result, idempotency_key="idem-1",
            reconciliation="unavailable",
        )
        self.assertEqual(unavailable["persisted"], "unknown")

        with self.assertRaises(ContractValidationError):
            map_request_persistence_outcome(
                {"kind": "duplicate", "request": request},
                idempotency_key="idem-1", reconciliation="complete",
                trusted_readback=trusted)

        for hotel_label, request_label in (
                ("request-hotel", "another-request"),
                ("another-hotel", "another-request")):
            other_result, _, _, _, _, _, _ = self.trusted_readback(
                hotel_label=hotel_label, request_label=request_label)
            with self.subTest(hotel_label=hotel_label):
                with self.assertRaises(ContractValidationError):
                    map_request_persistence_outcome(
                        other_result, idempotency_key="idem-1",
                        reconciliation="complete", trusted_readback=trusted)

        unrelated_operation = copy.deepcopy(result)
        unrelated_operation["plan"]["event"]["operation_id"] = str(uuid4())
        with self.assertRaises(ContractValidationError):
            map_request_persistence_outcome(
                unrelated_operation, idempotency_key="idem-1",
                reconciliation="complete", trusted_readback=trusted)

    def test_duplicate_reconciles_original_creation_and_preserves_status_history(self):
        result, _, request, created_event, draft, staff, hotel = self.trusted_readback()
        assigned = transition_request(
            request, "assigned",
            {"actor_id": "front", "hotel_id": request["hotel_id"], "kind": "staff"},
            staff, at="2026-11-06T13:00:00+01:00", operation_key="assign-1",
            assignee_id="housekeeper")
        assigned_request = assigned["request"]
        assignment_event = dict(assigned["plan"]["event"], commit_state="committed")
        duplicate = create_request(
            hotel, draft,
            {"actor_id": "guest-session-c", "hotel_id": request["hotel_id"],
             "kind": "guest", "guest_id": request["guest_id"]},
            staff, [assigned_request], at="2026-11-06T14:00:00+01:00",
            request_id=uid("ignored-retry-id"))
        self.assertEqual(duplicate["kind"], "duplicate")
        trusted = TrustedPersistenceReadback.from_reconciled_result(
            duplicate, assigned_request, [created_event, assignment_event],
            idempotency_key="idem-1")
        self.assertEqual(trusted.audit_reference, created_event["event_id"])
        outcome = map_request_persistence_outcome(
            duplicate, idempotency_key="idem-1", reconciliation="complete",
            trusted_readback=trusted)
        self.assertEqual(outcome["state"], "duplicate")
        self.assertEqual(outcome["request_reference"], assigned_request["request_id"])

        original_proof = TrustedPersistenceReadback.from_reconciled_result(
            result, request, [created_event], idempotency_key="idem-1")
        with self.assertRaisesRegex(ContractValidationError, "trusted_readback"):
            map_request_persistence_outcome(
                duplicate, idempotency_key="idem-1", reconciliation="complete",
                trusted_readback=original_proof)

        for altered_creation in (
                {**created_event, "commit_state": "pending"},
                {**created_event, "operation_signature": "0" * 64}):
            with self.subTest(altered_creation=altered_creation):
                with self.assertRaises(ContractValidationError):
                    TrustedPersistenceReadback.from_reconciled_result(
                        duplicate, assigned_request,
                        [altered_creation, assignment_event],
                        idempotency_key="idem-1")

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

    def test_duplicate_rejects_incomplete_or_uncommitted_audit_history(self):
        _, _, request, created_event, draft, staff, hotel = self.trusted_readback()
        actor = {"actor_id": "front", "hotel_id": request["hotel_id"],
                 "kind": "staff"}
        assigned = transition_request(
            request, "assigned", actor, staff, at="2026-11-06T13:00:00+01:00",
            operation_key="assign-1", assignee_id="housekeeper")
        actor = {"actor_id": "housekeeper", "hotel_id": request["hotel_id"],
                 "kind": "staff"}
        acknowledged = transition_request(
            assigned["request"], "acknowledged", actor, staff,
            at="2026-11-06T13:30:00+01:00", operation_key="acknowledge-1")
        in_progress = transition_request(
            acknowledged["request"], "in_progress", actor, staff,
            at="2026-11-06T14:00:00+01:00", operation_key="progress-1")
        duplicate = create_request(
            hotel, draft,
            {"actor_id": "guest-session-c", "hotel_id": request["hotel_id"],
             "kind": "guest", "guest_id": request["guest_id"]},
            staff, [in_progress["request"]], at="2026-11-06T15:00:00+01:00",
            request_id=uid("ignored-retry-id"))
        events = [
            dict(created_event, commit_state="committed"),
            dict(assigned["plan"]["event"], commit_state="committed"),
            dict(acknowledged["plan"]["event"], commit_state="committed"),
            dict(in_progress["plan"]["event"], commit_state="committed"),
        ]
        self.assertEqual(duplicate["kind"], "duplicate")
        valid_proof = TrustedPersistenceReadback.from_reconciled_result(
            duplicate, in_progress["request"], events, idempotency_key="idem-1")
        self.assertEqual(map_request_persistence_outcome(
            duplicate, idempotency_key="idem-1", reconciliation="complete",
            trusted_readback=valid_proof)["state"], "duplicate")

        invalid_histories = {
            "missing creation": events[1:],
            "missing intermediate": [events[0], events[1], events[3]],
            "sequence gap": [events[0], {**events[1], "sequence": 5}, events[2], events[3]],
            "duplicate event id": [events[0], {**events[1], "event_id": events[0]["event_id"]}, *events[2:]],
            "duplicate operation id": [events[0], {**events[1], "operation_id": events[0]["operation_id"]}, *events[2:]],
            "pending creation": [{**events[0], "commit_state": "pending"}, *events[1:]],
            "pending transition": [events[0], events[1], {**events[2], "commit_state": "pending"}, events[3]],
        }
        for label, history in invalid_histories.items():
            with self.subTest(history=label):
                with self.assertRaises(ContractValidationError):
                    TrustedPersistenceReadback.from_reconciled_result(
                        duplicate, in_progress["request"], history,
                        idempotency_key="idem-1")

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
