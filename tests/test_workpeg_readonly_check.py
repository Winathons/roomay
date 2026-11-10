"""Sanitized, mocked tests for the owner-run Workpeg read-only check."""
from contextlib import redirect_stdout
import io
import json
import os
from unittest import TestCase
from unittest.mock import patch

from backend.verify_workpeg_readonly import main
from domain.workpeg_adapter import HOTEL_ALIASES


PEG_ID = "57bb470b-d454-4a0e-b011-59dcdb9a77d4"
BUSINESS_ID = "c23f9f30-2ae8-4680-a801-1507308f3dd9"
SYNTHETIC_SECRET = "MOCK-ONLY-NOT-A-WORKPEG-CREDENTIAL"


class ReadOnlyWorkpegCheckTests(TestCase):
    def run_main(self):
        output = io.StringIO()
        with redirect_stdout(output):
            result = main()
        return result, output.getvalue()

    def test_missing_configuration_fails_without_creating_reader(self):
        with patch.dict(os.environ, {}, clear=True), patch(
                "backend.verify_workpeg_readonly.WorkpegHotelReader") as reader:
            result, output = self.run_main()
        self.assertEqual(result, 2)
        self.assertEqual(json.loads(output), {
            "status": "BLOCKED", "reason": "configuration_incomplete"})
        reader.assert_not_called()

    def test_malformed_business_or_peg_fails_before_network(self):
        for values in (
                {"WORKPEG_PK": SYNTHETIC_SECRET, "ROOMAY_WORKPEG_PEG_ID": PEG_ID,
                 "ROOMAY_WORKPEG_BUSINESS_ID": "not-a-business-uuid"},
                {"WORKPEG_PK": SYNTHETIC_SECRET, "ROOMAY_WORKPEG_PEG_ID": "123",
                 "ROOMAY_WORKPEG_BUSINESS_ID": BUSINESS_ID}):
            with self.subTest(values=sorted(values)), patch.dict(os.environ, values, clear=True), patch(
                    "backend.verify_workpeg_readonly.WorkpegHotelReader") as reader:
                result, output = self.run_main()
                self.assertEqual(result, 2)
                self.assertEqual(json.loads(output), {
                    "status": "BLOCKED", "reason": "configuration_invalid"})
                reader.assert_not_called()
                self.assertNotIn(SYNTHETIC_SECRET, output)

    def test_success_reports_aliases_and_counts_without_private_rows_or_credentials(self):
        private_marker = "SYNTHETIC-PRIVATE-GUEST-NAME"
        snapshot = {key: [{"display_name": private_marker}]
                    for key in HOTEL_ALIASES}
        values = {"WORKPEG_PK": SYNTHETIC_SECRET,
                  "ROOMAY_WORKPEG_PEG_ID": PEG_ID.upper(),
                  "ROOMAY_WORKPEG_BUSINESS_ID": BUSINESS_ID}
        with patch.dict(os.environ, values, clear=True), patch(
                "backend.verify_workpeg_readonly.WorkpegHotelReader") as reader_type:
            reader_type.return_value.read_snapshot.return_value = snapshot
            result, output = self.run_main()
        report = json.loads(output)
        self.assertEqual(result, 0)
        self.assertEqual(report["status"], "PASS")
        self.assertTrue(report["read_only"])
        self.assertEqual({item["alias"] for item in report["tables"]},
                         set(HOTEL_ALIASES.values()))
        self.assertTrue(all(item["row_count"] == 1 for item in report["tables"]))
        self.assertNotIn(SYNTHETIC_SECRET, output)
        self.assertNotIn(private_marker, output)
        args = reader_type.call_args.kwargs
        self.assertEqual(args["api_base"], "https://api.workpeg.com")
        self.assertEqual(args["peg_id"], PEG_ID)
        reader_type.return_value.read_snapshot.assert_called_once_with(BUSINESS_ID)

    def test_remote_errors_are_sanitized(self):
        values = {"WORKPEG_PK": SYNTHETIC_SECRET,
                  "ROOMAY_WORKPEG_PEG_ID": PEG_ID,
                  "ROOMAY_WORKPEG_BUSINESS_ID": BUSINESS_ID}
        with patch.dict(os.environ, values, clear=True), patch(
                "backend.verify_workpeg_readonly.WorkpegHotelReader") as reader_type:
            reader_type.return_value.read_snapshot.side_effect = RuntimeError(
                "sensitive response body " + SYNTHETIC_SECRET)
            result, output = self.run_main()
        self.assertEqual(result, 1)
        self.assertEqual(json.loads(output), {
            "status": "FAIL", "reason": "read_or_contract_check_failed"})
        self.assertNotIn(SYNTHETIC_SECRET, output)
        self.assertNotIn("sensitive response body", output)
