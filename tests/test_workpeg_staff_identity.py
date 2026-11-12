"""Offline security tests for the server-only Workpeg staff identity adapter."""
from copy import deepcopy
from types import SimpleNamespace
import unittest

from domain.fixtures import uid
from domain.workpeg_staff_identity import (
    TrustedStaffIdentityError, TrustedWorkpegStaffResolver,
)


BUSINESS = uid("trusted-identity-business")
HOTEL = uid("trusted-identity-hotel")
OTHER_BUSINESS = uid("trusted-identity-other-business")
OTHER_HOTEL = uid("trusted-identity-other-hotel")
SUBJECT = "workpeg-subject-business-and-member-scoped"


def fixture_roster():
    return [
        {"workpeg_subject": SUBJECT, "actor_id": "housekeeper",
         "hotel_id": HOTEL, "department": "housekeeping", "roles": [],
         "active": True},
        {"workpeg_subject": "other-subject", "actor_id": "front",
         "hotel_id": HOTEL, "department": "reception", "roles": [],
         "active": True},
    ]


class Sessions:
    def __init__(self, **identity):
        self.identity = SimpleNamespace(
            subject=SUBJECT, business_id=BUSINESS, role="member",
            email="display-only@example.test", **identity,
        ) if not identity else SimpleNamespace(
            **{"subject": SUBJECT, "business_id": BUSINESS, "role": "member",
               "email": "display-only@example.test", **identity}
        )
        self.proofs = []

    def resolve_verified(self, proof):
        self.proofs.append(proof)
        return self.identity


class Membership:
    def __init__(self, result=True):
        self.result = result
        self.calls = []

    def is_current_staff(self, subject, business_id):
        self.calls.append((subject, business_id))
        return self.result


class Hotels:
    def __init__(self, hotel=HOTEL):
        self.hotel = hotel
        self.calls = []

    def resolve_hotel(self, business_id):
        self.calls.append(business_id)
        return self.hotel


class Roster:
    def __init__(self, entries=None):
        self.entries = fixture_roster() if entries is None else entries
        self.calls = []

    def list_staff(self, business_id, hotel_id):
        self.calls.append((business_id, hotel_id))
        return deepcopy(self.entries)


def build_resolver(*, sessions=None, membership=None, hotels=None, roster=None):
    sessions = sessions or Sessions()
    membership = membership or Membership()
    hotels = hotels or Hotels()
    roster = roster or Roster()
    return TrustedWorkpegStaffResolver(sessions, membership, hotels, roster)


