"""Owner-run, read-only verification of the seven canonical hotel tables.

Run with ``python -m backend.verify_workpeg_readonly`` after injecting the
approved server-only key and exact development business/Peg UUIDs. Output is
intentionally limited to sanitized status, canonical aliases, and row counts.
"""
import argparse
import json
import os
import sys
from uuid import UUID

from backend.config import normalize_peg_uuid
from backend.workpeg_reader import WorkpegHotelReader, WorkpegReadError
from domain.workpeg_adapter import HOTEL_ALIASES


def main(argv=None):
    parser = argparse.ArgumentParser(description="Read-only Roomay Workpeg hotel data check")
    parser.add_argument(
        "--diagnostic", action="store_true",
        help="include allowlisted failure stage/status details; never includes response data",
    )
    args = parser.parse_args([] if argv is None else argv)
    workpeg_pk = os.environ.get("WORKPEG_PK", "")
    peg_id = os.environ.get("ROOMAY_WORKPEG_PEG_ID", "")
    business_id = os.environ.get("ROOMAY_WORKPEG_BUSINESS_ID", "")
    if not workpeg_pk or not peg_id or not business_id:
        if args.diagnostic:
            detail = {
                "status": "BLOCKED", "stage": "authentication", "alias": None,
                "http_status": None, "status_category": "configuration_invalid",
                "error_code": "workpeg_read_configuration_missing",
            }
        else:
            detail = {"status": "BLOCKED", "reason": "configuration_incomplete"}
        print(json.dumps(detail, sort_keys=True))
        return 2

    try:
        normalized_peg_id = normalize_peg_uuid(peg_id)
        if str(UUID(business_id)) != business_id:
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        if args.diagnostic:
            detail = {
                "status": "BLOCKED", "stage": "authentication", "alias": None,
                "http_status": None, "status_category": "configuration_invalid",
                "error_code": "workpeg_read_configuration_invalid",
            }
        else:
            detail = {"status": "BLOCKED", "reason": "configuration_invalid"}
        print(json.dumps(detail, sort_keys=True))
        return 2

    try:
        reader = WorkpegHotelReader(
            api_base="https://api.workpeg.com",
            workpeg_pk=workpeg_pk,
            peg_id=normalized_peg_id,
        )
        snapshot = reader.read_snapshot(business_id)
        tables = [
            {"alias": alias, "row_count": len(snapshot[key])}
            for key, alias in HOTEL_ALIASES.items()
        ]
    except WorkpegReadError as error:
        if args.diagnostic:
            print(json.dumps({"status": "FAIL", **error.diagnostic()}, sort_keys=True))
        else:
            print(json.dumps({"status": "FAIL", "reason": "read_or_contract_check_failed"}))
        return 1
    except Exception:
        if args.diagnostic:
            print(json.dumps({
                "status": "FAIL", "stage": "unknown", "alias": None,
                "http_status": None, "status_category": "unexpected_error",
                "error_code": "workpeg_internal_error",
            }, sort_keys=True))
        else:
            print(json.dumps({"status": "FAIL", "reason": "read_or_contract_check_failed"}))
        return 1

    print(json.dumps({
        "status": "PASS",
        "read_only": True,
        "peg_ownership": "verified",
        "permission_700": "verified",
        "schemas_and_snapshot": "verified",
        "tables": tables,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
