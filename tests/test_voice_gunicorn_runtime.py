"""Real local Gunicorn smoke test; it never sends an authenticated TTS request."""

import http.client
import os
from pathlib import Path
import shutil
import socket
import subprocess
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
PLACEHOLDER_TOKEN = "offline-placeholder-vapi-token-0000000000000000"
PLACEHOLDER_YARN_KEY = "offline-placeholder-yarngpt-key"


@unittest.skipUnless(os.name == "posix" and shutil.which("gunicorn"),
                     "Gunicorn runtime smoke runs on Linux CI only")
class GunicornRuntimeTests(unittest.TestCase):
    def test_gunicorn_stream_wsgi_entrypoint_and_reject_without_provider_call(self):
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]

        environment = {
            "PATH": os.environ.get("PATH", ""),
            "PYTHONPATH": str(ROOT),
            "ROOMAY_VAPI_BEARER_TOKEN": PLACEHOLDER_TOKEN,
            "YARNGPT_API_KEY": PLACEHOLDER_YARN_KEY,
            "ROOMAY_TTS_DEFAULT_VOICE": "remi",
            "YARNGPT_VOICE_REMI": "remi",
            "YARNGPT_TIMEOUT_SECONDS": "20",
        }
        command = [
            shutil.which("gunicorn"), "voice_adapter.tts_wsgi:application",
            "--bind", f"127.0.0.1:{port}", "--worker-class", "gthread",
            "--workers", "1", "--threads", "2", "--worker-connections", "16",
            "--backlog", "16", "--limit-request-line", "4094",
            "--limit-request-fields", "64", "--limit-request-field_size", "4096",
            "--timeout", "75", "--graceful-timeout", "25",
            "--access-logfile", "-", "--access-logformat",
            "%(m)s %(U)s %(s)s %(L)s",
        ]
        server = subprocess.Popen(command, cwd=ROOT, env=environment,
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                  text=True)
        try:
            deadline = time.monotonic() + 10
            get_status = None
            while time.monotonic() < deadline:
                if server.poll() is not None:
                    self.fail("Gunicorn exited before accepting local requests")
                try:
                    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=1)
                    connection.request("GET", "/synthesize")
                    response = connection.getresponse()
                    get_status = response.status
                    response.read()
                    connection.close()
                    break
                except OSError:
                    time.sleep(0.1)
            self.assertEqual(get_status, 405)

            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
            connection.request("POST", "/synthesize", body="{}",
                               headers={"Content-Type": "application/json"})
            response = connection.getresponse()
            self.assertEqual(response.status, 401)
            self.assertEqual(response.read(), b'{"error":"unauthorized"}')
            connection.close()
        finally:
            server.terminate()
            try:
                output, _ = server.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                output, _ = server.communicate(timeout=5)

        self.assertNotIn(PLACEHOLDER_TOKEN, output)
        self.assertNotIn(PLACEHOLDER_YARN_KEY, output)
        self.assertIn("GET /synthesize 405", output)
        self.assertIn("POST /synthesize 401", output)
        self.assertNotIn("Authorization", output)


if __name__ == "__main__":
    unittest.main()
