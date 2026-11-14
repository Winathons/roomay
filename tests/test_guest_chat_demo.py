"""Offline guest chat demo tests; every guest context and request is synthetic."""

from dataclasses import replace
import http.client
import io
import json
import shutil
import subprocess
import sys
import threading
import unittest
from pathlib import Path

from domain.fixtures import uid
from domain.staff_actions import _audit_history_is_consistent
from domain.conversation_intake import classify_text
from tools.guest_chat_demo import (
    LOOPBACK, DemoError, GuestChatDemo, make_server,
)

ROOT = Path(__file__).resolve().parents[1]


class GuestChatDemoFlowTests(unittest.TestCase):
    def setUp(self):
        self.demo = GuestChatDemo()
        self.session_id, self.initial = self.demo.create_session()

    def send(self, text, **kwargs):
        return self.demo.send_message(self.session_id, text, **kwargs)

    def test_greeting_is_not_a_hotel_request(self):
        for greeting in ("Hi", "Hi are you here", "Hello!", "Good evening", "Thanks",
                         "Hey Hi", "Hey hey", "Hi Remi", "How far Remi?"):
            with self.subTest(greeting=greeting):
                result = self.send(greeting)
                self.assertEqual(result["state"], "ready")
                self.assertIsNone(result["pending"])
                self.assertFalse(result["submitted"])
                self.assertFalse(result["persisted"])
                self.assertNotIn("Which room", result["messages"][-1]["text"])
                self.assertNotIn("describe what is happening", result["messages"][-1]["text"])
                self.assertTrue(any(value in result["messages"][-1]["text"]
                                    for value in ("Hello!", "You're welcome", "I’m here")))
        self.assertEqual(self.demo._sessions[self.session_id].scope.existing_requests, [])

    def test_independent_browser_roles_share_one_expiring_synthetic_scenario(self):
        scenario_code = self.demo.create_qa_scenario()["scenario_code"]
        guest_id, _ = self.demo.create_session(role="guest", scenario_code=scenario_code)
        reception_id, _ = self.demo.create_session(role="reception", scenario_code=scenario_code)
        housekeeping_id, _ = self.demo.create_session(
            role="housekeeping", scenario_code=scenario_code)
        self.assertEqual(len({guest_id, reception_id, housekeeping_id}), 3)

        proposal = self.demo.send_message(
            guest_id, "Please bring extra towels to my room.")
        revision = proposal["pending"]["revision"]
        self.demo.confirm(guest_id, revision)
        self.demo.confirm(guest_id, revision)
        guest = self.demo.role_view(guest_id)
        self.assertEqual(len(guest["requests"]), 1)
        request_id = self.demo._sessions[guest_id].demo_requests[0]["request_id"]

        reception = self.demo.role_view(reception_id)
        self.assertEqual(len(reception["requests"]), 1)
        self.assertEqual(reception["requests"][0]["status"], "received")
        self.demo.assign_latest_to_housekeeping(reception_id, request_id)
        self.assertEqual(len(self.demo.role_view(housekeeping_id)["requests"]), 1)
        for action in ("acknowledge", "start", "resolve"):
            self.demo.department_action(housekeeping_id, action, request_id)
        self.assertEqual(self.demo.role_view(guest_id)["requests"][0]["status"], "resolved")

        with self.assertRaises(DemoError) as denied:
            self.demo.assign_latest_to_housekeeping(guest_id, request_id)
        self.assertEqual(denied.exception.status, 403)
        with self.assertRaises(DemoError) as denied:
            self.demo.department_action(reception_id, "resolve", request_id)
        self.assertEqual(denied.exception.status, 403)
        wrong_room = self.demo.send_message(guest_id, "Send towels to room 120 instead.")
        self.assertEqual(wrong_room["state"], "handoff")

    def test_shared_scenario_expiry_and_invalid_join_fail_closed(self):
        now = [100.0]
        demo = GuestChatDemo(clock=lambda: now[0])
        code = demo.create_qa_scenario()["scenario_code"]
        session_id, _ = demo.create_session(role="guest", scenario_code=code)
        with self.assertRaises(DemoError) as invalid:
            demo.create_session(role="reception", scenario_code="not-a-scenario")
        self.assertEqual(invalid.exception.status, 401)
        now[0] += 20 * 60 + 1
        with self.assertRaises(DemoError) as expired:
            demo.role_view(session_id)
        self.assertEqual(expired.exception.status, 401)

    def test_greeting_prefix_does_not_mask_real_service_problems(self):
        for text, department in (("Hi, my AC isn't cooling", "Maintenance"),
                                 ("Abeg bring towels", "Housekeeping")):
            with self.subTest(text=text):
                demo = GuestChatDemo()
                session_id, _ = demo.create_session()
                result = demo.send_message(session_id, text)
                self.assertEqual(result["state"], "awaiting_confirmation")
                self.assertEqual(result["pending"]["summary"]["department"], department)
                self.assertFalse(result["submitted"])
                self.assertFalse(result["persisted"])

    def test_unclassified_conversation_is_not_converted_to_a_request_by_length(self):
        for text in ("Tell me something interesting about the day.",
                     "I had a lovely walk along the beach today.",
                     "What a beautiful evening here."):
            with self.subTest(text=text):
                result = self.send(text)
                self.assertEqual(result["state"], "ready")
                self.assertIsNone(result["pending"])
                self.assertFalse(self.demo._sessions[self.session_id].scope.existing_requests)

    def test_hotel_information_question_never_uses_unverified_model_facts(self):
        class Provider:
            def __init__(self): self.calls = []
            def reply(self, text, *, previous_chat_id=None):
                self.calls.append(text)
                return "chat_1", "Breakfast is served at 7 AM."
        provider = Provider()
        demo = GuestChatDemo(chat_provider=provider)
        session_id, _ = demo.create_session()
        demo.set_ai_chat_consent(session_id, True)
        for question in ("What time is breakfast?", "What's your address?",
                         "Do you have a gym?", "What's the Wi-Fi password?"):
            with self.subTest(question=question):
                result = demo.send_message(session_id, question)
                self.assertIn("don't have verified hotel information", result["messages"][-1]["text"])
        self.assertFalse(provider.calls)
        self.assertFalse(result["pending"])

    def test_explicit_room_problem_uses_triage_instead_of_model_facts(self):
        class Provider:
            calls = 0
            def reply(self, text, *, previous_chat_id=None):
                self.calls += 1
                return "chat_1", "I have reported this to the hotel."
        provider = Provider()
        demo = GuestChatDemo(chat_provider=provider)
        session_id, _ = demo.create_session()
        demo.set_ai_chat_consent(session_id, True)
        result = demo.send_message(session_id, "The Wi-Fi is down in my room.")
        self.assertEqual(result["state"], "awaiting_confirmation")
        self.assertEqual(result["pending"]["summary"]["department"], "Reception")
        self.assertEqual(provider.calls, 0)

    def test_ai_chat_requires_guest_consent_and_preserves_multi_turn_context(self):
        class Provider:
            def __init__(self): self.calls = []
            def reply(self, text, *, previous_chat_id=None):
                self.calls.append((text, previous_chat_id))
                number = len(self.calls)
                return f"chat_{number}", ("Hello! I’m doing well, thank you." if number == 1
                                           else "I dey fine, thank you. How can I help?")
        provider = Provider()
        demo = GuestChatDemo(chat_provider=provider)
        session_id, _ = demo.create_session()
        off = demo.send_message(session_id, "What's good, Remi?")
        self.assertIn("What would you like to talk about", off["messages"][-1]["text"])
        self.assertFalse(provider.calls)
        consented = demo.set_ai_chat_consent(session_id, True)
        self.assertTrue(consented["chat"]["ai_chat"]["consented"])
        first = demo.send_message(session_id, "What's good, Remi?")
        second = demo.send_message(session_id, "I dey alright, how you dey?")
        self.assertIn("I’m doing well", first["messages"][-1]["text"])
        self.assertIn("I dey fine", second["messages"][-1]["text"])
        self.assertEqual(provider.calls, [("What's good, Remi?", None),
                                          ("I dey alright, how you dey?", "chat_1")])
        self.assertFalse(second["pending"])
        self.assertFalse(second["submitted"])
        self.assertFalse(second["persisted"])
        self.assertFalse(demo._sessions[session_id].scope.existing_requests)
        demo.set_ai_chat_consent(session_id, False)
        demo.send_message(session_id, "Thanks, Remi.")
        self.assertEqual(len(provider.calls), 2)
        demo.set_ai_chat_consent(session_id, True)
        resumed = demo.send_message(session_id, "Can we keep chatting?")
        self.assertEqual(provider.calls[-1], ("Can we keep chatting?", None))
        self.assertEqual(resumed["state"], "ready")

    def test_ai_is_not_called_for_operational_intent_and_domain_routes_request(self):
        class Provider:
            calls = 0
            def reply(self, text, *, previous_chat_id=None):
                self.calls += 1
                return "chat_1", "Your request is complete."
        provider = Provider()
        demo = GuestChatDemo(chat_provider=provider)
        session_id, _ = demo.create_session()
        demo.set_ai_chat_consent(session_id, True)
        result = demo.send_message(session_id, "Abeg, bring extra towels to my room.")
        self.assertEqual(result["state"], "awaiting_confirmation")
        self.assertEqual(result["pending"]["summary"]["department"], "Housekeeping")
        self.assertEqual(provider.calls, 0)
        self.assertFalse(result["submitted"])
        self.assertFalse(result["persisted"])

    def test_untrusted_ai_action_claim_is_not_displayed(self):
        class Provider:
            def reply(self, text, *, previous_chat_id=None):
                return "chat_1", "I've submitted your request and notified Housekeeping."
        demo = GuestChatDemo(chat_provider=Provider())
        session_id, _ = demo.create_session()
        demo.set_ai_chat_consent(session_id, True)
        result = demo.send_message(session_id, "What's good, Remi?")
        self.assertIn("trouble reaching Remi", result["messages"][-1]["text"])
        self.assertNotIn("notified Housekeeping", result["messages"][-1]["text"])
        self.assertFalse(result["pending"])
        self.assertFalse(demo._sessions[session_id].scope.existing_requests)

    def test_room_only_then_greeting_preserves_missing_issue_context(self):
        self.assertEqual(self.send("Hi")["state"], "ready")
        room = self.send("205")
        self.assertEqual(room["state"], "needs_clarification")
        self.assertIn("describe the issue", room["messages"][-1]["text"])
        greeting = self.send("Hi are you here")
        self.assertEqual(greeting["state"], "needs_clarification")
        self.assertIsNone(greeting["pending"])
        issue = self.send("The AC is not cooling")
        self.assertEqual(issue["state"], "awaiting_confirmation")
        self.assertEqual(issue["pending"]["summary"]["department"], "Maintenance")
        self.assertIn("room 205", issue["pending"]["summary"]["description"])
        self.assertNotIn("Hi are you here", issue["pending"]["summary"]["description"])
        self.assertIn("for the Maintenance team", issue["messages"][-1]["text"])

    def test_natural_reception_triage_copy_and_no_greeting_ticket(self):
        result = self.send("There is a loud vibration in room 205.")
        self.assertEqual(result["state"], "awaiting_confirmation")
        self.assertIn("for Reception to review and triage", result["messages"][-1]["text"])
        self.assertNotIn("for Reception will", result["messages"][-1]["text"])
        self.assertFalse(result["submitted"])

    def test_greeting_preface_does_not_hide_real_service_request(self):
        result = self.send("Hi, my AC isn't cooling in room 205.")
        self.assertEqual(result["state"], "awaiting_confirmation")
        self.assertEqual(result["pending"]["summary"]["department"], "Maintenance")

    def test_pidgin_maintenance_request_requires_review_and_confirmation(self):
        view = self.send("Abeg, my AC no dey cool for room 205.")
        self.assertEqual(view["state"], "awaiting_confirmation")
        self.assertEqual(view["pending"]["summary"]["department"], "Maintenance")
        self.assertEqual(view["pending"]["summary"]["category"], "Air Conditioning")
        self.assertIn("not be sent or saved", view["messages"][-1]["text"])
        self.assertFalse(view["submitted"])
        self.assertFalse(view["persisted"])

        revision = view["pending"]["revision"]
        prepared = self.demo.confirm(self.session_id, revision)
        self.assertEqual(prepared["state"], "prepared")
        self.assertIn("has not been sent to hotel staff", prepared["messages"][-1]["text"])
        self.assertFalse(prepared["submitted"])
        self.assertFalse(prepared["persisted"])
        session = self.demo._sessions[self.session_id]
        self.assertEqual(len(session.scope.existing_requests), 1)
        self.assertEqual(session.scope.existing_requests[0]["department"], "maintenance")

        replay = self.demo.confirm(self.session_id, revision)
        self.assertEqual(replay, prepared)
        self.assertEqual(len(session.scope.existing_requests), 1)

    def test_nigerian_english_housekeeping_request_routes_canonically(self):
        view = self.send("Please bring extra towels to room 205.")
        self.assertEqual(view["state"], "awaiting_confirmation")
        self.assertEqual(view["pending"]["summary"]["department"], "Housekeeping")
        self.assertEqual(view["pending"]["summary"]["category"], "Extra Towels")

    def test_room_cleaning_and_room_service_use_canonical_departments(self):
        self.assertEqual(classify_text("Can I get room cleaning?")["category"], "room_cleaning")
        self.assertEqual(classify_text("Please send room service.")["category"], "room_service")
        self.assertEqual(classify_text("What time is breakfast?")["intent"], "room_enquiry")

    def test_synthetic_request_and_committed_audit_chain_reuse_canonical_domain(self):
        view = self.send("Please bring extra towels to room 205.")
        self.demo.confirm(self.session_id, view["pending"]["revision"])
        self.demo.switch_role(self.session_id, "reception")
        self.demo.assign_latest_to_housekeeping(self.session_id)
        self.demo.switch_role(self.session_id, "housekeeping")
        for action in ("acknowledge", "start", "resolve"):
            self.demo.department_action(self.session_id, action)
            session = self.demo._sessions[self.session_id]
            self.assertTrue(_audit_history_is_consistent(
                session.demo_requests[0], session.demo_audit))
        guest = self.demo.switch_role(self.session_id, "guest")
        self.assertEqual(guest["workspace"], "guest")
        self.assertEqual(guest["requests"][0]["status"], "resolved")
        self.assertNotIn("rooms", guest)
        self.assertNotIn("metrics", guest)
        self.assertNotIn("housekeeping", guest)
        self.assertNotIn("request_id", json.dumps(guest))
        self.assertNotIn("guest_id", json.dumps(guest))

    def test_missing_room_uses_trusted_scope_and_prepares_only_after_confirm(self):
        first = self.send("The AC is not cooling.")
        self.assertEqual(first["state"], "awaiting_confirmation")
        self.assertIsNotNone(first["pending"])
        self.assertNotIn("Which room", first["messages"][-1]["text"])
        self.assertIn("not be sent or saved", first["messages"][-1]["text"])
        confirmed = self.demo.confirm(self.session_id, first["pending"]["revision"])
        request = self.demo._sessions[self.session_id].scope.existing_requests[0]
        self.assertEqual(request["room_id"], uid("205"))
        self.assertFalse(confirmed["submitted"])

    def test_my_room_towels_and_ac_requests_use_verified_room_205(self):
        for text in (
            "Please bring two extra towels to my room.",
            "Please send towels.",
            "The AC is broken.",
        ):
            with self.subTest(text=text):
                demo = GuestChatDemo()
                session_id, _ = demo.create_session()
                result = demo.send_message(session_id, text)
                self.assertEqual(result["state"], "awaiting_confirmation")
                self.assertNotIn("Which room", result["messages"][-1]["text"])
                demo.confirm(session_id, result["pending"]["revision"])
                self.assertEqual(
                    demo._sessions[session_id].scope.existing_requests[0]["room_id"],
                    uid("205"),
                )

    def test_hotel_phrases_route_by_canonical_need_without_room_mismatch(self):
        for text, department in (
            ("Please send room service.", "Food And Beverage"),
            ("My room smells bad.", "Reception"),
            ("Can I get room cleaning?", "Housekeeping"),
        ):
            with self.subTest(text=text):
                demo = GuestChatDemo()
                session_id, _ = demo.create_session()
                result = demo.send_message(session_id, text)
                self.assertNotEqual(result["state"], "handoff")
                self.assertNotIn("doesn't match the stay", result["messages"][-1]["text"])
                self.assertEqual(result["state"], "awaiting_confirmation")
                self.assertEqual(result["pending"]["summary"]["department"], department)

    def test_room_120_claim_is_rejected_without_revealing_room_205(self):
        first = self.send("Please bring two extra towels to my room.")
        self.assertEqual(first["state"], "awaiting_confirmation")
        mismatch = self.send("YES I am in room 120.")
        self.assertEqual(mismatch["state"], "handoff")
        self.assertIsNone(mismatch["pending"])
        self.assertIn("doesn't match the stay I can verify", mismatch["messages"][-1]["text"])
        self.assertIn("contact Reception", mismatch["messages"][-1]["text"])
        self.assertNotIn("205", mismatch["messages"][-1]["text"])
        self.assertNotIn("120", mismatch["messages"][-1]["text"])
        self.assertFalse(self.demo._sessions[self.session_id].scope.existing_requests)

    def test_answer_to_problem_clarification_keeps_context_and_does_not_repeat(self):
        first = self.send("Help")
        self.assertEqual(first["state"], "needs_clarification")
        self.assertIn("describe what is happening", first["messages"][-1]["text"])
        second = self.send("The AC is broken")
        self.assertEqual(second["state"], "awaiting_confirmation")
        self.assertEqual(second["pending"]["summary"]["department"], "Maintenance")
        self.assertNotIn("Which room", second["messages"][-1]["text"])
        self.assertNotIn("describe what is happening", second["messages"][-1]["text"])

    def test_guest_supplied_wrong_room_is_not_authentication(self):
        result = self.send("Please bring towels to room 204.")
        self.assertEqual(result["state"], "handoff")
        self.assertIsNone(result["pending"])
        self.assertIn("doesn't match the stay I can verify", result["messages"][-1]["text"])
        self.assertFalse(self.demo._sessions[self.session_id].scope.existing_requests)

    def test_room_enquiry_hands_off_to_reception_without_booking_claim(self):
        result = self.send("Can I ask about room availability?")
        self.assertEqual(result["state"], "handoff")
        self.assertIn("Reception", result["messages"][-1]["text"])
        self.assertIn("No availability or booking has been confirmed", result["messages"][-1]["text"])
        self.assertFalse(result["submitted"])

    def test_emergency_uses_honest_human_handoff(self):
        result = self.send("There is smoke in room 205, this is an emergency.")
        self.assertEqual(result["state"], "handoff")
        self.assertIn("has not contacted anyone", result["messages"][-1]["text"])
        self.assertIsNone(result["pending"])
        self.assertFalse(result["submitted"])

    def test_provider_failure_is_unavailable_and_never_exposes_details(self):
        result = self.demo.send_message(
            self.session_id, "AC trouble in room 205", _provider_status="failed")
        self.assertEqual(result["state"], "unavailable")
        self.assertIn("couldn't safely understand", result["messages"][-1]["text"])
        self.assertNotIn("internal", result)
        self.assertFalse(result["submitted"])
        self.assertFalse(result["persisted"])

    def test_wrong_role_business_hotel_room_and_stay_fail_closed(self):
        session = self.demo._sessions[self.session_id]
        original_context, original_scope = session.context, session.scope
        invalid_contexts = (
            replace(original_context, role="manager"),
            replace(original_context, membership_verified=False),
            replace(original_context, hotel_id=uid("other-hotel")),
        )
        invalid_scopes = (
            replace(original_scope, business_id=uid("other-business")),
            replace(original_scope, record_business_id=uid("other-business")),
            replace(original_scope, trusted_snapshot_hotel_id=uid("other-hotel")),
            replace(original_scope, room_id=uid("204")),
            replace(original_scope, stay_id=uid("other-stay")),
        )
        for context in invalid_contexts:
            with self.subTest(context=context):
                session.context = context
                view = self.send("Please bring towels to room 205.")
                self.assertEqual(view["state"], "handoff")
                self.assertIsNone(view["pending"])
        session.context = original_context
        for scope in invalid_scopes:
            with self.subTest(scope=scope):
                session.scope = scope
                view = self.send("Please bring towels to room 205.")
                self.assertEqual(view["state"], "handoff")
                self.assertIsNone(view["pending"])
        session.context, session.scope = original_context, original_scope

    def test_old_confirmation_cannot_confirm_a_replacement_request(self):
        first = self.send("The AC is not cooling in room 205.")
        old_revision = first["pending"]["revision"]
        second = self.send("Please bring towels to room 205.")
        self.assertEqual(second["pending"]["revision"], old_revision)
        self.assertIn("Confirm or cancel it", second["messages"][-1]["text"])
        self.assertFalse(self.demo._sessions[self.session_id].scope.existing_requests)
        canceled = self.demo.cancel(self.session_id, old_revision)
        self.assertIsNone(canceled["pending"])
        self.assertIn("Nothing was prepared", canceled["messages"][-1]["text"])

    def test_confirmation_is_session_bound(self):
        proposal = self.send("Extra towels for room 205, please.")
        other_id, _ = self.demo.create_session()
        with self.assertRaises(DemoError):
            self.demo.confirm(other_id, proposal["pending"]["revision"])
        self.assertFalse(self.demo._sessions[other_id].scope.existing_requests)

    def test_guest_view_never_contains_internal_ids_plans_or_audit_data(self):
        view = self.send("AC not cooling in room 205.")
        prepared = self.demo.confirm(self.session_id, view["pending"]["revision"])
        guest_json = json.dumps(prepared, ensure_ascii=False)
        session = self.demo._sessions[self.session_id]
        self.assertNotIn("internal", prepared)
        self.assertNotIn("request_plan", guest_json)
        self.assertNotIn("audit", guest_json.lower())
        self.assertNotIn(uid("Guest C"), guest_json)
        self.assertNotIn(uid("stay"), guest_json)
        self.assertNotIn("request_id", guest_json)
        self.assertNotIn("idempotency_key", guest_json)
        self.assertFalse(prepared["submitted"])
        self.assertFalse(prepared["persisted"])
        # The hidden canonical plan remains in the server's synthetic session only.
        self.assertEqual(len(session.scope.existing_requests), 1)

    def test_unknown_ambiguous_request_clarifies_then_routes_human_triage(self):
        first = self.send("Something is making a loud vibration in room 205.")
        self.assertEqual(first["state"], "awaiting_confirmation")
        self.assertEqual(first["pending"]["summary"]["department"], "Reception")
        self.assertEqual(first["pending"]["summary"]["category"], "Needs human triage")

    def test_invalid_input_and_unknown_session_fail_safely(self):
        for text in ("", "  ", "x" * 1001, None):
            with self.subTest(text_type=type(text).__name__):
                with self.assertRaises(DemoError):
                    self.send(text)
        with self.assertRaises(DemoError) as caught:
            self.demo.send_message("not-a-session", "A request")
        self.assertEqual(caught.exception.status, 401)


