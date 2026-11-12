"""Server-side Vapi Chat client for the loopback-only Roomay QA journey.

The Chat API is a paid/beta provider boundary. This module never runs on import;
callers must explicitly construct a client after local operator opt-in. It is
conversation-only and has no hotel action or persistence methods.
"""

from __future__ import annotations

import json
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


CHAT_URL = "https://api.vapi.ai/chat"
MAX_INPUT_CHARS = 1000
MAX_OUTPUT_CHARS = 4000
MAX_RESPONSE_BYTES = 64 * 1024
CHAT_TIMEOUT_SECONDS = 12
_CHAT_ID = re.compile(r"^[A-Za-z0-9_-]{1,200}$")


class VapiChatUnavailable(RuntimeError):
    """Sanitized provider failure; deliberately contains no response details."""


def _valid_text(value, limit):
    return isinstance(value, str) and bool(value.strip()) and len(value) <= limit


class VapiChatClient:
    """Small bounded client for Vapi's documented POST /chat endpoint."""

    def __init__(self, private_key, assistant_id, *, opener=urlopen):
        if not isinstance(private_key, str) or len(private_key.strip()) < 20:
            raise ValueError("invalid_vapi_chat_configuration")
        if not isinstance(assistant_id, str) or not _CHAT_ID.fullmatch(assistant_id):
            raise ValueError("invalid_vapi_chat_configuration")
        self._private_key = private_key.strip()
        self._assistant_id = assistant_id
        self._opener = opener

    def reply(self, text, *, previous_chat_id=None):
        if not _valid_text(text, MAX_INPUT_CHARS):
            raise VapiChatUnavailable("invalid_input")
        if previous_chat_id is not None and (
                not isinstance(previous_chat_id, str)
                or not _CHAT_ID.fullmatch(previous_chat_id)):
            raise VapiChatUnavailable("invalid_context")

        payload = {"assistantId": self._assistant_id, "input": text.strip()}
        if previous_chat_id is not None:
            payload["previousChatId"] = previous_chat_id
        request = Request(
            CHAT_URL,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": "Bearer " + self._private_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with self._opener(request, timeout=CHAT_TIMEOUT_SECONDS) as response:
                status = response.getcode()
                raw = response.read(MAX_RESPONSE_BYTES + 1)
            if status != 200 or len(raw) > MAX_RESPONSE_BYTES:
                raise VapiChatUnavailable("provider_unavailable")
            body = json.loads(raw.decode("utf-8"))
            if not isinstance(body, dict):
                raise VapiChatUnavailable("malformed_response")
            chat_id = body.get("id")
            output = body.get("output")
            if (not isinstance(chat_id, str) or not _CHAT_ID.fullmatch(chat_id)
                    or not isinstance(output, list)):
                raise VapiChatUnavailable("malformed_response")
            replies = [
                item.get("content") for item in output
                if isinstance(item, dict) and item.get("role") == "assistant"
                and isinstance(item.get("content"), str)
            ]
            answer = "\n".join(part.strip() for part in replies if part.strip())
            if not answer or len(answer) > MAX_OUTPUT_CHARS:
                raise VapiChatUnavailable("malformed_response")
            return chat_id, answer
        except VapiChatUnavailable:
            raise
        except (HTTPError, URLError, TimeoutError, OSError, UnicodeDecodeError,
                json.JSONDecodeError, ValueError, TypeError):
            # Never include provider response bodies, URLs, credentials or exception
            # strings in UI/log output. There is intentionally no automatic retry.
            raise VapiChatUnavailable("provider_unavailable") from None
