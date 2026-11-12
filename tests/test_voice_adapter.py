"""Offline Vapi/YarnGPT adapter contracts; no keys or provider calls."""

import io
import json
import socket
import struct
import threading
import time
import unittest
from urllib.error import HTTPError

from voice_adapter.pcm import LinearPcmResampler, PcmFormatError
from voice_adapter.wsgi import VoiceConfig, create_app
from voice_adapter.yarngpt import (
    PcmAudioStream, ProviderError, YARN_CONVERSATION_URL, YarnConversationClient,
)


TOKEN = "vapi-test-token-not-a-real-secret-000000000000"
YARN_KEY = "offline-provider-placeholder-not-a-real-key"


class FakeResponse:
    status = 200

    def __init__(self, data=b"", content_type="audio/l16; rate=48000; channels=1", fail_after=None):
        self.headers = {"Content-Type": content_type}
        self.data = data
        self.position = 0
        self.closed = False
        self.fail_after = fail_after

    def read(self, size):
        if self.closed:
            return b""
        if self.fail_after is not None and self.position >= self.fail_after:
            raise OSError("synthetic disconnect")
        part = self.data[self.position:self.position + size]
        self.position += len(part)
        return part

    def close(self):
        self.closed = True


class FakeOpener:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.request = None
        self.timeout = None

    def open(self, request, timeout):
        self.request, self.timeout = request, timeout
        if self.error:
            raise self.error
        return self.response


def pcm_sine_samples(count):
    return b"".join(struct.pack("<h", ((index * 173) % 30000) - 15000)
                   for index in range(count))


def voice_config(**changes):
    values = {
        "vapi_bearer_token": TOKEN,
        "yarngpt_api_key": YARN_KEY,
        "voice_ids": {"mary": "mary-offline-id", "remi": "remi-offline-id", "umar": "umar-offline-id"},
        "default_voice": "mary",
        "assistant_voice_map": {"assistant-remi": "remi", "assistant-umar": "umar"},
    }
    values.update(changes)
    return VoiceConfig(**values)


def wsgi_call(app, document=None, *, token=TOKEN, path="/synthesize", method="POST",
              content_type="application/json", body=None):
    payload = body if body is not None else json.dumps(document).encode("utf-8")
    environ = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "CONTENT_TYPE": content_type,
        "CONTENT_LENGTH": str(len(payload)),
        "HTTP_AUTHORIZATION": "Bearer " + token if token is not None else "",
        "wsgi.input": io.BytesIO(payload),
    }
    response = {}

    def start_response(status, headers, exc_info=None):
        response["status"] = int(status.split(" ", 1)[0])
        response["headers"] = dict(headers)

    response["body"] = app(environ, start_response)
    return response


def vapi_request(rate=24000, assistant_id="assistant-remi", text="Hello from Roomay."):
    return {"message": {
        "type": "voice-request", "text": text, "sampleRate": rate,
        "timestamp": 1794146400000,
        "assistant": {"id": assistant_id, "name": "Offline test"},
        "call": {"id": "offline-call"},
    }}


class PcmResamplerTests(unittest.TestCase):
    def test_converts_provider_pcm_to_each_documented_vapi_sample_rate(self):
        source = pcm_sine_samples(4800)  # 100 ms at 48 kHz, synthetic only
        for rate, expected_samples in ((8000, 800), (16000, 1600),
                                       (22050, 2205), (24000, 2400),
                                       (44100, 4410)):
            with self.subTest(rate=rate):
                converter = LinearPcmResampler(48000, rate)
                chunks = [source[:901], source[901:4097], source[4097:]]
                output = b"".join(converter.feed(part) for part in chunks)
                output += converter.finish()
                self.assertEqual(len(output), expected_samples * 2)
                self.assertEqual(len(output) % 2, 0)

    def test_preserves_audio_across_odd_transport_chunk_boundaries(self):
        source = pcm_sine_samples(100)
        converter = LinearPcmResampler(24000, 24000)
        result = converter.feed(source[:17]) + converter.feed(source[17:]) + converter.finish()
        self.assertEqual(result, source)

    def test_rejects_incomplete_s16le_sample(self):
        converter = LinearPcmResampler(24000, 16000)
        converter.feed(b"\x01")
        with self.assertRaises(PcmFormatError):
            converter.finish()


