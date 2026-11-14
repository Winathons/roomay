"""Versioned guest MVP contract shape and fail-closed vocabulary checks."""
import json
from pathlib import Path
import unittest


SCHEMA_PATH = (Path(__file__).resolve().parents[1]
               / "docs/contracts/roomay.guest-mvp.v1.schema.json")


class GuestMvpContractV1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        cls.defs = cls.schema["$defs"]

    def test_contract_is_versioned_and_has_all_consumer_messages(self):
        self.assertEqual(self.schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertEqual(self.schema["$id"], "urn:roomay:contracts:guest-mvp:v1")
        self.assertEqual(self.schema["properties"]["contract_version"]["const"], "roomay.guest-mvp.v1")
        self.assertEqual(set(self.schema["properties"]["message_type"]["enum"]), {
            "guest_context", "hotel_information", "conversation_action",
            "request_draft", "request_outcome", "reception_transition",
            "guest_status_readback",
        })

    def test_public_shapes_reject_unspecified_fields_and_require_identity_scope(self):
        for name in self.schema["properties"]["message_type"]["enum"]:
            with self.subTest(name=name):
                definition = self.defs[name]
                self.assertEqual(definition["type"], "object")
                self.assertTrue(definition["additionalProperties"] is False)
                if name in {"conversation_action", "guest_context", "request_outcome"}:
                    self.assertTrue(definition["oneOf"])
                    for operation in definition["oneOf"]:
                        self.assertTrue(set(operation["required"]) <= set(definition["properties"]))
                else:
                    self.assertTrue(definition["required"])
                    self.assertTrue(set(definition["required"]) <= set(definition["properties"]))
        context = self.defs["guest_context"]["properties"]["stay"]
        self.assertIn("room_id", context["required"])
        self.assertIn("verified", context["required"])
        self.assertEqual(context["properties"]["verified"]["const"], True)

    def test_confirmation_and_mutation_are_distinct_explicit_operations(self):
        action = self.defs["conversation_action"]["properties"]
        self.assertEqual(set(action["operation"]["enum"]), {"message", "confirm", "cancel"})
        draft = self.defs["request_draft"]
        self.assertIn("confirmation_required", draft["required"])
        self.assertEqual(draft["properties"]["confirmation_required"]["const"], True)
        self.assertIn("confirmation_handle", draft["required"])

    def test_failure_and_persistence_states_are_explicitly_distinguished(self):
        failures = set(self.defs["failure_code"]["enum"])
        self.assertTrue({
            "unauthenticated", "wrong_business", "wrong_room", "stay_revoked",
            "stay_expired", "duplicate_operation", "workpeg_unavailable",
            "persistence_uncertain",
        } <= failures)
        outcomes = set(self.defs["request_outcome"]["properties"]["state"]["enum"])
        self.assertTrue({"created", "duplicate", "rejected", "unavailable", "uncertain"} <= outcomes)
        self.assertEqual(self.defs["guest_status_readback"]["properties"]["status"]["enum"],
                         ["received", "assigned", "acknowledged", "in_progress",
                          "resolved", "reopened", "cancelled", "escalated"])

    def test_guest_projection_excludes_internal_identity_and_audit_fields(self):
        fields = set(self.defs["guest_status_readback"]["properties"])
        self.assertFalse({"guest_id", "business_id", "stay_id", "room_id", "audit_events"} & fields)


if __name__ == "__main__":
    unittest.main()
