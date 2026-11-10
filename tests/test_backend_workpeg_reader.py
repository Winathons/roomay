"""Mocked, read-only boundary tests; no Workpeg API requests are made."""
from unittest import TestCase
from uuid import uuid4

from backend.workpeg_reader import WorkpegHotelReader, WorkpegReadError
from domain.workpeg_adapter import contract_by_key


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
        self.calls.append((url, params, headers, timeout))
        return self.response


class WorkpegReaderTests(TestCase):
    def setUp(self):
        self.business = str(uuid4())
        self.contract = contract_by_key()["rooms"]
        self.table = {
            "uuid": str(uuid4()), "name": self.contract["name"],
            "namespace": self.contract["namespace"], "permission": "700",
            "peg": 4812, "metadata": self.contract["metadata"],
            "columns": self.contract["columns"],
        }

    def test_server_reader_accepts_only_configured_peg_owned_table(self):
        http = FakeHTTP(FakeResponse(200, [self.table]))
        reader = WorkpegHotelReader(api_base="https://api.workpeg.com",
                                    workpeg_pk="synthetic-test-secret",
                                    peg_id="4812", http=http)
        table = reader._table(self.business, "rooms", "roomay_hotel_v1")
        self.assertEqual(table["uuid"], self.table["uuid"])
        self.assertEqual(http.calls[0][1], {"namespace": "roomay_hotel_v1"})
        self.assertEqual(http.calls[0][2], {"Authorization": "Bearer synthetic-test-secret"})
        self.assertEqual(len(http.calls), 1)

    def test_reader_fails_closed_for_wrong_peg_permission_or_schema(self):
        for changed in (
                {**self.table, "peg": 2},
                {**self.table, "permission": "777"},
                {**self.table, "columns": self.table["columns"][:-1]}):
            with self.subTest(changed=changed.get("peg", changed.get("permission", "schema"))):
                reader = WorkpegHotelReader(
                    api_base="https://api.workpeg.com", workpeg_pk="synthetic-test-secret",
                    peg_id="4812", http=FakeHTTP(FakeResponse(200, [changed])))
                with self.assertRaises(WorkpegReadError):
                    reader._table(self.business, "rooms", "roomay_hotel_v1")

    def test_reader_reports_denied_or_ambiguous_inventory_without_fallback(self):
        for response in (FakeResponse(403, {"detail": "denied"}),
                         FakeResponse(200, [self.table, self.table])):
            with self.subTest(response=response.status_code):
                reader = WorkpegHotelReader(
                    api_base="https://api.workpeg.com", workpeg_pk="synthetic-test-secret",
                    peg_id="4812", http=FakeHTTP(response))
                with self.assertRaises(WorkpegReadError):
                    reader._table(self.business, "rooms", "roomay_hotel_v1")


if __name__ == "__main__":
    import unittest
    unittest.main()
