"""Roomay guest service API and department inbox.

Workpeg is read-only for hotel data. New service requests/audit are written
atomically to PostgreSQL as the sole writer for this workflow.
"""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import secrets
from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from workpeg.auth import WorkpegAuth, SignInStart, WorkpegAuthError
from domain.service_requests import create_request, transition_request, request_view, route_category
from domain.staff_actions import _audit_history_is_consistent
from .models import (
    GuestInvitation, GuestSession, HotelBinding, OIDCState, OperationalAudit,
    OperationalRequest, PendingRequest, StaffBinding, StaffSession,
)

STAFF_TTL = timedelta(minutes=15)
GUEST_TTL = timedelta(minutes=30)
INVITE_TTL = timedelta(minutes=30)
PROPOSAL_TTL = timedelta(minutes=10)
ACTIVE_MEMBER_ROLES = {"owner", "admin", "member"}
ALLOWED_GUEST_CATEGORIES = {
    "extra_towels", "linen", "room_cleaning", "toiletries", "plumbing",
    "electrical", "air_conditioning", "room_equipment", "room_service",
    "dining", "minibar", "transport", "wake_up_call", "billing_question",
    "general_help",
}


def _digest(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _now():
    return datetime.now(timezone.utc)


def _expired(value, now):
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value <= now


def _public_request(data):
    return {key: data[key] for key in (
        "request_id", "category", "category_detail", "department", "description",
        "urgency", "status", "created_at", "updated_at",
    )}


def _staff_public_request(data, room_number=None):
    allowed = (
        "request_id", "category", "category_detail", "department", "description",
        "urgency", "status", "assigned_staff_id", "created_at", "updated_at",
        "acknowledge_by", "due_at", "version",
    )
    result = {key: data[key] for key in allowed if key in data}
    if room_number is not None:
        result["room_number"] = room_number
    return result


def _same_request_content(left, right):
    fields = ("hotel_id", "stay_id", "room_id", "guest_id", "origin", "category",
              "category_detail", "department", "description", "urgency", "sensitive")
    return all(left.get(field) == right.get(field) for field in fields)


class InvitationBody(BaseModel):
    stay_id: str
    guest_id: str


class PrepareBody(BaseModel):
    category: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=1000)
    idempotency_key: str = Field(min_length=36, max_length=36)
    urgency: str = "normal"


class ConfirmBody(BaseModel):
    confirmation_handle: str = Field(min_length=32, max_length=128)


class StaffTransitionBody(BaseModel):
    action: str
    operation_key: str = Field(min_length=8, max_length=200)
    assignee_id: str | None = None
    reason: str | None = None


