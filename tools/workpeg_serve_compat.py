"""Start the Workpeg UI server with a Windows JavaScript MIME compatibility fix.

Workpeg SDK 0.152.0 delegates static file MIME detection to Python's
``SimpleHTTPRequestHandler``. On Windows Python 3.13, ``.js`` can resolve to
``text/plain``; Chrome correctly refuses it when ``nosniff`` is enabled.
Registering the standard JavaScript media type in this process fixes the
handler without changing browser security or the installed SDK.

Usage (owner-operated only):
    python tools/workpeg_serve_compat.py ui/ --fake-cloud
"""

import mimetypes
import sys
from collections.abc import Sequence


def configure_javascript_mime() -> None:
    """Ensure the SDK's static handler serves .js as executable JavaScript."""
    mimetypes.add_type("text/javascript", ".js", strict=True)


def main(argv: Sequence[str] | None = None) -> None:
    configure_javascript_mime()
    from workpeg.cli import main as workpeg_main

    workpeg_main(["ui", "serve", *(sys.argv[1:] if argv is None else argv)])


if __name__ == "__main__":
    main()
