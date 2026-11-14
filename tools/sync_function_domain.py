"""Sync the pure domain modules required by a Workpeg Function image.

Function build context is ``function/``; repository-level ``domain/`` is not
visible to Docker COPY. Keep only this explicit dependency set vendored, and
use ``--check`` in tests/CI to detect drift from the canonical source.
"""
import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
MODULES = (
    "__init__.py",
    "hotel.py",
    "schema.py",
    "service_request_schema.py",
    "service_requests.py",
    "workpeg_adapter.py",
    "workpeg_function_tables.py",
)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="fail if Function domain copies differ from source")
    args = parser.parse_args(argv)
    source = ROOT / "domain"
    target = ROOT / "function" / "domain"
    target.mkdir(parents=True, exist_ok=True)
    mismatches = []
    for name in MODULES:
        original = source / name
        vendored = target / name
        # Git may check the canonical sources out with CRLF on Windows while
        # the image build and CI use LF. Compare normalized UTF-8 text and
        # always write LF so the mirrored package is reproducible cross-OS.
        original_text = original.read_text(encoding="utf-8")
        normalized = original_text.replace("\r\n", "\n").replace("\r", "\n")
        if args.check:
            if not vendored.is_file():
                mismatches.append(name)
                continue
            vendored_text = vendored.read_text(encoding="utf-8")
            vendored_normalized = vendored_text.replace("\r\n", "\n").replace("\r", "\n")
            if vendored_normalized != normalized:
                mismatches.append(name)
        else:
            vendored.write_bytes(normalized.encode("utf-8"))
    if mismatches:
        print("Function domain mirror is stale: " + ", ".join(mismatches), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
