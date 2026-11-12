"""Offline Vapi tool-call protocol and safety contracts; no network/provider use."""

import io
import json
import unittest

from voice_adapter.intent_tools import (
    TOOL_NAME,
    ToolConfig,
    create_tool_app,
    route_caller_intent,
)


TOKEN = "offline-vapi-tool-secret-placeholder-000000000000"


def document(utterance="Where is the hotel?", *, call_id="tool-call-1", vapi_call_id="offline-call", name=TOOL_NAME, arguments=None):
    if arguments is None:
        arguments = {"utterance": utterance}
    return {"message": {"type": "tool-calls", "call": {"id": vapi_call_id},
                        "toolCallList": [{"id": call_id, "type": "function",
                                          "function": {"name": name, "arguments": arguments}}]}}


def invoke(app, body=None, *, token=TOKEN, content_type="application/json", method="POST"):
    encoded = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
    environ = {"REQUEST_METHOD": method, "PATH_INFO": "/", "CONTENT_TYPE": content_type,
               "CONTENT_LENGTH": str(len(encoded)), "HTTP_AUTHORIZATION": "Bearer " + token,
               "wsgi.input": io.BytesIO(encoded)}
    response = {}

    def start_response(status, headers, exc_info=None):
        response["status"] = int(status.split(" ", 1)[0])
        response["headers"] = dict(headers)

    response["body"] = b"".join(app(environ, start_response))
    return response


def tool_result(response):
    return json.loads(json.loads(response["body"])["results"][0]["result"])


