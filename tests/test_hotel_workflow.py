"""Cross-workflow hotel regression coverage using in-memory synthetic records.

The assignments below only model observed command results inside a test copy.
They are not Roomay persistence commands and never call Workpeg.
"""
import unittest
from copy import deepcopy
from datetime import timedelta, timezone
from unittest.mock import patch

from domain.access_control import (
    AccessContext,
    AccessDenied,
    authorize_access,
    project_guest_profile,
)
from domain.checkout_commands import OperationContext, prepare_checkout
from domain.fixtures import synthetic_hotel, uid
from domain.hotel import room_eligibility, validate_snapshot
from domain.reception import build_reception_snapshot
from domain.reservation_commands import (
    ReservationRejected,
    WriteContext,
    prepare_authorized_room_confirmation,
    prepare_booking_request,
    prepare_check_in,
    reconcile_check_in_readback,
)
from domain.service_requests import (
    AuthorizationError,
    ConflictError,
    create_request,
    request_view,
    transition_request,
    validate_request,
)


BUSINESS_ID = uid("workflow-business")
HOTEL_ID = uid("workflow-hotel")
GUEST_ID = uid("Guest A")


class HotelWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.hotel = synthetic_hotel()
        self.context = WriteContext(
            business_id=BUSINESS_ID, snapshot_business_id=BUSINESS_ID,
            actor_id=uid("workflow-receptionist"), actor_role="receptionist",
            authorization_verified=True, snapshot_fresh=True,
            serialization_guard_held=True,
            authoritative_now="2026-11-06T16:00:00+01:00",
        )
        self.staff = [
            self.staff_record("front", "reception"),
            self.staff_record("engineer", "maintenance"),
            self.staff_record("housekeeper", "housekeeping"),
        ]

    @staticmethod
    def staff_record(actor_id, department):
        return {"actor_id": actor_id, "hotel_id": HOTEL_ID,
                "department": department, "roles": [], "active": True}

    @staticmethod
    def staff_actor(actor_id):
        return {"actor_id": actor_id, "hotel_id": HOTEL_ID, "kind": "staff"}

    def booking_request(self, snapshot, *, key, guest_id=GUEST_ID,
                        arrival="2026-11-06", departure="2026-11-08"):
        return prepare_booking_request(
            snapshot, idempotency_key=key, guest_id=guest_id,
            room_type_id=uid("standard"), arrival=arrival, departure=departure,
            party_size=1, source="advance",
        )

    def append_pending_request(self, snapshot, *, key, guest_id=GUEST_ID,
                               arrival="2026-11-20", departure="2026-11-22"):
        plan = self.booking_request(
            snapshot, key=key, guest_id=guest_id,
            arrival=arrival, departure=departure,
        )
        self.assertEqual(plan.action, "create_pending_request")
        snapshot["reservations"].append(deepcopy(plan.record))
        return plan

    def test_guest_request_to_checked_in_guest_service_lifecycle(self):
        original = deepcopy(self.hotel)
        request_plan = self.booking_request(
            self.hotel, key="workflow-booking-request-001",
        )
        self.assertEqual(request_plan.record["status"], "pending_confirmation")
        self.assertNotIn("room_id", request_plan.record)
        self.assertFalse(request_plan.persisted)
        self.assertEqual(self.hotel, original)

        # Test-only observation of a proposed request in an isolated snapshot.
        self.hotel["reservations"].append(deepcopy(request_plan.record))
        duplicate = self.booking_request(
            self.hotel, key="workflow-booking-request-001",
        )
        self.assertEqual(duplicate.action, "already_requested")
        self.assertFalse(duplicate.persisted)

        reservation_id = request_plan.reservation_id
        confirmation = prepare_authorized_room_confirmation(
            self.hotel, reservation_id=reservation_id,
            room_id=uid("204"), context=self.context,
        )
        self.assertFalse(confirmation.persisted)
        self.assertEqual(confirmation.record["status"], "confirmed")

        # A test snapshot reflects the confirmation plan; no database is used.
        reservation_index = next(
            i for i, row in enumerate(self.hotel["reservations"])
            if row["entity_id"] == reservation_id
        )
        self.hotel["reservations"][reservation_index] = deepcopy(confirmation.record)
        self.assertEqual(room_eligibility(
            self.hotel, reservation_id, uid("204")), ())
        self.assertIn("confirmed_reservation_assigned_elsewhere", room_eligibility(
            self.hotel, reservation_id, uid("206")))
        timezone_stub = timezone(timedelta(hours=1), name="synthetic Lagos offset")
        with patch("domain.reservation_commands.ZoneInfo", return_value=timezone_stub):
            check_in = prepare_check_in(
                self.hotel, reservation_id=reservation_id,
                occupant_guest_ids=[GUEST_ID],
                checked_in_at="2026-11-06T15:00:00+01:00",
                today="2026-11-06", hotel_timezone="Africa/Lagos",
                idempotency_key="workflow-check-in-attempt-0001",
                context=self.context,
            )
            self.assertFalse(check_in.persisted)
            self.hotel["stays"].append(deepcopy(check_in.stay_record))
            self.hotel["stay_guests"].extend(deepcopy(check_in.occupant_records))
            validate_snapshot(self.hotel)

            duplicate_check_in = prepare_check_in(
                self.hotel, reservation_id=reservation_id,
                occupant_guest_ids=[GUEST_ID],
                checked_in_at="2026-11-06T15:00:00+01:00",
                today="2026-11-06", hotel_timezone="Africa/Lagos",
                idempotency_key="workflow-check-in-attempt-0001",
                context=self.context,
            )
            self.assertEqual(duplicate_check_in.action, "already_checked_in")
            with self.assertRaisesRegex(
                    ReservationRejected, "reservation_already_used_or_idempotency_conflict"):
                prepare_check_in(
                    self.hotel, reservation_id=reservation_id,
                    occupant_guest_ids=[GUEST_ID],
                    checked_in_at="2026-11-06T15:00:00+01:00",
                    today="2026-11-06", hotel_timezone="Africa/Lagos",
                    idempotency_key="workflow-check-in-attempt-0002",
                    context=self.context,
                )

            guest_context = AccessContext(
                actor_id="guest-session-a", business_id=BUSINESS_ID,
                hotel_id=HOTEL_ID, role="guest", authenticated=True,
                membership_verified=True, business_binding_verified=True,
                guest_id=GUEST_ID,
            )
            profile = project_guest_profile(
                guest_context, business_id=BUSINESS_ID,
                record_business_id=BUSINESS_ID, snapshot=self.hotel,
                guest_id=GUEST_ID, trusted_snapshot_hotel_id=HOTEL_ID,
            )
            self.assertEqual(profile["entity_id"], GUEST_ID)

            guest_actor = {
                "actor_id": "guest-session-a", "hotel_id": HOTEL_ID,
                "kind": "guest", "guest_id": GUEST_ID,
            }
            draft = {
                "hotel_id": HOTEL_ID, "stay_id": check_in.stay_record["entity_id"],
                "room_id": uid("204"), "guest_id": GUEST_ID,
                "origin": "guest", "category": "plumbing",
                "description": "Synthetic workflow request for a leaking tap.",
                "urgency": "normal", "idempotency_key": "workflow-request-0001",
                "sensitive": False,
            }
            created = create_request(
                self.hotel, draft, guest_actor, self.staff, [],
                at="2026-11-06T16:30:00+01:00",
                request_id=uid("workflow-service-request"),
            )
            self.assertEqual(created["request"]["status"], "received")
            self.assertEqual(created["request"]["department"], "maintenance")

            # Feed each pure transition result into test-local state so later
            # commands can be exercised. This is not persistence or a commit.
            request = created["request"]
            audit_events = [deepcopy(created["plan"]["event"])]
            transitions = [
                ("assigned", "front", "2026-11-06T17:00:00+01:00",
                 {"assignee_id": "engineer"}),
                ("acknowledged", "engineer", "2026-11-06T17:15:00+01:00", {}),
                ("in_progress", "engineer", "2026-11-06T17:30:00+01:00", {}),
                ("resolved", "engineer", "2026-11-06T18:00:00+01:00", {}),
            ]
            for index, (target, actor_id, occurred, options) in enumerate(transitions):
                outcome = transition_request(
                    request, target, self.staff_actor(actor_id), self.staff,
                    at=occurred, operation_key=f"workflow-transition-{index}",
                    **options,
                )
                self.assertEqual(outcome["kind"], "transitioned")
                request = outcome["request"]
                audit_events.append(deepcopy(outcome["plan"]["event"]))
                validate_request(request)
            self.assertEqual(request["status"], "resolved")
            self.assertEqual([event["to_status"] for event in audit_events], [
                "received", "assigned", "acknowledged", "in_progress", "resolved",
            ])
            self.assertTrue(all(event["commit_state"] == "pending" for event in audit_events))

            reception = build_reception_snapshot(
                self.hotel, [request], today="2026-11-06",
            )
            room_card = next(row for row in reception["rooms"] if row["number"] == "204")
            self.assertEqual(room_card["occupancy"], "In house")
            self.assertEqual(reception["metrics"]["in_house"], 2)
            self.assertEqual(reception["requests"][0]["status"], "resolved")

            overdue_reception = build_reception_snapshot(
                self.hotel, [request], today="2026-11-09",
            )
            overdue_room = next(
                row for row in overdue_reception["rooms"] if row["number"] == "204"
            )
            self.assertEqual(overdue_room["occupancy"], "In house")
            overdue_guest = next(
                row for row in overdue_reception["in_house"] if row["room"] == "204"
            )
            self.assertEqual(overdue_guest["departure_status"], "OVERDUE")
            self.assertEqual(overdue_reception["departures"], [])
            self.assertEqual(check_in.stay_record["status"], "checked_in")

            guest_view = request_view(
                request, guest_actor, self.staff, snapshot=self.hotel,
            )
            self.assertEqual(guest_view["guest_id"], GUEST_ID)
            other_guest = dict(guest_actor, guest_id=uid("Guest B"))
            with self.assertRaisesRegex(AuthorizationError, "cross_guest_access"):
                request_view(request, other_guest, self.staff, snapshot=self.hotel)

        self.assertEqual(len(self.hotel["stays"]), 2)
        self.assertEqual(len(self.hotel["stay_guests"]), 2)
        self.assertTrue(all(plan.persisted is False for plan in (request_plan, confirmation, check_in)))

    def test_checkout_changes_physical_occupancy_only_in_test_copy_and_leaves_room_dirty(self):
        hotel = synthetic_hotel()
        original = deepcopy(hotel)
        context = OperationContext(
            business_id=BUSINESS_ID, snapshot_business_id=BUSINESS_ID,
            hotel_id=HOTEL_ID, snapshot_hotel_id=HOTEL_ID,
            actor_id=uid("workflow-checkout-reception"), actor_role="receptionist",
            authorization_verified=True, snapshot_fresh=True,
            serialization_guard_held=True,
            authoritative_now="2026-11-09T10:00:00+01:00",
        )
        with patch("domain.checkout_commands.ZoneInfo",
                   return_value=timezone(timedelta(hours=1))):
            plan = prepare_checkout(
                hotel, stay_id=uid("stay"),
                checked_out_at="2026-11-09T09:00:00+01:00",
                today="2026-11-09", hotel_timezone="Africa/Lagos",
                idempotency_key="workflow-checkout-op-0001", context=context,
            )

        test_copy = deepcopy(hotel)
        test_copy["stays"] = [
            plan.stay_after if row["entity_id"] == plan.stay_id else row
            for row in test_copy["stays"]
        ]
        test_copy["stay_guests"] = [
            next((after for after in plan.occupants_after
                  if after["entity_id"] == row["entity_id"]), row)
            for row in test_copy["stay_guests"]
        ]
        test_copy["rooms"] = [
            plan.room_after if row["entity_id"] == plan.room_id else row
            for row in test_copy["rooms"]
        ]
        validate_snapshot(test_copy)
        stay = next(row for row in test_copy["stays"] if row["entity_id"] == plan.stay_id)
        room = next(row for row in test_copy["rooms"] if row["entity_id"] == plan.room_id)
        occupant = next(row for row in test_copy["stay_guests"]
                        if row["entity_id"] == uid("occupant"))
        self.assertEqual(stay["status"], "checked_out")
        self.assertEqual(occupant["left_at"], stay["checked_out_at"])
        self.assertEqual(room["housekeeping"], "dirty")
        self.assertFalse(any(
            row["room_id"] == plan.room_id and row["status"] == "checked_in"
            for row in test_copy["stays"]
        ))
        self.assertEqual(test_copy["reservations"], hotel["reservations"])
        self.assertEqual(test_copy["room_blocks"], hotel["room_blocks"])
        self.assertEqual(hotel, original)
        self.assertEqual(hotel["stays"][0]["status"], "checked_in")
        self.assertFalse(plan.persisted)

    def test_duplicate_and_overlapping_reservations_are_rejected_safely(self):
        first = self.append_pending_request(
            self.hotel, key="workflow-overlap-request-001", guest_id=uid("Guest A"),
        )
        second = self.append_pending_request(
            self.hotel, key="workflow-overlap-request-002", guest_id=uid("Guest B"),
        )
        retry = self.booking_request(
            self.hotel, key="workflow-overlap-request-001",
            arrival="2026-11-20", departure="2026-11-22",
        )
        self.assertEqual(retry.action, "already_requested")

        confirmed = prepare_authorized_room_confirmation(
            self.hotel, reservation_id=first.reservation_id,
            room_id=uid("204"), context=self.context,
        )
        self.hotel["reservations"] = [
            confirmed.record if row["entity_id"] == first.reservation_id else row
            for row in self.hotel["reservations"]
        ]
        with self.assertRaisesRegex(ReservationRejected, "reservation_overlap"):
            prepare_authorized_room_confirmation(
                self.hotel, reservation_id=second.reservation_id,
                room_id=uid("204"), context=self.context,
            )

    def test_room_occupancy_housekeeping_disabled_and_maintenance_gates(self):
        occupied_candidate = self.append_pending_request(
            self.hotel, key="workflow-occupied-request-001",
            arrival="2026-11-06", departure="2026-11-08",
        )
        with self.assertRaises(ReservationRejected) as occupied:
            prepare_authorized_room_confirmation(
                self.hotel, reservation_id=occupied_candidate.reservation_id,
                room_id=uid("205"), context=self.context,
            )
        self.assertIn("occupied", occupied.exception.reasons)

        dirty_candidate = self.append_pending_request(
            self.hotel, key="workflow-dirty-request-001",
        )
        dirty_assignment = prepare_authorized_room_confirmation(
            self.hotel, reservation_id=dirty_candidate.reservation_id,
            room_id=uid("203"), context=self.context,
        )
        self.hotel["reservations"] = [
            dirty_assignment.record if row["entity_id"] == dirty_candidate.reservation_id else row
            for row in self.hotel["reservations"]
        ]
        later_context = WriteContext(**{
            **self.context.__dict__,
            "authoritative_now": "2026-11-21T16:00:00+01:00",
        })
        with patch("domain.reservation_commands.ZoneInfo",
                   return_value=timezone(timedelta(hours=1))):
            with self.assertRaisesRegex(ReservationRejected, "housekeeping_not_ready"):
                prepare_check_in(
                    self.hotel, reservation_id=dirty_candidate.reservation_id,
                    occupant_guest_ids=[GUEST_ID],
                    checked_in_at="2026-11-21T15:00:00+01:00",
                    today="2026-11-21", hotel_timezone="Africa/Lagos",
                    idempotency_key="workflow-dirty-checkin-0001",
                    context=later_context,
                )

        disabled_hotel = synthetic_hotel()
        disabled_hotel["rooms"][5]["enabled"] = False  # room 206
        disabled_candidate = self.append_pending_request(
            disabled_hotel, key="workflow-disabled-request-001",
        )
        with self.assertRaisesRegex(ReservationRejected, "room_disabled"):
            prepare_authorized_room_confirmation(
                disabled_hotel, reservation_id=disabled_candidate.reservation_id,
                room_id=uid("206"), context=self.context,
            )

        blocked_hotel = synthetic_hotel()
        blocked_candidate = self.append_pending_request(
            blocked_hotel, key="workflow-blocked-request-001",
        )
        before_block = room_eligibility(
            blocked_hotel, blocked_candidate.reservation_id, uid("206"),
        )
        self.assertEqual(before_block, ())
        blocked_hotel["room_blocks"].append({
            "entity_id": uid("workflow-maintenance-block"),
            "room_id": uid("206"), "start": "2026-11-20", "end": "2026-11-22",
            "reason": "Synthetic maintenance regression", "status": "active",
        })
        validate_snapshot(blocked_hotel)
        with self.assertRaisesRegex(ReservationRejected, "maintenance_block"):
            prepare_authorized_room_confirmation(
                blocked_hotel, reservation_id=blocked_candidate.reservation_id,
                room_id=uid("206"), context=self.context,
            )

    def test_stale_wrong_business_and_invalid_service_transitions_fail_closed(self):
        candidate = self.append_pending_request(
            self.hotel, key="workflow-authorization-request-001",
        )
        stale = WriteContext(**{**self.context.__dict__, "snapshot_fresh": False})
        with self.assertRaisesRegex(ReservationRejected, "stale_snapshot"):
            prepare_authorized_room_confirmation(
                self.hotel, reservation_id=candidate.reservation_id,
                room_id=uid("204"), context=stale,
            )
        wrong_business = WriteContext(**{
            **self.context.__dict__, "business_id": uid("other-business"),
        })
        with self.assertRaisesRegex(ReservationRejected, "wrong_business"):
            prepare_authorized_room_confirmation(
                self.hotel, reservation_id=candidate.reservation_id,
                room_id=uid("204"), context=wrong_business,
            )
        unauthorized = WriteContext(**{
            **self.context.__dict__, "authorization_verified": False,
        })
        with self.assertRaisesRegex(ReservationRejected, "authorized_staff_required"):
            prepare_authorized_room_confirmation(
                self.hotel, reservation_id=candidate.reservation_id,
                room_id=uid("204"), context=unauthorized,
            )

        guest_context = AccessContext(
            actor_id="guest-session", business_id=BUSINESS_ID,
            hotel_id=HOTEL_ID, role="guest", authenticated=True,
            membership_verified=True, business_binding_verified=True,
            guest_id=GUEST_ID,
        )
        with self.assertRaisesRegex(AccessDenied, "wrong_business"):
            authorize_access(
                guest_context, business_id=BUSINESS_ID,
                record_business_id=uid("other-business"),
                resource="guest_profile", action="read", record_guest_id=GUEST_ID,
            )

        guest_actor = {
            "actor_id": "guest-session", "hotel_id": HOTEL_ID,
            "kind": "guest", "guest_id": GUEST_ID,
        }
        request_result = create_request(
            self.hotel,
            {"hotel_id": HOTEL_ID, "stay_id": uid("stay"), "room_id": uid("205"),
             "guest_id": uid("Guest C"), "origin": "guest", "category": "plumbing",
             "description": "Synthetic request", "urgency": "normal",
             "idempotency_key": "workflow-invalid-transition-0001", "sensitive": False},
            {**guest_actor, "guest_id": uid("Guest C")}, self.staff, [],
            at="2026-11-06T16:00:00+01:00", request_id=uid("workflow-invalid-request"),
        )
        with self.assertRaisesRegex(ConflictError, "invalid_status_transition"):
            transition_request(
                request_result["request"], "resolved", self.staff_actor("engineer"),
                self.staff, at="2026-11-06T16:30:00+01:00",
                operation_key="workflow-illegal-resolve-0001",
            )

    def test_check_in_plan_readback_is_not_a_persistence_claim(self):
        candidate = self.append_pending_request(
            self.hotel, key="workflow-readback-request-001",
        )
        confirmed = prepare_authorized_room_confirmation(
            self.hotel, reservation_id=candidate.reservation_id,
            room_id=uid("204"), context=self.context,
        )
        self.hotel["reservations"] = [
            confirmed.record if row["entity_id"] == candidate.reservation_id else row
            for row in self.hotel["reservations"]
        ]
        later_context = WriteContext(**{
            **self.context.__dict__,
            "authoritative_now": "2026-11-21T16:00:00+01:00",
        })
        with patch("domain.reservation_commands.ZoneInfo",
                   return_value=timezone(timedelta(hours=1))):
            check_in = prepare_check_in(
                self.hotel, reservation_id=candidate.reservation_id,
                occupant_guest_ids=[GUEST_ID],
                checked_in_at="2026-11-21T15:00:00+01:00",
                today="2026-11-21", hotel_timezone="Africa/Lagos",
                idempotency_key="workflow-readback-checkin-0001",
                context=later_context,
            )
        self.assertEqual(reconcile_check_in_readback(
            check_in, self.hotel, context=later_context,
        ), "rows_absent_retry_only_under_held_guard")
        self.assertFalse(check_in.persisted)


if __name__ == "__main__":
    unittest.main()
