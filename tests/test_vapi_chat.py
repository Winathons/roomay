"""Mocked Vapi Chat API contract tests; never contact Vapi."""

import json
import unittest

from tools.vapi_chat import (
    CHAT_TIMEOUT_SECONDS, CHAT_URL, VapiChatClient, VapiChatUnavailable,
)


class FakeResponse:
    def __init__(self, value, status=200):
        self.value = value
        self.status = status
        self.closed = False

    def __enter__(self): return self
    def __exit__(self, *_args): self.closed = True
    def getcode(self): return self.status
    def read(self, limit): return self.value[:limit]


class VapiChatClientTests(unittest.TestCase):
    def test_posts_to_documented_endpoint_with_private_key_only_server_side(self):
        response = FakeResponse(json.dumps({
            "id": "chat_abc123",
            "output": [{"role": "assistant", "content": "Hello, welcome!"}],
        }).encode())
        captured = {}

        def opener(request, *, timeout):
            captured["url"] = request.full_url
            captured["headers"] = dict(request.header_items())
            captured["body"] = json.loads(request.data)
            captured["timeout"] = timeout
            return response

        client = VapiChatClient("private-vapi-key-for-tests-only", "assistant_test", opener=opener)
        chat_id, text = client.reply("Hello, Remi")
        self.assertEqual(captured["url"], CHAT_URL)
        self.assertEqual(captured["body"], {"assistantId": "assistant_test", "input": "Hello, Remi"})
        self.assertIn("Authorization", captured["headers"])
        self.assertEqual(captured["timeout"], CHAT_TIMEOUT_SECONDS)
        self.assertEqual((chat_id, text), ("chat_abc123", "Hello, welcome!"))
        self.assertTrue(response.closed)
        self.assertNotIn("private-vapi-key", text)

    def test_previous_chat_id_is_the_only_provider_history_pointer(self):
        response = FakeResponse(b'{"id":"chat_next","output":[{"role":"assistant","content":"I remember."}]}')
        captured = {}
        def opener(request, *, timeout):
            captured.update(json.loads(request.data))
            return response
        client = VapiChatClient("private-vapi-key-for-tests-only", "assistant_test", opener=opener)
        client.reply("Follow up", previous_chat_id="chat_first")
        self.assertEqual(captured, {
            "assistantId": "assistant_test", "input": "Follow up",
            "previousChatId": "chat_first",
        })

    def test_timeout_and_provider_errors_are_sanitized_without_retry(self):
        calls = []
        def opener(_request, *, timeout):
            calls.append(timeout)
            raise TimeoutError("secret response and bearer token must not leak")
        client = VapiChatClient("private-vapi-key-for-tests-only", "assistant_test", opener=opener)
        with self.assertRaises(VapiChatUnavailable) as caught:
            client.reply("Hi")
        self.assertEqual(str(caught.exception), "provider_unavailable")
        self.assertEqual(calls, [CHAT_TIMEOUT_SECONDS])
        self.assertNotIn("secret", str(caught.exception))

    def test_malformed_provider_payloads_fail_closed(self):
        for body in (b"{}", b"not-json", b'{"id":"chat_1","output":[]}'):
            with self.subTest(body=body):
                client = VapiChatClient(
                    "private-vapi-key-for-tests-only", "assistant_test",
                    opener=lambda *_args, **_kwargs: FakeResponse(body),
                )
                with self.assertRaises(VapiChatUnavailable):
                    client.reply("What is up?")

    def test_invalid_configuration_context_and_message_are_rejected(self):
        for key, assistant in (("short", "assistant_test"),
                               ("private-vapi-key-for-tests-only", "bad id")):
            with self.subTest(assistant=assistant), self.assertRaises(ValueError):
                VapiChatClient(key, assistant)
        client = VapiChatClient("private-vapi-key-for-tests-only", "assistant_test",
                                opener=lambda *_args, **_kwargs: self.fail("must not call network"))
        for text, previous in (("", None), ("x" * 1001, None), ("Hi", "bad id")):
            with self.subTest(text=text[:8], previous=previous), self.assertRaises(VapiChatUnavailable):
                client.reply(text, previous_chat_id=previous)


if __name__ == "__main__":
    unittest.main()
