"""Explicit, injected Workpeg Peg collector; no Workpeg transport is installed.

A future authenticated Peg UI adapter must provide a read/write/readback
implementation for an owner-approved, unconfirmed public-inquiry table.
This module cannot call Workpeg, accept guest claims, or confirm reservations.
"""
from __future__ import annotations

from .queue import IntakeError, canonical_uuid


class SyncError(ValueError):
    pass


def verified_receipt(item: dict, row: dict) -> dict:
    """Check an independently re-read Workpeg row against one staged item."""
    required = {"source_id", "business_id", "hotel_id", "payload_digest",
                "table_uuid", "row_id"}
    if not isinstance(row, dict) or not required.issubset(row):
        raise SyncError("workpeg_readback_missing")
    if (row["source_id"] != item["id"] or row["business_id"] != item["business_id"]
            or row["hotel_id"] != item["hotel_id"]
            or row["payload_digest"] != item["payload_digest"]):
        raise SyncError("workpeg_readback_mismatch")
    try:
        canonical_uuid(row["table_uuid"])
    except IntakeError:
        raise SyncError("workpeg_table_invalid") from None
    if type(row["row_id"]) is not int or row["row_id"] <= 0:
        raise SyncError("workpeg_row_invalid")
    return {key: row[key] for key in required}


async def collect_batch(items: list[dict], *, writer, ack):
    """Import only pending inquiries, then acknowledge verified readback.

    writer.find_by_source(id) -> row or None
    writer.write_unconfirmed_inquiry(item) -> None (NO reservation/stay/ticket)
    writer.find_by_source(id) -> independently re-read row
    ack(item, receipt) -> awaitable external queue acknowledgment

    No status is reported as imported until acknowledgment is confirmed.
    Atomic cross-Workpeg writes and concurrent uniqueness remain unproven.
    """
    results = []
    for item in items:
        ident = item.get("id") if isinstance(item, dict) else None
        try:
            if not isinstance(item, dict) or not isinstance(item.get("data"), dict):
                raise SyncError("invalid_queued_item")
            canonical_uuid(ident)
            current = await writer.find_by_source(ident)
            if current is None:
                await writer.write_unconfirmed_inquiry(item)
            # Even if the write returned success, do NOT ack without a
            # separate authoritative read of the matching persisted row.
            fresh = await writer.find_by_source(ident)
            receipt = verified_receipt(item, fresh)
            accepted = await ack(item, receipt)
            if accepted is not True:
                raise SyncError("acknowledgment_not_confirmed")
            results.append({"id": ident, "status": "collected_pending_manual_review"})
        except Exception:
            # Deliberately avoid reporting untrusted payloads or exceptions
            # (which may include tokens/contact PII) to a public caller.
            results.append({"id": ident, "status": "collection_unverified"})
    return results
