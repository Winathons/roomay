"""WOR-23 synthetic acceptance: one connected, OFFLINE planning-only journey.

This uses the real domain contracts over a private in-memory fixture. The
synthetic identities/guards cannot prove Workpeg OIDC, durable persistence,
cross-refresh visibility, atomic hotel writes, telephony, or notifications.
"""
from copy import deepcopy
from datetime import timedelta, timezone
from unittest import TestCase
from unittest.mock import patch

from domain.access_control import AccessContext, AccessDenied, authorize_access
from domain.checkout_commands import OperationContext, prepare_checkout
from domain.fixtures import synthetic_hotel, uid
from domain.hotel import room_eligibility, validate_snapshot
from domain.reception import build_reception_snapshot
from domain.reservation_commands import (
    ReservationRejected, WriteContext, prepare_authorized_room_confirmation,
    prepare_booking_request, prepare_check_in, prepare_walk_in_request,
)
from domain.service_requests import (
    AuthorizationError, create_request, reconcile_write, request_view,
    transition_request,
)


BUSINESS_ID = uid("wor23-business")
HOTEL_ID = uid("wor23-hotel")
GUEST_ID = uid("Guest A")
ROOM_ID = uid("204")
TIMEZONE = timezone(timedelta(hours=1), name="synthetic UTC+01:00")


