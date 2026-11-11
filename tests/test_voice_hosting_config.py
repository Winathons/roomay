"""Offline safety checks for the prepared Render WSGI configuration."""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]


class VoiceHostingConfigTests(unittest.TestCase):
    def test_render_service_uses_existing_tts_wsgi_and_bounded_runtime(self):
        config = (ROOT / "render.yaml").read_text(encoding="utf-8")
        self.assertIn("runtime: python", config)
        self.assertIn("plan: 0.5c-512mb", config)
        self.assertIn("region: frankfurt", config)
        self.assertIn('autoDeployTrigger: "off"', config)
        self.assertIn("voice_adapter.tts_wsgi:application", config)
        self.assertIn("--workers 1", config)
        self.assertIn("--threads 2", config)
        self.assertIn("--worker-connections 16", config)
        self.assertIn("--backlog 16", config)
        self.assertIn("--timeout 75", config)

    def test_required_provider_credentials_are_never_literal_blueprint_values(self):
        config = (ROOT / "render.yaml").read_text(encoding="utf-8")
        for key in ("ROOMAY_VAPI_BEARER_TOKEN", "YARNGPT_API_KEY"):
            with self.subTest(key=key):
                match = re.search(
                    rf"(?ms)^      - key: {key}\n(?P<value>.*?)(?=^      - key:|\Z)",
                    config,
                )
                self.assertIsNotNone(match)
                self.assertIn("sync: false", match.group("value"))
                self.assertNotIn("value:", match.group("value"))

    def test_remi_configuration_and_access_logs_are_minimal(self):
        config = (ROOT / "render.yaml").read_text(encoding="utf-8")
        self.assertIn("key: ROOMAY_TTS_DEFAULT_VOICE\n        value: remi", config)
        self.assertIn("key: YARNGPT_VOICE_REMI\n        value: remi", config)
        self.assertIn('key: YARNGPT_TIMEOUT_SECONDS\n        value: "20"', config)
        log_line = next(line for line in config.splitlines()
                        if "--access-logformat" in line)
        self.assertIn("%(U)s", log_line)  # path without query string
        for sensitive_field in ("%(h)s", "%(r)s", "%(q)s", "%(f)s", "%(a)s",
                                "Authorization", "YARNGPT_API_KEY"):
            self.assertNotIn(sensitive_field, log_line)

    def test_host_runtime_dependencies_are_separate_from_workpeg_sdk(self):
        requirements = (ROOT / "requirements-voice.txt").read_text(encoding="utf-8")
        self.assertIn("gunicorn==27.0.0", requirements)
        self.assertNotIn("workpeg", requirements.lower())


if __name__ == "__main__":
    unittest.main()