def create_app(*, session_factory, hotel_reader, settings, clock=_now,
               workpeg_auth=None):
    app = FastAPI(title="Roomay", docs_url=None, redoc_url=None)
    auth = workpeg_auth or WorkpegAuth(
        client_id=settings.oidc_client_id or "unconfigured",
        client_secret=settings.oidc_client_secret,
        redirect_uri=settings.oidc_redirect_uri or "https://invalid.invalid/callback",
    )

    def require_same_origin(request):
        origin = request.headers.get("origin")
        expected = getattr(settings, "public_base_url", "").rstrip("/")
        if origin != expected:
            raise HTTPException(403, "request_origin_denied")

    def staff_record(request):
        token = request.cookies.get("roomay_staff")
        if not token or len(token) > 256:
            raise HTTPException(401, "staff_authentication_required")
        with session_factory() as db:
            session = db.get(StaffSession, _digest(token))
            now = clock()
            if not session or session.revoked_at or _expired(session.expires_at, now):
                raise HTTPException(401, "staff_session_expired")
            if session.business_id != settings.business_id:
                raise HTTPException(403, "staff_business_denied")
            binding = db.scalar(select(StaffBinding).where(
                StaffBinding.business_id == session.business_id,
                StaffBinding.workpeg_subject == session.workpeg_subject,
                StaffBinding.active.is_(True)))
            hotel = db.get(HotelBinding, session.business_id)
            if not binding or not hotel or not hotel.active or binding.hotel_id != hotel.hotel_id:
                raise HTTPException(403, "staff_access_revoked")
            if session.workpeg_role not in ACTIVE_MEMBER_ROLES:
                raise HTTPException(403, "business_membership_denied")
            return {
                "session_hash": session.token_hash,
                "business_id": session.business_id, "hotel_id": hotel.hotel_id,
                "workpeg_subject": session.workpeg_subject,
                "workpeg_role": session.workpeg_role,
                "actor_id": binding.actor_id, "department": binding.department,
                "roles": list(binding.roles),
            }

    def guest_record(request):
        token = request.cookies.get("roomay_guest")
        if not token or len(token) > 256:
            raise HTTPException(401, "guest_verification_required")
        with session_factory() as db:
            session = db.get(GuestSession, _digest(token))
            if not session or session.revoked_at or _expired(session.expires_at, clock()):
                raise HTTPException(401, "guest_session_expired")
            scope = {key: getattr(session, key) for key in (
                "business_id", "hotel_id", "guest_id", "stay_id", "room_id")}
        try:
            snapshot = hotel_reader.read_snapshot(scope["business_id"])
        except Exception:
            raise HTTPException(503, "hotel_records_unavailable") from None
        stay = next((item for item in snapshot["stays"] if item["entity_id"] == scope["stay_id"]), None)
        occupants = [item for item in snapshot["stay_guests"] if item["stay_id"] == scope["stay_id"]
                     and item["guest_id"] == scope["guest_id"] and item.get("left_at") is None]
        if (not stay or stay.get("status") != "checked_in" or stay.get("room_id") != scope["room_id"]
                or len(occupants) != 1):
            raise HTTPException(403, "active_stay_required")
        return scope, snapshot

    def staff_directory(db, hotel_id):
        rows = db.scalars(select(StaffBinding).where(
            StaffBinding.hotel_id == hotel_id, StaffBinding.active.is_(True))).all()
        return [{"actor_id": row.actor_id, "hotel_id": row.hotel_id,
                 "department": row.department, "roles": list(row.roles), "active": row.active}
                for row in rows]

    @app.get("/healthz")
    def health():
        return {"status": "ok"}

    @app.get("/auth/workpeg/start")
    def oidc_start(response: Response):
        try:
            start = auth.begin()
        except Exception:
            raise HTTPException(503, "identity_provider_unavailable") from None
        binding = secrets.token_urlsafe(32)
        with session_factory.begin() as db:
            db.add(OIDCState(state_hash=_digest(start.state),
                             nonce=start.nonce, verifier=start.code_verifier,
                             browser_hash=_digest(binding)))
        redirect = RedirectResponse(start.url, status_code=303)
        redirect.headers["Cache-Control"] = "no-store"
        redirect.headers["Referrer-Policy"] = "no-referrer"
        redirect.set_cookie("roomay_oidc", binding, max_age=600, httponly=True,
                            secure=settings.cookie_secure, samesite="lax", path="/auth")
        return redirect

    @app.get("/auth/workpeg/callback")
    def oidc_callback(request: Request, code: str, state: str):
        browser = request.cookies.get("roomay_oidc")
        if not browser or len(state) > 256 or len(code) > 4096:
            raise HTTPException(400, "identity_callback_invalid")
        with session_factory.begin() as db:
            record = db.scalar(select(OIDCState).where(
                OIDCState.state_hash == _digest(state)).with_for_update())
            if (not record or not secrets.compare_digest(record.browser_hash, _digest(browser))
                    or _expired(record.created_at + timedelta(minutes=10), clock())):
                raise HTTPException(400, "identity_callback_invalid")
            start = SignInStart(url="", state=state,
                                code_verifier=record.verifier, nonce=record.nonce)
            db.delete(record)
        try:
            identity = auth.complete(code=code, state=state, start=start)
        except WorkpegAuthError:
            raise HTTPException(401, "workpeg_sign_in_failed") from None
        except Exception:
            raise HTTPException(503, "identity_provider_unavailable") from None
        if identity is None:
            raise HTTPException(401, "workpeg_sign_in_failed")
        try:
            business_id_valid = str(UUID(identity.business_id)) == identity.business_id
        except (ValueError, TypeError, AttributeError):
            business_id_valid = False
        if (not isinstance(identity.subject, str) or not identity.subject.strip()
                or len(identity.subject) > 255 or not isinstance(identity.role, str)
                or identity.role not in ACTIVE_MEMBER_ROLES
                or not business_id_valid or identity.business_id != settings.business_id):
            raise HTTPException(403, "business_membership_denied")
        raw = secrets.token_urlsafe(32)
        now = clock()
        with session_factory.begin() as db:
            hotel = db.get(HotelBinding, identity.business_id)
            binding = db.scalar(select(StaffBinding).where(
                StaffBinding.business_id == identity.business_id,
                StaffBinding.workpeg_subject == identity.subject,
                StaffBinding.active.is_(True)))
            if (not binding and settings.bootstrap_owner_enabled
                    and identity.is_owner is True):
                any_binding = db.scalar(select(StaffBinding.id).where(
                    StaffBinding.business_id == identity.business_id).limit(1))
                if any_binding:
                    raise HTTPException(403, "staff_not_authorized")
                if hotel and hotel.hotel_id != settings.hotel_id:
                    raise HTTPException(403, "hotel_binding_mismatch")
                if not hotel:
                    hotel = HotelBinding(business_id=identity.business_id,
                                         hotel_id=settings.hotel_id, active=True)
                    db.add(hotel)
                binding = StaffBinding(
                    id=str(uuid4()), business_id=identity.business_id,
                    hotel_id=settings.hotel_id, workpeg_subject=identity.subject,
                    actor_id="owner-" + _digest(identity.subject),
                    department="reception", roles=["hotel_manager", "request_admin"],
                    active=True)
                db.add(binding)
                db.flush()
            if not hotel or not hotel.active or not binding or binding.hotel_id != hotel.hotel_id:
                raise HTTPException(403, "staff_not_authorized")
            db.add(StaffSession(token_hash=_digest(raw), workpeg_subject=identity.subject,
                                business_id=identity.business_id, workpeg_role=identity.role,
                                expires_at=now + STAFF_TTL))
        response = RedirectResponse("/staff", status_code=303)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.delete_cookie("roomay_oidc", path="/auth")
        response.set_cookie("roomay_staff", raw, max_age=int(STAFF_TTL.total_seconds()),
                            httponly=True, secure=settings.cookie_secure,
                            samesite="strict", path="/")
        return response

    @app.post("/auth/logout")
    def logout(request: Request, response: Response):
        require_same_origin(request)
        token = request.cookies.get("roomay_staff")
        if token:
            with session_factory.begin() as db:
                record = db.get(StaffSession, _digest(token))
                if record:
                    record.revoked_at = clock()
        response.delete_cookie("roomay_staff", path="/")
        response.delete_cookie("roomay_guest", path="/")
        return {"ok": True}

    @app.post("/staff/stays/{stay_id}/guest-invitations")
    def issue_invitation(stay_id: str, body: InvitationBody, request: Request):
        require_same_origin(request)
        staff = staff_record(request)
        if staff["department"] != "reception" and not ({"hotel_manager", "request_admin"} & set(staff["roles"])):
            raise HTTPException(403, "invitation_issuance_denied")
        if body.stay_id != stay_id:
            raise HTTPException(400, "invalid_stay_reference")
        try:
            snapshot = hotel_reader.read_snapshot(staff["business_id"])
        except Exception:
            raise HTTPException(503, "hotel_records_unavailable") from None
        stay = next((row for row in snapshot["stays"] if row["entity_id"] == stay_id), None)
        occupants = [row for row in snapshot["stay_guests"] if row["stay_id"] == stay_id
                     and row["guest_id"] == body.guest_id and row.get("left_at") is None]
        if (not stay or stay.get("status") != "checked_in" or len(occupants) != 1
                or stay.get("room_id") is None):
            raise HTTPException(403, "active_registered_stay_required")
        token = secrets.token_urlsafe(32)
        invitation_id = str(uuid4())
        now = clock()
        with session_factory.begin() as db:
            issued_recently = db.scalar(select(func.count()).select_from(GuestInvitation).where(
                GuestInvitation.issued_by == staff["actor_id"],
                GuestInvitation.created_at >= now - timedelta(hours=1))) or 0
            if issued_recently >= 20:
                raise HTTPException(429, "invitation_rate_limited")
            db.add(GuestInvitation(invitation_id=invitation_id, token_hash=_digest(token), business_id=staff["business_id"],
                                   hotel_id=staff["hotel_id"], guest_id=body.guest_id,
                                   stay_id=stay_id, room_id=stay["room_id"],
                                   issued_by=staff["actor_id"], expires_at=now + INVITE_TTL))
        # Returned once to the authorized issuing staff member for out-of-band delivery.
        return Response(
            content=json.dumps({
                "invitation_id": invitation_id, "invitation": token,
                "expires_at": (now + INVITE_TTL).isoformat(),
                "delivery": "not_sent; deliver only to the verified on-file guest contact",
            }), media_type="application/json", headers={"Cache-Control": "no-store"})

    @app.get("/staff/active-stays")
    def active_stays_for_invitation(request: Request):
        staff = staff_record(request)
        if staff["department"] != "reception" and not (
                {"hotel_manager", "request_admin"} & set(staff["roles"])):
            raise HTTPException(403, "guest_invitation_access_denied")
        try:
            snapshot = hotel_reader.read_snapshot(staff["business_id"])
        except Exception:
            raise HTTPException(503, "hotel_records_unavailable") from None
        rooms = {row["entity_id"]: row["number"] for row in snapshot["rooms"]}
        guests = {row["entity_id"]: row["display_name"] for row in snapshot["guests"]}
        result = []
        for stay in snapshot["stays"]:
            if stay.get("status") != "checked_in" or stay.get("room_id") not in rooms:
                continue
            occupants = [row for row in snapshot["stay_guests"]
                         if row["stay_id"] == stay["entity_id"] and row.get("left_at") is None]
            for occupant in occupants:
                guest_name = guests.get(occupant.get("guest_id"))
                if not guest_name:
                    raise HTTPException(503, "hotel_records_invalid")
                result.append({"stay_id": stay["entity_id"],
                               "guest_id": occupant["guest_id"],
                               "room_number": rooms[stay["room_id"]],
                               "guest_name": guest_name})
        return result

    @app.post("/staff/guest-invitations/{invitation_id}/revoke")
    def revoke_invitation(invitation_id: str, request: Request):
        require_same_origin(request)
        staff = staff_record(request)
        if staff["department"] != "reception" and not (
                {"hotel_manager", "request_admin"} & set(staff["roles"])):
            raise HTTPException(403, "invitation_revocation_denied")
        with session_factory.begin() as db:
            invitation = db.get(GuestInvitation, invitation_id)
            if (not invitation or invitation.business_id != staff["business_id"]
                    or invitation.hotel_id != staff["hotel_id"]):
                raise HTTPException(404, "invitation_not_found")
            invitation.revoked_at = clock()
        return {"revoked": True}

    @app.post("/guest/logout")
    def guest_logout(request: Request, response: Response):
        require_same_origin(request)
        token = request.cookies.get("roomay_guest")
        if token:
            with session_factory.begin() as db:
                session = db.get(GuestSession, _digest(token))
                if session:
                    session.revoked_at = clock()
        response.delete_cookie("roomay_guest", path="/")
        return {"ok": True}

    @app.post("/guest/invitations/redeem")
    def redeem_invitation(request: Request, response: Response, body: dict):
        require_same_origin(request)
        token = body.get("invitation") if isinstance(body, dict) else None
        if not isinstance(token, str) or len(token) < 32 or len(token) > 128:
            raise HTTPException(400, "invitation_invalid")
        now = clock()
        with session_factory.begin() as db:
            invitation = db.scalar(select(GuestInvitation).where(
                GuestInvitation.token_hash == _digest(token)).with_for_update())
            if (not invitation or invitation.revoked_at or invitation.redeemed_at
                    or _expired(invitation.expires_at, now)):
                raise HTTPException(401, "invitation_invalid_or_expired")
            scope = {key: getattr(invitation, key) for key in (
                "business_id", "hotel_id", "guest_id", "stay_id", "room_id")}
            try:
                snapshot = hotel_reader.read_snapshot(scope["business_id"])
            except Exception:
                raise HTTPException(503, "hotel_records_unavailable") from None
            stay = next((row for row in snapshot["stays"] if row["entity_id"] == scope["stay_id"]), None)
            active = [row for row in snapshot["stay_guests"] if row["stay_id"] == scope["stay_id"]
                      and row["guest_id"] == scope["guest_id"] and row.get("left_at") is None]
            if not stay or stay.get("status") != "checked_in" or stay.get("room_id") != scope["room_id"] or len(active) != 1:
                invitation.revoked_at = now
                raise HTTPException(403, "active_stay_required")
            raw = secrets.token_urlsafe(32)
            db.add(GuestSession(token_hash=_digest(raw), **scope, expires_at=now + GUEST_TTL))
            invitation.redeemed_at = now
        response.set_cookie("roomay_guest", raw, max_age=int(GUEST_TTL.total_seconds()),
                            httponly=True, secure=settings.cookie_secure,
                            samesite="strict", path="/")
        return {"verified": True, "expires_at": (now + GUEST_TTL).isoformat()}

    @app.post("/guest/requests/prepare")
    def prepare_guest_request(body: PrepareBody, request: Request):
        require_same_origin(request)
        scope, snapshot = guest_record(request)
        try:
            if str(UUID(body.idempotency_key)) != body.idempotency_key.lower():
                raise ValueError
        except (ValueError, TypeError, AttributeError):
            raise HTTPException(400, "request_idempotency_key_invalid") from None
        if body.category not in ALLOWED_GUEST_CATEGORIES:
            raise HTTPException(400, "request_category_invalid")
        category, department, triage = route_category(body.category)
        if triage:
            raise HTTPException(400, "request_category_requires_reception")
        operation_key = _digest(scope["guest_id"] + ":" + body.idempotency_key)
        cookie = request.cookies.get("roomay_guest")
        with session_factory() as db:
            existing_proposal = db.scalar(select(PendingRequest).where(
                PendingRequest.session_hash == _digest(cookie),
                PendingRequest.operation_key == operation_key))
        if existing_proposal:
            if _expired(existing_proposal.expires_at, clock()):
                raise HTTPException(409, "request_confirmation_expired")
            original = existing_proposal.payload["target_request"]
            if (original.get("category") != body.category
                    or original.get("description") != body.description.strip()
                    or original.get("urgency") != body.urgency):
                raise HTTPException(409, "request_idempotency_conflict")
            data = original
            return {"confirmation_handle": existing_proposal.id, "summary": {
                "description": data["description"], "category": data["category_detail"],
                "department": data["department"], "urgency": data["urgency"],
            }, "requires_explicit_confirmation": True, "request_persisted": False}
        handle = str(uuid4())
        draft = {
            "hotel_id": scope["hotel_id"], "stay_id": scope["stay_id"],
            "room_id": scope["room_id"], "guest_id": scope["guest_id"],
            "origin": "guest", "category": category,
            "description": body.description.strip(), "urgency": body.urgency,
            "idempotency_key": operation_key, "sensitive": False,
        }
        try:
            planned = create_request(snapshot, draft,
                                     {"actor_id": scope["guest_id"], "hotel_id": scope["hotel_id"],
                                      "kind": "guest", "guest_id": scope["guest_id"]},
                                     [], [], at=clock().isoformat())
        except Exception:
            raise HTTPException(400, "request_not_valid_for_active_stay") from None
        if planned["kind"] != "created":
            raise HTTPException(409, "request_conflict")
        try:
            with session_factory.begin() as db:
                guest = db.get(GuestSession, _digest(cookie))
                if not guest or guest.revoked_at or _expired(guest.expires_at, clock()):
                    raise HTTPException(401, "guest_session_expired")
                recent_prepares = db.scalar(select(func.count()).select_from(PendingRequest).where(
                    PendingRequest.session_hash == guest.token_hash,
                    PendingRequest.created_at >= clock() - timedelta(hours=1))) or 0
                if recent_prepares >= 20:
                    raise HTTPException(429, "request_rate_limited")
                db.add(PendingRequest(id=handle, session_hash=guest.token_hash,
                                      operation_key=operation_key,
                                      payload=planned["plan"], expires_at=clock() + PROPOSAL_TTL))
        except IntegrityError:
            # A simultaneous retry with the same client key shares the first proposal.
            with session_factory() as db:
                existing_proposal = db.scalar(select(PendingRequest).where(
                    PendingRequest.session_hash == _digest(cookie),
                    PendingRequest.operation_key == operation_key))
            if (not existing_proposal or _expired(existing_proposal.expires_at, clock())
                    or existing_proposal.payload.get("target_request", {}).get("description")
                    != body.description.strip()
                    or existing_proposal.payload.get("target_request", {}).get("category")
                    != body.category
                    or existing_proposal.payload.get("target_request", {}).get("urgency")
                    != body.urgency):
                raise HTTPException(409, "request_idempotency_conflict") from None
            handle = existing_proposal.id
            planned = {"request": existing_proposal.payload["target_request"]}
        data = planned["request"]
        return {"confirmation_handle": handle, "summary": {
            "description": data["description"], "category": data["category_detail"],
            "department": department, "urgency": data["urgency"],
        }, "requires_explicit_confirmation": True, "request_persisted": False}

    @app.post("/guest/requests/confirm")
    def confirm_guest_request(body: ConfirmBody, request: Request):
        require_same_origin(request)
        scope, snapshot = guest_record(request)
        cookie = request.cookies.get("roomay_guest")
        try:
            with session_factory.begin() as db:
                guest = db.get(GuestSession, _digest(cookie))
                if not guest or guest.revoked_at or _expired(guest.expires_at, clock()):
                    raise HTTPException(401, "guest_session_expired")
                pending = db.scalar(select(PendingRequest).where(
                    PendingRequest.id == body.confirmation_handle).with_for_update())
                if not pending or pending.session_hash != guest.token_hash or _expired(pending.expires_at, clock()):
                    raise HTTPException(409, "confirmation_expired")
                plan = pending.payload
                target = plan["target_request"]
                if (target["hotel_id"] != scope["hotel_id"] or target["stay_id"] != scope["stay_id"]
                        or target["guest_id"] != scope["guest_id"]):
                    raise HTTPException(403, "request_scope_denied")
                if pending.consumed_at:
                    duplicate = db.scalar(select(OperationalRequest).where(
                        OperationalRequest.hotel_id == scope["hotel_id"],
                        OperationalRequest.idempotency_key == target["idempotency_key"]))
                    if duplicate:
                        audits = db.scalars(select(OperationalAudit).where(
                            OperationalAudit.request_id == duplicate.request_id).order_by(OperationalAudit.sequence)).all()
                        events = [item.event_data | {"commit_state": item.commit_state} for item in audits]
                        if (_same_request_content(duplicate.request_data, target)
                                and _audit_history_is_consistent(duplicate.request_data, events)):
                            reference, status = duplicate.request_id, duplicate.request_data["status"]
                            return {"persisted": True, "reference": reference, "status": status}
                    raise HTTPException(409, "confirmation_already_used")
                active_stay = next((row for row in snapshot["stays"]
                                    if row["entity_id"] == scope["stay_id"]), None)
                if not active_stay or active_stay.get("status") != "checked_in" or active_stay.get("room_id") != scope["room_id"]:
                    raise HTTPException(403, "active_stay_required")
                existing = db.scalar(select(OperationalRequest).where(
                    OperationalRequest.hotel_id == scope["hotel_id"],
                    OperationalRequest.idempotency_key == target["idempotency_key"]))
                if existing:
                    audits = db.scalars(select(OperationalAudit).where(
                        OperationalAudit.request_id == existing.request_id).order_by(OperationalAudit.sequence)).all()
                    events = [item.event_data | {"commit_state": item.commit_state} for item in audits]
                    if (_same_request_content(existing.request_data, target)
                            and _audit_history_is_consistent(existing.request_data, events)):
                        pending.consumed_at = clock()
                        return {"persisted": True, "reference": existing.request_id,
                                "status": existing.request_data["status"]}
                    raise HTTPException(503, "request_reconciliation_required")
                request_data = target
                event = dict(plan["event"])
                event["commit_state"] = "committed"
                db.add(OperationalRequest(request_id=request_data["request_id"],
                                          business_id=scope["business_id"], hotel_id=scope["hotel_id"],
                                          idempotency_key=request_data["idempotency_key"],
                                          request_data=request_data))
                db.add(OperationalAudit(event_id=event["event_id"], business_id=scope["business_id"],
                                        hotel_id=scope["hotel_id"], request_id=request_data["request_id"],
                                        operation_id=event["operation_id"], sequence=event["sequence"],
                                        event_data={key: value for key, value in event.items() if key != "commit_state"},
                                        commit_state="committed", occurred_at=clock()))
                db.flush()
                pending.consumed_at = clock()
                db.flush()
                verify = db.get(OperationalRequest, request_data["request_id"])
                if verify:
                    db.refresh(verify)
                audit_rows = db.scalars(select(OperationalAudit).where(
                    OperationalAudit.request_id == request_data["request_id"])).all()
                verified_events = [item.event_data | {"commit_state": item.commit_state} for item in audit_rows]
                if not verify or not _audit_history_is_consistent(verify.request_data, verified_events):
                    raise HTTPException(503, "request_persistence_unverified")
                reference, status = request_data["request_id"], request_data["status"]
        except IntegrityError:
            # Concurrent duplicate confirmation: uniqueness decides one winner.
            with session_factory() as db:
                existing = db.scalar(select(OperationalRequest).where(
                    OperationalRequest.hotel_id == scope["hotel_id"],
                    OperationalRequest.idempotency_key == plan["target_request"]["idempotency_key"]))
                if not existing:
                    raise HTTPException(503, "request_write_uncertain") from None
                audits = db.scalars(select(OperationalAudit).where(
                    OperationalAudit.request_id == existing.request_id).order_by(OperationalAudit.sequence)).all()
                events = [item.event_data | {"commit_state": item.commit_state} for item in audits]
                if (not _same_request_content(existing.request_data, plan["target_request"])
                        or not _audit_history_is_consistent(existing.request_data, events)):
                    if not _same_request_content(existing.request_data, plan["target_request"]):
                        raise HTTPException(409, "request_idempotency_conflict") from None
                    raise HTTPException(503, "request_reconciliation_required") from None
                reference, status = existing.request_id, existing.request_data["status"]
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(503, "request_write_uncertain") from None
        return {"persisted": True, "reference": reference, "status": status}

    @app.get("/guest/requests")
    def guest_requests(request: Request):
        scope, snapshot = guest_record(request)
        with session_factory() as db:
            rows = db.scalars(select(OperationalRequest).where(
                OperationalRequest.business_id == scope["business_id"],
                OperationalRequest.hotel_id == scope["hotel_id"])).all()
            requests = [row.request_data for row in rows if row.request_data["guest_id"] == scope["guest_id"]
                        and row.request_data["stay_id"] == scope["stay_id"]]
        return [_public_request(row) for row in requests]

    @app.get("/staff/requests")
    def staff_inbox(request: Request):
        staff = staff_record(request)
        try:
            snapshot = hotel_reader.read_snapshot(staff["business_id"])
        except Exception:
            raise HTTPException(503, "hotel_records_unavailable") from None
        room_numbers = {room["entity_id"]: room["number"] for room in snapshot["rooms"]}
        with session_factory() as db:
            query = select(OperationalRequest).where(
                OperationalRequest.business_id == staff["business_id"],
                OperationalRequest.hotel_id == staff["hotel_id"])
            rows = db.scalars(query).all()
            directory = staff_directory(db, staff["hotel_id"])
            actor = {"actor_id": staff["actor_id"], "hotel_id": staff["hotel_id"], "kind": "staff"}
            projected = []
            for row in rows:
                data = row.request_data
                privileged = bool({"hotel_manager", "request_admin"} & set(staff["roles"]))
                if staff["department"] != "reception" and not privileged and data["department"] != staff["department"]:
                    continue
                if data.get("sensitive") and not ({"incident_manager", "hotel_manager"} & set(staff["roles"])):
                    continue
                events = db.scalars(select(OperationalAudit).where(
                    OperationalAudit.request_id == row.request_id).order_by(OperationalAudit.sequence)).all()
                event_data = [event.event_data | {"commit_state": event.commit_state} for event in events]
                if not _audit_history_is_consistent(data, event_data):
                    continue
                try:
                    request_view(data, actor, directory)
                except Exception:
                    continue
                room_number = room_numbers.get(data.get("room_id"))
                if room_number is None:
                    continue
                projected.append(_staff_public_request(data, room_number))
            return projected

    @app.get("/staff/directory")
    def staff_directory_for_assignment(request: Request, department: str):
        staff = staff_record(request)
        if staff["department"] != "reception" and not ({"hotel_manager", "request_admin"} & set(staff["roles"])):
            raise HTTPException(403, "staff_directory_access_denied")
        with session_factory() as db:
            rows = db.scalars(select(StaffBinding).where(
                StaffBinding.business_id == staff["business_id"],
                StaffBinding.hotel_id == staff["hotel_id"],
                StaffBinding.department == department,
                StaffBinding.active.is_(True))).all()
            return [{"actor_id": item.actor_id, "department": item.department} for item in rows]

    @app.post("/staff/requests/{request_id}/transitions")
    def staff_transition(request_id: str, body: StaffTransitionBody, request: Request):
        require_same_origin(request)
        staff = staff_record(request)
        if body.action not in {"assign", "acknowledge", "in_progress", "resolve"}:
            raise HTTPException(400, "unsupported_transition")
        if body.action == "assign" and not body.assignee_id:
            raise HTTPException(400, "assignee_required")
        if body.action != "assign" and body.assignee_id is not None:
            raise HTTPException(400, "invalid_transition_shape")
        with session_factory.begin() as db:
            record = db.scalar(select(OperationalRequest).where(
                OperationalRequest.business_id == staff["business_id"],
                OperationalRequest.hotel_id == staff["hotel_id"],
                OperationalRequest.request_id == request_id).with_for_update())
            if not record:
                raise HTTPException(404, "request_not_found")
            audits = db.scalars(select(OperationalAudit).where(
                OperationalAudit.request_id == request_id).order_by(OperationalAudit.sequence).with_for_update()).all()
            events = [item.event_data | {"commit_state": item.commit_state} for item in audits]
            if not _audit_history_is_consistent(record.request_data, events):
                raise HTTPException(503, "request_reconciliation_required")
            directory = staff_directory(db, staff["hotel_id"])
            targets = {"assign": "assigned", "acknowledge": "acknowledged",
                       "in_progress": "in_progress", "resolve": "resolved"}
            try:
                result = transition_request(
                    record.request_data, targets[body.action],
                    {"actor_id": staff["actor_id"], "hotel_id": staff["hotel_id"], "kind": "staff"},
                    directory, at=clock().isoformat(), operation_key=body.operation_key,
                    assignee_id=(body.assignee_id if body.action == "assign" else None),
                    reason=body.reason)
            except Exception:
                raise HTTPException(403, "transition_not_authorized_or_invalid") from None
            if result["kind"] == "duplicate":
                return {"persisted": True,
                        "request": _staff_public_request(result["request"])}
            plan = result["plan"]
            event = dict(plan["event"])
            event["commit_state"] = "committed"
            record.request_data = plan["target_request"]
            db.add(OperationalAudit(event_id=event["event_id"], business_id=staff["business_id"],
                                    hotel_id=staff["hotel_id"], request_id=request_id,
                                    operation_id=event["operation_id"], sequence=event["sequence"],
                                    event_data={key: value for key, value in event.items() if key != "commit_state"},
                                    commit_state="committed", occurred_at=clock()))
            db.flush()
            check = db.scalars(select(OperationalAudit).where(
                OperationalAudit.request_id == request_id).order_by(OperationalAudit.sequence)).all()
            check_events = [item.event_data | {"commit_state": item.commit_state} for item in check]
            db.refresh(record)
            if not _audit_history_is_consistent(record.request_data, check_events):
                raise HTTPException(503, "request_persistence_unverified")
            return {"persisted": True,
                    "request": _staff_public_request(record.request_data)}

    @app.get("/guest", response_class=HTMLResponse)
    def guest_ui():
        return HTMLResponse(GUEST_HTML)

    @app.get("/staff", response_class=HTMLResponse)
    def staff_ui():
        return HTMLResponse(STAFF_HTML)

    @app.get("/staff/guest-access", response_class=HTMLResponse)
    def guest_access_ui():
        return HTMLResponse(GUEST_ACCESS_HTML, headers={"Cache-Control": "no-store"})

    app.state.session_factory = session_factory
    app.state.hotel_reader = hotel_reader
    return app


