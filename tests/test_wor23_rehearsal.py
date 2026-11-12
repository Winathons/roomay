"""WOR-23 CLI rehearsal regression. Never accesses Workpeg or a public host."""
import json
import subprocess
import sys
import unittest
from pathlib import Path

from tools.wor23_rehearsal import run_synthetic_rehearsal


ROOT = Path(__file__).resolve().parent.parent


class SyntheticRehearsalTests(unittest.TestCase):
    def test_core_journey_status_and_evidence_are_explicitly_local(self):
        result = run_synthetic_rehearsal()
        self.assertEqual(result["issue"], "WOR-23")
        self.assertEqual(result["outcome"], "synthetic_rehearsal_passed")
        self.assertEqual(result["evidence_scope"], "local_process_only")
        self.assertEqual(result["record_writes"], "none_external; process_memory_only")
        self.assertEqual(len(result["steps"]), len(set(result["steps"])))
        self.assertGreaterEqual(len(result["steps"]), 11)
        self.assertTrue(all(result["verified"].values()))
        for item in (
            "guest_reads_resolved_on_same_process_reload",
            "wrong_room_and_other_session_denied",
            "provider_failure_no_guest_submission",
            "separate_offline_blocked_room_reassignment_plan",
        ):
            self.assertIn(item, result["steps"])
        for blocker in (
            "real_workpeg_guest_request_write",
            "cross_process_or_cross_server_persistence",
            "real_workpeg_department_staff_auth_and_readback",
        ):
            self.assertIn(blocker, result["not_verified"])

    def test_output_is_sanitized_and_never_reports_real_success(self):
        report = json.dumps(run_synthetic_rehearsal())
        for private_marker in (
            "session_id", "guest_id", "request_id", "operation_signature",
            "Amara Okafor", "Chidi Nwosu", "Tola Ibrahim",
            "authorization_token", "access_token", "Bearer ",
        ):
            self.assertNotIn(private_marker, report)
        self.assertNotIn("hosted_rehearsal_passed", report)
        self.assertIn("process_memory_only", report)

    def test_command_prints_reproducible_json(self):
        result = subprocess.run(
            [sys.executable, "-m", "tools.wor23_rehearsal"],
            cwd=ROOT, capture_output=True, text=True, check=True, timeout=30,
        )
        self.assertEqual(result.stderr, "")
        payload = json.loads(result.stdout)
        self.assertEqual(payload["outcome"], "synthetic_rehearsal_passed")
        self.assertEqual(payload["verified"], run_synthetic_rehearsal()["verified"])


if __name__ == "__main__":
    unittest.main()
