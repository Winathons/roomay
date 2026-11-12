"""Offline integration tests for the trusted Housekeeping request boundary."""
from copy import deepcopy
from types import SimpleNamespace
import unittest

from domain.fixtures import synthetic_hotel, uid
from domain.housekeeping_requests import (
    HousekeepingRequestService, HousekeepingServiceError,
)
from domain.service_requests import create_request, transition_request
from domain.workpeg_staff_identity import TrustedWorkpegStaffResolver


BUSINESS = uid("wor14-housekeeping-business")
HOTEL = uid("wor14-housekeeping-hotel")
GUEST = uid("Guest C")
ROOM = uid("205")
STAY = uid("stay")
PROOF = "opaque-session-handle"


def directory():
    return [
        {"actor_id": "housekeeper", "hotel_id": HOTEL,
         "department": "housekeeping", "roles": [], "active": True},
        {"actor_id": "reception", "hotel_id": HOTEL,
         "department": "reception", "roles": [], "active": True},
        {"actor_id": "maintenance", "hotel_id": HOTEL,
         "department": "maintenance", "roles": [], "active": True},
    ]


def identity(department="housekeeping", **changes):
    value = {
        "authenticated": True, "membership_verified": True,
        "business_binding_verified": True, "active": True,
        "actor_id": "housekeeper", "business_id": BUSINESS, "hotel_id": HOTEL,
        "department": department, "roles": [],
        "staff_directory": directory(),
    }
    for row in value["staff_directory"]:
        if row["actor_id"] == value["actor_id"]:
            row["department"] = department
    value.update(changes)
    return value


class Resolver:
    def __init__(self, value=None, error=None):
        self.value = identity() if value is None else value
        self.error = error
        self.proofs = []

    def resolve(self, proof):
        self.proofs.append(proof)
        if self.error:
            raise self.error
        return deepcopy(self.value)


class InboxReader:
    def __init__(self, requests, business_id=BUSINESS, hotel_id=HOTEL,
                 complete=True):
        self.value = {
            "business_id": business_id, "hotel_id": hotel_id,
            "complete": complete, "requests": deepcopy(requests),
        }
        self.calls = []

    def list_requests(self, business_id):
        self.calls.append(business_id)
        return deepcopy(self.value)


class RequestReader:
    def __init__(self, request, events):
        self.value = {
            "business_id": BUSINESS, "hotel_id": HOTEL,
            "request": deepcopy(request), "fingerprint": "native-fp-2",
            "events": deepcopy(events),
        }
        self.calls = []

    def read_request(self, request_id, business_id):
        self.calls.append((request_id, business_id))
        return deepcopy(self.value)


class VerifiedOidcSession:
    def __init__(self, business_id=BUSINESS):
        self.business_id = business_id
        self.proofs = []

    def resolve_verified(self, proof):
        self.proofs.append(proof)
        return SimpleNamespace(
            subject="subject-for-this-business-only",
            business_id=self.business_id,
            role="member",
        )


class CurrentMembership:
    def __init__(self, active=True):
        self.active = active

    def is_current_staff(self, subject, business_id):
        return self.active is True and business_id == BUSINESS


class HotelMapping:
    def resolve_hotel(self, business_id):
        return HOTEL if business_id == BUSINESS else None


class StaffRoster:
    def list_staff(self, business_id, hotel_id):
        if business_id != BUSINESS or hotel_id != HOTEL:
            return []
        return [
            {"workpeg_subject": "subject-for-this-business-only",
             "actor_id": "housekeeper", "hotel_id": HOTEL,
             "department": "housekeeping", "roles": [], "active": True},
            {"workpeg_subject": "reception-subject", "actor_id": "reception",
             "hotel_id": HOTEL, "department": "reception", "roles": [],
             "active": True},
        ]


def trusted_resolver(*, business_id=BUSINESS, membership=True):
    return TrustedWorkpegStaffResolver(
        VerifiedOidcSession(business_id),
        CurrentMembership(membership),
        HotelMapping(),
        StaffRoster(),
    )


def request_outcome(category="extra_towels", description="Please bring towels.",
                    key="hk-one", request_id=None):
    return create_request(
        synthetic_hotel(),
        {"hotel_id": HOTEL, "stay_id": STAY, "room_id": ROOM,
         "guest_id": GUEST, "origin": "guest", "category": category,
         "description": description, "urgency": "normal",
         "idempotency_key": key, "sensitive": False},
        {"actor_id": "opaque-guest", "hotel_id": HOTEL, "kind": "guest",
         "guest_id": GUEST},
        directory(), [], at="2026-11-10T09:00:00+01:00",
        request_id=request_id or uid("request-" + key),
    )


def assigned_request():
    creation = request_outcome()
    assigned = transition_request(
        creation["request"], "assigned",
        {"actor_id": "reception", "hotel_id": HOTEL, "kind": "staff"},
        directory(), at="2026-11-10T09:05:00+01:00",
        operation_key="assign-to-housekeeping", assignee_id="housekeeper",
    )
    committed_creation = dict(creation["plan"]["event"], commit_state="committed")
    committed_assignment = dict(assigned["plan"]["event"], commit_state="committed")
    return assigned["request"], [committed_creation, committed_assignment]


def command(request, **changes):
    value = {
        "request_id": request["request_id"], "action": "acknowledge",
        "operation_key": "hk-acknowledge-1",
        "expected_version": request["version"],
        "expected_fingerprint": "native-fp-2",
    }
    value.update(changes)
    return value


