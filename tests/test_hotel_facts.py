"""Offline tests for source-backed fact resolution; no hotel facts are seeded."""
from copy import deepcopy
from dataclasses import replace
import unittest

from domain.access_control import AccessContext
from domain.fixtures import synthetic_hotel, uid
from domain.hotel_facts import (
    FACT_UNAVAILABLE_MESSAGE, FactScope, FactSourcePolicy, FactTopic,
    HotelFactRecord, resolve_hotel_fact, resolve_hotel_fact_from_reader,
)


BUSINESS = uid("facts-business")
HOTEL = uid("facts-hotel")
GUEST = uid("Guest C")
STAY = uid("stay")
ROOM = uid("205")
NOW = "2026-11-14T12:00:00+01:00"
OBSERVED = "2026-11-14T11:59:00+01:00"
TEST_SOURCE = FactSourcePolicy(
    namespace="test_only", table="test_fact_source", field_id="opaque_value",
    scope=FactScope.ROOM,
)
TEST_VALUE = "opaque-approved-fact-sentinel"


class HotelFactResolutionTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = synthetic_hotel()
        self.guest = AccessContext(
            actor_id="trusted-test-adapter", business_id=BUSINESS,
            hotel_id=HOTEL, role="guest", authenticated=True,
            membership_verified=True, business_binding_verified=True,
            guest_id=GUEST,
        )
        self.fact = HotelFactRecord(
            topic=FactTopic.WIFI, value=TEST_VALUE, business_id=BUSINESS,
            hotel_id=HOTEL, scope=FactScope.ROOM, observed_at=OBSERVED,
            source_namespace=TEST_SOURCE.namespace,
            source_table=TEST_SOURCE.table, source_field=TEST_SOURCE.field_id,
            room_id=ROOM,
        )
        self.kwargs = dict(
            context=self.guest, business_id=BUSINESS,
            record_business_id=BUSINESS, hotel_id=HOTEL,
            trusted_snapshot_hotel_id=HOTEL, snapshot=self.snapshot,
            observed_at=OBSERVED, now=NOW, stay_id=STAY, room_id=ROOM,
            approved_sources={FactTopic.WIFI: TEST_SOURCE},
        )

    def resolve(self, records=None, **kwargs):
        values = dict(self.kwargs)
        values.update(kwargs)
        return resolve_hotel_fact(FactTopic.WIFI,
                                  [self.fact] if records is None else records,
                                  **values)

    def test_valid_source_backed_room_answer_is_verbatim_and_minimal(self):
        result = self.resolve()
        self.assertEqual((result.status, result.answer, result.message),
                         ("answered", TEST_VALUE, TEST_VALUE))
        self.assertFalse(hasattr(result, "code"))
        self.assertNotIn(BUSINESS, repr(result))
        self.assertNotIn(HOTEL, repr(result))
        self.assertNotIn(ROOM, repr(result))
        self.assertNotIn(STAY, repr(result))

    def test_hotel_level_fact_and_authorized_reception_access_use_same_policy(self):
        hotel_policy = FactSourcePolicy(
            namespace="test_only", table="test_fact_source",
            field_id="opaque_value", scope=FactScope.HOTEL)
        record = replace(self.fact, topic=FactTopic.HOTEL_POLICY,
                         scope=FactScope.HOTEL, room_id=None)
        guest_result = resolve_hotel_fact(
            FactTopic.HOTEL_POLICY, [record], **{
                **self.kwargs,
                "approved_sources": {FactTopic.HOTEL_POLICY: hotel_policy},
            })
        receptionist = AccessContext(
            actor_id="trusted-test-reception", business_id=BUSINESS,
            hotel_id=HOTEL, role="receptionist", authenticated=True,
            membership_verified=True, business_binding_verified=True,
        )
        staff_result = resolve_hotel_fact(
            FactTopic.HOTEL_POLICY, [record], **{
                **self.kwargs,
                "context": receptionist,
                "stay_id": None,
                "room_id": None,
                "approved_sources": {FactTopic.HOTEL_POLICY: hotel_policy},
            })
        self.assertEqual(guest_result.answer, TEST_VALUE)
        self.assertEqual(staff_result.answer, TEST_VALUE)

    def test_missing_fact_and_unconfigured_source_return_helpful_fallback(self):
        missing = self.resolve(records=[])
        unconfigured = self.resolve(approved_sources={})
        for result in (missing, unconfigured):
            self.assertEqual(result.status, "unavailable")
            self.assertIsNone(result.answer)
            self.assertEqual(result.message, FACT_UNAVAILABLE_MESSAGE)

    def test_cross_business_hotel_and_wrong_room_facts_fail_closed(self):
        for changes in (
            {"business_id": uid("other-business")},
            {"hotel_id": uid("other-hotel")},
            {"room_id": uid("120")},
        ):
            with self.subTest(changes=changes):
                self.assertEqual(self.resolve(records=[replace(self.fact, **changes)]).status,
                                 "unavailable")
        wrong_context = replace(self.guest, business_id=uid("other-business"))
        self.assertEqual(self.resolve(context=wrong_context).status, "unavailable")

    def test_unverified_guest_stay_wrong_guest_and_revoked_membership_deny(self):
        for changes in (
            {"guest_id": uid("Guest A")},
            {"authenticated": False},
            {"membership_verified": False},
            {"business_binding_verified": False},
        ):
            with self.subTest(changes=changes):
                self.assertEqual(self.resolve(context=replace(self.guest, **changes)).status,
                                 "unavailable")
        self.assertEqual(self.resolve(stay_id=uid("other-stay")).status, "unavailable")
        self.assertEqual(self.resolve(room_id=uid("120")).status, "unavailable")

    def test_checked_out_or_departed_guest_no_longer_has_room_fact_access(self):
        snapshot = deepcopy(self.snapshot)
        snapshot["stays"][0].update(
            status="checked_out", checked_out_at="2026-11-08T10:00:00+01:00")
        snapshot["stay_guests"][0]["left_at"] = "2026-11-08T10:00:00+01:00"
        self.assertEqual(self.resolve(snapshot=snapshot).status, "unavailable")
        snapshot = deepcopy(self.snapshot)
        snapshot["stay_guests"][0]["left_at"] = "2026-11-07T10:00:00+01:00"
        self.assertEqual(self.resolve(snapshot=snapshot).status, "unavailable")

    def test_stale_future_and_malformed_observation_times_refuse_answer(self):
        for observed, now in (
            ("2026-11-14T11:00:00+01:00", NOW),
            ("2026-11-14T13:00:00+01:00", NOW),
            ("not-a-time", NOW),
        ):
            with self.subTest(observed=observed):
                self.assertEqual(self.resolve(
                    records=[replace(self.fact, observed_at=observed)],
                    observed_at=observed, now=now).status, "unavailable")

    def test_duplicate_or_mismapped_source_records_are_not_used(self):
        self.assertEqual(self.resolve(records=[self.fact, self.fact]).status, "unavailable")
        mismapped = replace(self.fact, source_field="unapproved_field")
        self.assertEqual(self.resolve(records=[mismapped]).status, "unavailable")
        self.assertEqual(self.resolve(records=[object()]).status, "unavailable")

    def test_provider_failure_is_sanitized_and_does_not_leak_exception(self):
        def broken_reader(**_):
            raise RuntimeError("private URL and token MUST_NOT_LEAK")

        result = resolve_hotel_fact_from_reader(
            broken_reader, FactTopic.WIFI, **self.kwargs)
        self.assertEqual(result.status, "unavailable")
        self.assertEqual(result.message, FACT_UNAVAILABLE_MESSAGE)
        self.assertFalse(hasattr(result, "code"))
        self.assertNotIn("MUST_NOT_LEAK", repr(result))

    def test_reader_is_not_invoked_for_denied_or_unconfigured_preflight(self):
        calls = []

        def reader(**kwargs):
            calls.append(kwargs)
            return [self.fact], OBSERVED

        denied_scopes = (
            {"context": replace(self.guest, authenticated=False)},
            {"context": replace(self.guest, membership_verified=False)},
            {"business_id": uid("other-business")},
            {"hotel_id": uid("other-hotel")},
            {"room_id": uid("120")},
            {"stay_id": uid("other-stay")},
            {"approved_sources": {}},
        )
        for changes in denied_scopes:
            with self.subTest(changes=changes):
                result = resolve_hotel_fact_from_reader(
                    reader, FactTopic.WIFI, **{**self.kwargs, **changes})
                self.assertEqual(result.status, "unavailable")
                self.assertEqual(result.message, FACT_UNAVAILABLE_MESSAGE)
                self.assertNotIn("code", vars(result))
        self.assertEqual(calls, [])

    def test_reader_receives_only_trusted_scope_not_guest_text(self):
        seen = {}

        def reader(**kwargs):
            seen.update(kwargs)
            return [self.fact], OBSERVED

        result = resolve_hotel_fact_from_reader(
            reader, FactTopic.WIFI, **self.kwargs)
        self.assertEqual(result.status, "answered")
        self.assertEqual(result.answer, TEST_VALUE)
        self.assertEqual(set(seen), {"topic", "business_id", "hotel_id", "room_id"})
        self.assertNotIn("question", seen)
        self.assertNotIn("guest_id", seen)

    def test_non_guest_without_verified_workpeg_membership_is_denied(self):
        anonymous = replace(self.guest, role="nonmember", authenticated=False,
                            membership_verified=False, guest_id=None)
        self.assertEqual(self.resolve(context=anonymous).status, "unavailable")


if __name__ == "__main__":
    unittest.main()
