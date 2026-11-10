"""Read-only hotel snapshot client using documented Workpeg REST endpoints."""
from urllib.parse import quote
import requests

from backend.config import normalize_peg_uuid
from domain.workpeg_adapter import AdapterError, HOTEL_ALIASES, contract_by_key, decode_rows
from domain.hotel import validate_snapshot


READ_STAGES = {
    "authentication", "table_discovery", "metadata_validation",
    "row_access", "snapshot_validation", "unknown",
}
SAFE_STATUS_CATEGORIES = {
    "network_error", "unauthenticated", "forbidden", "not_found",
    "bad_request", "rate_limited", "server_error", "unexpected_http_status",
    "malformed_response", "contract_invalid", "ownership_mismatch",
    "snapshot_invalid", "unexpected_error", "configuration_invalid",
}
SAFE_ERROR_CODES = {
    "workpeg_read_configuration_missing",
    "workpeg_read_configuration_invalid",
    "workpeg_unavailable", "workpeg_access_denied",
    "workpeg_malformed_response", "workpeg_table_missing_or_ambiguous",
    "workpeg_table_ownership_mismatch", "workpeg_table_contract_mismatch",
    "workpeg_pagination_incomplete", "workpeg_hotel_snapshot_invalid",
    "workpeg_http_400", "workpeg_http_401", "workpeg_http_403",
    "workpeg_http_404", "workpeg_http_error", "workpeg_internal_error",
}


class WorkpegReadError(RuntimeError):
    """Stable, sanitized failure details suitable for explicitly opted-in diagnostics."""

    def __init__(self, code, *, stage="unknown", alias=None, http_status=None,
                 status_category="unexpected_error"):
        safe_code = code if code in SAFE_ERROR_CODES else "workpeg_internal_error"
        self.code = safe_code
        self.stage = stage if stage in READ_STAGES else "unknown"
        self.alias = alias if alias in HOTEL_ALIASES.values() else None
        self.http_status = (http_status if isinstance(http_status, int)
                            and not isinstance(http_status, bool)
                            and 100 <= http_status <= 599 else None)
        self.status_category = (status_category if status_category in SAFE_STATUS_CATEGORIES
                                else "unexpected_error")
        super().__init__(self.code)

    def diagnostic(self):
        """Return only allowlisted stage/status identifiers; never exception text."""
        return {
            "stage": self.stage,
            "alias": self.alias,
            "http_status": self.http_status,
            "status_category": self.status_category,
            "error_code": self.code,
        }


def _http_failure(status, stage, alias):
    if status == 401:
        return WorkpegReadError("workpeg_http_401", stage="authentication",
                                alias=alias, http_status=status,
                                status_category="unauthenticated")
    if status == 403:
        return WorkpegReadError("workpeg_http_403", stage=stage, alias=alias,
                                http_status=status, status_category="forbidden")
    if status == 404:
        return WorkpegReadError("workpeg_http_404", stage=stage, alias=alias,
                                http_status=status, status_category="not_found")
    if status == 400:
        return WorkpegReadError("workpeg_http_400", stage=stage, alias=alias,
                                http_status=status, status_category="bad_request")
    if status == 429:
        category = "rate_limited"
    elif isinstance(status, int) and status >= 500:
        category = "server_error"
    else:
        category = "unexpected_http_status"
    return WorkpegReadError("workpeg_http_error", stage=stage, alias=alias,
                            http_status=status, status_category=category)


