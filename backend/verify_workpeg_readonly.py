"""Owner-run, read-only verification of the seven canonical hotel tables.

Run with ``python -m backend.verify_workpeg_readonly`` after injecting the
approved server-only key and exact development business/Peg UUIDs. Output is
intentionally limited to sanitized status, canonical aliases, and row counts.
"""
import json
import os
import sys
from uuid import UUID

from backend.config import normalize_peg_uuid
from backend.workpeg_reader import WorkpegHotelReader, WorkpegReadError
from domain.workpeg_adapter import HOTEL_ALIASES


def main():
    workpeg_pk = os.environ.get("WORKPEG_PK", "")
    peg_id = os.environ.get("ROOMAY_WORKPEG_PEG_ID", "")
    business_id = os.environ.get("ROOMAY_WORKPEG_BUSINESS_ID", "")
    if not workpeg_pk or not peg_id or not business_id:
        print(json.dumps({"status": "BLOCKED", "reason": "configuration_incomplete"}))
        return 2

    try:
        normalized_peg_id = normalize_peg_uuid(peg_id)
        if str(UUID(business_id)) != business_id:
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        print(json.dumps({"status": "BLOCKED", "reason": "configuration_invalid"}))
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
    except WorkpegReadError:
        print(json.dumps({"status": "FAIL", "reason": "read_or_contract_check_failed"}))
        return 1
    except Exception:
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
    sys.exit(main())