class GuestChatDemoHttpTests(unittest.TestCase):
    def test_qa_selector_controller_sends_only_explicit_shared_scenario_code(self):
        node = shutil.which("node")
        self.assertIsNotNone(node, "Node is required for the QA selector controller test")
        result = subprocess.run(
            [node, str(ROOT / "tests" / "qa_workspace_selector.cjs")],
            capture_output=True, text=True, check=False, timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_documented_module_launch_imports_from_repository_root(self):
        # The module entrypoint resolves sibling domain imports without PYTHONPATH.
        repository_root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [sys.executable, "-m", "tools.guest_chat_demo", "--help"],
            cwd=repository_root,
            capture_output=True,
            text=True,
            # A fresh Windows Python process can take several seconds to import
            # the Workpeg-linked project during the full compiled test suite.
            timeout=30,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--port", result.stdout)
        self.assertIn("--enable-local-qa", result.stdout)
        self.assertIn("--enable-vapi-web-call", result.stdout)

    def setUp(self):
        self.server = make_server(port=0, enable_local_qa=True)
        self.origin = f"http://{LOOPBACK}:{self.server.server_port}"

    def tearDown(self):
        self.server.server_close()

    def test_real_http_greeting_returns_conversation_without_creating_request(self):
        server = make_server(port=0, enable_local_qa=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        connection = http.client.HTTPConnection(LOOPBACK, server.server_port, timeout=3)
        origin = f"http://{LOOPBACK}:{server.server_port}"
        try:
            connection.request("POST", "/api/session", body=b"{}", headers={
                "Content-Type": "application/json", "Origin": origin,
            })
            initial = connection.getresponse()
            self.assertEqual(initial.status, 200)
            cookie = initial.getheader("Set-Cookie").split(";", 1)[0]
            initial.read()

            connection.request("POST", "/api/message", body=b'{"text":"Hey Hi"}', headers={
                "Content-Type": "application/json", "Origin": origin, "Cookie": cookie,
            })
            response = connection.getresponse()
            payload = json.loads(response.read())
            self.assertEqual(response.status, 200)
            self.assertEqual(payload["workspace"], "guest")
            self.assertEqual([item["role"] for item in payload["chat"]["messages"][-2:]],
                             ["guest", "assistant"])
            self.assertEqual(payload["chat"]["messages"][-2]["text"], "Hey Hi")
            self.assertIn("Hello!", payload["chat"]["messages"][-1]["text"])
            self.assertNotIn("describe what is happening", payload["chat"]["messages"][-1]["text"])
            self.assertIsNone(payload["chat"]["pending"])
            self.assertEqual(payload["requests"], [])
            self.assertFalse(payload["chat"]["submitted"])
            self.assertFalse(payload["chat"]["persisted"])
        finally:
            connection.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_qa_join_code_creates_independent_cookies_with_shared_http_state(self):
        status, _, raw = self.dispatch("/api/qa/scenario", method="POST", body=b"{}")
        self.assertEqual(status, 200)
        code = json.loads(raw)["scenario_code"]

        def join(role):
            status, headers, body = self.dispatch(
                "/api/qa/select", method="POST",
                body=json.dumps({"role": role, "scenario_code": code}).encode())
            self.assertEqual(status, 200, body.decode())
            self.assertIn("Set-Cookie", headers)
            return headers["Set-Cookie"].split(";", 1)[0]

        guest_cookie, reception_cookie, housekeeping_cookie = map(
            join, ("guest", "reception", "housekeeping"))
        self.assertEqual(len({guest_cookie, reception_cookie, housekeeping_cookie}), 3)

        def act(path, data, cookie):
            status, _, raw_result = self.dispatch(
                path, method="POST", body=json.dumps(data).encode(), cookie=cookie)
            self.assertEqual(status, 200, raw_result.decode())
            return json.loads(raw_result)

        proposal = act("/api/message", {"text": "Please bring extra towels."}, guest_cookie)
        self.assertEqual(proposal["chat"]["state"], "awaiting_confirmation")
        act("/api/confirm", {"revision": proposal["chat"]["pending"]["revision"]}, guest_cookie)
        reception = act("/api/session", {}, reception_cookie)
        self.assertEqual(reception["workspace"], "reception")
        self.assertEqual(reception["requests"][0]["status"], "received")
        request_id = reception["requests"][0]["request_id"]
        act("/api/assign", {"request_id": request_id}, reception_cookie)
        housekeeping = act("/api/session", {}, housekeeping_cookie)
        self.assertEqual(housekeeping["workspace"], "housekeeping")
        self.assertEqual(housekeeping["requests"][0]["status"], "assigned")
        for action in ("acknowledge", "start", "resolve"):
            act("/api/staff-action", {"action": action, "request_id": request_id},
                housekeeping_cookie)
        guest_after_reload = act("/api/session", {}, guest_cookie)
        self.assertEqual(guest_after_reload["requests"][0]["status"], "resolved")
        denied, _, _ = self.dispatch(
            "/api/staff-action", method="POST",
            body=json.dumps({"action": "resolve", "request_id": request_id}).encode(),
            cookie=guest_cookie)
        self.assertEqual(denied, 403)

    def test_real_http_greeting_prefix_still_creates_guarded_ac_proposal(self):
        server = make_server(port=0, enable_local_qa=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        connection = http.client.HTTPConnection(LOOPBACK, server.server_port, timeout=3)
        origin = f"http://{LOOPBACK}:{server.server_port}"
        try:
            connection.request("POST", "/api/session", body=b"{}", headers={
                "Content-Type": "application/json", "Origin": origin,
            })
            initial = connection.getresponse()
            self.assertEqual(initial.status, 200)
            cookie = initial.getheader("Set-Cookie").split(";", 1)[0]
            initial.read()
            connection.request("POST", "/api/message", body=b'{"text":"Hi, my AC isn\'t cooling"}', headers={
                "Content-Type": "application/json", "Origin": origin, "Cookie": cookie,
            })
            response = connection.getresponse()
            payload = json.loads(response.read())
            self.assertEqual(response.status, 200)
            self.assertEqual(payload["chat"]["pending"]["summary"]["department"], "Maintenance")
            self.assertFalse(payload["chat"]["submitted"])
            self.assertFalse(payload["chat"]["persisted"])
            self.assertEqual(payload["requests"], [])
        finally:
            connection.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_browser_chat_submit_and_error_feedback_preserve_input(self):
        result = subprocess.run(
            ["node", str(ROOT / "tests" / "guest_chat_app.cjs")],
            cwd=ROOT, capture_output=True, text=True, timeout=20, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("passed", result.stdout)

    def test_text_ai_consent_is_session_bound_server_side_and_guest_only(self):
        class MockChatProvider:
            def __init__(self):
                self.calls = []

            def reply(self, text, *, previous_chat_id=None):
                self.calls.append((text, previous_chat_id))
                return "mock-chat-1", "Hello! I’m happy to help with your stay."

        provider = MockChatProvider()
        private_key = "private-placeholder-never-returned-or-used-by-test"
        demo = GuestChatDemo(chat_provider=provider)
        server = make_server(
            demo=demo, port=0, enable_local_qa=True, enable_vapi_chat=True,
            chat_environment={
                "ROOMAY_VAPI_CHAT_PRIVATE_KEY": private_key,
                "ROOMAY_VAPI_CHAT_ASSISTANT_ID": "assistant-test",
            },
        )
        try:
            status, headers, initial = self.dispatch(
                "/api/session", method="POST", body=b"{}", server=server)
            self.assertEqual(status, 200)
            cookie = headers["Set-Cookie"].split(";", 1)[0]
            self.assertNotIn(private_key, initial.decode("utf-8"))

            # A configured provider does not receive messages before explicit
            # per-session guest consent.
            status, _, unconsented = self.dispatch(
                "/api/message", method="POST",
                body=json.dumps({"text": "What's good, Remi?"}).encode(),
                cookie=cookie, server=server)
            self.assertEqual(status, 200)
            self.assertFalse(provider.calls)
            self.assertNotIn(private_key, unconsented.decode("utf-8"))

            status, _, consented = self.dispatch(
                "/api/chat/consent", method="POST",
                body=b'{"enabled":true}', cookie=cookie, server=server)
            self.assertEqual(status, 200)
            self.assertTrue(json.loads(consented)["chat"]["ai_chat"]["consented"])
            status, _, reply = self.dispatch(
                "/api/message", method="POST",
                body=json.dumps({"text": "What's good, Remi?"}).encode(),
                cookie=cookie, server=server)
            self.assertEqual(status, 200)
            self.assertEqual(len(provider.calls), 1)
            self.assertNotIn(private_key, reply.decode("utf-8"))

            self.dispatch("/api/qa/select", method="POST",
                          body=b'{"role":"housekeeping"}', cookie=cookie, server=server)
            status, _, denied = self.dispatch(
                "/api/chat/consent", method="POST",
                body=b'{"enabled":false}', cookie=cookie, server=server)
            self.assertEqual(status, 403)
            self.assertNotIn(private_key, denied.decode("utf-8"))
        finally:
            server.server_close()

    def dispatch(self, path, *, method="GET", body=None, cookie=None,
                 origin=None, host=None, server=None):
        target = server or self.server
        target_origin = f"http://{LOOPBACK}:{target.server_port}"
        headers = [f"Host: {host or f'{LOOPBACK}:{target.server_port}'}"]
        if body is not None:
            headers.extend(("Content-Type: application/json",
                            f"Origin: {origin or target_origin}",
                            f"Content-Length: {len(body)}"))
        if cookie:
            headers.append("Cookie: " + cookie)
        request = (f"{method} {path} HTTP/1.1\r\n" + "\r\n".join(headers)
                   + "\r\n\r\n").encode("ascii") + (body or b"")

        class MemoryWriter:
            def __init__(self):
                self.buffer = io.BytesIO()
                self.closed = False

            def write(self, value):
                return self.buffer.write(value)

            def flush(self):
                pass

            def close(self):
                self.closed = True

        class MemoryConnection:
            def __init__(self, request_bytes):
                self.reader = io.BytesIO(request_bytes)
                self.writer = MemoryWriter()

            def makefile(self, mode, buffering=None):
                return self.reader if "r" in mode else self.writer

            def close(self):
                pass

        connection = MemoryConnection(request)
        class MemoryHandler(target.RequestHandlerClass):
            wbufsize = 1

        handler = MemoryHandler(connection, (LOOPBACK, target.server_port), target)
        output = connection.writer.buffer.getvalue().decode("iso-8859-1")
        head, _, response_body = output.partition("\r\n\r\n")
        lines = head.split("\r\n")
        status = int(lines[0].split(" ", 2)[1])
        response_headers = {}
        for line in lines[1:]:
            if ":" in line:
                name, value = line.split(":", 1)
                response_headers[name.strip()] = value.strip()
        return status, response_headers, response_body.encode("iso-8859-1")

    def test_separate_guest_page_has_no_staff_navigation_or_development_copy(self):
        self.assertEqual(self.server.server_address[0], LOOPBACK)
        status, headers, html = self.dispatch("/")
        self.assertEqual(status, 302)
        self.assertEqual(headers["Location"], "/stay")
        status, headers, html = self.dispatch("/stay")
        text = html.decode("utf-8")
        self.assertEqual(status, 200)
        self.assertIn("The Linden House", text)
        self.assertIn("My Stay", text)
        self.assertNotIn("/staff/reception", text)
        self.assertNotIn("/staff/housekeeping", text)
        self.assertNotIn("SYNTHETIC DEMO", text)
        self.assertNotIn("FICTIONAL SESSION", text)
        self.assertNotIn("DEMO VIEW", text)
        self.assertIn("default-src 'self'", headers["Content-Security-Policy"])
        self.assertIn('src="/voice_intake.js"', text)
        self.assertIn("aria-live=\"polite\"", text)
        self.assertIn("id=\"voice-button\"", text)
        self.assertIn("id=\"voice-remote-consent\"", text)
        self.assertIn('id="call-remi"', text)
        self.assertIn('id="request-heading">Chat with Remi', text)
        self.assertIn('id="send-button" class="send-button" type="submit" aria-label="Send message"', text)
        self.assertIn('id="chat-ai-consent" class="chat-ai-consent" hidden', text)
        composer = text.split('<div class="composer-entry">', 1)[1].split('</div>', 1)[0]
        self.assertLess(composer.index('id="voice-button"'), composer.index('id="send-button"'))
        self.assertIn("Enter to send · Shift + Enter for a new line", text)
        self.assertIn("Vapi chat conversations are logged", text)
        self.assertIn('aria-haspopup="dialog"', text)
        self.assertIn('id="remi-call-overlay" class="remi-dialog-overlay" hidden', text)
        self.assertIn('role="dialog" aria-modal="true"', text)
        self.assertIn('id="remi-call-duration"', text)
        self.assertIn('id="close-remi"', text)
        self.assertIn('state="idle" paused', text)
        self.assertIn('id="end-remi"', text)
        self.assertIn('id="mute-remi"', text)
        self.assertIn('id="remi-orb"', text)
        self.assertIn('src="/roomay-orb.js"', text)
        self.assertIn("Vapi may process or retain call metadata", text)
        self.assertIn("provider's privacy terms apply", text)
        status, headers, app_js = self.dispatch("/app.js")
        self.assertEqual(status, 200)
        self.assertIn("text/javascript", headers["Content-Type"])
        self.assertIn("textContent", app_js.decode("utf-8"))
        self.assertIn("Send message", app_js.decode("utf-8"))
        self.assertNotIn('"Send request"', app_js.decode("utf-8"))
        status, headers, voice_js = self.dispatch("/voice_intake.js")
        self.assertEqual(status, 200)
        self.assertIn("text/javascript", headers["Content-Type"])
        voice_source = voice_js.decode("utf-8")
        self.assertIn('beginRecognition("on-device")', voice_source)
        self.assertIn('beginRecognition("browser-managed")', voice_source)
        self.assertIn('showConsent()', voice_source)
        self.assertIn('id="voice-remote-dialog" class="voice-consent-overlay" hidden', text)
        self.assertIn('aria-label="Dictate a message"', text)
        self.assertNotIn('id="voice-help"', text)
        self.assertNotIn('Use my browser’s speech service if needed', text)
        self.assertIn('selectedMode = mode', voice_source)
        self.assertIn('recognition.processLocally = mode === "on-device"', voice_source)
        status, headers, orb = self.dispatch("/roomay-orb.js")
        self.assertEqual(status, 200)
        self.assertIn("text/javascript", headers["Content-Type"])
        self.assertIn("customElements.define('roomay-orb'", orb.decode("utf-8"))
        self.assertIn("prefers-reduced-motion", orb.decode("utf-8"))
        self.assertNotIn("getUserMedia", orb.decode("utf-8"))
        self.assertNotIn("preview/", html.decode("utf-8"))

    def test_voice_calls_are_off_by_default_and_sdk_is_not_loaded(self):
        status, _, html = self.dispatch("/stay")
        self.assertEqual(status, 200)
        self.assertNotIn('<script src="/vapi_sdk.js"', html.decode("utf-8"))
        status, _, _ = self.dispatch("/api/voice/config", method="POST", body=b"{}")
        self.assertEqual(status, 404)
        status, _, _ = self.dispatch("/vapi_sdk.js")
        self.assertEqual(status, 404)

    def test_opt_in_voice_config_is_session_scoped_public_only_and_bounded(self):
        env = {
            "ROOMAY_VAPI_PUBLIC_KEY": "pk_local_example_public_key_123",
            "ROOMAY_VAPI_TEST_ASSISTANT_ID": "assistant-test-201",
            "ROOMAY_VAPI_TEST_ASSISTANT_VOICE": "remi",
            "ROOMAY_VAPI_TEST_LLM_PROVIDER": "openai",
            "ROOMAY_VAPI_TEST_LLM_MODEL": "gpt-4o",
            "VAPI_PRIVATE_API_KEY": "must-not-be-read-or-returned",
        }
        server = make_server(port=0, enable_local_qa=True,
                             enable_vapi_web_call=True, vapi_environment=env)
        try:
            status, _, html = self.dispatch("/stay", server=server)
            self.assertEqual(status, 200)
            self.assertIn('<script src="/vapi_sdk.js" defer></script>', html.decode("utf-8"))
            status, _, _ = self.dispatch("/api/voice/config", method="POST",
                                         body=b"{}", server=server)
            self.assertEqual(status, 401)
            status, session_headers, _ = self.dispatch("/api/session", method="POST",
                                                       body=b"{}", server=server)
            cookie = session_headers["Set-Cookie"].split(";", 1)[0]
            status, _, body = self.dispatch("/api/voice/config", method="POST",
                                            body=b"{}", cookie=cookie, server=server)
            self.assertEqual(status, 200)
            config = json.loads(body)
            self.assertEqual(config["assistantId"], "assistant-test-201")
            self.assertEqual(config["assistantLabel"], "Remi")
            self.assertEqual(config["modelProvider"], "openai")
            self.assertEqual(config["modelName"], "gpt-4o")
            self.assertEqual(config["maxDurationSeconds"], 180)
            self.assertEqual(config["publicKey"], env["ROOMAY_VAPI_PUBLIC_KEY"])
            self.assertNotIn("must-not-be-read-or-returned", body.decode("utf-8"))
            status, _, claim = self.dispatch("/api/voice/claim", method="POST",
                                             body=b"{}", cookie=cookie, server=server)
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(claim)["calls_remaining"], 2)
            self.assertEqual(self.dispatch("/api/voice/claim", method="POST",
                                           body=b"{}", cookie=cookie, server=server)[0], 409)
            self.dispatch("/api/voice/release", method="POST", body=b"{}",
                          cookie=cookie, server=server)
            for _ in range(2):
                self.assertEqual(self.dispatch("/api/voice/claim", method="POST",
                                               body=b"{}", cookie=cookie, server=server)[0], 200)
                self.dispatch("/api/voice/release", method="POST", body=b"{}",
                              cookie=cookie, server=server)
            self.assertEqual(self.dispatch("/api/voice/claim", method="POST",
                                           body=b"{}", cookie=cookie, server=server)[0], 429)
            self.dispatch("/api/qa/select", method="POST",
                          body=b'{"role":"housekeeping"}', cookie=cookie, server=server)
            self.assertEqual(self.dispatch("/api/voice/config", method="POST",
                                           body=b"{}", cookie=cookie, server=server)[0], 403)
            self.assertEqual(self.dispatch("/api/voice/config", method="POST",
                                           body=b"{}", cookie=cookie,
                                           origin="http://attacker.invalid", server=server)[0], 403)
        finally:
            server.server_close()

    def test_voice_web_call_requires_qa_and_valid_assistant_settings(self):
        with self.assertRaisesRegex(ValueError, "requires_local_qa"):
            make_server(port=0, enable_vapi_web_call=True, vapi_environment={})
        bad_envs = [
            {"ROOMAY_VAPI_PUBLIC_KEY": "short", "ROOMAY_VAPI_TEST_ASSISTANT_ID": "assistant",
             "ROOMAY_VAPI_TEST_ASSISTANT_VOICE": "remi",
             "ROOMAY_VAPI_TEST_LLM_PROVIDER": "openai", "ROOMAY_VAPI_TEST_LLM_MODEL": "gpt-4o"},
            {"ROOMAY_VAPI_PUBLIC_KEY": "pk_example_0123456789", "ROOMAY_VAPI_TEST_ASSISTANT_ID": "assistant",
             "ROOMAY_VAPI_TEST_ASSISTANT_VOICE": "mary",
             "ROOMAY_VAPI_TEST_LLM_PROVIDER": "openai", "ROOMAY_VAPI_TEST_LLM_MODEL": "gpt-4o"},
            {"ROOMAY_VAPI_PUBLIC_KEY": "pk_example_0123456789", "ROOMAY_VAPI_TEST_ASSISTANT_ID": "assistant",
             "ROOMAY_VAPI_TEST_ASSISTANT_VOICE": "remi"},
        ]
        for env in bad_envs:
            with self.subTest(env=env):
                server = make_server(port=0, enable_local_qa=True,
                                     enable_vapi_web_call=True, vapi_environment=env)
                try:
                    self.assertFalse(server.enable_vapi_web_call)
                    self.assertEqual(self.dispatch("/api/voice/config", method="POST",
                                                    body=b"{}", server=server)[0], 404)
                finally:
                    server.server_close()
        status, headers, call_js = self.dispatch("/vapi_call.js")
        self.assertEqual(status, 200)
        self.assertIn("text/javascript", headers["Content-Type"])
        self.assertIn("api/voice/config", call_js.decode("utf-8"))

    def test_staff_routes_require_matching_server_session_and_show_separate_pages(self):
        status, _, _ = self.dispatch("/staff/reception")
        self.assertEqual(status, 401)
        status, headers, _ = self.dispatch("/api/session", method="POST", body=b"{}")
        self.assertEqual(status, 200)
        guest_cookie = headers["Set-Cookie"].split(";", 1)[0]
        status, _, body = self.dispatch("/staff/reception", cookie=guest_cookie)
        self.assertEqual(status, 403)
        self.assertNotIn("Room board", body.decode("utf-8"))

        status, _, result = self.dispatch(
            "/api/qa/select", method="POST", body=b'{"role":"reception"}', cookie=guest_cookie)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(result)["path"], "/staff/reception")
        status, _, html = self.dispatch("/staff/reception", cookie=guest_cookie)
        self.assertEqual(status, 200)
        self.assertIn("Reception Dashboard", html.decode("utf-8"))
        status, _, _ = self.dispatch("/staff/housekeeping", cookie=guest_cookie)
        self.assertEqual(status, 403)

        self.dispatch("/api/qa/select", method="POST", body=b'{"role":"housekeeping"}', cookie=guest_cookie)
        status, _, html = self.dispatch("/staff/housekeeping", cookie=guest_cookie)
        self.assertEqual(status, 200)
        self.assertIn("Housekeeping", html.decode("utf-8"))
        self.assertNotIn("href=\"/staff/reception\"", html.decode("utf-8"))

    def test_internal_qa_switcher_is_opt_in_and_not_product_navigation(self):
        status, _, html = self.dispatch("/__qa/")
        self.assertEqual(status, 200)
        self.assertIn("does not sign you in", html.decode("utf-8"))
        self.assertIn('class="brand" href="/__qa/"', html.decode("utf-8"))
        self.assertNotIn("/__qa/", self.dispatch("/stay")[2].decode("utf-8"))
        server = make_server(port=0)
        try:
            self.assertFalse(getattr(server, "enable_local_qa", False))
            # The default non-QA server does not register the role selection route.
            connection = self.dispatch("/__qa/", server=server)
            self.assertEqual(connection[0], 404)
            status, session_headers, _ = self.dispatch(
                "/api/session", method="POST", body=b"{}", server=server)
            self.assertEqual(status, 200)
            cookie = session_headers["Set-Cookie"].split(";", 1)[0]
            status, _, denied = self.dispatch("/staff/housekeeping", cookie=cookie, server=server)
            self.assertEqual(status, 403)
            self.assertNotIn("/__qa/", denied.decode("utf-8"))
            self.assertIn('href="/stay"', denied.decode("utf-8"))
        finally:
            server.server_close()

    def test_local_role_mismatch_recovers_without_losing_resolved_status(self):
        status, headers, body = self.dispatch("/api/session", method="POST", body=b"{}")
        self.assertEqual(status, 200)
        cookie = headers["Set-Cookie"].split(";", 1)[0]

        def act(path, payload):
            status, _, result = self.dispatch(
                path, method="POST", body=json.dumps(payload).encode(), cookie=cookie)
            self.assertEqual(status, 200, result.decode())
            return json.loads(result)

        proposal = act("/api/message", {"text": "Extra towels for room 205, please."})
        act("/api/confirm", {"revision": proposal["chat"]["pending"]["revision"]})
        act("/api/qa/select", {"role": "reception"})
        reception = act("/api/session", {})
        request_id = reception["requests"][0]["request_id"]
        act("/api/assign", {"request_id": request_id})
        act("/api/qa/select", {"role": "housekeeping"})
        for action in ("acknowledge", "start", "resolve"):
            act("/api/staff-action", {"action": action, "request_id": request_id})

        # Opening the guest route in the wrong test role remains denied, but
        # gives local QA a recovery path. Selecting Guest reuses the same
        # server-side session, so the completed request and audit stay intact.
        status, _, denied = self.dispatch("/stay", cookie=cookie)
        self.assertEqual(status, 403)
        self.assertIn("/__qa/", denied.decode("utf-8"))
        status, _, qa_page = self.dispatch("/__qa/", cookie=cookie)
        self.assertEqual(status, 200)
        self.assertIn("does not sign you in", qa_page.decode("utf-8"))
        act("/api/qa/select", {"role": "guest"})
        status, _, guest_page = self.dispatch("/stay", cookie=cookie)
        self.assertEqual(status, 200)
        status, _, refreshed = self.dispatch(
            "/api/session", method="POST", body=b"{}", cookie=cookie)
        self.assertEqual(status, 200)
        restored = json.loads(refreshed)
        self.assertEqual(restored["workspace"], "guest")
        self.assertEqual(restored["requests"][0]["status"], "resolved")
        self.assertIn('data-workspace="guest"', guest_page.decode("utf-8"))

    def test_browser_session_stays_server_side_and_never_returns_internal_contract(self):
        status, headers, body = self.dispatch("/api/session", method="POST", body=b"{}")
        self.assertEqual(status, 200)
        cookie = headers["Set-Cookie"]
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Strict", cookie)
        cookie_pair = cookie.split(";", 1)[0]
        session_view = json.loads(body)
        self.assertNotIn("session_id", session_view)
        self.assertEqual(session_view["workspace"], "guest")
        self.assertFalse(session_view["chat"]["submitted"])
        self.assertNotIn("rooms", session_view)
        self.assertNotIn("metrics", session_view)
        self.assertNotIn("housekeeping", session_view)

        message = json.dumps({"text": "Abeg, my AC no dey cool for room 205."}).encode()
        status, _, body = self.dispatch("/api/message", method="POST", body=message,
                                        cookie=cookie_pair)
        self.assertEqual(status, 200)
        view = json.loads(body)
        self.assertEqual(view["workspace"], "guest")
        self.assertEqual(view["chat"]["pending"]["summary"]["department"], "Maintenance")
        self.assertNotIn("internal", view)
        self.assertNotIn("request_plan", json.dumps(view))

    def test_cross_origin_and_host_spoofing_are_rejected(self):
        body = b"{}"
        status, _, _ = self.dispatch("/api/session", method="POST", body=body,
                                     origin="http://example.invalid")
        self.assertEqual(status, 403)
        status, _, _ = self.dispatch("/", host=f"example.invalid:{self.server.server_port}")
        self.assertEqual(status, 403)

    def test_protected_action_requires_session_cookie(self):
        status, _, _ = self.dispatch("/api/confirm", method="POST", body=b'{"revision":1}')
        self.assertEqual(status, 401)

    def test_complete_browser_journey_is_server_scoped_and_survives_reload(self):
        status, headers, body = self.dispatch("/api/session", method="POST", body=b"{}")
        self.assertEqual(status, 200)
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        state = json.loads(body)
        self.assertEqual(state["workspace"], "guest")
        self.assertEqual(state["property_name"], "The Linden House")
        self.assertTrue(state["example_property"])
        self.assertEqual(state["guest"]["room"], "205")
        self.assertEqual(state["guest"]["stay_status"], "checked_in")
        self.assertEqual(state["guest"]["name"], "Amara Okafor")
        self.assertEqual(set(state), {"workspace", "property_name", "example_property", "guest", "requests", "chat", "reception_contact"})

        status, _, body = self.dispatch(
            "/api/message", method="POST",
            body=json.dumps({"text": "Please bring extra towels to room 205."}).encode(),
            cookie=cookie,
        )
        self.assertEqual(status, 200)
        state = json.loads(body)
        self.assertEqual(state["chat"]["pending"]["summary"]["department"], "Housekeeping")
        revision = state["chat"]["pending"]["revision"]
        self.assertNotIn("rooms", state)
        self.assertNotIn("metrics", state)
        status, _, body = self.dispatch(
            "/api/confirm", method="POST",
            body=json.dumps({"revision": revision}).encode(), cookie=cookie,
        )
        self.assertEqual(status, 200)
        state = json.loads(body)
        self.assertEqual(state["requests"][0]["status"], "received")
        self.assertIn("has not been sent to hotel staff", state["chat"]["messages"][-1]["text"])
        def act(path, payload):
            status, _, result = self.dispatch(
                path, method="POST", body=json.dumps(payload).encode(), cookie=cookie)
            self.assertEqual(status, 200, result.decode())
            return json.loads(result)

        self.assertEqual(act("/api/qa/select", {"role": "reception"})["path"], "/staff/reception")
        state = act("/api/session", {})
        self.assertEqual(state["workspace"], "reception")
        self.assertEqual(state["metrics"]["in_house"], 2)
        self.assertEqual(state["metrics"]["arrivals"], 1)
        self.assertEqual(state["metrics"]["departures"], 1)
        self.assertEqual(state["metrics"]["maintenance_blocked_rooms"], 1)
        self.assertNotIn("guest", state)
        request_id = state["requests"][0]["request_id"]
        state = act("/api/assign", {"request_id": request_id})
        self.assertEqual(state["requests"][0]["status"], "assigned")
        self.assertIn("Chidi Nwosu", json.dumps(state["in_house"]))
        self.assertEqual(act("/api/qa/select", {"role": "housekeeping"})["path"], "/staff/housekeeping")
        state = act("/api/session", {})
        self.assertEqual(state["workspace"], "housekeeping")
        self.assertNotIn("guest", state)
        self.assertNotIn("metrics", state)
        self.assertNotIn("arrivals", state)
        self.assertEqual(state["requests"][0]["room"], "205")
        self.assertNotIn("Amara Okafor", json.dumps(state))
        for action, expected in (("acknowledge", "acknowledged"),
                                 ("start", "in_progress"), ("resolve", "resolved")):
            state = act("/api/staff-action", {"action": action, "request_id": request_id})
            self.assertEqual(state["requests"][0]["status"], expected)
        self.assertEqual(act("/api/qa/select", {"role": "guest"})["path"], "/stay")
        denied = self.dispatch("/api/staff-action", method="POST",
                               body=json.dumps({"action": "resolve", "request_id": request_id}).encode(),
                               cookie=cookie)
        self.assertEqual(denied[0], 403)

        status, _, body = self.dispatch("/api/session", method="POST", body=b"{}", cookie=cookie)
        self.assertEqual(status, 200)
        reloaded = json.loads(body)
        self.assertEqual(reloaded["workspace"], "guest")
        self.assertEqual(reloaded["requests"][0]["status"], "resolved")
        self.assertEqual(reloaded["requests"][0]["department"], "Housekeeping")
        self.assertNotIn("request_id", json.dumps(reloaded))
        self.assertNotIn("operation_signature", json.dumps(reloaded))
        self.assertNotIn("guest_id", json.dumps(reloaded))
        self.assertIn("Request updates are limited to this example session", (ROOT / "tools/guest_chat_demo_assets/index.html").read_text())

    def test_example_sessions_do_not_share_guest_requests_or_chat_state(self):
        status, first_headers, first_body = self.dispatch(
            "/api/session", method="POST", body=b"{}")
        self.assertEqual(status, 200)
        first_cookie = first_headers["Set-Cookie"].split(";", 1)[0]
        status, _, first_body = self.dispatch(
            "/api/message", method="POST",
            body=json.dumps({"text": "Please bring extra towels to room 205."}).encode(),
            cookie=first_cookie,
        )
        self.assertEqual(status, 200)
        pending = json.loads(first_body)["chat"]["pending"]
        status, _, first_body = self.dispatch(
            "/api/confirm", method="POST",
            body=json.dumps({"revision": pending["revision"]}).encode(),
            cookie=first_cookie,
        )
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(first_body)["requests"][0]["status"], "received")

        status, second_headers, second_body = self.dispatch(
            "/api/session", method="POST", body=b"{}")
        self.assertEqual(status, 200)
        second_cookie = second_headers["Set-Cookie"].split(";", 1)[0]
        second = json.loads(second_body)
        self.assertEqual(second["workspace"], "guest")
        self.assertEqual(second["requests"], [])
        self.assertEqual(len(second["chat"]["messages"]), 1)
        self.assertEqual(second["chat"]["state"], "ready")

    def test_browser_refuses_actions_outside_server_selected_test_role(self):
        status, headers, _ = self.dispatch("/api/session", method="POST", body=b"{}")
        self.assertEqual(status, 200)
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        status, _, body = self.dispatch("/api/assign", method="POST",
                                        body=b'{"request_id":"unknown"}', cookie=cookie)
        self.assertEqual(status, 403)
        self.assertEqual(json.loads(body)["error"], "demo_reception_role_required")
        status, _, body = self.dispatch(
            "/api/qa/select", method="POST", body=b'{"role":"owner"}', cookie=cookie)
        self.assertEqual(status, 400)
if __name__ == "__main__":
    unittest.main()
