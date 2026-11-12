"""WOR-68 regression: only main triggers the required release-check workflow.

This tests the checked-in workflow contract, not whether the GitHub ruleset
actually enforces it. GitHub administrator must configure ruleset separately.
"""
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "workpeg-ui.yml"


class MainBranchWorkflowTests(unittest.TestCase):
    def test_only_main_triggers_release_workflow(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        branches = re.findall(r"^\s*branches:\s*\[([^\]]+)\]\s*$", text, re.MULTILINE)
        self.assertEqual(branches, ["main", "main"])
        self.assertIn("pull_request:", text)
        self.assertIn("push:", text)
        self.assertNotIn("staging", text)

    def test_check_name_and_offline_release_gates_stay_registered(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("name: Roomay UI Check", text)
        self.assertIn("name: Workpeg UI build", text)
        self.assertIn("python -m unittest discover -s tests -v", text)
        self.assertIn("python -m compileall -q ui function domain tests", text)
        self.assertIn("workpeg ui build ui/", text)
        self.assertIn("test_release_candidate.py", text)
        self.assertIn("permissions:\n  contents: read", text)
        self.assertNotIn("workpeg ui serve", text)
        self.assertNotIn("--fake-cloud", text)


if __name__ == "__main__":
    unittest.main()
