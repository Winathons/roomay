"""Minimal WSGI endpoint for Vapi custom TTS; no Workpeg route or dependency."""

import hmac
import hashlib
import json
import math
import os
import secrets
from dataclasses import dataclass, field

from .yarngpt import ProviderError, YarnConversationClient


VAPI_SAMPLE_RATES = frozenset((8000, 16000, 22050, 24000, 44100))
VOICE_ALIASES = frozenset(("mary", "remi", "umar"))
MAX_REQUEST_BYTES = 64 * 1024
MAX_TEXT_CHARS = 5000


@dataclass(frozen=True)
class VoiceConfig:
    vapi_bearer_token: str
    yarngpt_api_key: str
    voice_ids: dict
    default_voice: str = "mary"
    assistant_voice_map: dict = field(default_factory=dict)
    timeout_seconds: int = 20

    def validate(self):
        if not isinstance(self.vapi_bearer_token, str) or len(self.vapi_bearer_token) < 32:
            raise ValueError("vapi_bearer_token_must_be_32_chars")
        if not isinstance(self.yarngpt_api_key, str) or not self.yarngpt_api_key.strip():
            raise ValueError("yarngpt_api_key_required")
        if self.default_voice not in VOICE_ALIASES:
            raise ValueError("invalid_default_voice")
        if not isinstance(self.voice_ids, dict):
            raise ValueError("voice_ids_required")
        for alias in VOICE_ALIASES:
            value = self.voice_ids.get(alias)
            if (not isinstance(value, str) or not value.strip() or value != value.strip()
                    or len(value) > 128):
                raise ValueError("all_provider_voice_ids_required")
        if not isinstance(self.assistant_voice_map, dict):
            raise ValueError("invalid_assistant_voice_map")
        if any(not isinstance(key, str) or not key or not isinstance(value, str)
               or value not in VOICE_ALIASES
               for key, value in self.assistant_voice_map.items()):
            raise ValueError("invalid_assistant_voice_map")
        if isinstance(self.timeout_seconds, bool) or not isinstance(self.timeout_seconds, int) or not 1 <= self.timeout_seconds <= 60:
            raise ValueError("invalid_timeout")

    @classmethod
    def from_environment(cls, environ=None):
        env = os.environ if environ is None else environ
        try:
            assistant_map = json.loads(env.get("ROOMAY_VAPI_ASSISTANT_VOICE_MAP", "{}"))
            voice_ids = {
                "mary": env.get("YARNGPT_VOICE_MARY", ""),
                "remi": env.get("YARNGPT_VOICE_REMI", ""),
                "umar": env.get("YARNGPT_VOICE_UMAR", ""),
            }
        except (TypeError, ValueError):
            raise ValueError("invalid_voice_configuration") from None
        config = cls(
            vapi_bearer_token=env.get("ROOMAY_VAPI_BEARER_TOKEN", ""),
            yarngpt_api_key=env.get("YARNGPT_API_KEY", ""),
            voice_ids=voice_ids,
            default_voice=env.get("ROOMAY_TTS_DEFAULT_VOICE", "mary").lower(),
            assistant_voice_map=assistant_map,
            timeout_seconds=int(env.get("YARNGPT_TIMEOUT_SECONDS", "20")),
        )
        config.validate()
        return config


def _response(start_response, status, body, headers=None):
    payload = json.dumps(body, separators=(",", ":")).encode("utf-8")
    response_headers = [("Content-Type", "application/json; charset=utf-8"),
                        ("Content-Length", str(len(payload))), ("Cache-Control", "no-store")]
    if headers:
        response_headers.extend(headers)
    start_response(f"{status} {_STATUS_TEXT.get(status, 'Error')}", response_headers)
    return [payload]


_STATUS_TEXT = {
    200: "OK", 400: "Bad Request", 401: "Unauthorized", 405: "Method Not Allowed",
    413: "Payload Too Large", 429: "Too Many Requests", 500: "Internal Server Error",
    502: "Bad Gateway", 503: "Service Unavailable", 504: "Gateway Timeout",
}


