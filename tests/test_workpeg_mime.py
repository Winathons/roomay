"""Offline response-header regression for the installed Workpeg UI handler."""
import io
import tempfile
import unittest
from pathlib import Path

from workpeg.ui.build import build_ui
from workpeg.ui import serve

from tools.workpeg_serve_compat import configure_javascript_mime


ROOT = Path(__file__).resolve().parents[1]


class CompiledSite:
    def __init__(self, directory: Path):
        self.directory = directory
        self.index = directory / "index.html"

    def resolve(self, path: str):
        candidate = self.directory / path.lstrip("/")
        return candidate if candidate.is_file() else None

    def page(self, content: bytes) -> bytes:
        return content


class WorkpegJavaScriptMimeTests(unittest.TestCase):
    def test_sdk_handler_serves_compiled_javascript_with_executable_mime(self):
        scratch = ROOT / "build"
        scratch.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as output:
            directory = Path(output)
            build_ui(str(ROOT / "ui" / "main.py"), str(directory), peg_namespace="roomay")
            configure_javascript_mime()
            handler = serve._site_handler(
                serve._SilentHandler, CompiledSite(directory),
                (("X-Content-Type-Options", "nosniff"),),
            )
            for filename in ("app.js", "workpeg-runtime.js"):
                with self.subTest(filename=filename):
                    expected = (directory / filename).read_bytes()
                    response = handler.__new__(handler)
                    wire = io.BytesIO()
                    response.path = f"/{filename}"
                    response.request_version = "HTTP/1.1"
                    response.wfile = wire
                    response._headers_buffer = []
                    response.send_response = lambda status: setattr(response, "status", status)
                    response._answer(body=True)
                    head, body = wire.getvalue().split(b"\r\n\r\n", 1)
                    headers = dict(line.decode("latin1").split(": ", 1)
                                   for line in head.split(b"\r\n") if b": " in line)
                    self.assertEqual(response.status, 200)
                    self.assertEqual(headers["Content-Type"], "text/javascript")
                    self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
                    self.assertEqual(body, expected)
                    self.assertIn(b"Workpeg", expected)
                    self.assertNotIn(b"404 Not Found", expected)


if __name__ == "__main__":
    unittest.main()
