"""WOR-21 read-only Pulse: deterministic hotel complaints, no Workpeg writes."""
from dataclasses import replace
from datetime import datetime, timedelta
from unittest import TestCase

from domain.fixtures import synthetic_hotel, uid
from domain.hotel import validate_snapshot
from domain.pulse import (
    PulseContext, PulsePolicy, PulseRejected, build_pulse_snapshot,
    prepare_pulse_review,
)
from domain.service_requests import create_request, validate_request

HOTEL = uid("pulse-hotel")
BUSINESS = uid("pulse-business")
START = "2026-11-06T10:00:00+01:00"


class PulseTests(TestCase):
    def setUp(self):
        self.hotel = synthetic_hotel()
        # Expand strictly fictional stays so each cooling report can originate
        # from a real, distinct room and its own verified in-house guest.
        for label, room, guest in (
            ("pulse-room-204", "204", "Guest A"),
            ("pulse-room-201", "201", "Guest B"),
        ):
            booking_id = uid(label + "-booking")
            stay_id = uid(label + "-stay")
            self.hotel["reservations"].append(dict(
                entity_id=booking_id, guest_id=uid(guest),
                room_type_id=uid("standard"), room_id=uid(room),
                arrival="2026-11-06", departure="2026-11-08",
                party_size=1, source="walk_in", status="confirmed",
            ))
            self.hotel["stays"].append(dict(
                entity_id=stay_id, reservation_id=booking_id,
                room_id=uid(room), status="checked_in",
                checked_in_at="2026-11-06T09:00:00+01:00",
            ))
            self.hotel["stay_guests"].append(dict(
                entity_id=uid(label + "-occupant"), stay_id=stay_id,
                guest_id=uid(guest), joined_at="2026-11-06T09:00:00+01:00",
            ))
        validate_snapshot(self.hotel)
        self.context = PulseContext(
            business_id=BUSINESS, snapshot_business_id=BUSINESS,
            hotel_id=HOTEL, snapshot_hotel_id=HOTEL,
            actor_id="synthetic-manager", actor_role="manager",
            authorization_verified=True, snapshot_fresh=True,
            requests_complete=True,
        )
        self.reports = [
            self.report("cooling-1", "205", "stay", "Guest C",
                        "air_conditioning", minutes=0),
            self.report("cooling-2", "204", "pulse-room-204-stay", "Guest A",
                        "air_conditioning", minutes=40),
            self.report("cooling-3", "201", "pulse-room-201-stay", "Guest B",
                        "air_conditioning", minutes=80),
            self.report("food", "205", "stay", "Guest C",
                        "room_service", minutes=60),
            self.report("towel", "205", "stay", "Guest C",
                        "extra_towels", minutes=70),
        ]

    def report(self, label, room, stay, guest, category, *, minutes=0):
        at = (datetime.fromisoformat(START) +
              timedelta(minutes=minutes)).isoformat()
        guest_id = uid(guest)
        return create_request(
            self.hotel,
            dict(
                hotel_id=HOTEL, stay_id=uid(stay), room_id=uid(room),
                guest_id=guest_id, origin="guest", category=category,
                description="Synthetic private details for " + label,
                urgency="normal", idempotency_key="pulse-" + label + "-key",
                sensitive=False,
            ),
            dict(actor_id="synthetic-guest-" + label, kind="guest",
                 hotel_id=HOTEL, guest_id=guest_id),
            [], [], at=at, request_id=uid("pulse-request-" + label),
        )["request"]

    def snapshot(self, *, requests=None, as_of="2026-11-06T12:30:00+01:00",
                 context=None, policy=None):
        return build_pulse_snapshot(
            self.hotel, self.reports if requests is None else requests,
            context=self.context if context is None else context,
            as_of=as_of, policy=policy,
        )

    def test_three_cooling_complaints_yield_one_explainable_suggestion(self):
        pulse = self.snapshot()
        self.assertTrue(pulse.read_only)
        self.assertEqual(len(pulse.suggestions), 1)
        suggestion = pulse.suggestions[0]
        self.assertEqual(suggestion.category, "air_conditioning")
        self.assertEqual(suggestion.department, "maintenance")
        self.assertEqual(suggestion.kind, "multi_room_pattern")
        self.assertEqual(suggestion.open_request_count, 3)
        self.assertEqual(set(suggestion.room_ids),
                         {uid("205"), uid("204"), uid("201")})
        self.assertEqual(set(suggestion.request_ids),
                         {row["request_id"] for row in self.reports[:3]})
        self.assertIn("not a confirmed shared cause", suggestion.explanation)
        self.assertFalse(suggestion.persisted)
        self.assertFalse(any(row.category in {"room_service", "extra_towels"}
                             for row in pulse.suggestions))
        # Never expose customer names, messages or their raw description in
        # aggregated manager view.
        self.assertNotIn("Synthetic private details", str(pulse))
        self.assertNotIn(uid("Guest C"), str(pulse))

    def test_no_order_dependence_or_noisy_single_complaint_clustering(self):
        first = self.snapshot()
        reversed_input = self.snapshot(requests=list(reversed(self.reports)))
        self.assertEqual(first.suggestions, reversed_input.suggestions)
        only_two = self.snapshot(requests=self.reports[:2])
        self.assertFalse(only_two.suggestions)
        cutoff = self.snapshot(policy=PulsePolicy(window_minutes=60))
        self.assertFalse(cutoff.suggestions)
        same_room = [
            self.report(f"repeat-{i}", "205", "stay", "Guest C",
                        "air_conditioning", minutes=i * 10)
            for i in range(3)
        ]
        repeated = self.snapshot(requests=same_room)
        self.assertEqual(repeated.suggestions[0].kind, "repeated_room_issue")

    def test_closed_or_sensitive_tickets_do_not_leak_into_pulse(self):
        closed = [dict(row) for row in self.reports]
        closed[0]["status"] = "cancelled"
        closed[0]["cancelled_at"] = closed[0]["updated_at"]
        validate_request(closed[0])
        self.assertEqual(self.snapshot(requests=closed).suggestions, ())
        sensitive = [dict(row) for row in self.reports]
        sensitive[0]["sensitive"] = True
        self.assertFalse(self.snapshot(requests=sensitive).suggestions)
        result = self.snapshot(requests=sensitive, as_of="2026-11-06T14:01:00+01:00")
        self.assertNotIn(sensitive[0]["request_id"],
                         {item.request_id for item in result.overdue})

    def test_overdue_acknowledgement_and_resolution_on_read(self):
        before_deadline = self.snapshot(
            requests=self.reports[:1], as_of="2026-11-06T10:20:00+01:00",
        )
        self.assertEqual(before_deadline.overdue, ())
        ack_overdue = self.snapshot(
            requests=self.reports[:1], as_of="2026-11-06T10:31:00+01:00",
        )
        self.assertEqual(len(ack_overdue.overdue), 1)
        alert = ack_overdue.overdue[0]
        self.assertTrue(alert.acknowledgement_overdue)
        self.assertFalse(alert.resolution_overdue)
        self.assertTrue(alert.requires_staff_review)
        self.assertFalse(alert.escalation_sent)
        due = self.snapshot(
            requests=self.reports[:1], as_of="2026-11-06T14:01:00+01:00",
        )
        self.assertTrue(due.overdue[0].resolution_overdue)
        grace = self.snapshot(
            requests=self.reports[:1], as_of="2026-11-06T10:31:00+01:00",
            policy=PulsePolicy(acknowledgement_grace_minutes=10),
        )
        self.assertEqual(grace.overdue, ())

    def test_acknowledged_ticket_not_misclassified_as_unacknowledged(self):
        report = dict(self.reports[0])
        report.update(
            status="acknowledged", assigned_staff_id="synthetic-staff",
            assigned_at="2026-11-06T10:05:00+01:00",
            acknowledged_at="2026-11-06T10:15:00+01:00",
            updated_at="2026-11-06T10:15:00+01:00",
        )
        validate_request(report)
        pulse = self.snapshot(
            requests=[report], as_of="2026-11-06T10:40:00+01:00",
        )
        self.assertEqual(pulse.overdue, ())
        overdue = self.snapshot(
            requests=[report], as_of="2026-11-06T14:01:00+01:00",
        )
        self.assertTrue(overdue.overdue[0].resolution_overdue)
        self.assertFalse(overdue.overdue[0].acknowledgement_overdue)

    def test_reopened_ticket_does_not_reuse_old_ack_deadline_as_fresh(self):
        report = dict(self.reports[0])
        report.update(
            status="reopened", reopened_at="2026-11-06T13:00:00+01:00",
            updated_at="2026-11-06T13:00:00+01:00",
        )
        validate_request(report)
        pulse = self.snapshot(
            requests=[report], as_of="2026-11-06T14:01:00+01:00",
        )
        self.assertTrue(pulse.overdue[0].resolution_overdue)
        self.assertFalse(pulse.overdue[0].acknowledgement_overdue)

    def test_fail_closed_for_untrusted_roles_cross_business_hotel_and_stale_data(self):
        for changes, reason in (
            ({"actor_role": "guest"}, "management_authorization_required"),
            ({"actor_role": "receptionist"}, "management_authorization_required"),
            ({"authorization_verified": False}, "management_authorization_required"),
            ({"snapshot_business_id": uid("other-business")}, "wrong_business"),
            ({"snapshot_hotel_id": uid("other-hotel")}, "wrong_hotel"),
            ({"snapshot_fresh": False}, "complete_fresh_request_snapshot_required"),
            ({"requests_complete": False}, "complete_fresh_request_snapshot_required"),
        ):
            with self.subTest(changes=changes), self.assertRaisesRegex(
                    PulseRejected, reason):
                self.snapshot(context=replace(self.context, **changes))

    def test_bad_request_inputs_are_rejected_not_silently_dropped(self):
        wrong_hotel = [dict(row) for row in self.reports]
        wrong_hotel[0]["hotel_id"] = uid("foreign-hotel")
        with self.assertRaisesRegex(PulseRejected, "wrong_hotel_request"):
            self.snapshot(requests=wrong_hotel)
        duplicate = self.reports + [dict(self.reports[0])]
        with self.assertRaisesRegex(PulseRejected, "duplicate_pulse_request"):
            self.snapshot(requests=duplicate)
        missing_room = [dict(row) for row in self.reports]
        missing_room[0]["room_id"] = uid("unknown-room")
        with self.assertRaisesRegex(PulseRejected, "unknown_request_room_or_stay"):
            self.snapshot(requests=missing_room)
        future = [dict(row) for row in self.reports]
        future[0]["updated_at"] = "2026-11-07T00:00:00+01:00"
        with self.assertRaisesRegex(PulseRejected, "future_pulse_request"):
            self.snapshot(requests=future)
        with self.assertRaisesRegex(PulseRejected, "complete_fresh_request_snapshot_required"):
            self.snapshot(requests=())
        invalid_hotel = dict(self.hotel)
        del invalid_hotel["rooms"]
        with self.assertRaisesRegex(PulseRejected, "invalid_or_incomplete_pulse_snapshot"):
            build_pulse_snapshot(
                invalid_hotel, [], context=self.context,
                as_of="2026-11-06T12:30:00+01:00",
            )

    def test_invalid_policy_or_bad_time_fails_closed(self):
        for policy in (
            PulsePolicy(min_complaints=1),
            PulsePolicy(min_complaints=True),
            PulsePolicy(window_minutes=0),
            PulsePolicy(window_minutes=2000),
            PulsePolicy(resolution_grace_minutes=-1),
        ):
            with self.subTest(policy=policy), self.assertRaisesRegex(
                    PulseRejected, "invalid_pulse_policy"):
                self.snapshot(policy=policy)
        with self.assertRaisesRegex(PulseRejected, "invalid_or_incomplete_pulse_snapshot"):
            self.snapshot(as_of="2026-11-06T12:30:00")

    def test_manager_review_is_unpersisted_audit_intent(self):
        pulse = self.snapshot()
        suggestion = pulse.suggestions[0]
        first = prepare_pulse_review(
            pulse, suggestion_id=suggestion.suggestion_id, action="accept",
            notes="Investigate possible shared cooling fault",
            context=self.context, idempotency_key="pulse-review-00001",
        )
        self.assertFalse(first.persisted)
        self.assertTrue(first.requires_committed_audit)
        self.assertTrue(first.requires_authoritative_guard)
        self.assertEqual(first.audit_intent["request_ids"], suggestion.request_ids)
        self.assertEqual(first.audit_intent["actor_id"], self.context.actor_id)
        self.assertEqual(first.audit_intent["action"], "accept")
        self.assertEqual(len(self.snapshot().suggestions), 1)
        other = prepare_pulse_review(
            pulse, suggestion_id=suggestion.suggestion_id, action="dismiss",
            notes="False pattern; unrelated room events",
            context=self.context, idempotency_key="pulse-review-00002",
        )
        self.assertEqual(other.action, "dismiss")

    def test_review_authority_and_replay_denial(self):
        pulse = self.snapshot()
        suggestion_id = pulse.suggestions[0].suggestion_id
        kwargs = dict(
            pulse=pulse, suggestion_id=suggestion_id, action="accept",
            notes="Review cooling complaints", context=self.context,
            idempotency_key="pulse-review-00001",
        )
        plan = prepare_pulse_review(**kwargs)
        prior = {
            "idempotency_key": plan.idempotency_key,
            "operation_id": plan.operation_id,
            "operation_signature": plan.operation_signature,
        }
        with self.assertRaisesRegex(PulseRejected, "operation_already_attempted_readback_required"):
            prepare_pulse_review(**kwargs, prior_operation=prior)
        with self.assertRaisesRegex(PulseRejected, "idempotency_key_reused_for_different_review"):
            prepare_pulse_review(**dict(kwargs, action="dismiss"), prior_operation=prior)
        for change, reason in (
            ({"actor_role": "guest"}, "management_authorization_required"),
            ({"snapshot_business_id": uid("wrong")}, "wrong_business"),
            ({"requests_complete": False}, "complete_fresh_request_snapshot_required"),
        ):
            with self.subTest(change=change), self.assertRaisesRegex(
                    PulseRejected, reason):
                prepare_pulse_review(
                    **dict(kwargs, context=replace(self.context, **change)),
                )
        for changes, reason in (
            ({"action": "block_floor"}, "invalid_incident_review_action"),
            ({"notes": ""}, "incident_review_notes_required"),
            ({"suggestion_id": uid("unknown")}, "unknown_incident_suggestion"),
            ({"idempotency_key": "short"}, "invalid_idempotency_key"),
        ):
            with self.subTest(changes=changes), self.assertRaisesRegex(
                    PulseRejected, reason):
                prepare_pulse_review(**dict(kwargs, **changes))


if __name__ == "__main__":
    import unittest
    unittest.main()