class WorkpegStaffIdentityTests(unittest.TestCase):
    def test_valid_member_bound_by_verified_business_subject_and_private_roster(self):
        sessions, member, hotels, roster = Sessions(), Membership(), Hotels(), Roster()
        resolver = build_resolver(sessions=sessions, membership=member,
                                  hotels=hotels, roster=roster)
        resolved = resolver.resolve("opaque-server-session-handle")
        self.assertEqual(sessions.proofs, ["opaque-server-session-handle"])
        self.assertEqual(member.calls, [(SUBJECT, BUSINESS)])
        self.assertEqual(hotels.calls, [BUSINESS])
        self.assertEqual(roster.calls, [(BUSINESS, HOTEL)])
        self.assertEqual(resolved, {
            "authenticated": True, "membership_verified": True,
            "business_binding_verified": True, "active": True,
            "actor_id": "housekeeper", "business_id": BUSINESS,
            "hotel_id": HOTEL, "department": "housekeeping", "roles": [],
            "staff_directory": [
                {"actor_id": "housekeeper", "hotel_id": HOTEL,
                 "department": "housekeeping", "roles": [], "active": True},
                {"actor_id": "front", "hotel_id": HOTEL,
                 "department": "reception", "roles": [], "active": True},
            ],
        })
        self.assertNotIn("workpeg_subject", str(resolved))
        self.assertNotIn("display-only@example.test", str(resolved))

    def test_workpeg_admin_does_not_automatically_become_roomay_admin(self):
        result = build_resolver(sessions=Sessions(role="admin")).resolve("proof")
        self.assertEqual(result["roles"], [])
        self.assertEqual(result["department"], "housekeeping")

    def test_email_is_never_used_as_identity_key(self):
        wrong_subject = build_resolver(
            sessions=Sessions(subject="different-business-subject",
                              email="display-only@example.test"),
        )
        with self.assertRaisesRegex(TrustedStaffIdentityError,
                                    "staff_not_authorized"):
            wrong_subject.resolve("proof")

    def test_guest_missing_or_untrusted_claim_shape_denied(self):
        for changes in (
            {"role": "guest"}, {"role": "nonmember"},
            {"role": ["admin"]}, {"business_id": OTHER_BUSINESS},
            {"business_id": "invalid"}, {"subject": ""},
            {"subject": None},
        ):
            with self.subTest(changes=changes):
                result = build_resolver(sessions=Sessions(**changes))
                code = ("staff_identity_unverified"
                        if changes.get("role") is not None
                        or changes.get("business_id") == "invalid"
                        or changes.get("subject") in {"", None}
                        else "staff_not_authorized")
                # A valid different business is selected from the verified
                # identity; absent a matching business-specific roster binding,
                # the caller must still be refused.
                if changes.get("business_id") == OTHER_BUSINESS:
                    code = "staff_not_authorized"
                    result = build_resolver(
                        sessions=Sessions(**changes),
                        roster=Roster([{**row, "hotel_id": HOTEL,
                                      "workpeg_subject": "other-subject-" + str(i)}
                                      for i, row in enumerate(fixture_roster())]),
                    )
                with self.assertRaises(TrustedStaffIdentityError) as caught:
                    result.resolve("proof")
                self.assertEqual(caught.exception.code, code)

        class Claims:
            def resolve_verified(self, _proof):
                return {"subject": SUBJECT, "business_id": BUSINESS,
                        "role": "member", "authenticated": True}
        with self.assertRaisesRegex(TrustedStaffIdentityError,
                                    "staff_identity_unverified"):
            build_resolver(sessions=Claims()).resolve("proof")

    def test_inactive_revoked_or_unknown_membership_denied(self):
        for value in (False, None, "true"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(TrustedStaffIdentityError,
                                            "staff_membership_unverified"):
                    build_resolver(membership=Membership(value)).resolve("proof")
        roster = fixture_roster()
        roster[0]["active"] = False
        with self.assertRaisesRegex(TrustedStaffIdentityError, "staff_not_authorized"):
            build_resolver(roster=Roster(roster)).resolve("proof")

    def test_hotel_business_binding_must_be_verified(self):
        with self.assertRaisesRegex(TrustedStaffIdentityError,
                                    "staff_hotel_mapping_unverified"):
            build_resolver(hotels=Hotels("not-a-uuid")).resolve("proof")
        with self.assertRaisesRegex(TrustedStaffIdentityError,
                                    "staff_directory_unverified"):
            build_resolver(hotels=Hotels(OTHER_HOTEL)).resolve("proof")

    def test_duplicate_roster_subject_actor_and_privileges_denied(self):
        for entries in (
            fixture_roster() + [fixture_roster()[0]],
            [{**fixture_roster()[0], "workpeg_subject": "duplicate",
              "actor_id": "front"}, fixture_roster()[1]],
            [{**fixture_roster()[0], "roles": ["request_admin", "request_admin"]}],
            [{**fixture_roster()[0], "roles": ["superuser"]}],
            [{**fixture_roster()[0], "roles": [[]]}],
            [{**fixture_roster()[0], "department": ["housekeeping"]}],
            [{**fixture_roster()[0], "active": 1}],
            [{**fixture_roster()[0], "unexpected": "client-role"}],
            [{}], [],
        ):
            with self.subTest(entries=entries):
                with self.assertRaisesRegex(TrustedStaffIdentityError,
                                            "staff_directory_unverified"):
                    build_resolver(roster=Roster(entries)).resolve("proof")

    def test_port_failures_are_sanitized(self):
        class Explodes:
            def resolve_verified(self, _proof):
                raise RuntimeError("sensitive session token")
        with self.assertRaises(TrustedStaffIdentityError) as caught:
            build_resolver(sessions=Explodes()).resolve("secret")
        self.assertEqual(caught.exception.code, "staff_identity_unavailable")
        self.assertNotIn("token", str(caught.exception))

        class ExplodingMembers:
            def is_current_staff(self, *_args):
                raise RuntimeError("sensitive membership response")
        with self.assertRaisesRegex(TrustedStaffIdentityError,
                                    "staff_membership_unavailable"):
            build_resolver(membership=ExplodingMembers()).resolve("proof")

        class ExplodingHotels:
            def resolve_hotel(self, *_args):
                raise RuntimeError("private hotel mapping")
        with self.assertRaisesRegex(TrustedStaffIdentityError,
                                    "staff_hotel_mapping_unavailable"):
            build_resolver(hotels=ExplodingHotels()).resolve("proof")

        class ExplodingRoster:
            def list_staff(self, *_args):
                raise RuntimeError("private guest record")
        with self.assertRaisesRegex(TrustedStaffIdentityError,
                                    "staff_directory_unavailable"):
            build_resolver(roster=ExplodingRoster()).resolve("proof")

    def test_invalid_port_configuration_refused(self):
        with self.assertRaisesRegex(TrustedStaffIdentityError,
                                    "trusted_staff_ports_required"):
            TrustedWorkpegStaffResolver(None, Membership(), Hotels(), Roster())


if __name__ == "__main__":
    unittest.main()
