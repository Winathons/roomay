"""WOR-70: confirm the inactive Workpeg Function cannot claim live success."""
import importlib.util
import inspect
import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "function" / "app" / "main.py"
DOCKERFILE = ROOT / "function" / "Dockerfile"


def load_entrypoint():
    spec = importlib.util.spec_from_file_location("roomay_function_contract", ENTRY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.main


class FunctionReadinessTests(unittest.TestCase):
    def test_entrypoint_has_documented_workpeg_signature(self):
        main = load_entrypoint()
        self.assertEqual(tuple(inspect.signature(main).parameters), ("context", "payload"))

    def test_all_envelopes_fail_closed_without_logging_or_side_effects(self):
        main = load_entrypoint()
        cases = (
            ({}, {}),
            ({"actor": "agent", "business": "test"}, {"status": "confirmed"}),
            ({"table": {"name": "reservations"}, "staff": {"email": "fictional@example.test"}},
             {"guest_id": "fictional", "status": "confirmed"}),
            ({"business": "test", "token": "sensitive-fixture-token"}, {"request": "towels"}),
        )
        for context, payload in cases:
            with self.subTest(context_shape=tuple(context.keys())):
                before_context = repr(context)
                before_payload = repr(payload)
                with self.assertRaisesRegex(RuntimeError, "^roomay_function_not_configured$") as exc:
                    main(context, payload)
                self.assertNotIn("sensitive-fixture-token", str(exc.exception))
                self.assertEqual(repr(context), before_context)
                self.assertEqual(repr(payload), before_payload)

    def test_malformed_inputs_refused_without_parsing_untrusted_claims(self):
        main = load_entrypoint()
        for context, payload in ((None, {}), ({}, None), ([], {}), ({}, []),
                                 ("staff", {"status": "confirmed"})):
            with self.subTest(context_type=type(context).__name__):
                with self.assertRaisesRegex(ValueError, "^invalid_workpeg_function_envelope$"):
                    main(context, payload)

    def test_dockerfile_uses_published_versioned_base_and_no_network_install(self):
        dockerfile = DOCKERFILE.read_text(encoding="utf-8")
        self.assertIn(
            "FROM registry.gitlab.com/workpeg/workpeg-sdk/pegfn-base:0.157.0",
            dockerfile,
        )
        self.assertIn("COPY app /app/app", dockerfile)
        self.assertIsNone(re.search(r"(?im)^\s*(RUN|ENTRYPOINT|USER|EXPOSE|ADD)\s", dockerfile))
        self.assertNotIn("pip install", "\n".join(
            line for line in dockerfile.splitlines() if not line.lstrip().startswith("#")
        ))
        self.assertTrue(dockerfile.isascii(), "Workpeg requires ASCII Dockerfile")

    def test_release_remains_ui_only_and_no_actions_are_registered(self):
        manifest = json.loads((ROOT / "workpeg.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest, {"namespace": "roomay"})
        self.assertEqual((ROOT / "function" / "requirements.txt").read_text(encoding="utf-8"), "")


if __name__ == "__main__":
    unittest.main()
