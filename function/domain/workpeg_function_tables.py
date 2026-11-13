"""Server-side Workpeg Tables port for platform-invoked Functions.

This adapter is deliberately separate from the Peg UI client. It consumes
only the Workpeg Function envelope's call-scoped token and business, never
WORKPEG_PK and never a caller-provided Peg-Namespace header. Successful Tables
API reads are the ownership evidence: Workpeg validates the signed token and
jails its access to the calling Peg's tables in the invocation business.

The adapter does not authenticate a public /invoke endpoint. Construct it only
inside ``main(context, payload)`` with the platform-supplied ``context``; never
pass ``payload.context`` or a browser role/business/header into it. Workpeg
still enforces the token's person-level table permissions on every operation.
"""
import base64
import json
from copy import deepcopy
from dataclasses import dataclass, field
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .workpeg_adapter import (
    AdapterError,
    _issue_function_peg_scope_attestation,
    _table_inventory_fingerprint,
)


ROOMAY_PEG_NAMESPACE = "roomay"
WORKPEG_TABLES_API = "https://api.workpeg.com"
REQUEST_TIMEOUT_SECONDS = 10


class FunctionTablesError(ValueError):
    """Safe Workpeg API error; contains no token, response body, or URL."""

    def __init__(self, code, status=None):
        self.code = code
        self.status = status
        super().__init__(code)


@dataclass(frozen=True)
class _Invocation:
    business_id: str
    peg_namespace: str
    staff_email: str = field(repr=False)
    token: str = field(repr=False, compare=False)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        return None


