"""Smoke-check deployable WSGI entry points without provider/network calls."""

import os
import subprocess
import sys
import unittest


class VoiceDeploymentEntrypointTests(unittest.TestCase):
    def test_two_endpoints_import_with_isolated_placeholder_configuration(self):
        env = {"PATH": os.environ.get("PATH", "")}
        if "SYSTEMROOT" in os.environ:
            env["SYSTEMROOT"] = os.environ["SYSTEMROOT"]
        env.update({
            "ROOMAY_VAPI_TOOL_BEARER_TOKEN": "offline-tool-token-placeholder-0000000000000000",
            "ROOMAY_VAPI_BEARER_TOKEN": "offline-tts-token-placeholder-0000000000000000",
            "YARNGPT_API_KEY": "offline-yarngpt-key-placeholder",
            "ROOMAY_TTS_DEFAULT_VOICE": "remi",
            "YARNGPT_VOICE_REMI": "remi",
        })
        result = subprocess.run(
            [sys.executable, "-c", (
                "from voice_adapter.tool_wsgi import application as tool; "
                "from voice_adapter.tts_wsgi import application as tts; "
                "assert callable(tool) and callable(tts)"
            )],
            cwd=os.path.dirname(os.path.dirname(__file__)),
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, msg="WSGI entry point import failed")
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "")


if __name__ == "__main__":
    unittest.main()