GUEST_HTML = """<!doctype html><html lang='en'><meta charset='utf-8'><meta name='viewport' content='width=device-width'><title>Roomay Guest Requests</title><main><h1>Roomay</h1><p>Private guest service requests</p><label>Invitation code <input id='invite' autocomplete='one-time-code'></label><button id='redeem'>Verify invitation</button><section id='form' hidden><label>Request type <select id='category'><option value='extra_towels'>Extra towels</option><option value='room_cleaning'>Room cleaning</option><option value='plumbing'>Plumbing</option><option value='air_conditioning'>Air conditioning</option><option value='room_service'>Room service</option><option value='general_help'>General help</option></select></label><label>Describe what you need <textarea id='description' maxlength='1000'></textarea></label><button id='prepare'>Review request</button><div id='review' hidden><p id='summary'></p><button id='confirm'>Confirm and send request</button><button id='cancel'>Cancel</button></div></section><p id='message' role='status'></p><section><h2>My requests</h2><ul id='requests'></ul></section></main><script>
const msg=document.getElementById('message'), form=document.getElementById('form'), review=document.getElementById('review');
async function call(url,body){const r=await fetch(url,{method:body?'POST':'GET',credentials:'same-origin',headers:body?{'Content-Type':'application/json'}:{},body:body?JSON.stringify(body):undefined});const d=await r.json();if(!r.ok)throw new Error(d.detail||'Request unavailable');return d}
const safeErrors={guest_verification_required:'Enter the stay invitation from Reception.',invitation_invalid_or_expired:'This invitation is invalid or expired. Contact Reception.',active_stay_required:'Your active stay could not be verified. Please contact Reception.',hotel_records_unavailable:'Hotel records are temporarily unavailable. Try again shortly.',request_category_invalid:'Choose a request type from the list.',request_category_requires_reception:'Please contact Reception for this request.',request_not_valid_for_active_stay:'This request could not be matched to your active stay.',request_confirmation_expired:'The review expired. Please review your request again.',request_idempotency_conflict:'This request changed. Review it again before confirming.',request_rate_limited:'Too many request attempts. Please contact Reception.',request_write_uncertain:'We could not confirm whether the request was saved. Refresh My requests before trying again.'};
function showError(error){msg.textContent=safeErrors[error.message]||'Roomay is temporarily unavailable. Please try again or contact Reception.'}
document.getElementById('redeem').onclick=async()=>{try{await call('/guest/invitations/redeem',{invitation:document.getElementById('invite').value});form.hidden=false;msg.textContent='Stay invitation verified.';load()}catch(e){showError(e)}};
let idempotencyKey=sessionStorage.getItem('roomay-request-key')||crypto.randomUUID();
function rotateKey(){idempotencyKey=crypto.randomUUID();sessionStorage.setItem('roomay-request-key',idempotencyKey)}
sessionStorage.setItem('roomay-request-key',idempotencyKey);
document.getElementById('description').addEventListener('input',()=>{rotateKey();review.hidden=true});
document.getElementById('category').addEventListener('change',()=>{rotateKey();review.hidden=true});
document.getElementById('prepare').onclick=async()=>{const button=document.getElementById('prepare');button.disabled=true;msg.textContent='Preparing your request for review…';try{const d=await call('/guest/requests/prepare',{category:document.getElementById('category').value,description:document.getElementById('description').value,urgency:'normal',idempotency_key:idempotencyKey});review.dataset.handle=d.confirmation_handle;document.getElementById('summary').textContent=d.summary.description+' — '+d.summary.department;review.hidden=false;msg.textContent='Review the exact request. It has not been sent or saved as an operational request.'}catch(e){showError(e)}finally{button.disabled=false}};
document.getElementById('confirm').onclick=async()=>{const button=document.getElementById('confirm');button.disabled=true;msg.textContent='Verifying the saved request…';try{const d=await call('/guest/requests/confirm',{confirmation_handle:review.dataset.handle});if(!d.persisted||!d.reference)throw new Error('request_write_uncertain');review.hidden=true;rotateKey();msg.textContent='Request saved in Roomay. Hotel staff have not been notified.';load()}catch(e){showError(e)}finally{button.disabled=false}};
document.getElementById('cancel').onclick=()=>{review.hidden=true;rotateKey();msg.textContent='Cancelled. No operational request was created.'};
async function load(){try{const rows=await call('/guest/requests');const ul=document.getElementById('requests');ul.replaceChildren();for(const row of rows){const li=document.createElement('li');li.textContent=row.category+' — '+row.status;ul.append(li)}}catch(e){showError(e)}}
</script></html>"""

