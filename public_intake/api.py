"""Non-deployed public booking inquiry intake API factory (WOR-72).

Production activation intentionally unavailable: no OIDC client or staff
Workpeg permission has been verified. A local test factory exists only to
exercise the HTTP/SQL boundary with synthetic data and fake staff identity.
"""
from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Callable

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import IntegrityError

from .queue import IntakeError, acknowledge, enqueue, lease


@dataclass(frozen=True)
class TrustedStaff:
    """Server-verified OIDC identity; NEVER populated from public JSON."""

    business_id: str
    hotel_id: str
    subject: str
    is_workpeg_owner: bool


class InquiryBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    idempotency_key: str
    arrival: str
    departure: str
    party_size: int
    email: str
    room_type: str = ""
    note: str = ""
    consent: bool


class LeaseBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    limit: int = Field(default=20, ge=1, le=20)


class ReadbackBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    source_id: str
    business_id: str
    hotel_id: str
    payload_digest: str
    table_uuid: str
    row_id: int = Field(gt=0)


class AckBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    id: str
    lease_token: str
    readback: ReadbackBody


def create_intake_app(*, session_factory, rate_limit_secret: bytes,
                      staff_resolver: Callable[[Request], TrustedStaff] | None = None,
                      clock: Callable[[], int] = lambda: int(time.time()),
                      test_mode: bool = False) -> FastAPI:
    """A guarded local test app, not a production deployment entrypoint.

    A real owner-only staff resolver must be built on the officially
    registered OIDC flow and revalidated membership; only tests may supply
    a synthetic resolver here. Once the Workpeg rights/retention gates pass,
    a separately reviewed production adapter can intentionally replace this.
    """
    if not test_mode:
        raise RuntimeError("public_intake_deployment_not_authorized")
    if not isinstance(rate_limit_secret, bytes) or len(rate_limit_secret) < 32:
        raise RuntimeError("intake_rate_limit_key_missing")

    app = FastAPI(title="ROOMAY temporary public intake (test-only)",
                  docs_url=None, redoc_url=None, openapi_url=None)

    @app.exception_handler(IntakeError)
    async def handle_intake_error(_request: Request, error: IntakeError):
        return JSONResponse({"error": error.code}, status_code=error.status,
                            headers={"Cache-Control": "no-store"})

    def owner(request: Request) -> TrustedStaff:
        if staff_resolver is None:
            raise HTTPException(503, "staff_oidc_not_configured")
        actor = staff_resolver(request)
        if not isinstance(actor, TrustedStaff) or not actor.subject:
            raise HTTPException(401, "staff_authentication_required")
        if actor.is_workpeg_owner is not True:
            raise HTTPException(403, "workpeg_owner_required")
        return actor

    @app.post("/api/v1/public/portals/{portal_id}/booking-inquiries")
    def public_inquiry(portal_id: str, body: InquiryBody, request: Request):
        try:
            with session_factory.begin() as db:
                entry = enqueue(
                    db, portal_id=portal_id, idempotency_key=body.idempotency_key,
                    data=body.model_dump(exclude={"idempotency_key"}),
                    address=(request.client.host if request.client else "unknown"),
                    secret=rate_limit_secret, now=clock())
                result = {
                    "receipt_id": entry.inquiry_id,
                    "status": ("collected_pending_manual_review" if entry.acknowledged_at
                               is not None else "queued_pending_staff_collection"),
                    "booking_confirmed": False,
                    "workpeg_delivery_confirmed": False,
                }
        except IntegrityError:
            # Concurrent duplicate insert/rate-window creation: refuse
            # rather than returning a 500 or claiming anything was saved.
            raise HTTPException(409, "retry_indeterminate") from None
        return JSONResponse(result, status_code=202,
                            headers={"Cache-Control": "no-store"})

    @app.post("/api/v1/staff/inquiries/lease")
    def staff_lease(body: LeaseBody, request: Request):
        actor = owner(request)
        with session_factory.begin() as db:
            batch = lease(db, business_id=actor.business_id, hotel_id=actor.hotel_id,
                          subject=actor.subject, now=clock(), limit=body.limit)
        return JSONResponse({"items": batch},
                            headers={"Cache-Control": "no-store"})

    @app.post("/api/v1/staff/inquiries/ack")
    def staff_ack(body: AckBody, request: Request):
        actor = owner(request)
        with session_factory.begin() as db:
            changed = acknowledge(db, business_id=actor.business_id,
                                  hotel_id=actor.hotel_id, subject=actor.subject,
                                  inquiry_id=body.id, lease_token=body.lease_token,
                                  readback=body.readback.model_dump(), now=clock())
        return JSONResponse({"acknowledged": changed},
                            headers={"Cache-Control": "no-store"})

    return app
