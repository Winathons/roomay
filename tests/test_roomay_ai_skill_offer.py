"""Contract tests for the standalone business-scoped ROOMAY Workpeg AI Skill offer.

These are local static invariants. They do not establish that Workpeg AI
actually invoked a tool, sent an email, saved a Workpeg row or verified a stay.
"""
import json
from pathlib import Path
import re
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
        self.assertEqual(self.offer["version"], "0.3.0")
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

    def test_delivery_claim_requires_verified_send(self):
        text = self.instructions.lower()
        self.assertIn("genuine successful tool result", text)
        self.assertIn("trusted hotel directory", text)
        self.assertIn("do not claim it was sent", text)
        self.assertIn("complete creation-audit readback", text)
        self.assertIn("no real send action", text) if "no real send action" in text else self.assertIn("no verified sending tool", text)

    def test_status_updates_require_trusted_audit(self):
        text = self.instructions.lower()
        for token in ("complete", "audit", "in progress", "resolved", "status", "stay-scoped"):
            self.assertIn(token, text)

    def test_hazard_and_privacy_guards(self):
        text = self.instructions.lower()
        for token in ("buzzing", "sparking", "burning", "emergency", "other guests", "guest stay"):
            self.assertIn(token, text)


if __name__ == "__main__":
    unittest.main()
