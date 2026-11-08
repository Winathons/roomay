"""YarnGPT conversation-stream client using only the Python standard library."""

import json
import re
import socket
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .pcm import LinearPcmResampler, PcmFormatError


YARN_CONVERSATION_URL = "https://api.yarngpt.ai/api/v1/streaming/conversation"
_RATE = re.compile(r"(?:^|;)\s*rate\s*=\s*(\d+)(?:\s*;|$)", re.I)
_CHANNELS = re.compile(r"(?:^|;)\s*channels\s*=\s*(\d+)(?:\s*;|$)", re.I)


class ProviderError(Exception):
    def __init__(self, code, status=502, retry_after=None):
        self.code = code
        self.status = status
        self.retry_after = retry_after
        super().__init__(code)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _pcm_rate(content_type):
    if not isinstance(content_type, str) or not content_type.lower().startswith("audio/l16"):
        raise ProviderError("provider_audio_format_invalid")
    rate_match = _RATE.search(content_type)
    channels_match = _CHANNELS.search(content_type)
    if not rate_match or not channels_match:
        raise ProviderError("provider_audio_format_invalid")
    rate = int(rate_match.group(1))
    channels = int(channels_match.group(1))
    # Bound malformed metadata before constructing a resampler.
    if not 1000 <= rate <= 192000 or channels != 1:
        raise ProviderError("provider_audio_format_invalid")
    return rate


def _provider_status(status, headers=None):
    if status == 429:
        retry = None
        if headers:
            candidate = headers.get("Retry-After")
            if candidate and candidate.isdigit():
                retry = str(min(int(candidate), 3600))
        return ProviderError("provider_rate_limited", status=429, retry_after=retry)
    if status == 401:
        return ProviderError("provider_auth_failed")
    if status in (408, 504):
        return ProviderError("provider_timeout", status=504)
    return ProviderError("provider_unavailable")


class YarnConversationClient:
    def __init__(self, api_key, timeout_seconds=20, opener=None, chunk_size=8192):
        if not isinstance(api_key, str) or not api_key.strip():
            raise ValueError("yarngpt_api_key_required")
        if timeout_seconds <= 0 or chunk_size <= 0:
            raise ValueError("invalid_provider_limits")
        self._api_key = api_key.strip()
        self.timeout_seconds = timeout_seconds
        self.chunk_size = chunk_size
        self._opener = opener or build_opener(_NoRedirect())

    def open_audio(self, text, voice_id, target_rate, idempotency_key=None):
        body = json.dumps({"text": text, "voice": voice_id, "output_format": "pcm"}).encode("utf-8")
        headers = {
            "Authorization": "Bearer " + self._api_key,
            "Content-Type": "application/json",
            "Accept": "audio/l16",
        }
        if idempotency_key is not None:
            if not isinstance(idempotency_key, str) or not 1 <= len(idempotency_key) <= 64:
                raise ValueError("invalid_idempotency_key")
            headers["Idempotency-Key"] = idempotency_key
        request = Request(
            YARN_CONVERSATION_URL,
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            response = self._opener.open(request, timeout=self.timeout_seconds)
        except HTTPError as error:
            status, response_headers = error.code, error.headers
            error.close()
            raise _provider_status(status, response_headers) from None
        except (TimeoutError, socket.timeout):
            raise ProviderError("provider_timeout", status=504) from None
        except (URLError, OSError):
            raise ProviderError("provider_unavailable", status=504) from None

        status = getattr(response, "status", None)
        if status is None and hasattr(response, "getcode"):
            status = response.getcode()
        if status != 200:
            try:
                response.close()
            finally:
                raise _provider_status(status or 502, getattr(response, "headers", None))
        try:
            source_rate = _pcm_rate(response.headers.get("Content-Type"))
        except ProviderError:
            response.close()
            raise
        return PcmAudioStream(response, source_rate, target_rate, self.chunk_size)


class PcmAudioStream:
    """Closeable stream. WSGI iterator close propagates client cancellation."""

    def __init__(self, response, source_rate, target_rate, chunk_size=8192):
        self._response = response
        self._resampler = LinearPcmResampler(source_rate, target_rate)
        self._chunk_size = chunk_size
        self._closed = False

    def __iter__(self):
        return self

    def __next__(self):
        if self._closed:
            raise StopIteration
        try:
            while True:
                chunk = self._response.read(self._chunk_size)
                if not chunk:
                    self._closed = True
                    self._response.close()
                    tail = self._resampler.finish()
                    if tail:
                        return tail
                    raise StopIteration
                converted = self._resampler.feed(chunk)
                if converted:
                    return converted
        except StopIteration:
            raise
        except (TimeoutError, socket.timeout):
            self.close()
            raise ProviderError("provider_timeout", status=504) from None
        except Exception:
            self.close()
            raise ProviderError("provider_stream_interrupted", status=502) from None
        except PcmFormatError:
            self.close()
            raise ProviderError("provider_audio_malformed", status=502) from None

    def close(self):
        if not self._closed:
            self._closed = True
            self._response.close()