STAFF_HTML = """<!doctype html><html lang='en'><meta charset='utf-8'><meta name='viewport' content='width=device-width'><title>Roomay Staff Inbox</title><main><h1>Roomay Staff Inbox</h1><a href='/auth/workpeg/start'>Sign in with Workpeg</a> <a href='/staff/guest-access'>Issue guest access</a> <button id='logout'>Sign out</button> <button id='refresh'>Refresh requests</button><ul id='items'></ul><p id='message' role='status'></p></main><script>
const list=document.getElementById('items'),msg=document.getElementById('message');async function load(){try{const r=await fetch('/staff/requests',{credentials:'same-origin'});if(!r.ok)throw new Error('Staff access unavailable. Sign in through Workpeg.');const rows=await r.json();list.replaceChildren();for(const row of rows){const li=document.createElement('li'),title=document.createElement('strong'),desc=document.createElement('p'),room=document.createElement('p'),actions=document.createElement('div');title.textContent=row.department+' — '+row.status;room.textContent='Room '+row.room_number;desc.textContent=row.description;li.append(title,room,desc);if(row.status==='received'){const select=document.createElement('select'),button=document.createElement('button');select.setAttribute('aria-label','Assign to department staff');button.textContent='Assign';button.onclick=()=>act(row,'assign',select.value);actions.append(select,button);fetch('/staff/directory?department='+encodeURIComponent(row.department),{credentials:'same-origin'}).then(r=>r.ok?r.json():[]).then(people=>{select.replaceChildren();for(const person of people){const option=document.createElement('option');option.value=person.actor_id;option.textContent=person.actor_id;select.append(option)}})}else if(row.status==='assigned'){const b=document.createElement('button');b.textContent='Acknowledge';b.onclick=()=>act(row,'acknowledge');actions.append(b)}else if(row.status==='acknowledged'){const b=document.createElement('button');b.textContent='Start work';b.onclick=()=>act(row,'in_progress');actions.append(b)}else if(row.status==='in_progress'){const b=document.createElement('button');b.textContent='Resolve';b.onclick=()=>act(row,'resolve');actions.append(b)}li.append(actions);list.append(li)}}catch(e){msg.textContent=e.message}}async function act(row,action,assignee_id){try{if(action==='assign'&&!assignee_id)throw new Error('Choose an assignee first');const r=await fetch('/staff/requests/'+row.request_id+'/transitions',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({action,operation_key:crypto.randomUUID(),assignee_id})});if(!r.ok)throw new Error('Action was not persisted; refresh and verify the saved status.');msg.textContent='Status and audit saved.';load()}catch(e){msg.textContent=e.message}}document.getElementById('refresh').onclick=load;document.getElementById('logout').onclick=async()=>{await fetch('/auth/logout',{method:'POST',credentials:'same-origin',headers:{'Origin':location.origin}});location.reload()};load();
</script></html>"""