class CallerRoutingTests(unittest.TestCase):
    def test_public_hotel_enquiry_does_not_invent_hotel_facts(self):
        result = route_caller_intent("What is your address and do you have parking?")
        self.assertEqual(result["state"], "public_enquiry_unavailable")
        self.assertIn("no hotel details were assumed", result["message"])
        self.assertFalse(result["submitted"])

    def test_booking_enquiry_never_claims_availability_or_confirmation(self):
        for phrase in ("Can I book a room for tomorrow?", "What are your room rates?"):
            with self.subTest(phrase=phrase):
                result = route_caller_intent(phrase)
                self.assertIn(result["state"], {"booking_enquiry", "public_enquiry_unavailable"})
                self.assertTrue("No availability" in result["message"] or "nothing has been quoted" in result["message"])
                self.assertFalse(result["persisted"])

    def test_existing_guest_request_is_routed_but_requires_verified_stay(self):
        for phrase, department, language in (
            ("Please bring extra towels to room 205", "housekeeping", "english"),
            ("Abeg, bring extra towels to room 205", "housekeeping", "english"),
            ("My air conditioning is not cooling in room 205", "maintenance", "english"),
            ("Abeg, my AC no dey cool for room 205", "maintenance", "nigerian_pidgin"),
            ("Water dey leak in room 205", "maintenance", "nigerian_pidgin"),
        ):
            with self.subTest(phrase=phrase):
                result = route_caller_intent(phrase)
                self.assertEqual(result["state"], "guest_verification_required")
                self.assertEqual(result["department"], department)
                self.assertEqual(result["response_language"], language)
                self.assertFalse(result["submitted"])
                self.assertFalse(result["persisted"])
                self.assertNotIn("205", json.dumps(result))

    def test_room_number_and_caller_claim_are_not_authentication(self):
        result = route_caller_intent("I am in room 205, send extra towels")
        self.assertEqual(result["state"], "guest_verification_required")
        self.assertTrue(result["verification_required"])
        self.assertNotIn("205", json.dumps(result))

    def test_forgotten_pin_is_not_bypassed_or_requested(self):
        result = route_caller_intent("I forgot my stay PIN")
        self.assertEqual(result["state"], "verification_unavailable")
        self.assertIn("do not share a PIN", result["message"])
        self.assertTrue(result["handoff_required"])

    def test_urgent_caller_is_told_human_help_is_needed_without_claiming_transfer(self):
        result = route_caller_intent("There is a fire and smoke in the corridor")
        self.assertEqual(result["state"], "human_handoff")
        self.assertTrue(result["handoff_required"])
        self.assertIn("has not contacted or transferred", result["message"])

    def test_unclear_intent_asks_one_short_category_clarification(self):
        result = route_caller_intent("Hello, I need some help")
        self.assertEqual(result["state"], "needs_clarification")
        self.assertIn("hotel information", result["message"])

    def test_pidgin_room_availability_and_booking_are_distinct_and_truthful(self):
        availability = route_caller_intent("Abeg, una get room for tonight?")
        booking = route_caller_intent("Abeg, I wan book room for tomorrow")
        price_question = route_caller_intent("How much una dey charge to lodge?")
        self.assertEqual(availability["state"], "public_enquiry_unavailable")
        self.assertEqual(booking["state"], "booking_enquiry")
        self.assertEqual(price_question["state"], "booking_enquiry")
        for result in (availability, booking, price_question):
            self.assertEqual(result["response_language"], "nigerian_pidgin")
            self.assertFalse(result["submitted"])
            self.assertFalse(result["persisted"])
        self.assertIn("no room don hold or book", availability["message"])
        self.assertIn("no reservation don confirm", booking["message"])
        self.assertIn("no reservation don confirm", price_question["message"])

    def test_pidgin_housekeeping_and_maintenance_keep_guest_verification_gate(self):
        housekeeping = route_caller_intent("Abeg bring extra towels to room 205")
        maintenance = route_caller_intent("My AC no dey cool for room 205")
        self.assertEqual(housekeeping["department"], "housekeeping")
        self.assertEqual(maintenance["department"], "maintenance")
        for result, language in ((housekeeping, "english"), (maintenance, "nigerian_pidgin")):
            self.assertEqual(result["state"], "guest_verification_required")
            self.assertEqual(result["response_language"], language)
            self.assertTrue(result["verification_required"])
            self.assertFalse(result["submitted"])
            self.assertFalse(result["persisted"])
            self.assertNotIn("205", json.dumps(result))

    def test_pidgin_human_and_emergency_requests_signal_handoff_without_claiming_transfer(self):
        human = route_caller_intent("Abeg, make I talk to receptionist")
        emergency = route_caller_intent("Fire don start, person dey bleed")
        for result in (human, emergency):
            self.assertEqual(result["state"], "human_handoff")
            self.assertEqual(result["response_language"], "nigerian_pidgin")
            self.assertTrue(result["handoff_required"])
            self.assertFalse(result["submitted"])
            self.assertFalse(result["persisted"])
            self.assertIn("transfer", result["message"].lower())
            self.assertTrue("no fit transfer" in result["message"].lower()
                            or "never contact or transfer" in result["message"].lower())

    def test_english_pidgin_and_code_switching_follow_current_utterance(self):
        turns = (
            ("Could you tell me about parking at the hotel?", "english"),
            ("Please, abeg, una get room for tonight?", "english"),
            ("Could you check room availability, please?", "english"),
            ("Abeg, I wan ask about booking", "nigerian_pidgin"),
        )
        for utterance, language in turns:
            with self.subTest(utterance=utterance):
                result = route_caller_intent(utterance)
                self.assertEqual(result["response_language"], language)
                self.assertFalse(result["submitted"])
                self.assertFalse(result["persisted"])

    def test_isolated_pidgin_expression_does_not_override_english_request(self):
        for utterance in (
            "Please, abeg, can you bring extra towels to my room?",
            "Abeg, I need extra towels in my room",
            "Could you please check availability, abeg?",
            "Please, abeg, una get room for tonight?",
        ):
            with self.subTest(utterance=utterance):
                outcome = route_caller_intent(utterance)
                self.assertEqual(outcome["response_language"], "english")
                self.assertFalse(outcome["submitted"])
                self.assertFalse(outcome["persisted"])

    def test_clearly_pidgin_grammar_still_supported_without_claimed_hotel_action(self):
        for utterance in (
            "Abeg, una get room for tonight?",
            "Abeg, I wan book room tomorrow",
            "My AC no dey cool for room 205",
            "Water dey leak in room 205",
            "Abeg, make I talk to receptionist",
        ):
            with self.subTest(utterance=utterance):
                outcome = route_caller_intent(utterance)
                self.assertEqual(outcome["response_language"], "nigerian_pidgin")
                self.assertFalse(outcome["submitted"])
                self.assertFalse(outcome["persisted"])

    def test_representative_pidgin_enquiries_preserve_routing_and_safety(self):
        examples = (
            ("Abeg, una get room for tonight?", "public_enquiry_unavailable", "reception", False),
            ("Wetin be room price if I wan lodge tomorrow?", "booking_enquiry", "reception", False),
            ("Abeg, I wan make una bring extra towels to my room", "guest_verification_required", "housekeeping", False),
            ("AC no dey cool for my room", "guest_verification_required", "maintenance", False),
            ("Abeg, make I talk to receptionist", "human_handoff", None, True),
            ("Fire don start, person dey bleed, abeg help", "human_handoff", None, True),
        )
        for utterance, state, department, handoff in examples:
            with self.subTest(utterance=utterance):
                result = route_caller_intent(utterance)
                self.assertEqual(result["state"], state)
                self.assertEqual(result["department"], department)
                self.assertEqual(result["response_language"], "nigerian_pidgin")
                self.assertEqual(result["handoff_required"], handoff)
                self.assertFalse(result["submitted"])
                self.assertFalse(result["persisted"])

    def test_mixed_english_pidgin_turns_follow_each_latest_utterance(self):
        turns = (
            ("Could you please bring extra towels?", "english"),
            ("Abeg, my AC no dey cool", "nigerian_pidgin"),
            ("Please tell me if I need to verify my stay", "english"),
        )
        for utterance, expected_language in turns:
            with self.subTest(utterance=utterance):
                result = route_caller_intent(utterance)
                self.assertEqual(result["response_language"], expected_language)
                self.assertIn(result["state"], {
                    "guest_verification_required", "public_enquiry_unavailable", "needs_clarification"
                })
                self.assertFalse(result["submitted"])
                self.assertFalse(result["persisted"])

    def test_mixed_english_clarification_does_not_force_pidgin(self):
        result = route_caller_intent("Abeg, I need help")
        self.assertEqual(result["state"], "needs_clarification")
        self.assertEqual(result["response_language"], "english")
        self.assertIn("hotel information", result["message"])
        self.assertIn("new booking", result["message"])
        self.assertIn("existing stay", result["message"])
        self.assertIn("receptionist", result["message"])


class VapiToolBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.app = create_tool_app(ToolConfig(TOKEN))

    def test_protocol_returns_one_minimal_result_per_call(self):
        response = invoke(self.app, document("I need extra towels"))
        self.assertEqual(response["status"], 200)
        payload = json.loads(response["body"])
        self.assertEqual(set(payload), {"results"})
        self.assertEqual(payload["results"][0]["toolCallId"], "tool-call-1")
        result = tool_result(response)
        self.assertEqual(result["state"], "guest_verification_required")
        self.assertEqual(result["response_language"], "english")
        self.assertEqual(result["submitted"], False)
        self.assertEqual(result["persisted"], False)
        self.assertEqual(response["headers"]["Cache-Control"], "no-store")

    def test_unauthenticated_provider_call_is_rejected_before_reading_body(self):
        class Unreadable:
            def read(self, size):
                raise AssertionError("body should not be read before authentication")

        environ = {"REQUEST_METHOD": "POST", "CONTENT_TYPE": "application/json",
                   "CONTENT_LENGTH": "10", "HTTP_AUTHORIZATION": "Bearer wrong",
                   "wsgi.input": Unreadable()}
        response = {}
        body = self.app(environ, lambda status, headers, exc_info=None: response.update(status=status))
        self.assertEqual(response["status"].split()[0], "401")
        self.assertEqual(json.loads(b"".join(body)), {"error": "unauthorized"})

    def test_tool_result_never_echoes_guest_content_or_internal_details(self):
        text = "my private contact is guest@example.invalid; bring towels to room 205"
        response = invoke(self.app, document(text))
        raw = response["body"].decode("utf-8")
        self.assertNotIn("guest@example.invalid", raw)
        self.assertNotIn("205", raw)
        self.assertNotIn("internal", raw)

    def test_replay_returns_same_result_and_changed_replay_fails_closed(self):
        first = tool_result(invoke(self.app, document("Need towels")))
        same = tool_result(invoke(self.app, document("Need towels")))
        changed = json.loads(invoke(self.app, document("Need a repair"))["body"])["results"][0]
        self.assertEqual(first, same)
        self.assertIn("error", changed)
        self.assertNotIn("result", changed)

    def test_tool_call_ids_are_scoped_to_the_vapi_call(self):
        initial = tool_result(invoke(self.app, document("Need towels")))
        other_call = tool_result(invoke(self.app, document("The AC is broken", vapi_call_id="other-call")))
        self.assertEqual(initial["state"], "guest_verification_required")
        self.assertEqual(other_call["state"], "guest_verification_required")
        self.assertEqual(other_call["department"], "maintenance")

    def test_malformed_or_forged_tool_arguments_are_rejected(self):
        invalid_envelopes = [
            {}, {"message": {"type": "tool-calls", "toolCallList": []}},
            document(call_id="bad id"),
            {"message": {"type": "tool-calls", "toolCallList": [
                {"id": "same", "type": "function", "function": {"name": TOOL_NAME, "arguments": {"utterance": "a"}}},
                {"id": "same", "type": "function", "function": {"name": TOOL_NAME, "arguments": {"utterance": "b"}}},
            ]}},
        ]
        for payload in invalid_envelopes:
            with self.subTest(payload=payload):
                self.assertEqual(invoke(self.app, payload)["status"], 400)
        for payload in (document(arguments={"utterance": "", "room_number": "205"}),
                        document(name=TOOL_NAME, arguments={"utterance": ["not text"]})):
            with self.subTest(payload=payload):
                response = invoke(self.app, payload)
                self.assertEqual(response["status"], 200)
                self.assertIn("error", json.loads(response["body"])["results"][0])
        duplicate_keys = b'{"message":{"type":"tool-calls","type":"tool-calls","toolCallList":[]}}'
        self.assertEqual(invoke(self.app, duplicate_keys)["status"], 400)

    def test_unknown_tool_and_router_failure_return_safe_unavailable(self):
        unknown_response = invoke(self.app, document(name="delete_guest", arguments={"id": "x"}))
        self.assertEqual(unknown_response["status"], 200)
        unknown = json.loads(unknown_response["body"])["results"][0]
        self.assertEqual(set(unknown), {"toolCallId", "error"})
        self.assertNotIn("result", unknown)
        failing = create_tool_app(ToolConfig(TOKEN), router=lambda _: (_ for _ in ()).throw(RuntimeError("private failure")))
        failure_response = invoke(failing, document("Abeg, una get room?"))
        outcome = json.loads(failure_response["body"])["results"][0]
        self.assertEqual(failure_response["status"], 200)
        self.assertEqual(set(outcome), {"toolCallId", "error"})
        self.assertIn("Abeg", outcome["error"])
        self.assertNotIn("private failure", json.dumps(outcome))

    def test_malformed_per_tool_arguments_use_vapi_error_field_with_http_200(self):
        response = invoke(self.app, document(arguments={"utterance": "Abeg", "role": "owner"}))
        self.assertEqual(response["status"], 200)
        item = json.loads(response["body"])["results"][0]
        self.assertEqual(set(item), {"toolCallId", "error"})
        self.assertIn("invalid arguments", item["error"])
        self.assertNotIn("result", item)

    def test_rate_limit_and_request_size_are_enforced(self):
        limited = create_tool_app(ToolConfig(TOKEN, requests_per_minute=1))
        self.assertEqual(invoke(limited, document())["status"], 200)
        limited_response = invoke(limited, document())
        self.assertEqual(limited_response["status"], 200)
        limited_item = json.loads(limited_response["body"])["results"][0]
        self.assertEqual(set(limited_item), {"toolCallId", "error"})
        self.assertIn("busy", limited_item["error"])
        oversized = invoke(self.app, b"x" * (32 * 1024 + 1))
        self.assertEqual(oversized["status"], 413)

    def test_method_and_content_type_are_restricted(self):
        self.assertEqual(invoke(self.app, document(), method="GET")["status"], 405)
        self.assertEqual(invoke(self.app, document(), content_type="text/plain")["status"], 400)

    def test_tool_configuration_rejects_short_credentials_and_unbounded_limits(self):
        with self.assertRaises(ValueError):
            ToolConfig("too-short").validate()
        with self.assertRaises(ValueError):
            ToolConfig(TOKEN, requests_per_minute=0).validate()

    def test_path_is_restricted(self):
        encoded = json.dumps(document()).encode("utf-8")
        environ = {"REQUEST_METHOD": "POST", "PATH_INFO": "/unrelated",
                   "CONTENT_TYPE": "application/json", "CONTENT_LENGTH": str(len(encoded)),
                   "HTTP_AUTHORIZATION": "Bearer " + TOKEN, "wsgi.input": io.BytesIO(encoded)}
        result = {}
        response = b"".join(self.app(environ, lambda status, headers, exc_info=None: result.update(status=status)))
        self.assertEqual(result["status"].split()[0], "404")
        self.assertEqual(json.loads(response), {"error": "not_found"})

    def test_environment_tts_default_is_remi_and_optional_voice_aliases_remain(self):
        from voice_adapter.wsgi import VoiceConfig

        config = VoiceConfig.from_environment({
            "ROOMAY_VAPI_BEARER_TOKEN": TOKEN,
            "YARNGPT_API_KEY": "offline-placeholder",
        })
        self.assertEqual(config.default_voice, "remi")
        self.assertEqual(config.voice_ids, {"remi": "remi"})


if __name__ == "__main__":
    unittest.main()