class SyntheticAcceptanceJourney(TestCase):
    def setUp(self):
        hotel = synthetic_hotel()
        # Eight rooms / two types, with an existing active stay, future
        # reservation, dirty room and maintenance block.
        hotel["rooms"] = [r for r in hotel["rooms"] if int(r["number"]) <= 208]
        validate_snapshot(hotel)
        self.hotel = hotel
        self.untouched_fixture = deepcopy(hotel)
        self.write_context = WriteContext(
            business_id=BUSINESS_ID, snapshot_business_id=BUSINESS_ID,
            actor_id=uid("wor23-reception"), actor_role="receptionist",
            authorization_verified=True, snapshot_fresh=True,
            serialization_guard_held=True,
            authoritative_now="2026-11-06T16:00:00+01:00",
        )
        self.directory = [
            {"actor_id": "front", "hotel_id": HOTEL_ID,
             "department": "reception", "roles": [], "active": True},
            {"actor_id": "maintenance", "hotel_id": HOTEL_ID,
             "department": "maintenance", "roles": [], "active": True},
            {"actor_id": "housekeeper", "hotel_id": HOTEL_ID,
             "department": "housekeeping", "roles": [], "active": True},
        ]

    @staticmethod
    def staff_actor(actor):
        return {"actor_id": actor, "hotel_id": HOTEL_ID, "kind": "staff"}

    @staticmethod
    def guest_actor(guest_id=GUEST_ID):
        return {"actor_id": "synthetic-guest-session", "hotel_id": HOTEL_ID,
                "kind": "guest", "guest_id": guest_id}

    def test_connected_walkin_ac_maintenance_alternative_and_checkout_plan(self):
        hotel = self.hotel
        self.assertEqual(len(hotel["rooms"]), 8)
        self.assertEqual(len(hotel["room_types"]), 2)
        self.assertEqual(len(hotel["stays"]), 1)
        self.assertEqual(next(r for r in hotel["rooms"]
                              if r["number"] == "203")["housekeeping"], "dirty")
        self.assertEqual(len(hotel["room_blocks"]), 1)

        # Walk-in creates an UNCOMMITTED pending reservation; there is no stay.
        walkin = prepare_walk_in_request(
            hotel, idempotency_key="wor23-walkin-001", guest_id=GUEST_ID,
            room_type_id=uid("standard"), arrival="2026-11-06",
            departure="2026-11-08", party_size=1, context=self.write_context,
        )
        self.assertFalse(walkin.persisted)
        self.assertEqual(walkin.record["source"], "walk_in")
        self.assertEqual(walkin.record["status"], "pending_confirmation")
        self.assertNotIn("room_id", walkin.record)
        self.assertEqual(len(hotel["stays"]), 1)
        hotel["reservations"].append(deepcopy(walkin.record))

        # This is a proposed confirmation, not a Workpeg table write.
        confirmation = prepare_authorized_room_confirmation(
            hotel, reservation_id=walkin.reservation_id, room_id=ROOM_ID,
            context=self.write_context,
        )
        self.assertFalse(confirmation.persisted)
        hotel["reservations"] = [
            deepcopy(confirmation.record)
            if r["entity_id"] == walkin.reservation_id else r
            for r in hotel["reservations"]
        ]
        self.assertEqual(room_eligibility(
            hotel, walkin.reservation_id, ROOM_ID,
            check_in=True, today="2026-11-06", staff_approved=True,
        ), ())

        with patch("domain.reservation_commands.ZoneInfo", return_value=TIMEZONE):
            checkin = prepare_check_in(
                hotel, reservation_id=walkin.reservation_id,
                occupant_guest_ids=[GUEST_ID],
                checked_in_at="2026-11-06T15:00:00+01:00",
                today="2026-11-06", hotel_timezone="Africa/Lagos",
                idempotency_key="wor23-checkin-001", context=self.write_context,
            )
        self.assertFalse(checkin.persisted)
        hotel["stays"].append(deepcopy(checkin.stay_record))
        hotel["stay_guests"].extend(deepcopy(checkin.occupant_records))
        validate_snapshot(hotel)
        self.assertEqual(build_reception_snapshot(
            hotel, [], today="2026-11-06",
        )["metrics"]["in_house"], 2)

        # Guest AC request plans a ticket and pending audit. No notification
        # or AI provider is called; pending != committed or staff notified.
        request_draft = {
            "hotel_id": HOTEL_ID, "stay_id": checkin.stay_record["entity_id"],
            "room_id": ROOM_ID, "guest_id": GUEST_ID,
            "origin": "guest", "category": "air_conditioning",
            "description": "Synthetic AC is not cooling.",
            "urgency": "normal", "idempotency_key": "wor23-ac-001",
            "sensitive": False,
        }
        created = create_request(
            hotel, request_draft, self.guest_actor(), self.directory, [],
            at="2026-11-06T16:05:00+01:00",
            request_id=uid("wor23-ac-ticket"),
        )
        self.assertEqual(created["kind"], "created")
        self.assertEqual(created["request"]["department"], "maintenance")
        self.assertEqual(created["plan"]["event"]["commit_state"], "pending")
        self.assertEqual(reconcile_write(created["plan"], None, []),
                         "append_pending_event")
        replay = create_request(
            hotel, request_draft, self.guest_actor(), self.directory,
            [created["request"]], at="2026-11-06T16:10:00+01:00",
            request_id=uid("wor23-ignored-retry"),
        )
        self.assertEqual(replay["kind"], "duplicate")
        self.assertIsNone(replay["plan"])
        with self.assertRaisesRegex(AuthorizationError, "cross_guest_access"):
            request_view(created["request"], self.guest_actor(uid("Guest B")),
                         self.directory, snapshot=hotel)

        request = created["request"]
        events = [deepcopy(created["plan"]["event"])]
        for status, actor_id, at, extra in (
            ("assigned", "front", "2026-11-06T16:20:00+01:00",
             {"assignee_id": "maintenance"}),
            ("acknowledged", "maintenance", "2026-11-06T16:50:00+01:00", {}),
            ("in_progress", "maintenance", "2026-11-06T17:00:00+01:00", {}),
            ("resolved", "maintenance", "2026-11-06T18:00:00+01:00", {}),
        ):
            transition = transition_request(
                request, status, self.staff_actor(actor_id), self.directory,
                at=at, operation_key="wor23-transition-" + status, **extra,
            )
            self.assertEqual(transition["kind"], "transitioned")
            self.assertEqual(transition["plan"]["event"]["actor_id"], actor_id)
            self.assertEqual(transition["plan"]["event"]["to_status"], status)
            self.assertEqual(transition["plan"]["event"]["commit_state"], "pending")
            request = transition["request"]
            events.append(deepcopy(transition["plan"]["event"]))
        self.assertEqual(request["status"], "resolved")
        self.assertEqual(request["version"], 5)
        self.assertGreater(request["acknowledged_at"], request["acknowledge_by"])
        self.assertEqual([event["to_status"] for event in events], [
            "received", "assigned", "acknowledged", "in_progress", "resolved",
        ])
        self.assertEqual(request_view(
            request, self.guest_actor(), self.directory, snapshot=hotel,
        )["status"], "resolved")

        # Another future reservation cannot claim a newly blocked room. This
        # is local eligibility, not an atomic reservation/maintenance writer.
        candidate = prepare_booking_request(
            hotel, idempotency_key="wor23-alternative-001",
            guest_id=uid("Guest B"), room_type_id=uid("standard"),
            arrival="2026-11-20", departure="2026-11-22",
            party_size=1, source="advance",
        )
        self.assertFalse(candidate.persisted)
        hotel["reservations"].append(deepcopy(candidate.record))
        self.assertEqual(room_eligibility(
            hotel, candidate.reservation_id, uid("206"),
        ), ())
        hotel["room_blocks"].append({
            "entity_id": uid("wor23-block-206"), "room_id": uid("206"),
            "start": "2026-11-20", "end": "2026-11-22",
            "reason": "Synthetic AC maintenance", "status": "active",
        })
        validate_snapshot(hotel)
        with self.assertRaisesRegex(ReservationRejected, "maintenance_block"):
            prepare_authorized_room_confirmation(
                hotel, reservation_id=candidate.reservation_id,
                room_id=uid("206"), context=self.write_context,
            )
        alternative = prepare_authorized_room_confirmation(
            hotel, reservation_id=candidate.reservation_id,
            room_id=uid("202"), context=self.write_context,
        )
        self.assertFalse(alternative.persisted)
        self.assertEqual(alternative.record["room_id"], uid("202"))
        self.assertEqual(alternative.record["status"], "confirmed")
        # Alternate confirmation remains a proposal; do not pretend saved.

        # Checkout plans three distinct changes: stay, occupant and room dirty.
        # Apply only to an isolated copy, never an authoritative Workpeg record.
        checkout_context = OperationContext(
            business_id=BUSINESS_ID, snapshot_business_id=BUSINESS_ID,
            hotel_id=HOTEL_ID, snapshot_hotel_id=HOTEL_ID,
            actor_id=uid("wor23-reception"), actor_role="receptionist",
            authorization_verified=True, snapshot_fresh=True,
            serialization_guard_held=True,
            authoritative_now="2026-11-07T11:00:00+01:00",
        )
        with patch("domain.checkout_commands.ZoneInfo", return_value=TIMEZONE):
            checkout = prepare_checkout(
                hotel, stay_id=checkin.stay_record["entity_id"],
                checked_out_at="2026-11-07T10:00:00+01:00",
                today="2026-11-07", hotel_timezone="Africa/Lagos",
                idempotency_key="wor23-checkout-001",
                context=checkout_context,
            )
        self.assertFalse(checkout.persisted)
        after = deepcopy(hotel)
        after["stays"] = [
            deepcopy(checkout.stay_after) if s["entity_id"] == checkout.stay_id else s
            for s in after["stays"]
        ]
        after["stay_guests"] = [
            deepcopy(next((o for o in checkout.occupants_after
                           if o["entity_id"] == g["entity_id"]), g))
            for g in after["stay_guests"]
        ]
        after["rooms"] = [
            deepcopy(checkout.room_after) if r["entity_id"] == checkout.room_id else r
            for r in after["rooms"]
        ]
        validate_snapshot(after)
        self.assertEqual(checkout.room_after["housekeeping"], "dirty")
        self.assertEqual(checkout.stay_after["status"], "checked_out")
        self.assertEqual(next(o for o in after["stay_guests"]
                              if o["stay_id"] == checkout.stay_id)["left_at"],
                         checkout.stay_after["checked_out_at"])
        self.assertEqual(next(r for r in after["rooms"]
                              if r["entity_id"] == ROOM_ID)["housekeeping"], "dirty")
        self.assertEqual(next(s for s in hotel["stays"]
                              if s["entity_id"] == checkout.stay_id)["status"], "checked_in")
        self.assertEqual(self.untouched_fixture, self._original_fixture())

    @staticmethod
    def _original_fixture():
        snapshot = synthetic_hotel()
        snapshot["rooms"] = [
            r for r in snapshot["rooms"] if int(r["number"]) <= 208
        ]
        return snapshot

    def test_qr_room_number_and_wrong_business_are_not_guest_authorization(self):
        # An unverified URL/QR/caller has no trusted session. Staff-asserted
        # hotel and business values cannot turn that into membership.
        qr_only = AccessContext(
            actor_id="room-204-qr", business_id=BUSINESS_ID, hotel_id=HOTEL_ID,
            role="guest", authenticated=False,
            membership_verified=False, business_binding_verified=False,
            guest_id=GUEST_ID,
        )
        with self.assertRaises(AccessDenied):
            authorize_access(
                qr_only, business_id=BUSINESS_ID,
                record_business_id=BUSINESS_ID, resource="guest_profile",
                action="read", record_guest_id=GUEST_ID,
            )
        verified_guest = AccessContext(
            actor_id="synthetic-stay-verified", business_id=BUSINESS_ID,
            hotel_id=HOTEL_ID, role="guest", authenticated=True,
            membership_verified=True, business_binding_verified=True,
            guest_id=GUEST_ID,
        )
        with self.assertRaisesRegex(AccessDenied, "wrong_business"):
            authorize_access(
                verified_guest, business_id=BUSINESS_ID,
                record_business_id=uid("wrong-business"),
                resource="guest_profile", action="read", record_guest_id=GUEST_ID,
            )
        with self.assertRaisesRegex(AccessDenied, "guest_scope_denied"):
            authorize_access(
                verified_guest, business_id=BUSINESS_ID,
                record_business_id=BUSINESS_ID,
                resource="guest_profile", action="read",
                record_guest_id=uid("Guest B"),
            )


if __name__ == "__main__":
    import unittest
    unittest.main()
