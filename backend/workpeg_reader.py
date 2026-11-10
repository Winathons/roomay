"""Read-only hotel snapshot client using documented Workpeg REST endpoints."""
from urllib.parse import quote
import requests

from domain.workpeg_adapter import AdapterError, HOTEL_ALIASES, contract_by_key, decode_rows
from domain.hotel import validate_snapshot


class WorkpegReadError(RuntimeError):
    pass


class WorkpegHotelReader:
    """Reads canonical hotel rows only; never creates or mutates Workpeg data."""
    def __init__(self, *, api_base, workpeg_pk, peg_id, http=requests, timeout=8):
        if not api_base or not workpeg_pk or not peg_id:
            raise WorkpegReadError("workpeg_read_configuration_missing")
        self.api_base, self._pk, self.peg_id = api_base.rstrip("/"), workpeg_pk, str(peg_id)
        self.http, self.timeout = http, timeout

    def _get(self, url, params=None):
        try:
            response = self.http.get(url, params=params,
                                     headers={"Authorization": "Bearer " + self._pk},
                                     timeout=self.timeout, allow_redirects=False)
        except Exception:
            raise WorkpegReadError("workpeg_unavailable") from None
        if response.status_code in (401, 403, 404):
            raise WorkpegReadError("workpeg_access_denied")
        if response.status_code != 200:
            raise WorkpegReadError("workpeg_unavailable")
        try:
            return response.json()
        except Exception:
            raise WorkpegReadError("workpeg_malformed_response") from None

    def _table(self, business_id, name, namespace):
        url = f"{self.api_base}/v1/businesses/{quote(business_id, safe='')}/tables/"
        result = self._get(url, {"namespace": namespace})
        if not isinstance(result, list):
            raise WorkpegReadError("workpeg_malformed_response")
        matches = [table for table in result if isinstance(table, dict)
                   and table.get("name") == name and table.get("namespace") == namespace]
        if len(matches) != 1:
            raise WorkpegReadError("workpeg_table_missing_or_ambiguous")
        table = matches[0]
        if (str(table.get("permission")) != "700"
                or str(table.get("peg")) != self.peg_id
                or not isinstance(table.get("uuid"), str)):
            raise WorkpegReadError("workpeg_table_ownership_mismatch")
        contract = contract_by_key()[name]
        try:
            from domain.workpeg_adapter import validate_table_response
            validate_table_response(contract, table)
        except AdapterError:
            raise WorkpegReadError("workpeg_table_contract_mismatch") from None
        return table

    def _rows(self, business_id, table_uuid):
        rows, offset, page_size = [], 0, 100
        url = (f"{self.api_base}/v1/businesses/{quote(business_id, safe='')}"
               f"/tables/{quote(table_uuid, safe='')}/rows/")
        for _ in range(100):
            page = self._get(url, {"limit": page_size, "offset": offset})
            if not isinstance(page, list) or len(page) > page_size:
                raise WorkpegReadError("workpeg_malformed_response")
            rows.extend(page)
            if len(page) < page_size:
                return rows
            offset += page_size
        raise WorkpegReadError("workpeg_pagination_incomplete")

    def read_snapshot(self, business_id):
        rows_by_table = {}
        for key, alias in HOTEL_ALIASES.items():
            contract = contract_by_key()[key]
            table = self._table(business_id, contract["name"], contract["namespace"])
            rows_by_table[key] = self._rows(business_id, table["uuid"])
        decoded = {}
        try:
            for key in HOTEL_ALIASES:
                decoded[key], _ = decode_rows(key, business_id, rows_by_table[key])
            validate_snapshot(decoded)
        except (AdapterError, ValueError, TypeError, KeyError):
            raise WorkpegReadError("workpeg_hotel_snapshot_invalid") from None
        return decoded