class HousekeepingRequestServiceTests(unittest.TestCase):
    def setUp(self):
        self.hk_request = request_outcome()["request"]
        self.maintenance_request = request_outcome(
            category="plumbing", description="The sink is leaking.",
            key="maintenance-one",
        )["request"]
        self.resolver = Resolver()
        self.inbox_reader = InboxReader([self.hk_request, self.maintenance_request])
        self.request_reader = RequestReader(*assigned_request())
        self.service = HousekeepingRequestService(
            self.resolver, self.inbox_reader, self.request_reader,
            lambda: "2026-11-10T09:06:00+01:00",
        )

    def test_verified_housekeeper_gets_only_housekeeping_projection(self):
        result = self.service.inbox(PROOF)
        self.assertEqual(result["state"], "loaded")
        self.assertEqual(len(result["requests"]), 1)
        row = result["requests"][0]
        self.assertEqual(row["department"], "housekeeping")
        self.assertEqual(row["description"], "Please bring towels.")
        for field in ("guest_id", "stay_id", "hotel_id", "idempotency_key",
                      "last_event_id", "last_operation_signature"):
            self.assertNotIn(field, row)
        self.assertEqual(self.inbox_reader.calls, [BUSINESS])
        self.assertEqual(self.resolver.proofs, [PROOF])

    def test_workpeg_oidc_resolver_composes_into_housekeeping_projection(self):
        resolver = trusted_resolver()
        service = HousekeepingRequestService(
            resolver, self.inbox_reader, self.request_reader,
            lambda: "2026-11-10T09:06:00+01:00",
        )
        result = service.inbox(PROOF)
        self.assertEqual(len(result["requests"]), 1)
        self.assertEqual(result["requests"][0]["department"], "housekeeping")
        self.assertNotIn("subject-for-this-business-only", str(result))

        revoked = HousekeepingRequestService(
            trusted_resolver(membership=False), self.inbox_reader,
            self.request_reader, lambda: "2026-11-10T09:06:00+01:00",
        )
        with self.assertRaisesRegex(
                HousekeepingServiceError, "staff_identity_unavailable"):
            revoked.inbox(PROOF)

    def test_cross_business_or_incomplete_inbox_fails_closed(self):
        self.inbox_reader.value["business_id"] = uid("wrong-business")
        with self.assertRaisesRegex(
                HousekeepingServiceError, "housekeeping_inbox_unavailable"):
            self.service.inbox(PROOF)
        self.inbox_reader.value["business_id"] = BUSINESS
        self.inbox_reader.value["complete"] = False
        with self.assertRaisesRegex(
                HousekeepingServiceError, "housekeeping_inbox_unavailable"):
            self.service.inbox(PROOF)

    def test_wrong_department_revoked_membership_and_forged_identity_fail(self):
        wrong_department = identity("maintenance")
        service = HousekeepingRequestService(
            Resolver(wrong_department), self.inbox_reader, self.request_reader,
            lambda: "2026-11-10T09:06:00+01:00",
        )
        with self.assertRaisesRegex(
                HousekeepingServiceError, "housekeeping_access_denied"):
            service.inbox(PROOF)

        revoked = identity(membership_verified=False)
        service = HousekeepingRequestService(
            Resolver(revoked), self.inbox_reader, self.request_reader,
            lambda: "2026-11-10T09:06:00+01:00",
        )
        with self.assertRaisesRegex(
                HousekeepingServiceError, "housekeeping_access_denied"):
            service.inbox(PROOF)

        with self.assertRaisesRegex(
                HousekeepingServiceError, "invalid_staff_command"):
            self.service.prepare_action(PROOF, command(
                self.request_reader.value["request"], actor_id="reception",
                role="manager", business_id=uid("forged-business"),
            ))

    def test_action_plan_is_private_unpersisted_and_blocked_on_missing_audit(self):
        request = self.request_reader.value["request"]
        result = self.service.prepare_action(PROOF, command(request))
        self.assertEqual(result["status"], "acknowledged")
        self.assertFalse(result["persisted"])
        self.assertNotIn("plan", result)
        for field in ("guest_id", "stay_id", "hotel_id", "description",
                      "last_operation_signature"):
            self.assertNotIn(field, result)

        self.request_reader.value["events"] = []
        with self.assertRaisesRegex(
                HousekeepingServiceError, "unreconciled_request_audit"):
            self.service.prepare_action(PROOF, command(request))

    def test_unauthorized_actions_and_private_reader_failures_are_sanitized(self):
        request = self.request_reader.value["request"]
        with self.assertRaisesRegex(
                HousekeepingServiceError, "housekeeping_action_not_allowed"):
            self.service.prepare_action(PROOF, command(request, action="assign"))

        class BrokenResolver:
            def resolve(self, _proof):
                raise RuntimeError("private Workpeg session and token")

        service = HousekeepingRequestService(
            BrokenResolver(), self.inbox_reader, self.request_reader,
            lambda: "2026-11-10T09:06:00+01:00",
        )
        with self.assertRaisesRegex(
                HousekeepingServiceError, "staff_identity_unavailable") as caught:
            service.inbox(PROOF)
        self.assertNotIn("token", str(caught.exception))

    def test_duplicate_inbox_identity_fails_closed(self):
        self.inbox_reader.value["requests"] = [
            self.hk_request, deepcopy(self.hk_request),
        ]
        with self.assertRaisesRegex(
                HousekeepingServiceError, "housekeeping_inbox_unavailable"):
            self.service.inbox(PROOF)


if __name__ == "__main__":
    unittest.main()
