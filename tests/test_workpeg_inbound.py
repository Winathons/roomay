import unittest
from unittest.mock import Mock

import requests

from domain.workpeg_inbound import (
    InboundConfig, InboundError, WorkpegInboundTransport,
    stable_idempotency_key,
)


BIZ = "11111111-1111-4111-8111-111111111111"
TABLE = "22222222-2222-4222-8222-222222222222"


def response(status, body=None, headers=None):
    result = Mock(status_code=status)
    result.json.return_value = body
    result.headers = headers or {}
    return result


class WorkpegInboundTests(unittest.TestCase):
    def setUp(self):
        self.session = Mock()
        self.transport = WorkpegInboundTransport(
            InboundConfig(True, "wpin_test_secret", BIZ, TABLE),
            session=self.session)

    def test_disabled_by_default_makes_no_request(self):
        transport = WorkpegInboundTransport(InboundConfig(), session=self.session)
        with self.assertRaisesRegex(InboundError, "transport_disabled"):
            transport.write_staging_row(source_id="q-1", data={"source_id": "q-1"}, business_id=BIZ)
        self.session.request.assert_not_called()

    def test_destination_checked_before_post_and_staging_is_not_staff_delivery(self):
        self.session.request.side_effect = [
            response(200, {"business": BIZ, "table": TABLE}),
            response(201, {"id": 42, "business": BIZ, "table": TABLE}),
        ]
        result = self.transport.write_staging_row(
            source_id="queue-id-1", business_id=BIZ,
            data={"source_id": "queue-id-1", "payload_digest": "d" * 64})
        self.assertEqual(result["status"], "workpeg_staging_persisted")
        self.assertEqual(result["operational_request_state"], "not_asserted")
        self.assertEqual(result["staff_acknowledgement_state"], "not_asserted")
        first, second = self.session.request.call_args_list
        self.assertEqual(first.args[:2], ("GET", "https://api.workpeg.com/v1/inbound/whoami/"))
        self.assertFalse(first.kwargs["allow_redirects"])
        self.assertFalse(second.kwargs["allow_redirects"])
        self.assertEqual(second.kwargs["headers"]["Idempotency-Key"], stable_idempotency_key("queue-id-1"))
        self.assertNotIn("Origin", second.kwargs["headers"])
        self.assertEqual(second.kwargs["data"], b'{"data":{"source_id":"queue-id-1","payload_digest":"' + b"d" * 64 + b'"}}')

    def test_destination_mismatch_stops_before_write(self):
        self.session.request.return_value = response(200, {"business": BIZ, "table": "wrong"})
        with self.assertRaisesRegex(InboundError, "destination_mismatch"):
            self.transport.write_staging_row(source_id="q", business_id=BIZ, data={"x": "y"})
        self.assertEqual(self.session.request.call_count, 1)

    def test_wrong_business_stops_before_any_request(self):
        with self.assertRaisesRegex(InboundError, "business_scope_mismatch"):
            self.transport.write_staging_row(source_id="q", business_id="wrong", data={"x": "y"})
        self.session.request.assert_not_called()

    def test_duplicate_response_is_staging_only(self):
        self.session.request.side_effect = [
            response(200, {"business": BIZ, "table": TABLE}),
            response(200, {"id": 42, "business": BIZ, "table": TABLE}),
        ]
        result = self.transport.write_staging_row(source_id="q", business_id=BIZ, data={"x": "y"})
        self.assertEqual(result["staging_row_id"], 42)
        self.assertEqual(result["staff_acknowledgement_state"], "not_asserted")

    def test_timeout_and_409_are_unknown_and_retry_same_key(self):
        self.session.request.side_effect = [response(200, {"business": BIZ, "table": TABLE}), requests.Timeout()]
        with self.assertRaises(InboundError) as caught:
            self.transport.write_staging_row(source_id="same", business_id=BIZ, data={"x": "y"})
        self.assertEqual(caught.exception.state, "staging_outcome_unknown")
        first_key = self.session.request.call_args.kwargs["headers"]["Idempotency-Key"]
        self.assertEqual(first_key, stable_idempotency_key("same"))

        self.session.request.side_effect = [
            response(200, {"business": BIZ, "table": TABLE}), response(409)]
        with self.assertRaisesRegex(InboundError, "write_in_progress"):
            self.transport.write_staging_row(source_id="same", business_id=BIZ, data={"x": "y"})
        self.assertEqual(self.session.request.call_args.kwargs["headers"]["Idempotency-Key"],
                         first_key)

    def test_auth_rate_limit_and_hook_failure_are_distinct(self):
        cases = [(401, "unauthorized"), (403, "forbidden"), (429, "rate_limited"),
                 (503, "hook_unavailable")]
        for status, code in cases:
            with self.subTest(status=status):
                self.session.request.side_effect = [
                    response(200, {"business": BIZ, "table": TABLE}), response(status)]
                with self.assertRaises(InboundError) as caught:
                    self.transport.write_staging_row(source_id="q", business_id=BIZ, data={"x": "y"})
                self.assertIn(code, caught.exception.code)

    def test_retry_after_is_parsed_and_capped(self):
        self.session.request.side_effect = [
            response(200, {"business": BIZ, "table": TABLE}),
            response(429, headers={"Retry-After": "7200"}),
        ]
        with self.assertRaises(InboundError) as caught:
            self.transport.write_staging_row(source_id="q", business_id=BIZ, data={"x": "y"})
        self.assertEqual(caught.exception.state, "staging_not_written")
        self.assertEqual(caught.exception.retry_after, 3600)

        self.session.request.side_effect = [
            response(200, {"business": BIZ, "table": TABLE}),
            response(409, headers={"Retry-After": "3"}),
        ]
        with self.assertRaises(InboundError) as caught:
            self.transport.write_staging_row(source_id="q", business_id=BIZ, data={"x": "y"})
        self.assertEqual(caught.exception.state, "staging_outcome_unknown")
        self.assertEqual(caught.exception.retry_after, 3)

    def test_timeout_while_checking_whoami_is_known_not_written(self):
        self.session.request.side_effect = requests.Timeout()
        with self.assertRaises(InboundError) as caught:
            self.transport.write_staging_row(source_id="q", business_id=BIZ, data={"x": "y"})
        self.assertEqual(caught.exception.state, "staging_not_written")
        self.assertEqual(self.session.request.call_count, 1)

    def test_oversized_payload_does_not_make_a_request(self):
        with self.assertRaisesRegex(InboundError, "payload_too_large"):
            self.transport.write_staging_row(
                source_id="q", business_id=BIZ, data={"note": "x" * (256 * 1024)})
        self.session.request.assert_not_called()

    def test_whoami_authorization_failure_does_not_post(self):
        self.session.request.return_value = response(401)
        with self.assertRaisesRegex(InboundError, "unauthorized"):
            self.transport.write_staging_row(source_id="q", business_id=BIZ, data={"x": "y"})
        self.assertEqual(self.session.request.call_count, 1)

    def test_idempotency_key_is_stable_printable_and_bounded(self):
        key = stable_idempotency_key("source-1")
        self.assertEqual(key, stable_idempotency_key("source-1"))
        self.assertLessEqual(len(key), 100)
        self.assertTrue(key.isascii() and all(32 <= ord(char) <= 126 for char in key))


if __name__ == "__main__":
    unittest.main()
