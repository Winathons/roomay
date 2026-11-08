"""Offline guest conversation intake contract tests; no providers or writes."""
import unittest

from domain.access_control import AccessContext
from domain.conversation_intake import (
    ConversationScope, classify_text, handle_conversation_turn,
)
from domain.fixtures import synthetic_hotel, uid


BUSINESS = uid("conversation-business")
HOTEL = uid("conversation-hotel")
AT = "2026-11-06T12:00:00+01:00"


class ConversationIntakeTests(unittest.TestCase):
    def setUp(self):
        self.hotel = synthetic_hotel()
        self.guest_id = uid("Guest C")
        self.context = AccessContext(
            actor_id="trusted-guest-session", business_id=BUSINESS,
            hotel_id=HOTEL, role="guest", authenticated=True,
            membership_verified=True, business_binding_verified=True,
            guest_id=self.guest_id,
        )
        self.scope = ConversationScope(
            business_id=BUSINESS, record_business_id=BUSINESS,
            trusted_snapshot_hotel_id=HOTEL, snapshot=self.hotel,
            stay_id=uid("stay"), room_id=uid("205"), staff_directory=[],
            existing_requests=[],
        )

    def turn(self, text, **kwargs):
        values = {
            "channel": "typed_chat", "conversation_id": "conversation-1",
            "turn_id": "confirmation-event-1", "at": AT,
            "access_context": self.context, "scope": self.scope,
        }
        values.update(kwargs)
        return handle_conversation_turn(text, **values)

    def test_english_and_pidgin_examples_use_canonical_categories_and_departments(self):
        examples = [
            ("The faulty AC is not cooling in room 205.", "air_conditioning", "maintenance"),
            ("AC stopped working in room number 205.", "air_conditioning", "maintenance"),
            ("Abeg bring extra towels to room 205.", "extra_towels", "housekeeping"),
            ("Water dey leak from the pipe in room 205.", "plumbing", "maintenance"),
        ]
        for text, category, department in examples:
            with self.subTest(text=text):
                intent = classify_text(text)
                self.assertEqual(intent["category"], category)
                self.assertEqual(intent["department"], department)
                self.assertEqual(intent["room_number"], "205")
        self.assertEqual(classify_text("AC is broken in room A-201")["room_number"], "A-201")
        self.assertIsNone(classify_text("The room is too hot")["room_number"])

    def test_room_enquiry_hands_off_to_reception_without_availability_claim(self):
        result = self.turn("Can I ask about room availability?")
        self.assertEqual(result["state"], "handoff")
        self.assertTrue(result["handoff_required"])
        self.assertIn("No availability or booking has been confirmed", result["message"])
        self.assertNotIn("request_plan", result["internal"])

    def test_missing_or_ambiguous_room_number_requires_clarification(self):
        missing = self.turn("The AC is not cooling.")
        ambiguous = self.turn("The AC in room 205 and room 206 is not cooling.")
        self.assertEqual(missing["state"], "needs_clarification")
        self.assertEqual(missing["clarification"], "room_number")
        self.assertEqual(ambiguous["state"], "needs_clarification")
        self.assertEqual(ambiguous["clarification"], "room_number")
        self.assertNotIn("request_plan", missing["internal"])

    def test_unverified_guest_identity_hands_off_without_disclosing_stay(self):
        result = self.turn("Please bring towels to room 205.", access_context=None)
        self.assertEqual(result["state"], "handoff")
        self.assertIn("couldn't verify an active stay", result["message"])
        self.assertNotIn(self.guest_id, str(result))
        self.assertNotIn("request_plan", result["internal"])

    def test_wrong_room_stay_or_business_fails_closed(self):
        wrong_room = ConversationScope(
            **{**self.scope.__dict__, "room_id": uid("204")},
        )
        wrong_stay = ConversationScope(
            **{**self.scope.__dict__, "stay_id": uid("walk-in-stay")},
        )
        wrong_business = ConversationScope(
            **{**self.scope.__dict__, "record_business_id": uid("other-business")},
        )
        wrong_hotel_mapping = ConversationScope(
            **{**self.scope.__dict__, "trusted_snapshot_hotel_id": uid("other-hotel")},
        )
        wrong_guest = AccessContext(
            actor_id="other-guest", business_id=BUSINESS, hotel_id=HOTEL,
            role="guest", authenticated=True, membership_verified=True,
            business_binding_verified=True, guest_id=uid("Guest B"),
        )
        for scope, access in (
                (wrong_room, self.context), (wrong_stay, self.context),
                (wrong_business, self.context), (wrong_hotel_mapping, self.context),
                (self.scope, wrong_guest)):
            with self.subTest(scope=scope):
                result = self.turn("Bring towels to room 204.", scope=scope,
                                   access_context=access)
                self.assertEqual(result["state"], "handoff")
                self.assertNotIn("request_plan", result["internal"])

    def test_guest_must_confirm_before_any_request_plan_is_prepared(self):
        result = self.turn("Extra towels please, room 205.", confirmed=False)
        self.assertEqual(result["state"], "awaiting_confirmation")
        self.assertNotIn("request_plan", result["internal"])
        self.assertFalse(result["submitted"])
        self.assertFalse(result["persisted"])

    def test_confirmed_request_reuses_canonical_service_request_plan_only(self):
        result = self.turn("Extra towels please, room 205.", confirmed=True)
        self.assertEqual(result["state"], "prepared")
        self.assertFalse(result["submitted"])
        self.assertFalse(result["persisted"])
        self.assertIn("request_plan", result["internal"])
        request = result["internal"]["request_plan"]["target_request"]
        self.assertEqual(request["category"], "extra_towels")
        self.assertEqual(request["department"], "housekeeping")
        self.assertEqual(request["status"], "received")
        self.assertEqual(request["origin"], "guest")
        self.assertNotIn("ticket", result["message"].lower())
        self.assertNotIn("reference", result["message"].lower())
        self.assertNotIn("request_id", result)
        guest_facing = {key: value for key, value in result.items() if key != "internal"}
        self.assertNotIn(self.guest_id, str(guest_facing))
        self.assertNotIn("205", result["message"])

    def test_typed_chat_and_future_vapi_transcript_share_the_same_contract(self):
        text = "The AC is faulty in room 205."
        chat = self.turn(text, channel="typed_chat", confirmed=True)
        call = self.turn(text, channel="vapi", confirmed=True)
        self.assertEqual(chat["state"], "prepared")
        self.assertEqual(call["state"], "prepared")
        chat_request = chat["internal"]["request_plan"]["target_request"]
        call_request = call["internal"]["request_plan"]["target_request"]
        self.assertEqual(chat_request["category"], call_request["category"])
        self.assertEqual(chat_request["department"], call_request["department"])
        # The existing canonical request model does not distinguish guest chat
        # from a guest speaking through Vapi; both use its guest origin.
        self.assertEqual(call_request["origin"], "guest")
        self.assertNotEqual(chat_request["idempotency_key"], call_request["idempotency_key"])

    def test_duplicate_confirmation_has_stable_plan_and_existing_duplicate_has_no_plan(self):
        text = "The AC is faulty in room 205."
        first = self.turn(text, confirmed=True)
        retry = self.turn(text, confirmed=True)
        self.assertEqual(first["internal"]["request_plan"], retry["internal"]["request_plan"])
        existing_scope = ConversationScope(
            **{**self.scope.__dict__, "existing_requests": [
                first["internal"]["request_plan"]["target_request"]
            ]},
        )
        duplicate = self.turn(text, confirmed=True, scope=existing_scope)
        self.assertEqual(duplicate["state"], "duplicate")
        self.assertNotIn("request_plan", duplicate["internal"])
        self.assertFalse(duplicate["persisted"])

    def test_wrong_ai_department_is_rejected(self):
        candidate = {
            "intent": "service_request", "category": "air_conditioning",
            "department": "housekeeping", "urgency": "normal",
            "room_number": "205",
        }
        result = self.turn("AC is faulty in room 205", classifier_output=candidate)
        self.assertEqual(result["state"], "unavailable")
        self.assertEqual(result["internal"]["failure_code"], "invalid_classifier_output")
        self.assertNotIn("request_plan", result["internal"])

    def test_invalid_ai_shapes_and_values_fail_closed_without_raw_output(self):
        for candidate in (
            {"intent": "service_request"},
            {"intent": [], "category": "plumbing", "department": "maintenance",
             "urgency": "normal", "room_number": "205"},
            {"intent": "service_request", "category": "delete_guest",
             "department": "reception", "urgency": "normal", "room_number": "205"},
            {"intent": "service_request", "category": "plumbing",
             "department": "maintenance", "urgency": "urgent",
             "room_number": "205", "guest_id": self.guest_id},
            {"intent": "service_request", "category": "plumbing",
             "department": "maintenance", "urgency": "normal",
             "room_number": "205"},
        ):
            result = self.turn("Pipe issue in the room", classifier_output=candidate)
            self.assertEqual(result["state"], "unavailable")
            self.assertNotIn("request_plan", result["internal"])
            self.assertNotIn(self.guest_id, str(result))

    def test_emergency_requires_human_handoff_and_never_self_escalates(self):
        result = self.turn("Smoke in room 205, this is an emergency.", confirmed=True)
        self.assertEqual(result["state"], "handoff")
        self.assertTrue(result["handoff_required"])
        self.assertEqual(result["internal"]["intent"]["urgency"], "urgent")
        self.assertIn("has not contacted anyone", result["message"])
        self.assertNotIn("request_plan", result["internal"])

    def test_unknown_issue_routes_to_reception_triage_after_confirmation(self):
        result = self.turn("There is a loud vibration in room 205.", confirmed=True)
        request = result["internal"]["request_plan"]["target_request"]
        self.assertEqual(result["state"], "prepared")
        self.assertEqual(request["category"], "unknown")
        self.assertEqual(request["department"], "reception")
        self.assertTrue(request["triage_required"])

    def test_provider_timeout_and_failure_are_safe_unavailable_states(self):
        for state in ("timeout", "failed", {"error": "SECRET_SENTINEL"}):
            result = self.turn(
                "Issue in room 205", provider_status=state,
            )
            self.assertEqual(result["state"], "unavailable")
            self.assertFalse(result["submitted"])
            self.assertFalse(result["persisted"])
            self.assertNotIn("SECRET_SENTINEL", str(result))

    def test_pidgin_emergency_text_overrides_classifier(self):
        candidate = {
            "intent": "service_request", "category": "general_help",
            "department": "reception", "urgency": "normal", "room_number": "205",
        }
        result = self.turn(
            "Abeg, smoke dey inside room 205, emergency.",
            classifier_output=candidate, confirmed=True,
        )
        self.assertEqual(result["state"], "handoff")
        self.assertEqual(result["internal"]["intent"]["urgency"], "urgent")
        self.assertNotIn("request_plan", result["internal"])

    def test_urgent_classifier_result_always_hands_off_to_a_human(self):
        candidate = {
            "intent": "service_request", "category": "plumbing",
            "department": "maintenance", "urgency": "urgent",
            "room_number": "205",
        }
        result = self.turn(
            "The pipe has a problem in room 205.", classifier_output=candidate,
            confirmed=True,
        )
        self.assertEqual(result["state"], "handoff")
        self.assertTrue(result["handoff_required"])
        self.assertNotIn("request_plan", result["internal"])

    def test_urgent_wording_also_requires_human_handoff(self):
        result = self.turn("Please urgently fix the plumbing in room 205.", confirmed=True)
        self.assertEqual(result["state"], "handoff")
        self.assertEqual(result["internal"]["intent"]["urgency"], "urgent")
        self.assertNotIn("request_plan", result["internal"])


if __name__ == "__main__":
    unittest.main()
