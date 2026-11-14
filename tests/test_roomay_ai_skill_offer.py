"""Contract tests for the standalone business-scoped ROOMAY Workpeg AI Skill offer.

These are local static invariants. They do not establish that Workpeg AI
actually invoked a tool, sent an email, saved a Workpeg row or verified a stay.
"""
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
OFFER = ROOT / "skills" / "roomay-service-intake.json"


class RoomaySkillOfferTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = OFFER.read_bytes()
        cls.offer = json.loads(cls.raw.decode("utf-8"))
        cls.instructions = cls.offer["instructions"]

    def test_standalone_offer_has_valid_bounds_and_keys(self):
        self.assertLessEqual(len(self.raw), 64 * 1024)
        self.assertLessEqual(len(self.instructions.encode("utf-8")), 10000)
        self.assertEqual(
            set(self.offer),
            {"name", "version", "title", "description", "command", "message", "instructions"},
        )
        self.assertEqual(self.offer["name"], "roomay-service-intake")
        self.assertEqual(self.offer["version"], "0.4.0")
        self.assertLessEqual(len(self.offer["command"]), 48)
        self.assertLessEqual(len(self.offer["message"]), 400)

    def test_guest_entry_is_friendly_and_without_internal_disclaimers(self):
        self.assertIn("Hi ROOMAY, I need some help.", self.offer["message"])
        self.assertNotIn("fictional", self.offer["message"].lower())
        self.assertNotIn("draft only", self.offer["message"].lower())
        self.assertNotIn("not submitted", self.offer["message"].lower())
        self.assertIn("welcome to roomay", self.instructions.lower())

    def test_reception_is_coordination_hub(self):
        guidance = self.instructions.lower()
        for word in ("reception", "maintenance", "housekeeping", "food & beverage", "confirmation"):
            self.assertIn(word, guidance)

    def test_no_guest_homework_after_confirmation(self):
        guidance = self.instructions.lower()
        self.assertIn("thanks! i've noted your air-conditioning request here", guidance)
        self.assertIn("do not tell the guest to share it with the front desk", guidance)
        self.assertIn("end the message there", guidance)
        self.assertIn("no real authorized send/save", guidance)

    def test_no_false_delivery_or_status(self):
        guidance = self.instructions.lower()
        self.assertIn("only after a successful actual tool result", guidance)
        self.assertIn("do not call it a committed roomay service ticket", guidance)
        self.assertIn("complete committed audit history", guidance)
        self.assertIn("never manufacture delivery", guidance)
        self.assertIn("no verified source", guidance)

    def test_status_updates_are_guest_scoped_and_evidence_based(self):
        guidance = self.instructions.lower()
        for phrase in ("active stay", "trusted session identity", "actual request",
                       "status and audit", "if there is no verified source",
                       "do not imply background monitoring"):
            self.assertIn(phrase, guidance)

    def test_hazard_and_privacy_guards(self):
        text = self.instructions.lower()
        for token in ("buzzing", "sparking", "burning", "emergency", "other guests", "guest stay"):
            self.assertIn(token, text)


if __name__ == "__main__":
    unittest.main()
