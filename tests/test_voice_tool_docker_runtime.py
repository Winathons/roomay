"""Offline image smoke for isolated Vapi Function intent router.

No provider calls, hotel-data reads or hosted writes. Docker smoke is opt-in in
local development and enabled in the repository's CI workflow.
"""

import http.client
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest
import uuid


ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = ROOT / "Dockerfile.tool"
TOKEN = "offline-tool-test-secret-please-never-use-in-production-00001"


class ToolImageContractTests(unittest.TestCase):
    def test_distinct_from_tts_and_copies_pure_domain_code(self):
        image = DOCKERFILE.read_text(encoding="utf-8")
        self.assertIn("FROM python:3.13.5-slim", image)
        self.assertIn("voice_adapter.tool_wsgi:application", image)
        self.assertIn("COPY domain/", image)
        self.assertIn("COPY voice_adapter/", image)
        self.assertIn("USER 10001:10001", image)
        self.assertIn("0.0.0.0:${PORT:-8080}", image)
        self.assertIn("--workers 1", image)
        self.assertIn("--threads 2", image)
        self.assertIn("%(m)s %(U)s %(s)s %(L)s", image)
        self.assertNotIn("YARNGPT_API_KEY=", image)
        self.assertNotIn("ROOMAY_VAPI_BEARER_TOKEN=", image)
        self.assertNotIn("ROOMAY_VAPI_TOOL_BEARER_TOKEN=", image)
        ignore = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
        self.assertNotIn("domain/", ignore)
        for path in (".git", ".venv", ".env", ".env.*", "*.pem", "*.key", "*.crt", "tests/"):
            with self.subTest(path=path):
                self.assertIn(path, ignore)


@unittest.skipUnless(
    os.environ.get("ROOMAY_RUN_DOCKER_TESTS") == "1" and shutil.which("docker"),
    "Docker smoke requires ROOMAY_RUN_DOCKER_TESTS=1 and a running Docker engine",
)
class ToolDockerRuntimeSmokeTests(unittest.TestCase):
    def test_container_returns_405_401_400_and_truthful_200(self):
        suffix = uuid.uuid4().hex[:12]
        tag, name = "roomay-tool-smoke-" + suffix, "roomay-tool-smoke-" + suffix
        with tempfile.TemporaryDirectory(prefix="roomay-tool-docker-config-") as config:
            env = dict(os.environ, DOCKER_CONFIG=config)
            built = subprocess.run(
                ["docker", "build", "--file", str(DOCKERFILE), "--tag", tag, str(ROOT)],
                cwd=ROOT, env=env, capture_output=True, text=True, timeout=300, check=False,
            )
            self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
            try:
                run = subprocess.run(
                    [
                        "docker", "run", "--detach", "--rm", "--name", name,
                        "--publish", "127.0.0.1::8080",
                        "--env", "PORT=8080",
                        "--env", "ROOMAY_VAPI_TOOL_BEARER_TOKEN=" + TOKEN,
                        "--env", "ROOMAY_VAPI_TOOL_REQUESTS_PER_MINUTE=10",
                        tag,
                    ],
                    env=env, capture_output=True, text=True, timeout=30, check=False,
                )
                self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
                port_result = subprocess.run(
                    ["docker", "port", name, "8080/tcp"],
                    env=env, capture_output=True, text=True, timeout=15, check=False,
                )
                self.assertEqual(port_result.returncode, 0, port_result.stdout + port_result.stderr)
                host_port = int(port_result.stdout.strip().rsplit(":", 1)[1])

                def request(method, body=None, *, bearer=None):
                    payload = (json.dumps(body).encode("utf-8") if body is not None else b"")
                    headers = {"Content-Type": "application/json"}
                    if bearer is not None:
                        headers["Authorization"] = "Bearer " + bearer
                    conn = http.client.HTTPConnection("127.0.0.1", host_port, timeout=3)
                    try:
                        conn.request(method, "/tool-calls", body=payload, headers=headers)
                        response = conn.getresponse()
                        return response.status, response.read()
                    finally:
                        conn.close()

                deadline = time.monotonic() + 30
                while True:
                    try:
                        status, _ = request("GET")
                        self.assertEqual(status, 405)
                        break
                    except OSError:
                        if time.monotonic() > deadline:
                            self.fail("tool container did not start")
                        time.sleep(0.2)

                status, raw = request("POST", {}, bearer="invalid-placeholder-token")
                self.assertEqual(status, 401)
                self.assertIn(b"unauthorized", raw)

                status, raw = request("POST", {}, bearer=TOKEN)
                self.assertEqual(status, 400)
                self.assertIn(b"invalid", raw)

                body = {"message": {"type": "tool-calls", "call": {"id": "offline-call"},
                                   "toolCallList": [
                                       {"id": "tool-1", "type": "function", "function": {
                                           "name": "roomay_route_caller_intent",
                                           "arguments": {"utterance": "Please bring extra towels to room 205"},
                                       }}
                                   ]}}
                status, raw = request("POST", body, bearer=TOKEN)
                self.assertEqual(status, 200)
                result = json.loads(raw)["results"][0]
                self.assertEqual(result["toolCallId"], "tool-1")
                routing = json.loads(result["result"])
                self.assertEqual(routing["state"], "guest_verification_required")
                self.assertEqual(routing["department"], "housekeeping")
                self.assertFalse(routing["submitted"])
                self.assertFalse(routing["persisted"])
                self.assertNotIn("205", json.dumps(routing))
                self.assertNotIn(TOKEN, raw.decode("utf-8"))

                logs = subprocess.run(
                    ["docker", "logs", name], env=env, capture_output=True,
                    text=True, timeout=15, check=False,
                )
                self.assertNotIn(TOKEN, logs.stdout + logs.stderr)
                self.assertNotIn("Please bring extra towels", logs.stdout + logs.stderr)
            finally:
                subprocess.run(
                    ["docker", "rm", "--force", name],
                    env=env, capture_output=True, text=True, timeout=30, check=False,
                )
                subprocess.run(
                    ["docker", "image", "rm", "--force", tag],
                    env=env, capture_output=True, text=True, timeout=40, check=False,
                )


if __name__ == "__main__":
    unittest.main()
