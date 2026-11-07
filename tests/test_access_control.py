"""Offline access policy checks; no Workpeg identity or hosted permissions."""
import unittest
from copy import deepcopy

from domain.access_control import (
    AccessContext,
    AccessDenied,
    authorize_access,
    authorize_hotel_snapshot,
    project_guest_profile,
    project_room_inventory,
    project_service_request,
    safe_error_message,
    validate_hotel_snapshot,
)
from domain.fixtures import synthetic_hotel, uid
from domain.service_requests import create_request


class AccessControlContractTests(unittest.TestCase):
    def setUp(self):
        self.hotel = synthetic_hotel()
        self.business = uid("access-business")
        self.hotel_id = uid("access-hotel")
        self.guest_id = uid("Guest C")
        self.staff = [
            {"actor_id": "front", "hotel_id": self.hotel_id,
             "department": "reception", "roles": [], "active": True},
            {"actor_id": "housekeeper", "hotel_id": self.hotel_id,
             "department": "housekeeping", "roles": [], "active": True},
        ]
        guest_actor = {"actor_id": "guest-session", "hotel_id": self.hotel_id,
                       "kind": "guest", "guest_id": self.guest_id}
        draft = {
            "hotel_id": self.hotel_id, "stay_id": uid("stay"),
            "room_id": uid("205"), "guest_id": self.guest_id,
            "origin": "guest", "category": "extra_towels",
            "description": "Please bring two towels.", "urgency": "normal",
            "idempotency_key": "guest-session:request-1", "sensitive": False,
        }
        self.request = create_request(
            self.hotel, draft, guest_actor, self.staff, [],
            at="2026-11-06T12:00:00+01:00", request_id=uid("access-request"),
        )["request"]

    def context(self, role="receptionist", *, department=None, guest_id=None,
                authenticated=True, member=True, business_verified=True,
                privileges=()):
        return AccessContext(
            actor_id="actor-123", business_id=self.business,
            hotel_id=self.hotel_id, role=role,
            authenticated=authenticated, membership_verified=member,
            business_binding_verified=business_verified, department=department,
            guest_id=guest_id, privileges=privileges,
        )

    def authorize(self, context, *, resource="reservations", action="read",
                  business_id=None, record_business_id=None, **kwargs):
        return authorize_access(
            context, business_id=business_id or self.business,
            record_business_id=record_business_id or self.business,
            resource=resource, action=action, **kwargs,
        )

    def test_missing_invalid_and_unverified_authorization_context_fails_closed(self):
        for context, code in [
            (None, "authorization_context_missing"),
            (self.context(authenticated=False), "unauthenticated"),
            (self.context(member=False), "membership_unverified"),
            (self.context(business_verified=False), "business_binding_unverified"),
            (self.context(role="nonmember"), "not_hotel_member"),
            (self.context(role="department_staff"), "authorization_context_invalid"),
        ]:
            with self.subTest(code=code):
                with self.assertRaisesRegex(AccessDenied, code):
                    self.authorize(context)

    def test_malformed_claim_shapes_fail_closed_without_type_errors(self):
        malformed = [
            AccessContext("actor", self.business, self.hotel_id, [], True, True, True),
            AccessContext("actor", self.business, self.hotel_id, "manager", True,
                          True, True, privileges=([],)),
            AccessContext("actor", self.business, self.hotel_id, "department_staff",
                          True, True, True, department=[]),
        ]
        for context in malformed:
            with self.subTest(context=context):
                with self.assertRaisesRegex(AccessDenied, "authorization_context_invalid"):
                    self.authorize(context)
        with self.assertRaisesRegex(AccessDenied, "authorization_context_invalid"):
            self.authorize(self.context(), resource=[], action="read")
        with self.assertRaisesRegex(AccessDenied, "invalid_record_reference"):
            self.authorize(
                self.context(role="department_staff", department="housekeeping"),
                resource="service_requests", action="read", record_department=[],
            )

    def test_wrong_business_and_wrong_row_business_fail_closed(self):
        with self.assertRaisesRegex(AccessDenied, "wrong_business"):
            self.authorize(self.context(), business_id=uid("other-business"))
        with self.assertRaisesRegex(AccessDenied, "wrong_business"):
            self.authorize(self.context(), record_business_id=uid("other-business"))

    def test_guest_can_only_project_own_minimal_profile(self):
        guest = self.context(role="guest", guest_id=self.guest_id)
        profile = project_guest_profile(
            guest, business_id=self.business, record_business_id=self.business,
            snapshot=self.hotel, guest_id=self.guest_id,
            trusted_snapshot_hotel_id=self.hotel_id,
        )
        self.assertEqual(profile, {
            "entity_id": self.guest_id, "display_name": "Fictional Guest C",
        })
        with self.assertRaisesRegex(AccessDenied, "guest_scope_denied"):
            project_guest_profile(
                guest, business_id=self.business, record_business_id=self.business,
                snapshot=self.hotel, guest_id=uid("Guest A"),
                trusted_snapshot_hotel_id=self.hotel_id,
            )
        with self.assertRaisesRegex(AccessDenied, "access_denied"):
            self.authorize(guest, resource="guest_personal_data", record_guest_id=self.guest_id)

    def test_guest_cannot_read_reservations_but_reception_can(self):
        with self.assertRaisesRegex(AccessDenied, "access_denied"):
            self.authorize(
                self.context(role="guest", guest_id=self.guest_id),
                record_guest_id=self.guest_id,
            )
        self.assertTrue(self.authorize(self.context(role="receptionist")))

    def test_room_snapshot_fails_closed_without_trusted_hotel_mapping(self):
        context = self.context(role="receptionist")
        with self.assertRaisesRegex(AccessDenied, "hotel_mapping_unverified"):
            project_room_inventory(
                context, business_id=self.business, record_business_id=self.business,
                snapshot=self.hotel, room_id=uid("201"),
            )
        with self.assertRaisesRegex(AccessDenied, "hotel_mapping_unverified"):
            project_room_inventory(
                context, business_id=self.business, record_business_id=self.business,
                snapshot=self.hotel, room_id=uid("201"),
                trusted_snapshot_hotel_id=uid("different-hotel"),
            )
        # Only a separate mapping claim permits this offline contract projection.
        room = project_room_inventory(
            context, business_id=self.business, record_business_id=self.business,
            snapshot=self.hotel, room_id=uid("201"),
            trusted_snapshot_hotel_id=self.hotel_id,
        )
        self.assertEqual(room["number"], "201")

    def test_department_room_projection_is_minimal_and_operations_are_scoped(self):
        housekeeping = self.context(role="department_staff", department="housekeeping")
        room = project_room_inventory(
            housekeeping, business_id=self.business,
            record_business_id=self.business, snapshot=self.hotel, room_id=uid("201"),
            trusted_snapshot_hotel_id=self.hotel_id,
        )
        self.assertEqual(set(room), {"entity_id", "number", "room_type_id"})
        self.assertEqual(room["number"], "201")
        self.assertTrue(self.authorize(
            housekeeping, resource="housekeeping_status", action="update",
        ))
        with self.assertRaisesRegex(AccessDenied, "access_denied"):
            self.authorize(housekeeping, resource="reservations", action="read")
        maintenance = self.context(role="department_staff", department="maintenance")
        self.assertTrue(self.authorize(
            maintenance, resource="room_maintenance_blocks", action="create",
        ))
        with self.assertRaisesRegex(AccessDenied, "access_denied"):
            self.authorize(maintenance, resource="housekeeping_status", action="update")

    def test_departmental_request_view_is_scoped_and_redacts_guest_identity(self):
        housekeeping = self.context(role="department_staff", department="housekeeping")
        view = project_service_request(
            housekeeping, business_id=self.business, record_business_id=self.business,
            request=self.request,
        )
        self.assertEqual(view["department"], "housekeeping")
        self.assertEqual(view["room_id"], uid("205"))
        for private_field in ("guest_id", "stay_id", "hotel_id", "idempotency_key",
                              "last_event_id", "last_operation_signature"):
            self.assertNotIn(private_field, view)

        maintenance = self.context(role="department_staff", department="maintenance")
        with self.assertRaisesRegex(AccessDenied, "wrong_department"):
            project_service_request(
                maintenance, business_id=self.business, record_business_id=self.business,
                request=self.request,
            )
        other_hotel_request = dict(self.request, hotel_id=uid("another-hotel"))
        with self.assertRaisesRegex(AccessDenied, "wrong_hotel"):
            project_service_request(
                housekeeping, business_id=self.business,
                record_business_id=self.business, request=other_hotel_request,
            )

    def test_guest_request_view_requires_own_active_registered_stay(self):
        guest = self.context(role="guest", guest_id=self.guest_id)
        view = project_service_request(
            guest, business_id=self.business, record_business_id=self.business,
            request=self.request, snapshot=self.hotel,
            trusted_snapshot_hotel_id=self.hotel_id,
        )
        self.assertEqual(view["request_id"], self.request["request_id"])
        self.assertNotIn("room_id", view)
        wrong_guest = AccessContext(**{**guest.__dict__, "guest_id": uid("Guest A")})
        with self.assertRaisesRegex(AccessDenied, "guest_scope_denied"):
            project_service_request(
                wrong_guest, business_id=self.business,
                record_business_id=self.business, request=self.request,
                snapshot=self.hotel, trusted_snapshot_hotel_id=self.hotel_id,
            )
        with self.assertRaisesRegex(AccessDenied, "guest_scope_denied"):
            no_active_stay = synthetic_hotel()
            no_active_stay["stays"] = []
            no_active_stay["stay_guests"] = []
            project_service_request(
                guest, business_id=self.business, record_business_id=self.business,
                request=self.request, snapshot=no_active_stay,
                trusted_snapshot_hotel_id=self.hotel_id,
            )

        wrong_room_request = dict(self.request, room_id=uid("201"))
        with self.assertRaisesRegex(AccessDenied, "guest_scope_denied"):
            project_service_request(
                guest, business_id=self.business, record_business_id=self.business,
                request=wrong_room_request, snapshot=self.hotel,
                trusted_snapshot_hotel_id=self.hotel_id,
            )

    def test_guest_profile_requires_active_registered_occupant_but_staff_access_remains(self):
        guest = self.context(role="guest", guest_id=self.guest_id)
        staff = self.context(role="receptionist")
        no_stay = synthetic_hotel()
        no_stay["stays"] = []
        no_stay["stay_guests"] = []
        with self.assertRaisesRegex(AccessDenied, "guest_scope_denied"):
            project_guest_profile(
                guest, business_id=self.business, record_business_id=self.business,
                snapshot=no_stay, guest_id=self.guest_id,
                trusted_snapshot_hotel_id=self.hotel_id,
            )

        checked_out = synthetic_hotel()
        checked_out["stays"][0]["status"] = "checked_out"
        checked_out["stays"][0]["checked_out_at"] = "2026-11-06T13:00:00+01:00"
        checked_out["stay_guests"][0]["left_at"] = "2026-11-06T13:00:00+01:00"
        with self.assertRaisesRegex(AccessDenied, "guest_scope_denied"):
            project_guest_profile(
                guest, business_id=self.business, record_business_id=self.business,
                snapshot=checked_out, guest_id=self.guest_id,
                trusted_snapshot_hotel_id=self.hotel_id,
            )

        occupant_left = synthetic_hotel()
        occupant_left["stay_guests"][0]["left_at"] = "2026-11-06T13:00:00+01:00"
        with self.assertRaisesRegex(AccessDenied, "guest_scope_denied"):
            project_guest_profile(
                guest, business_id=self.business, record_business_id=self.business,
                snapshot=occupant_left, guest_id=self.guest_id,
                trusted_snapshot_hotel_id=self.hotel_id,
            )

        self.assertEqual(project_guest_profile(
            staff, business_id=self.business, record_business_id=self.business,
            snapshot=no_stay, guest_id=uid("Guest A"),
            trusted_snapshot_hotel_id=self.hotel_id,
        )["entity_id"], uid("Guest A"))

    def test_invalid_room_or_guest_references_fail_before_data_is_authorized(self):
        for table, field, bad_value in (
            ("rooms", "room_type_id", uid("missing-room-type")),
            ("reservations", "guest_id", uid("missing-guest")),
        ):
            broken = deepcopy(self.hotel)
            broken[table][0][field] = bad_value
            with self.subTest(table=table, field=field):
                with self.assertRaisesRegex(AccessDenied, "invalid_hotel_snapshot"):
                    authorize_hotel_snapshot(
                        self.context(role="receptionist"),
                        business_id=self.business, record_business_id=self.business,
                        resource="reservations", action="read", snapshot=broken,
                        trusted_snapshot_hotel_id=self.hotel_id,
                    )

    def test_sensitive_requests_require_manager_or_verified_incident_privilege(self):
        sensitive = dict(self.request, sensitive=True)
        housekeeping = self.context(role="department_staff", department="housekeeping")
        with self.assertRaisesRegex(AccessDenied, "access_denied"):
            project_service_request(
                housekeeping, business_id=self.business,
                record_business_id=self.business, request=sensitive,
            )
        manager = self.context(role="manager")
        self.assertEqual(project_service_request(
            manager, business_id=self.business, record_business_id=self.business,
            request=sensitive,
        )["sensitive"], True)
        incident = self.context(role="receptionist", privileges=("incident_manager",))
        self.assertTrue(self.authorize(
            incident, resource="service_requests", action="read",
            record_department="housekeeping", sensitive=True,
        ))

    def test_error_messages_never_echo_private_exception_text(self):
        private_text = "Fictional Guest C passport 123-SECRET"
        safe = safe_error_message(ValueError(private_text))
        self.assertNotIn(private_text, safe)
        self.assertEqual(safe, "Hotel information is temporarily unavailable.")
        denied = AccessDenied("wrong_business")
        self.assertEqual(safe_error_message(denied),
                         "These records are outside the active hotel business.")

    def test_snapshot_validator_reuses_hotel_domain_rules(self):
        self.assertIn("rooms", validate_hotel_snapshot(self.hotel))
        with self.assertRaisesRegex(AccessDenied, "invalid_hotel_snapshot"):
            validate_hotel_snapshot({"rooms": []})


if __name__ == "__main__":
    unittest.main()
