"""Mocked, read-only boundary tests; no Workpeg API requests are made."""
from unittest import TestCase
from uuid import uuid4

from backend.workpeg_reader import WorkpegHotelReader, WorkpegReadError
from domain.workpeg_adapter import HOTEL_ALIASES, contract_by_key


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code, self.payload = status_code, payload

    def json(self):
        return self.payload


class FakeHTTP:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def get(self, url, *, params, headers, timeout, allow_redirects):
        self.calls.append((url, params, headers, timeout, allow_redirects))
        return self.response


class WorkpegReaderTests(TestCase):
    PEG_ID = "eaa64b99-4b8f-4fc5-b9ab-249e4955a141"

    def setUp(self):
        self.business = str(uuid4())
        self.contract = contract_by_key()["rooms"]
        self.table = {
            "uuid": str(uuid4()), "name": self.contract["name"],
            "namespace": self.contract["namespace"], "permission": "700",
            "peg": self.PEG_ID, "metadata": self.contract["metadata"],
            "columns": self.contract["columns"],
        }

    def test_server_reader_accepts_only_configured_peg_owned_table(self):
        http = FakeHTTP(FakeResponse(200, [self.table]))
        reader = WorkpegHotelReader(api_base="https://api.workpeg.com",
                                    workpeg_pk="synthetic-test-secret",
                                    peg_id=self.PEG_ID, http=http)
        table = reader._table(self.business, "rooms", "roomay_hotel_v1")
        self.assertEqual(table["uuid"], self.table["uuid"])
        self.assertEqual(http.calls[0][1], {"namespace": "roomay_hotel_v1"})
        self.assertEqual(http.calls[0][2], {"Authorization": "Bearer synthetic-test-secret"})
        self.assertEqual(http.calls[0][0],
                         f"https://api.workpeg.com/v1/businesses/{self.business}/tables/")
        self.assertEqual(http.calls[0][3:], (8, False))
        self.assertEqual(len(http.calls), 1)

    def test_reader_normalizes_native_peg_uuid_and_rejects_invalid_configured_id(self):
        uppercase_peg = self.PEG_ID.upper()
        table = {**self.table, "peg": uppercase_peg}
        reader = WorkpegHotelReader(
            api_base="https://api.workpeg.com", workpeg_pk="synthetic-test-secret",
            peg_id=uppercase_peg, http=FakeHTTP(FakeResponse(200, [table])))
        self.assertEqual(reader.peg_id, self.PEG_ID)
        self.assertEqual(reader._table(self.business, "rooms", "roomay_hotel_v1")["peg"], uppercase_peg)
        with self.assertRaisesRegex(WorkpegReadError, "workpeg_read_configuration_invalid"):
            WorkpegHotelReader(api_base="https://api.workpeg.com", workpeg_pk="synthetic-test-secret",
                               peg_id="4812", http=FakeHTTP(FakeResponse(200, [self.table])))

    def test_reader_fails_closed_for_wrong_peg_permission_or_schema(self):
        for changed in (
                {**self.table, "peg": "11111111-1111-4111-8111-111111111111"},
                {**self.table, "peg": 4812},
                {**self.table, "peg": "malformed-peg-identity"},
                {**self.table, "peg": None},
                {**self.table, "permission": "777"},
                {**self.table, "columns": self.table["columns"][:-1]}):
            with self.subTest(changed=changed.get("peg", changed.get("permission", "schema"))):
                reader = WorkpegHotelReader(
                    api_base="https://api.workpeg.com", workpeg_pk="synthetic-test-secret",
                    peg_id=self.PEG_ID, http=FakeHTTP(FakeResponse(200, [changed])))
                with self.assertRaises(WorkpegReadError):
                    reader._table(self.business, "rooms", "roomay_hotel_v1")

    def test_reader_reports_denied_or_ambiguous_inventory_without_fallback(self):
        for response in (FakeResponse(403, {"detail": "denied"}),
                         FakeResponse(200, [self.table, self.table])):
            with self.subTest(response=response.status_code):
                reader = WorkpegHotelReader(
                    api_base="https://api.workpeg.com", workpeg_pk="synthetic-test-secret",
                    peg_id=self.PEG_ID, http=FakeHTTP(response))
                with self.assertRaises(WorkpegReadError):
                    reader._table(self.business, "rooms", "roomay_hotel_v1")

    def test_diagnostic_status_for_http_auth_and_table_discovery_failures(self):
        alias = "roomay-hotel-v1-rooms"
        expected = {
            401: ("authentication", "unauthenticated", "workpeg_http_401"),
            403: ("table_discovery", "forbidden", "workpeg_http_403"),
            404: ("table_discovery", "not_found", "workpeg_http_404"),
            400: ("table_discovery", "bad_request", "workpeg_http_400"),
        }
        for status, (stage, category, code) in expected.items():
            with self.subTest(status=status):
                reader = WorkpegHotelReader(
                    api_base="https://api.workpeg.com", workpeg_pk="synthetic-test-secret",
                    peg_id=self.PEG_ID,
                    http=FakeHTTP(FakeResponse(status, {"detail": "must never escape"})))
                with self.assertRaises(WorkpegReadError) as caught:
                    reader._table(self.business, "rooms", "roomay_hotel_v1", alias=alias)
                details = caught.exception.diagnostic()
                self.assertEqual(details["stage"], stage)
                self.assertEqual(details["alias"], alias)
                self.assertEqual(details["http_status"], status)
                self.assertEqual(details["status_category"], category)
                self.assertEqual(details["error_code"], code)
                self.assertNotIn("must never escape", str(caught.exception))

    def test_row_access_and_malformed_metadata_have_distinct_stages(self):
        alias = "roomay-hotel-v1-rooms"
        denied_reader = WorkpegHotelReader(
            api_base="https://api.workpeg.com", workpeg_pk="synthetic-test-secret",
            peg_id=self.PEG_ID,
            http=FakeHTTP(FakeResponse(403, {"detail": "private"})))
        with self.assertRaises(WorkpegReadError) as caught:
            denied_reader._rows(self.business, str(uuid4()), alias=alias)
        self.assertEqual(caught.exception.diagnostic(), {
            "stage": "row_access", "alias": alias, "http_status": 403,
            "status_category": "forbidden", "error_code": "workpeg_http_403",
        })

        malformed = {**self.table, "columns": self.table["columns"][:-1]}
        metadata_reader = WorkpegHotelReader(
            api_base="https://api.workpeg.com", workpeg_pk="synthetic-test-secret",
            peg_id=self.PEG_ID, http=FakeHTTP(FakeResponse(200, [malformed])))
        with self.assertRaises(WorkpegReadError) as caught:
            metadata_reader._table(self.business, "rooms", "roomay_hotel_v1", alias=alias)
        self.assertEqual(caught.exception.diagnostic(), {
            "stage": "metadata_validation", "alias": alias, "http_status": None,
            "status_category": "contract_invalid",
            "error_code": "workpeg_table_contract_mismatch",
        })

    def test_row_validation_failure_and_unexpected_transport_error_are_sanitized(self):
        alias = "roomay-hotel-v1-room-types"
        # A malformed row reaches domain decoding only after all table and row
        # fetches. The public diagnostic retains the safe canonical table alias.
        malformed_rows = {key: [] for key in HOTEL_ALIASES}
        malformed_rows["room_types"] = [{"not": "a Workpeg row"}]
        reader = WorkpegHotelReader(
            api_base="https://api.workpeg.com", workpeg_pk="synthetic-test-secret",
            peg_id=self.PEG_ID, http=FakeHTTP(FakeResponse(200, [])))
        reader._table = lambda *args, **kwargs: self.table
        reader._rows = lambda *args, **kwargs: malformed_rows["room_types"]
        with self.assertRaises(WorkpegReadError) as caught:
            reader.read_snapshot(self.business)
        self.assertEqual(caught.exception.diagnostic()["stage"], "snapshot_validation")
        self.assertEqual(caught.exception.diagnostic()["alias"], alias)
        self.assertEqual(caught.exception.diagnostic()["error_code"],
                         "workpeg_hotel_snapshot_invalid")

        class BrokenHTTP:
            def get(self, *args, **kwargs):
                raise RuntimeError("private URL and response text")

        broken = WorkpegHotelReader(
            api_base="https://api.workpeg.com", workpeg_pk="synthetic-test-secret",
            peg_id=self.PEG_ID, http=BrokenHTTP())
        with self.assertRaises(WorkpegReadError) as caught:
            broken._table(self.business, "rooms", "roomay_hotel_v1", alias="roomay-hotel-v1-rooms")
        self.assertEqual(caught.exception.diagnostic()["status_category"], "network_error")
        self.assertEqual(caught.exception.diagnostic()["error_code"], "workpeg_unavailable")
        self.assertNotIn("private URL", str(caught.exception))


if __name__ == "__main__":
    import unittest
    unittest.main()