class YarnClientTests(unittest.TestCase):
    def test_sends_streaming_pcm_request_and_never_places_key_in_body(self):
        response = FakeResponse(pcm_sine_samples(100))
        opener = FakeOpener(response=response)
        client = YarnConversationClient(YARN_KEY, timeout_seconds=7, opener=opener)
        stream = client.open_audio("Synthetic hello", "validated-provider-id", 16000,
                                   idempotency_key="safe-test-key")
        request = opener.request
        self.assertEqual(request.full_url, YARN_CONVERSATION_URL)
        self.assertEqual(request.get_header("Authorization"), "Bearer " + YARN_KEY)
        self.assertEqual(request.get_header("Idempotency-key"), "safe-test-key")
        self.assertEqual(json.loads(request.data), {
            "text": "Synthetic hello", "voice": "validated-provider-id", "output_format": "pcm"})
        self.assertEqual(opener.timeout, 7)
        self.assertTrue(b"".join(stream))
        self.assertTrue(response.closed)

    def test_rate_limit_is_explicit_and_retry_after_is_bounded(self):
        error = HTTPError(YARN_CONVERSATION_URL, 429, "limited", {"Retry-After": "999999"}, None)
        client = YarnConversationClient(YARN_KEY, opener=FakeOpener(error=error))
        with self.assertRaises(ProviderError) as caught:
            client.open_audio("hello", "voice", 8000)
        self.assertEqual(caught.exception.status, 429)
        self.assertEqual(caught.exception.retry_after, "3600")

    def test_provider_authentication_failure_is_sanitized(self):
        error = HTTPError(YARN_CONVERSATION_URL, 401, "invalid key", {}, None)
        client = YarnConversationClient(YARN_KEY, opener=FakeOpener(error=error))
        with self.assertRaises(ProviderError) as caught:
            client.open_audio("hello", "voice", 8000)
        self.assertEqual(caught.exception.code, "provider_auth_failed")
        self.assertEqual(caught.exception.status, 502)

    def test_provider_connect_timeout_is_bounded_and_reported(self):
        client = YarnConversationClient(YARN_KEY, timeout_seconds=3,
                                        opener=FakeOpener(error=socket.timeout("offline timeout")))
        with self.assertRaises(ProviderError) as caught:
            client.open_audio("hello", "voice", 8000)
        self.assertEqual(caught.exception.code, "provider_timeout")
        self.assertEqual(caught.exception.status, 504)

    def test_connection_timeout_is_capped_by_remaining_synthesis_deadline(self):
        opener = FakeOpener(response=FakeResponse(pcm_sine_samples(100)))
        client = YarnConversationClient(YARN_KEY, timeout_seconds=20, opener=opener)
        client.open_audio("hello", "voice", 8000,
                          deadline_at=time.monotonic() + 0.25).close()
        self.assertGreater(opener.timeout, 0)
        self.assertLessEqual(opener.timeout, 0.25)

    def test_total_stream_deadline_expires_during_continuous_audio_and_closes_response(self):
        class ContinuousResponse(FakeResponse):
            def __init__(self):
                super().__init__()

            def read(self, size):
                time.sleep(0.005)
                if self.closed:
                    return b""
                return pcm_sine_samples(max(2, size // 2))

        response = ContinuousResponse()
        stream = PcmAudioStream(response, 48000, 24000,
                                deadline_at=time.monotonic() + 0.05)
        yielded = 0
        with self.assertRaises(ProviderError) as caught:
            while True:
                next(stream)
                yielded += 1
        self.assertEqual(caught.exception.code, "provider_timeout")
        self.assertGreater(yielded, 0)
        self.assertTrue(response.closed)

    def test_stream_deadline_closes_response_even_if_client_stops_consuming(self):
        class BlockingResponse(FakeResponse):
            def read(self, size):
                time.sleep(0.04)
                return super().read(size)

        response = BlockingResponse(pcm_sine_samples(1000))
        stream = PcmAudioStream(response, 48000, 24000,
                                deadline_at=time.monotonic() + 0.01)
        time.sleep(0.03)
        self.assertTrue(response.closed)
        with self.assertRaises(ProviderError) as caught:
            next(stream)
        self.assertEqual(caught.exception.code, "provider_timeout")

    def test_deadline_does_not_guarantee_completion_of_an_already_blocked_read(self):
        class NonInterruptibleResponse:
            def __init__(self):
                self.closed = False
                self.read_started = threading.Event()
                self.close_called = threading.Event()
                self.release_read = threading.Event()

            def read(self, size):
                self.read_started.set()
                self.release_read.wait()
                return pcm_sine_samples(32)

            def close(self):
                # Models a transport whose close notification does not cancel
                # an already-running blocking read.
                self.closed = True
                self.close_called.set()

        response = NonInterruptibleResponse()
        stream = PcmAudioStream(response, 48000, 24000,
                                deadline_at=time.monotonic() + 0.05)
        outcomes = []

        def consume_one_chunk():
            try:
                next(stream)
                outcomes.append("pcm")
            except ProviderError as error:
                outcomes.append(error.code)

        reader = threading.Thread(target=consume_one_chunk, daemon=True)
        reader.start()
        self.assertTrue(response.read_started.wait(1))
        self.assertTrue(response.close_called.wait(1), "deadline should attempt stream cleanup")
        # The timer expires, but the active read still owns control. This is
        # why the current urllib transport cannot promise a hard wall-clock cap.
        self.assertTrue(reader.is_alive())
        response.release_read.set()
        reader.join(1)
        self.assertFalse(reader.is_alive())
        self.assertEqual(outcomes, ["provider_timeout"])
        self.assertTrue(response.closed)

    def test_rejects_unexpected_provider_content_type(self):
        client = YarnConversationClient(YARN_KEY, opener=FakeOpener(
            response=FakeResponse(b"not pcm", content_type="audio/wav")))
        with self.assertRaises(ProviderError) as caught:
            client.open_audio("hello", "voice", 8000)
        self.assertEqual(caught.exception.code, "provider_audio_format_invalid")

    def test_truncated_pcm_is_classified_as_malformed_audio(self):
        # Three bytes cannot represent a complete sequence of 16-bit PCM samples.
        response = FakeResponse(b"\x10\x00\xff")
        client = YarnConversationClient(YARN_KEY, opener=FakeOpener(response=response))
        stream = client.open_audio("hello", "voice", 24000)
        with self.assertRaises(ProviderError) as caught:
            b"".join(stream)
        self.assertEqual(caught.exception.code, "provider_audio_malformed")
        self.assertEqual(caught.exception.status, 502)
        self.assertTrue(response.closed)

    def test_default_chunk_size_favors_early_streaming(self):
        response = FakeResponse(pcm_sine_samples(3000))
        requested_sizes = []
        original_read = response.read

        def record_read(size):
            requested_sizes.append(size)
            return original_read(size)

        response.read = record_read
        stream = YarnConversationClient(
            YARN_KEY, opener=FakeOpener(response=response)
        ).open_audio("hello", "voice", 24000)
        self.assertTrue(next(stream))
        self.assertEqual(requested_sizes[0], 2048)
        stream.close()
        self.assertTrue(response.closed)

    def test_upstream_disconnect_closes_the_response(self):
        response = FakeResponse(pcm_sine_samples(200), fail_after=32)
        stream = YarnConversationClient(YARN_KEY, opener=FakeOpener(response=response),
                                        chunk_size=32).open_audio("hello", "voice", 48000)
        next(stream)
        with self.assertRaises(ProviderError) as caught:
            next(stream)
        self.assertEqual(caught.exception.code, "provider_stream_interrupted")
        self.assertTrue(response.closed)


class VapiWsgiAdapterTests(unittest.TestCase):
    def test_returns_raw_pcm_and_uses_assistant_voice_mapping(self):
        source = pcm_sine_samples(4800)

        class Client:
            def __init__(self):
                self.args = None

            def open_audio(self, text, voice_id, target_rate, idempotency_key=None, deadline_at=None):
                self.args = (text, voice_id, target_rate, idempotency_key)
                converter = LinearPcmResampler(48000, target_rate)

                class Stream:
                    def __init__(self):
                        self.parts = iter((converter.feed(source), converter.finish()))
                        self.closed = False

                    def __iter__(self):
                        return self

                    def __next__(self):
                        part = next(self.parts)
                        if not part:
                            return self.__next__()
                        return part

                    def close(self):
                        self.closed = True
                return Stream()

        client = Client()
        app = create_app(voice_config(), client=client)
        response = wsgi_call(app, vapi_request(rate=16000))
        self.assertEqual(response["status"], 200)
        self.assertEqual(response["headers"]["Content-Type"], "application/octet-stream")
        self.assertEqual(response["headers"]["X-Content-Type-Options"], "nosniff")
        audio = b"".join(response["body"])
        self.assertEqual(len(audio), 1600 * 2)
        self.assertEqual(client.args[:3], ("Hello from Roomay.", "remi-offline-id", 16000))
        self.assertEqual(len(client.args[3]), 64)

    def test_vapi_retry_with_same_call_and_payload_reuses_nonreversible_provider_key(self):
        class EmptyClient:
            def __init__(self):
                self.keys = []

            def open_audio(self, text, voice_id, target_rate, idempotency_key=None, deadline_at=None):
                self.keys.append(idempotency_key)
                class EmptyStream:
                    def __iter__(self):
                        return self

                    def __next__(self):
                        raise StopIteration

                    def close(self):
                        pass
                return EmptyStream()

        client = EmptyClient()
        app = create_app(voice_config(), client=client)
        wsgi_call(app, vapi_request())
        wsgi_call(app, vapi_request())
        self.assertEqual(client.keys[0], client.keys[1])
        self.assertNotIn("offline-call", client.keys[0])
        self.assertNotIn("Hello from Roomay.", client.keys[0])

    def test_rejects_missing_or_invalid_vapi_credentials_before_provider(self):
        class NeverClient:
            def open_audio(self, *args):
                self.fail("provider must not be called")

        app = create_app(voice_config(), client=NeverClient())
        for supplied in (None, "wrong-token", "non-ascii-\u00e9"):
            with self.subTest(token=supplied):
                response = wsgi_call(app, vapi_request(), token=supplied)
                self.assertEqual(response["status"], 401)
                self.assertEqual(json.loads(b"".join(response["body"])), {"error": "unauthorized"})

    def test_authenticated_synthesis_requests_are_rate_limited_and_fail_closed(self):
        now = [100.0]
        calls = []

        class EmptyClient:
            def open_audio(self, *args, **kwargs):
                calls.append(1)

                class EmptyStream:
                    def __iter__(self):
                        return self

                    def __next__(self):
                        raise StopIteration

                    def close(self):
                        pass
                return EmptyStream()

        app = create_app(voice_config(rate_limit_requests=1,
                                      rate_limit_window_seconds=30),
                         client=EmptyClient(), clock=lambda: now[0])
        unauthorized = wsgi_call(app, vapi_request(), token="incorrect")
        self.assertEqual(unauthorized["status"], 401)
        first = wsgi_call(app, vapi_request())
        self.assertEqual(first["status"], 502)
        limited = wsgi_call(app, vapi_request())
        self.assertEqual(limited["status"], 429)
        self.assertEqual(limited["headers"]["Retry-After"], "30")
        self.assertEqual(json.loads(b"".join(limited["body"])), {"error": "rate_limited"})
        self.assertEqual(len(calls), 1)
        now[0] += 31
        self.assertEqual(wsgi_call(app, vapi_request())["status"], 502)
        self.assertEqual(len(calls), 2)

    def test_limiter_storage_and_deadline_configuration_are_bounded(self):
        for changes in ({"rate_limit_requests": 0}, {"rate_limit_requests": 1001},
                        {"rate_limit_window_seconds": 0},
                        {"synthesis_deadline_seconds": 121}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                voice_config(**changes).validate()

    def test_rate_limiter_internal_failure_fails_closed_without_provider_use(self):
        class NeverClient:
            def open_audio(self, *args, **kwargs):
                self.fail("limiter failure must block provider use")

        def broken_clock():
            raise RuntimeError("internal-only detail")

        response = wsgi_call(create_app(voice_config(), client=NeverClient(),
                                        clock=broken_clock), vapi_request())
        self.assertEqual(response["status"], 503)
        self.assertEqual(json.loads(b"".join(response["body"])),
                         {"error": "rate_limit_unavailable"})

    def test_unexpected_first_stream_failure_closes_upstream_and_is_sanitized(self):
        class BrokenStream:
            closed = False

            def __iter__(self):
                return self

            def __next__(self):
                raise RuntimeError("sensitive provider detail")

            def close(self):
                self.closed = True

        stream = BrokenStream()

        class Client:
            def open_audio(self, *args, **kwargs):
                return stream

        response = wsgi_call(create_app(voice_config(), client=Client()), vapi_request())
        self.assertEqual(response["status"], 502)
        self.assertEqual(json.loads(b"".join(response["body"])), {"error": "synthesis_failed"})
        self.assertTrue(stream.closed)

    def test_empty_provider_audio_fails_before_success_headers(self):
        app = create_app(voice_config(), client=YarnConversationClient(
            YARN_KEY, opener=FakeOpener(response=FakeResponse(b""))))
        response = wsgi_call(app, vapi_request())
        self.assertEqual(response["status"], 502)
        self.assertEqual(json.loads(b"".join(response["body"])), {"error": "empty_provider_audio"})

    def test_provider_failure_is_sanitized(self):
        class FailedClient:
            def open_audio(self, *args, **kwargs):
                raise ProviderError("provider_unavailable", 502)

        response = wsgi_call(create_app(voice_config(), client=FailedClient()), vapi_request())
        self.assertEqual(response["status"], 502)
        self.assertNotIn(YARN_KEY.encode(), b"".join(response["body"]))

    def test_provider_rate_limit_is_returned_without_secret_details(self):
        class LimitedClient:
            def open_audio(self, *args, **kwargs):
                raise ProviderError("provider_rate_limited", 429, retry_after="9")

        response = wsgi_call(create_app(voice_config(), client=LimitedClient()), vapi_request())
        self.assertEqual(response["status"], 429)
        self.assertEqual(response["headers"]["Retry-After"], "9")

    def test_malformed_requests_and_unsupported_rates_fail_closed(self):
        app = create_app(voice_config(), client=object())
        invalid = [
            {}, {"message": None}, {"message": {"type": "other"}},
            {"message": {"type": "voice-request", "text": " "}},
            vapi_request(rate=12345), vapi_request(rate=True),
            {"message": {**vapi_request()["message"], "timestamp": "today"}},
            {"message": {**vapi_request()["message"], "timestamp": float("nan")}},
            {"message": {**vapi_request()["message"], "assistant": "bad"}},
            {"message": {**vapi_request()["message"], "assistant": {"id": []}}},
        ]
        for document in invalid:
            with self.subTest(document=document):
                response = wsgi_call(app, document)
                self.assertEqual(response["status"], 400)
                self.assertIsInstance(json.loads(b"".join(response["body"])), dict)

    def test_wrong_method_content_type_and_path_are_rejected(self):
        app = create_app(voice_config(), client=object())
        self.assertEqual(wsgi_call(app, vapi_request(), method="GET")["status"], 405)
        self.assertEqual(wsgi_call(app, vapi_request(), content_type="text/plain")["status"], 400)
        self.assertEqual(wsgi_call(app, vapi_request(), path="/unknown")["status"], 404)
        self.assertEqual(wsgi_call(app, body=b"x" * (64 * 1024 + 1))["status"], 413)

    def test_configuration_requires_secrets_and_default_voice_but_other_voices_are_optional(self):
        with self.assertRaises(ValueError):
            voice_config(vapi_bearer_token="short").validate()
        with self.assertRaises(ValueError):
            voice_config(voice_ids={"mary": "id"}, default_voice="remi").validate()
        with self.assertRaises(ValueError):
            VoiceConfig.from_environment({})

    def test_client_disconnect_closes_upstream_stream(self):
        response = FakeResponse(pcm_sine_samples(200), fail_after=32)
        app = create_app(voice_config(), client=YarnConversationClient(
            YARN_KEY, opener=FakeOpener(response=response), chunk_size=32))
        result = wsgi_call(app, vapi_request(rate=24000))
        iterator = result["body"]
        next(iterator)
        iterator.close()  # WSGI servers close the iterable when a client disconnects.
        self.assertTrue(response.closed)


if __name__ == "__main__":
    unittest.main()