class WorkpegFunctionTables:
    """Documented Tables REST calls using a Workpeg-minted Function token.

    ``transport`` is an offline test seam exposing ``request(method, url,
    headers, body, timeout)`` and returning ``(status, parsed_json)``. The
    production transport uses HTTPS, default certificate validation, a fixed
    Workpeg API host and refuses redirects. HTTP 401/403 are reported as safe
    error codes and are never retried.
    """

    def __init__(self, context, *, expected_business_id, transport=None):
        self._invocation = self._parse_context(context, expected_business_id)
        self._transport = transport
        self._observed_lists = {}

    @staticmethod
    def _canonical_uuid(value):
        if not isinstance(value, str) or len(value) != 36:
            return False
        try:
            from uuid import UUID
            return str(UUID(value)) == value
        except (ValueError, TypeError, AttributeError):
            return False

    @staticmethod
    def _token_peg_namespace(token):
        # This is only a mismatch-rejection check, never authentication. The
        # authenticated API request below validates the token signature.
        parts = token.split(".")
        if len(parts) != 3 or not parts[1]:
            raise FunctionTablesError("function_token_malformed")
        try:
            encoded = parts[1] + "=" * ((4 - len(parts[1]) % 4) % 4)
            claims = json.loads(base64.urlsafe_b64decode(encoded.encode("ascii")))
        except (ValueError, TypeError, UnicodeError, json.JSONDecodeError):
            raise FunctionTablesError("function_token_malformed") from None
        namespace = claims.get("peg_namespace") if isinstance(claims, dict) else None
        if namespace != ROOMAY_PEG_NAMESPACE:
            raise FunctionTablesError("function_peg_scope_mismatch")
        return namespace

    @classmethod
    def _parse_context(cls, context, expected_business_id):
        if not isinstance(context, dict):
            raise FunctionTablesError("function_context_missing")
        business_id = context.get("business")
        token = context.get("token")
        staff = context.get("staff")
        if (not cls._canonical_uuid(expected_business_id)
                or business_id != expected_business_id):
            raise FunctionTablesError("function_business_scope_mismatch")
        if not isinstance(token, str) or not token:
            raise FunctionTablesError("function_token_missing")
        if not isinstance(staff, dict) or not isinstance(staff.get("email"), str) or not staff["email"].strip():
            raise FunctionTablesError("function_actor_missing")
        namespace = cls._token_peg_namespace(token)
        return _Invocation(
            business_id=business_id,
            peg_namespace=namespace,
            staff_email=staff["email"].strip().casefold(),
            token=token,
        )

    @property
    def business_id(self):
        return self._invocation.business_id

    @property
    def peg_namespace(self):
        return self._invocation.peg_namespace

    @property
    def staff_email(self):
        """Verified Function context identity for a trusted resolver to map."""
        return self._invocation.staff_email

    def _url(self, table_uuid=None, resource=None, query=None):
        base = (WORKPEG_TABLES_API + "/v1/businesses/"
                + quote(self.business_id, safe="") + "/tables/")
        if table_uuid is not None:
            base += quote(table_uuid, safe="") + "/"
        if resource:
            base += resource
        if query:
            base += "?" + urlencode(query)
        return base

    def _request(self, method, url, body=None):
        headers = {
            "Authorization": "Bearer " + self._invocation.token,
            "Accept": "application/json",
        }
        if body is not None:
            headers["Content-Type"] = "application/json"
        if self._transport is not None:
            try:
                status, result = self._transport.request(
                    method, url, headers, deepcopy(body), REQUEST_TIMEOUT_SECONDS)
            except Exception:
                raise FunctionTablesError("workpeg_transport_unavailable") from None
        else:
            request = Request(
                url,
                data=None if body is None else json.dumps(body).encode("utf-8"),
                headers=headers,
                method=method,
            )
            try:
                response = build_opener(_NoRedirect()).open(
                    request, timeout=REQUEST_TIMEOUT_SECONDS)
                status = response.status
                raw = response.read()
                result = json.loads(raw.decode("utf-8")) if raw else None
            except HTTPError as error:
                status = error.code
                result = None
            except (URLError, TimeoutError, OSError, ValueError, UnicodeError):
                raise FunctionTablesError("workpeg_transport_unavailable") from None
        if status == 401:
            raise FunctionTablesError("workpeg_function_token_rejected", status)
        if status == 403:
            raise FunctionTablesError("workpeg_actor_or_business_forbidden", status)
        if status in (404, 410):
            raise FunctionTablesError("workpeg_scoped_resource_unavailable", status)
        if not isinstance(status, int) or not 200 <= status < 300:
            raise FunctionTablesError("workpeg_operation_failed", status if isinstance(status, int) else None)
        return result

    def get_tables(self, namespace):
        if namespace not in ("roomay_hotel_v1", "roomay_requests_v1"):
            raise FunctionTablesError("unsupported_table_namespace")
        result = self._request("GET", self._url(query={"namespace": namespace}))
        if not isinstance(result, list) or any(not isinstance(item, dict) for item in result):
            raise FunctionTablesError("malformed_table_inventory")
        self._observed_lists[namespace] = deepcopy(result)
        return result

    def attest_inventory(self, tables_by_namespace, *, business_id, actor_id):
        """Return a one-operation scope proof after both authenticated GETs."""
        if business_id != self.business_id:
            raise FunctionTablesError("function_business_scope_mismatch")
        if not isinstance(actor_id, str) or not actor_id.strip():
            raise FunctionTablesError("function_actor_missing")
        if set(self._observed_lists) != {"roomay_hotel_v1", "roomay_requests_v1"}:
            raise FunctionTablesError("function_scope_inventory_incomplete")
        if not isinstance(tables_by_namespace, dict):
            raise FunctionTablesError("malformed_table_inventory")
        for namespace in ("roomay_hotel_v1", "roomay_requests_v1"):
            if tables_by_namespace.get(namespace) != self._observed_lists[namespace]:
                raise FunctionTablesError("function_scope_inventory_mismatch")
        return _issue_function_peg_scope_attestation(
            business_id=self.business_id,
            peg_namespace=self.peg_namespace,
            actor_id=actor_id,
            inventory_fingerprint=_table_inventory_fingerprint(tables_by_namespace),
        )

    def get_rows(self, table_uuid, limit=100, offset=0):
        if not self._canonical_uuid(table_uuid) or type(limit) is not int or limit < 1 or type(offset) is not int or offset < 0:
            raise FunctionTablesError("invalid_row_query")
        result = self._request("GET", self._url(
            table_uuid, "rows/", {"limit": limit, "offset": offset}))
        if not isinstance(result, list):
            raise FunctionTablesError("malformed_row_inventory")
        return result

    def add_row(self, table_uuid, row):
        if not self._canonical_uuid(table_uuid) or not isinstance(row, dict):
            raise FunctionTablesError("invalid_row_create")
        return self._request("POST", self._url(table_uuid, "rows/"), row)

    def update_row(self, table_uuid, row_id, patch):
        if (not self._canonical_uuid(table_uuid) or type(row_id) is not int
                or row_id <= 0 or not isinstance(patch, dict)):
            raise FunctionTablesError("invalid_row_update")
        return self._request(
            "PATCH", self._url(table_uuid, "rows/" + str(row_id) + "/"), patch)