class WorkpegHotelReader:
    """Reads canonical hotel rows only; never creates or mutates Workpeg data."""
    def __init__(self, *, api_base, workpeg_pk, peg_id, http=requests, timeout=8):
        if not api_base or not workpeg_pk or not peg_id:
            raise WorkpegReadError("workpeg_read_configuration_missing",
                                   stage="authentication", status_category="configuration_invalid")
        try:
            normalized_peg_id = normalize_peg_uuid(peg_id)
        except ValueError:
            raise WorkpegReadError("workpeg_read_configuration_invalid",
                                   stage="authentication", status_category="configuration_invalid") from None
        self.api_base, self._pk, self.peg_id = api_base.rstrip("/"), workpeg_pk, normalized_peg_id
        self.http, self.timeout = http, timeout

    def _get(self, url, params=None, *, stage, alias):
        try:
            response = self.http.get(url, params=params,
                                     headers={"Authorization": "Bearer " + self._pk},
                                     timeout=self.timeout, allow_redirects=False)
        except Exception:
            raise WorkpegReadError("workpeg_unavailable", stage=stage, alias=alias,
                                   status_category="network_error") from None
        try:
            status = response.status_code
        except Exception:
            raise WorkpegReadError("workpeg_malformed_response", stage=stage,
                                   alias=alias, status_category="malformed_response") from None
        if status != 200:
            raise _http_failure(status, stage, alias)
        try:
            return response.json()
        except Exception:
            raise WorkpegReadError("workpeg_malformed_response", stage=stage,
                                   alias=alias, http_status=200,
                                   status_category="malformed_response") from None

    def _table(self, business_id, name, namespace, *, alias=None):
        stage = "table_discovery"
        try:
            url = f"{self.api_base}/v1/businesses/{quote(business_id, safe='')}/tables/"
            result = self._get(url, {"namespace": namespace}, stage=stage, alias=alias)
            if not isinstance(result, list):
                raise WorkpegReadError("workpeg_malformed_response", stage=stage,
                                       alias=alias, status_category="malformed_response")
            matches = [table for table in result if isinstance(table, dict)
                       and table.get("name") == name and table.get("namespace") == namespace]
            if len(matches) != 1:
                raise WorkpegReadError("workpeg_table_missing_or_ambiguous", stage=stage,
                                       alias=alias, status_category="not_found")
            table = matches[0]
            stage = "metadata_validation"
            try:
                table_peg_id = normalize_peg_uuid(table.get("peg"))
            except ValueError:
                raise WorkpegReadError("workpeg_table_ownership_mismatch", stage=stage,
                                       alias=alias, status_category="ownership_mismatch") from None
            if (str(table.get("permission")) != "700"
                    or table_peg_id != self.peg_id
                    or not isinstance(table.get("uuid"), str)):
                raise WorkpegReadError("workpeg_table_ownership_mismatch", stage=stage,
                                       alias=alias, status_category="ownership_mismatch")
            contract = contract_by_key()[name]
            try:
                from domain.workpeg_adapter import validate_table_response
                validate_table_response(contract, table)
            except AdapterError:
                raise WorkpegReadError("workpeg_table_contract_mismatch", stage=stage,
                                       alias=alias, status_category="contract_invalid") from None
            return table
        except WorkpegReadError:
            raise
        except Exception:
            raise WorkpegReadError("workpeg_internal_error", stage=stage, alias=alias,
                                   status_category="unexpected_error") from None

    def _rows(self, business_id, table_uuid, *, alias=None):
        stage = "row_access"
        try:
            rows, offset, page_size = [], 0, 100
            url = (f"{self.api_base}/v1/businesses/{quote(business_id, safe='')}"
                   f"/tables/{quote(table_uuid, safe='')}/rows/")
            for _ in range(100):
                page = self._get(url, {"limit": page_size, "offset": offset},
                                 stage=stage, alias=alias)
                if not isinstance(page, list) or len(page) > page_size:
                    raise WorkpegReadError("workpeg_malformed_response", stage=stage,
                                           alias=alias, status_category="malformed_response")
                rows.extend(page)
                if len(page) < page_size:
                    return rows
                offset += page_size
            raise WorkpegReadError("workpeg_pagination_incomplete", stage=stage,
                                   alias=alias, status_category="malformed_response")
        except WorkpegReadError:
            raise
        except Exception:
            raise WorkpegReadError("workpeg_internal_error", stage=stage, alias=alias,
                                   status_category="unexpected_error") from None

    def read_snapshot(self, business_id):
        rows_by_table = {}
        for key, alias in HOTEL_ALIASES.items():
            contract = contract_by_key()[key]
            table = self._table(business_id, contract["name"], contract["namespace"], alias=alias)
            rows_by_table[key] = self._rows(business_id, table["uuid"], alias=alias)
        decoded = {}
        for key, alias in HOTEL_ALIASES.items():
            try:
                decoded[key], _ = decode_rows(key, business_id, rows_by_table[key])
            except Exception:
                raise WorkpegReadError("workpeg_hotel_snapshot_invalid",
                                       stage="snapshot_validation", alias=alias,
                                       status_category="snapshot_invalid") from None
        try:
            validate_snapshot(decoded)
        except Exception:
            raise WorkpegReadError("workpeg_hotel_snapshot_invalid",
                                   stage="snapshot_validation",
                                   status_category="snapshot_invalid") from None
        return decoded
