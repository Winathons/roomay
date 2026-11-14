"""Offline guest verification and short-lived session contracts.

No Workpeg authentication method is implemented here. Production adapters must
verify challenge evidence and resolve current hotel rows through trusted,
server-side sources before this policy may issue a session.
"""
from copy import deepcopy
from dataclasses import dataclass, field
import hashlib
import secrets
import threading
import time
from uuid import uuid4

from .access_control import AccessContext, AccessDenied, authorize_hotel_snapshot
from .conversation_intake import ConversationScope


SESSION_TTL_SECONDS = 15 * 60
CHANNELS = frozenset({"typed_chat", "vapi"})


class GuestSessionError(ValueError):
    """Fixed-code guest access refusal; never includes record or provider data."""

    def __init__(self, code):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class ChallengeEvidence:
    """Untrusted challenge receipt submitted to a trusted verifier.

    It deliberately carries no business, hotel, guest, stay, or room identity.
    The verifier must derive the guest subject from the authoritative challenge
    record after validating provider authenticity, intended recipient, expiry,
    attempt limits, replay protection, and possession.
    """

    challenge_id: str
    proof: object
    # Set only by the trusted request adapter from server-observed network
    # identity. Never parse it from guest JSON or an untrusted forwarded header.
    trusted_source_key: str | None = None


@dataclass(frozen=True)
class GuestSubject:
    """Identity resolved by the trusted challenge verifier, never the browser."""

    business_id: str
    hotel_id: str
    guest_id: str
    # Challenges issued for a particular active stay bind these values too.
    # Legacy provider adapters may omit them; production challenge issuance
    # must include both so a re-check-in or room move requires a new challenge.
    stay_id: str | None = None
    room_id: str | None = None


@dataclass(frozen=True)
class ResolvedGuestStay:
    """Trusted, freshly read scope from the server-side hotel adapter."""

    business_id: str
    record_business_id: str
    hotel_id: str
    trusted_snapshot_hotel_id: str
    guest_id: str
    stay_id: str
    room_id: str
    snapshot: dict
    staff_directory: list
    existing_requests: list


@dataclass(frozen=True)
class GuestActionGrant:
    """Private server-side action scope; never serialize into a guest response."""

    context: AccessContext
    scope: ConversationScope
    conversation_id: str


@dataclass
class _SessionRecord:
    token_digest: str
    subject: GuestSubject
    actor_id: str
    stay_id: str
    room_id: str
    created_at: float
    expires_at: float
    conversation_id: str
    action_lock: object = field(default_factory=threading.RLock)
    pending: dict | None = None
    completed: dict | None = None
    interactions: dict = field(default_factory=dict)


