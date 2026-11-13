"""Optional server-side Workpeg Inbound Key writer for approved staging rows.

This transport is deliberately not wired into guest APIs, Vapi, or the
canonical service-request writer. Callers must supply a staging-table row
payload and retain their own queue state until they reconcile the response.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from uuid import UUID

import requests


API = "https://api.workpeg.com/v1/inbound"
TIMEOUT_SECONDS = (3.05, 10)


@dataclass(frozen=True)
class InboundConfig:
    enabled: bool = False
    key: str = ""
    business_id: str = ""
    table_id: str = ""


class InboundError(RuntimeError):
    """Safe error code; never includes a response body or credential."""

    def __init__(self, code: str, state: str, retry_after: int | None = None):
        super().__init__(code)
        self.code = code
        self.state = state
        self.retry_after = retry_after


def stable_idempotency_key(source_id: str) -> str:
    """Return a deterministic, printable Workpeg key without exposing source IDs."""
    if not isinstance(source_id, str) or not source_id:
        raise ValueError("invalid_source_id")
    digest = hashlib.sha256(("roomay-inbound-v1\0" + source_id).encode()).hexdigest()
    return "roomay-v1-" + digest


class WorkpegInboundTransport:
    """Send only to a verified destination through an injected HTTP session.

    A 200 is Workpeg's documented idempotent replay response; 201 is its
    initial row-creation response. Both mean staging persistence only.
    """

    def __init__(self, config: InboundConfig, *, session=None):
        self.config = config
        self.session = session or requests.Session()

    def _enabled_config(self):
        c = self.config
        if c.enabled is not True:
            raise InboundError("transport_disabled", "not_attempted")
        if (not isinstance(c.key, str) or not c.key.startswith("wpin_")
                or len(c.key) <= 5 or any(ord(char) < 33 or ord(char) > 126 for char in c.key)):
            raise InboundError("inbound_key_unavailable", "not_attempted")
        if not self._canonical_uuid(c.business_id) or not self._canonical_uuid(c.table_id):
            raise InboundError("destination_unconfigured", "not_attempted")

    @staticmethod
    def _canonical_uuid(value):
        try:
            return isinstance(value, str) and str(UUID(value)) == value
        except (ValueError, TypeError, AttributeError):
            return False

    @staticmethod
    def _retry_after(response):
        """Return a bounded numeric Retry-After value, without trusting it as a URL."""
        value = response.headers.get("Retry-After") if response.headers else None
        if not isinstance(value, str) or not value.isascii() or not value.isdigit():
            return None
        return min(int(value), 3600)

    def _request(self, method, path, *, headers, body=None, timeout_state="staging_not_written"):
        try:
            return self.session.request(
                method, API + path, headers=headers, data=body,
                timeout=TIMEOUT_SECONDS, allow_redirects=False)
        except requests.Timeout:
            raise InboundError("workpeg_timeout_retry_same_key", timeout_state) from None
        except requests.RequestException:
            raise InboundError("workpeg_unavailable_retry_same_key", timeout_state) from None

    def _auth_headers(self):
        # Do not add Origin: Workpeg rejects browser-originated inbound calls.
        return {"Authorization": "Bearer " + self.config.key,
                "Accept": "application/json"}

    def verify_destination(self):
        self._enabled_config()
        response = self._request("GET", "/whoami/", headers=self._auth_headers())
        if response.status_code in (401, 403):
            raise InboundError("inbound_key_unauthorized", "staging_not_written")
        if response.status_code == 429:
            raise InboundError("workpeg_rate_limited", "staging_not_written",
                               self._retry_after(response))
        if response.status_code != 200:
            raise InboundError("destination_verification_failed", "staging_not_written")
        try:
            identity = response.json()
        except (ValueError, TypeError):
            raise InboundError("destination_verification_invalid", "staging_not_written") from None
        if (not isinstance(identity, dict)
                or identity.get("business") != self.config.business_id
                or identity.get("table") != self.config.table_id):
            raise InboundError("destination_mismatch", "staging_not_written")
        return True

    def write_staging_row(self, *, source_id: str, data: dict,
                          business_id: str) -> dict:
        """Create/replay exactly one staging row; never write canonical tickets."""
        self._enabled_config()
        if business_id != self.config.business_id:
            raise InboundError("business_scope_mismatch", "not_attempted")
        if not isinstance(data, dict) or not data:
            raise InboundError("invalid_staging_payload", "not_attempted")
        try:
            encoded = json.dumps({"data": data}, ensure_ascii=True, separators=(",", ":"))
        except (TypeError, ValueError):
            raise InboundError("invalid_staging_payload", "not_attempted") from None
        if len(encoded.encode("utf-8")) > 256 * 1024:
            raise InboundError("staging_payload_too_large", "not_attempted")
        # Same source always maps to same key, including after timeout/restart.
        key = stable_idempotency_key(source_id)
        self.verify_destination()
        headers = self._auth_headers()
        headers["Content-Type"] = "application/json"
        headers["Idempotency-Key"] = key
        response = self._request("POST", "/rows/", headers=headers,
                                 body=encoded.encode("utf-8"), timeout_state="staging_outcome_unknown")
        if response.status_code == 409:
            raise InboundError("workpeg_write_in_progress_retry_after", "staging_outcome_unknown",
                               self._retry_after(response))
        if response.status_code == 401:
            raise InboundError("inbound_key_unauthorized", "staging_not_written")
        if response.status_code == 403:
            raise InboundError("inbound_write_forbidden", "staging_not_written")
        if response.status_code == 429:
            raise InboundError("workpeg_rate_limited_retry_after", "staging_not_written",
                               self._retry_after(response))
        if response.status_code == 503:
            raise InboundError("workpeg_hook_unavailable_retry_after", "staging_outcome_unknown",
                               self._retry_after(response))
        if response.status_code == 422:
            raise InboundError("staging_row_rejected", "staging_not_written")
        if response.status_code not in (200, 201):
            state = "staging_outcome_unknown" if response.status_code >= 500 else "staging_not_written"
            raise InboundError("workpeg_write_failed", state)
        try:
            result = response.json()
        except (ValueError, TypeError):
            raise InboundError("staging_outcome_unknown", "staging_outcome_unknown") from None
        if (not isinstance(result, dict) or result.get("business") != self.config.business_id
                or result.get("table") != self.config.table_id
                or type(result.get("id")) is not int or result["id"] < 1):
            raise InboundError("staging_readback_required", "staging_outcome_unknown")
        return {
            "status": "workpeg_staging_persisted",
            "staging_row_id": result["id"],
            "business_id": result["business"],
            "table_id": result["table"],
            "idempotency_key": key,
            "operational_request_state": "not_asserted",
            "staff_acknowledgement_state": "not_asserted",
        }