GUEST_ACCESS_HTML = """<!doctype html><html lang='en'><meta charset='utf-8'><meta name='viewport' content='width=device-width'><title>Roomay Guest Access</title><main><h1>Guest access invitation</h1><p>Reception only. Verify the guest using the hotel's existing on-file contact process before sharing a code.</p><button id='load'>Load active registered stays</button><label for='stay'>Guest stay</label><select id='stay' disabled></select><button id='issue' disabled>Prepare one-time invitation</button><section id='result' hidden><h2>One-time code</h2><output id='code'></output><button id='copy'>Copy code</button><p>Not sent by Roomay. Deliver only to the guest through the independently verified contact. The code expires in 30 minutes and can be redeemed once.</p></section><p id='message' role='status'></p><a href='/staff'>Back to staff inbox</a></main><script>
const list=document.getElementById('stay'),msg=document.getElementById('message'),result=document.getElementById('result');let active=[];
async function call(url,options={}){const r=await fetch(url,{...options,credentials:'same-origin'});const d=await r.json();if(!r.ok)throw new Error(d.detail||'unavailable');return d}
document.getElementById('load').onclick=async()=>{msg.textContent='Loading active registered stays…';try{active=await call('/staff/active-stays');list.replaceChildren();for(const item of active){const option=document.createElement('option');option.value=item.stay_id+'|'+item.guest_id;option.textContent='Room '+item.room_number+' — '+item.guest_name;list.append(option)}list.disabled=active.length===0;document.getElementById('issue').disabled=active.length===0;msg.textContent=active.length?'Select the verified guest stay.':'No active registered stays are available.'}catch(e){msg.textContent='Guest access is unavailable for this account or hotel.'}};
document.getElementById('issue').onclick=async()=>{if(!list.value)return;if(!window.confirm('Have you independently verified this guest using the on-file hotel contact?'))return;const [stay_id,guest_id]=list.value.split('|');document.getElementById('issue').disabled=true;msg.textContent='Preparing a one-time invitation…';try{const d=await call('/staff/stays/'+encodeURIComponent(stay_id)+'/guest-invitations',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({stay_id,guest_id})});document.getElementById('code').textContent=d.invitation;result.hidden=false;msg.textContent='Invitation prepared. It was not delivered.'}catch(e){msg.textContent='Invitation was not created. Verify access and try again.'}finally{document.getElementById('issue').disabled=false}};
document.getElementById('copy').onclick=async()=>{try{await navigator.clipboard.writeText(document.getElementById('code').textContent);msg.textContent='Code copied. Share it only through the verified guest contact.'}catch(e){msg.textContent='Copy was unavailable. Select the code manually and share it securely.'}};
</script></html>"""