def _hash_token(token):
    if not isinstance(token, str) or not token or len(token) > 256:
        return None
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class GuestSessionAuthority:
    """Issue random, server-held, stay-scoped guest sessions after verification.

    ``verify_evidence`` and ``resolve_stay`` are trusted adapter capabilities,
    not request callbacks. The latter is called at issuance and on every use so
    a checked-out/left guest or changed business/stay/room fails closed.
    """

    def __init__(self, *, verify_evidence, resolve_stay,
                 clock=time.monotonic, token_factory=None, max_sessions=10000):
        if not callable(verify_evidence) or not callable(resolve_stay):
            raise TypeError("trusted verification and stay resolution adapters are required")
        if type(max_sessions) is not int or max_sessions < 1:
            raise ValueError("invalid session capacity")
        self._verify_evidence = verify_evidence
        self._resolve_stay = resolve_stay
        self._clock = clock
        self._token_factory = token_factory or (lambda: secrets.token_urlsafe(32))
        self._max_sessions = max_sessions
        self._sessions = {}
        self._used_challenges = set()
        self._lock = threading.RLock()

    @staticmethod
    def _subject(value):
        if not isinstance(value, GuestSubject):
            raise GuestSessionError("verification_required")
        if any(not isinstance(item, str) or not item.strip()
               for item in (value.business_id, value.hotel_id, value.guest_id)):
            raise GuestSessionError("verification_required")
        if ((value.stay_id is None) != (value.room_id is None)
                or any(item is not None and (not isinstance(item, str) or not item.strip())
                       for item in (value.stay_id, value.room_id))):
            raise GuestSessionError("verification_required")
        return value

    def _validate_stay(self, subject, value, *, expected=None, actor_id="verified-guest-session"):
        if not isinstance(value, ResolvedGuestStay):
            raise GuestSessionError("stay_unavailable")
        if (value.business_id != subject.business_id
                or value.record_business_id != subject.business_id
                or value.hotel_id != subject.hotel_id
                or value.trusted_snapshot_hotel_id != subject.hotel_id
                or value.guest_id != subject.guest_id):
            raise GuestSessionError("scope_mismatch")
        if (not isinstance(value.snapshot, dict)
                or not isinstance(value.staff_directory, list)
                or not isinstance(value.existing_requests, list)):
            raise GuestSessionError("stay_unavailable")
        try:
            context = AccessContext(
                actor_id=actor_id, business_id=subject.business_id,
                hotel_id=subject.hotel_id, role="guest", authenticated=True,
                membership_verified=True, business_binding_verified=True,
                guest_id=subject.guest_id,
            )
            authorize_hotel_snapshot(
                context, business_id=value.business_id,
                record_business_id=value.record_business_id,
                resource="guest_profile", action="read", snapshot=value.snapshot,
                trusted_snapshot_hotel_id=value.trusted_snapshot_hotel_id,
                record_guest_id=value.guest_id,
            )
            authorize_hotel_snapshot(
                context, business_id=value.business_id,
                record_business_id=value.record_business_id,
                resource="guest_stay_summary", action="read", snapshot=value.snapshot,
                trusted_snapshot_hotel_id=value.trusted_snapshot_hotel_id,
                record_guest_id=value.guest_id, stay_id=value.stay_id,
                room_id=value.room_id,
            )
        except (AccessDenied, TypeError, ValueError, KeyError, AttributeError):
            raise GuestSessionError("active_registered_stay_required") from None
        if expected is not None and (value.stay_id != expected[0] or value.room_id != expected[1]):
            # Room moves lack a trusted audit contract; require a fresh verification.
            raise GuestSessionError("stay_scope_changed")
        return context

    def _expire(self, now):
        expired = [digest for digest, record in self._sessions.items()
                   if now >= record.expires_at]
        for digest in expired:
            self._sessions.pop(digest, None)

    def complete_challenge(self, evidence):
        """Verify untrusted evidence, derive identity, then issue an opaque token.

        ``verify_evidence`` returns a GuestSubject only after the trusted
        provider adapter has validated the challenge and enforced its
        per-recipient/source attempt and replay limits. Client-supplied identity
        fields are not accepted by this API.
        """
        if (not isinstance(evidence, ChallengeEvidence)
                or not isinstance(evidence.challenge_id, str)
                or not evidence.challenge_id.strip()
                or len(evidence.challenge_id) > 256):
            raise GuestSessionError("verification_required")
        with self._lock:
            now = self._clock()
            self._expire(now)
            if evidence.challenge_id in self._used_challenges:
                raise GuestSessionError("challenge_replayed")
            try:
                subject = self._verify_evidence(evidence)
            except GuestSessionError:
                raise
            except Exception:
                raise GuestSessionError("verification_failed") from None
            if not isinstance(subject, GuestSubject):
                raise GuestSessionError("verification_failed")
            # Burn successful one-time evidence before attempting hotel reads;
            # a provider/store outage must not make a verified receipt reusable.
            self._used_challenges.add(evidence.challenge_id)
            subject = self._subject(subject)
            try:
                resolved = self._resolve_stay(subject)
            except Exception:
                raise GuestSessionError("stay_unavailable") from None
            expected = ((subject.stay_id, subject.room_id)
                        if subject.stay_id is not None else None)
            self._validate_stay(subject, resolved, expected=expected)
            if len(self._sessions) >= self._max_sessions:
                raise GuestSessionError("session_capacity_reached")
            token = self._token_factory()
            digest = _hash_token(token)
            if digest is None or digest in self._sessions:
                raise GuestSessionError("session_unavailable")
            self._sessions[digest] = _SessionRecord(
                token_digest=digest, subject=subject, actor_id=str(uuid4()),
                stay_id=resolved.stay_id,
                room_id=resolved.room_id, created_at=now,
                expires_at=now + SESSION_TTL_SECONDS, conversation_id=str(uuid4()),
            )
            return token

    def revoke(self, token):
        """Revoke one server-held session; never accept a browser identity claim."""
        digest = _hash_token(token)
        if digest is None:
            return False
        with self._lock:
            return self._sessions.pop(digest, None) is not None

    def resolve_for_action(self, token):
        """Return private claims after expiry and fresh stay revalidation."""
        digest = _hash_token(token)
        if digest is None:
            raise GuestSessionError("invalid_session")
        with self._lock:
            now = self._clock()
            self._expire(now)
            record = self._sessions.get(digest)
            if record is None:
                raise GuestSessionError("invalid_or_expired_session")
            try:
                resolved = self._resolve_stay(record.subject)
            except Exception:
                raise GuestSessionError("stay_unavailable") from None
            try:
                context = self._validate_stay(
                    record.subject, resolved, expected=(record.stay_id, record.room_id),
                    actor_id=record.actor_id)
            except GuestSessionError as error:
                if error.code in {
                    "active_registered_stay_required", "scope_mismatch", "stay_scope_changed",
                }:
                    # Checkout, identity/scope mismatch, or a room/stay change
                    # permanently invalidates this bearer credential.
                    self._sessions.pop(digest, None)
                raise
            # Rebuild scope from the newest validated snapshot, never from client data.
            scope = ConversationScope(
                business_id=resolved.business_id,
                record_business_id=resolved.record_business_id,
                trusted_snapshot_hotel_id=resolved.trusted_snapshot_hotel_id,
                snapshot=deepcopy(resolved.snapshot), stay_id=resolved.stay_id,
                room_id=resolved.room_id,
                staff_directory=deepcopy(resolved.staff_directory),
                existing_requests=deepcopy(resolved.existing_requests),
            )
            return record, GuestActionGrant(context, scope, record.conversation_id)
