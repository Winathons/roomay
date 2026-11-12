"""Offline Docker build/start smoke for the existing Remi TTS WSGI app."""

import http.client
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest
import uuid


ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = ROOT / "Dockerfile.voice"


class VoiceDockerfileContractTests(unittest.TestCase):
    def test_dockerfile_preserves_runtime_and_contains_no_credentials(self):
        dockerfile = DOCKERFILE.read_text(encoding="utf-8")
        self.assertIn("FROM python:3.13.5-slim", dockerfile)
        self.assertIn("requirements-voice.txt", dockerfile)
        self.assertIn("voice_adapter.tts_wsgi:application", dockerfile)
        self.assertIn("0.0.0.0:${PORT:-8080}", dockerfile)
        self.assertIn("--workers 1", dockerfile)
        self.assertIn("--threads 2", dockerfile)
        self.assertIn("--worker-class gthread", dockerfile)
        self.assertIn("--access-logformat '%(m)s %(U)s %(s)s %(L)s'", dockerfile)
        self.assertNotIn("YARNGPT_API_KEY=", dockerfile)
        self.assertNotIn("ROOMAY_VAPI_BEARER_TOKEN=", dockerfile)

    def test_build_context_excludes_local_secrets_and_development_artifacts(self):
        ignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")
        for pattern in (".git", ".venv", ".env", ".env.*", "*.pem", "*.key", "*.crt"):
            with self.subTest(pattern=pattern):
                self.assertIn(pattern, ignore)


@unittest.skipUnless(
    os.environ.get("ROOMAY_RUN_DOCKER_TESTS") == "1" and shutil.which("docker"),
    "Set ROOMAY_RUN_DOCKER_TESTS=1 with a working Docker engine to build and run the voice image",
)
class VoiceDockerRuntimeSmokeTests(unittest.TestCase):
    def test_image_builds_and_serves_auth_rejection_without_provider_call(self):
        tag = "roomay-voice-smoke-" + uuid.uuid4().hex[:12]
        name = "roomay-voice-smoke-" + uuid.uuid4().hex[:12]
        docker_config = tempfile.TemporaryDirectory(prefix=".docker-smoke-config-", dir=ROOT)
        self.addCleanup(docker_config.cleanup)
        docker_env = dict(os.environ, DOCKER_CONFIG=docker_config.name)
        build = subprocess.run(
            ["docker", "build", "--file", str(DOCKERFILE), "--tag", tag, str(ROOT)],
            cwd=ROOT, env=docker_env, capture_output=True, text=True, timeout=300, check=False,
        )
        self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
        try:
            run = subprocess.run(
                [
                    "docker", "run", "--detach", "--rm", "--name", name,
                    "--publish", "127.0.0.1::8080",
                    "--env", "PORT=8080",
                    "--env", "ROOMAY_VAPI_BEARER_TOKEN=offline-vapi-placeholder-token-000000000000",
                    "--env", "YARNGPT_API_KEY=offline-yarngpt-placeholder",
                    "--env", "ROOMAY_TTS_DEFAULT_VOICE=remi",
                    "--env", "YARNGPT_VOICE_REMI=remi",
                    tag,
                ],
                env=docker_env, capture_output=True, text=True, timeout=20, check=False,
            )
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            port_result = subprocess.run(
                ["docker", "port", name, "8080/tcp"],
                env=docker_env, capture_output=True, text=True, timeout=10, check=False,
            )
            self.assertEqual(port_result.returncode, 0, port_result.stderr)
            host_port = int(port_result.stdout.strip().rsplit(":", 1)[1])

            deadline = time.monotonic() + 20
            while True:
                try:
                    connection = http.client.HTTPConnection("127.0.0.1", host_port, timeout=2)
                    connection.request("GET", "/synthesize")
                    response = connection.getresponse()
                    self.assertEqual(response.status, 405)
                    response.read()
                    connection.close()
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        logs = subprocess.run(
                            ["docker", "logs", name], capture_output=True,
                            env=docker_env, text=True, timeout=10, check=False,
                        )
                        self.fail("container did not start: " + logs.stdout + logs.stderr)
                    time.sleep(0.2)

            connection = http.client.HTTPConnection("127.0.0.1", host_port, timeout=2)
            connection.request("POST", "/synthesize", body="{}",
                               headers={"Content-Type": "application/json"})
            response = connection.getresponse()
            self.assertEqual(response.status, 401)
            self.assertEqual(response.read(), b'{"error":"unauthorized"}')
            connection.close()

            logs = subprocess.run(
                ["docker", "logs", name], capture_output=True,
                env=docker_env, text=True, timeout=10, check=False,
            )
            self.assertNotIn("offline-vapi-placeholder-token-000000000000", logs.stdout + logs.stderr)
            self.assertNotIn("offline-yarngpt-placeholder", logs.stdout + logs.stderr)
        finally:
            subprocess.run(["docker", "rm", "--force", name],
                           env=docker_env, capture_output=True, text=True, timeout=20, check=False)
            subprocess.run(["docker", "image", "rm", "--force", tag],
                           env=docker_env, capture_output=True, text=True, timeout=30, check=False)


if __name__ == "__main__":
    unittest.main()