def _parse_message(environ):
    raw_length = environ.get("CONTENT_LENGTH")
    if not raw_length or not raw_length.isdigit():
        raise ValueError("content_length_required")
    length = int(raw_length)
    if length <= 0:
        raise ValueError("empty_request")
    if length > MAX_REQUEST_BYTES:
        raise OverflowError("request_too_large")
    raw = environ["wsgi.input"].read(length)
    if len(raw) != length:
        raise ValueError("truncated_request")
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ValueError("invalid_json") from None
    if not isinstance(document, dict) or not isinstance(document.get("message"), dict):
        raise ValueError("invalid_request")
    message = document["message"]
    if message.get("type") != "voice-request":
        raise ValueError("invalid_message_type")
    text = message.get("text")
    if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT_CHARS:
        raise ValueError("invalid_text")
    rate = message.get("sampleRate")
    if isinstance(rate, bool) or not isinstance(rate, int) or rate not in VAPI_SAMPLE_RATES:
        raise ValueError("unsupported_sample_rate")
    timestamp = message.get("timestamp")
    if (isinstance(timestamp, bool) or not isinstance(timestamp, (int, float))
            or not math.isfinite(timestamp) or timestamp <= 0):
        raise ValueError("invalid_timestamp")
    assistant = message.get("assistant", {})
    if assistant is not None and not isinstance(assistant, dict):
        raise ValueError("invalid_assistant")
    assistant_id = assistant.get("id") if assistant else None
    if assistant_id is not None and (not isinstance(assistant_id, str) or not assistant_id
                                      or len(assistant_id) > 128):
        raise ValueError("invalid_assistant_id")
    call = message.get("call", {})
    if call is not None and not isinstance(call, dict):
        raise ValueError("invalid_call")
    call_id = call.get("id") if call else None
    if call_id is not None and (not isinstance(call_id, str) or not call_id or len(call_id) > 128):
        raise ValueError("invalid_call_id")
    return text.strip(), rate, assistant_id, call_id, timestamp


def create_app(config, client=None):
    """Create a Vapi custom-voice WSGI app; providers are injectable for tests."""
    config.validate()
    provider = client or YarnConversationClient(config.yarngpt_api_key, config.timeout_seconds)

    def app(environ, start_response):
        if environ.get("REQUEST_METHOD") != "POST":
            return _response(start_response, 405, {"error": "method_not_allowed"},
                             [("Allow", "POST")])
        if environ.get("PATH_INFO") not in ("/", "/synthesize"):
            return _response(start_response, 404, {"error": "not_found"})
        if environ.get("CONTENT_TYPE", "").split(";", 1)[0].strip().lower() != "application/json":
            return _response(start_response, 400, {"error": "invalid_content_type"})
        supplied = environ.get("HTTP_AUTHORIZATION", "")
        prefix = "Bearer "
        provided_token = supplied[len(prefix):] if supplied.startswith(prefix) else ""
        if not hmac.compare_digest(provided_token.encode("utf-8"),
                                   config.vapi_bearer_token.encode("utf-8")):
            return _response(start_response, 401, {"error": "unauthorized"},
                             [("WWW-Authenticate", "Bearer")])
        try:
            text, sample_rate, assistant_id, call_id, timestamp = _parse_message(environ)
        except OverflowError:
            return _response(start_response, 413, {"error": "request_too_large"})
        except ValueError as error:
            return _response(start_response, 400, {"error": str(error)})

        alias = config.assistant_voice_map.get(assistant_id, config.default_voice)
        voice_id = config.voice_ids[alias]
        if call_id is None:
            idempotency_key = secrets.token_hex(32)
        else:
            key_material = "\0".join((call_id, str(timestamp), assistant_id or "",
                                       voice_id, text)).encode("utf-8")
            idempotency_key = hmac.new(
                config.yarngpt_api_key.encode("utf-8"), key_material, hashlib.sha256
            ).hexdigest()
        try:
            stream = provider.open_audio(text, voice_id, sample_rate,
                                         idempotency_key=idempotency_key)
            first = next(stream, b"")
            if not first:
                stream.close()
                return _response(start_response, 502, {"error": "empty_provider_audio"})
        except ProviderError as error:
            error_headers = [("Retry-After", error.retry_after)] if error.retry_after else None
            return _response(start_response, error.status, {"error": error.code}, error_headers)

        start_response("200 OK", [
            ("Content-Type", "application/octet-stream"),
            ("Cache-Control", "no-store"),
            ("X-Content-Type-Options", "nosniff"),
        ])

        def body():
            try:
                yield first
                yield from stream
            finally:
                stream.close()
        return body()

    return app
