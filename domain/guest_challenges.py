"""Provider-neutral guest challenge orchestration ports.

The included stores are process-local development/test implementations. They
make thread-level operations atomic, but do not provide cross-process limits or
restart recovery. Production adapters must supply a durable store and trusted
provider/source identity; this module does not call Workpeg or deliver codes.
"""
from collections import defaultdict, deque
from dataclasses import dataclass, replace
import hashlib
import secrets
import threading
import time
from typing import Protocol

from .guest_access import ChallengeEvidence, GuestSessionError, GuestSubject


CHALLENGE_TTL_SECONDS = 5 * 60
MAX_CHALLENGE_ATTEMPTS = 5
ISSUE_RATE_LIMIT = 3
ISSUE_RATE_WINDOW_SECONDS = 60 * 60
VERIFY_RATE_LIMIT = 10
VERIFY_RATE_WINDOW_SECONDS = 15 * 60


class GuestChallengeError(GuestSessionError):
    """Fixed-code challenge refusal without provider or identity details."""


@dataclass(frozen=True)
class GuestChallengeRecord:
    """Server-held identity binding; never serialize this record to a guest."""

    challenge_id: str
    subject: GuestSubject
    recipient_key_digest: str
    created_at: float
    expires_at: float
    state: str = "pending"
    provider_reference: str | None = None
    attempts: int = 0


@dataclass(frozen=True)
class IssuedGuestChallenge:
    """Safe issuance receipt; the delivery secret remains with the provider."""

    challenge_id: str
    expires_at: float


class GuestChallengeStore(Protocol):
    """Storage port whose begin/consume operations must be atomic.

    A durable implementation must preserve uniqueness and compare-and-set
    semantics across every worker. It stores verification state only, never
    hotel operational rows or guest service requests.
    """

    def create(self, record: GuestChallengeRecord) -> bool: ...
    def get(self, challenge_id: str) -> GuestChallengeRecord | None: ...
    def activate(self, challenge_id: str, provider_reference: str, now: float) -> bool: ...
    def begin_attempt(self, challenge_id: str, now: float,
                      max_attempts: int) -> GuestChallengeRecord: ...
    def consume(self, challenge_id: str, now: float) -> GuestChallengeRecord: ...
    def revoke(self, challenge_id: str) -> bool: ...


class GuestChallengeProvider(Protocol):
    """External delivery and possession-verification provider boundary."""

    def issue(self, *, challenge_id: str, recipient_ref: str,
              expires_at: float) -> str: ...
    def verify(self, *, provider_reference: str, proof: str) -> bool: ...


class GuestContactResolver(Protocol):
    """Resolve only the verified guest's existing, on-file contact handle."""

    def resolve_on_file_contact(self, subject: GuestSubject) -> str: ...


class GuestRateLimiter(Protocol):
    """Rate-limit port; production implementations must be shared and durable."""

    def allow(self, keys: tuple[str, ...], *, now: float,
              limit: int, window_seconds: int) -> bool: ...


class InMemoryGuestChallengeStore:
    """Atomic only within this Python process; never a production store."""

    def __init__(self, *, max_records=10000):
        if type(max_records) is not int or max_records < 1:
            raise ValueError("invalid challenge capacity")
        self.max_records = max_records
        self._records = {}
        self._lock = threading.RLock()

    def create(self, record):
        with self._lock:
            expired = [key for key, value in self._records.items()
                       if value.expires_at <= record.created_at]
            for key in expired:
                self._records.pop(key, None)
            if record.challenge_id in self._records:
                return False
            if len(self._records) >= self.max_records:
                return False
            self._records[record.challenge_id] = record
            return True

    def get(self, challenge_id):
        with self._lock:
            return self._records.get(challenge_id)

    def activate(self, challenge_id, provider_reference, now):
        with self._lock:
            record = self._records.get(challenge_id)
            if (record is None or record.state != "pending" or now >= record.expires_at
                    or not provider_reference):
                return False
            self._records[challenge_id] = replace(
                record, state="active", provider_reference=provider_reference)
            return True

    def begin_attempt(self, challenge_id, now, max_attempts):
        with self._lock:
            record = self._records.get(challenge_id)
            if record is None:
                raise GuestChallengeError("challenge_invalid")
            if now >= record.expires_at:
                self._records[challenge_id] = replace(record, state="expired")
                raise GuestChallengeError("challenge_expired")
            if record.state in {"consumed", "revoked"}:
                raise GuestChallengeError("challenge_replayed")
            if record.state != "active":
                raise GuestChallengeError("challenge_unavailable")
            if record.attempts >= max_attempts:
                raise GuestChallengeError("challenge_attempt_limit")
            record = replace(record, attempts=record.attempts + 1)
            self._records[challenge_id] = record
            return record

    def consume(self, challenge_id, now):
        with self._lock:
            record = self._records.get(challenge_id)
            if record is None:
                raise GuestChallengeError("challenge_invalid")
            if now >= record.expires_at:
                self._records[challenge_id] = replace(record, state="expired")
                raise GuestChallengeError("challenge_expired")
            if record.state != "active":
                raise GuestChallengeError("challenge_replayed")
            consumed = replace(record, state="consumed")
            self._records[challenge_id] = consumed
            return consumed

    def revoke(self, challenge_id):
        with self._lock:
            record = self._records.get(challenge_id)
            if record is None or record.state in {"consumed", "revoked", "expired"}:
                return False
            self._records[challenge_id] = replace(record, state="revoked")
            return True


class InMemoryGuestRateLimiter:
    """Thread-safe sliding-window limiter for one process and offline tests."""

    def __init__(self, *, max_keys=50000):
        if type(max_keys) is not int or max_keys < 1:
            raise ValueError("invalid rate-limit capacity")
        self.max_keys = max_keys
        self._events = defaultdict(deque)
        self._lock = threading.RLock()

    @staticmethod
    def _digest(key):
        return hashlib.sha256(key.encode("utf-8")).hexdigest()

    def allow(self, keys, *, now, limit, window_seconds):
        if (not keys or type(limit) is not int or limit < 1
                or type(window_seconds) is not int or window_seconds < 1):
            raise ValueError("invalid rate-limit request")
        digests = tuple(dict.fromkeys(self._digest(key) for key in keys))
        with self._lock:
            for digest, events in list(self._events.items()):
                while events and events[0][0] <= now - events[0][1]:
                    events.popleft()
                if not events:
                    self._events.pop(digest, None)
            if sum(digest not in self._events for digest in digests) + len(self._events) > self.max_keys:
                return False
            queues = [self._events[digest] for digest in digests]
            if any(sum(1 for at, _window in events if at > now - window_seconds) >= limit
                   for events in queues):
                return False
            for events in queues:
                events.append((now, window_seconds))
            return True


def _nonempty(value, maximum):
    return isinstance(value, str) and bool(value.strip()) and len(value) <= maximum


def _subject(value):
    if (not isinstance(value, GuestSubject)
            or not all(_nonempty(item, 200) for item in (
                value.business_id, value.hotel_id, value.guest_id))
            or not _nonempty(value.stay_id, 200)
            or not _nonempty(value.room_id, 200)):
        raise GuestChallengeError("trusted_guest_scope_required")
    return value


def _digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class GuestChallengeService:
    """Issue and consume one-time challenges before ``GuestSessionAuthority``.

    The contact resolver and ``source_key`` are trusted server capabilities.
    The contact resolver must return only an existing on-file contact handle;
    the source key must come from trusted ingress, never a browser field or
    untrusted proxy header.
    The challenge record, not provider/browser claims, supplies GuestSubject.
    """

    def __init__(self, *, provider, contact_resolver: GuestContactResolver,
                 store: GuestChallengeStore,
                 rate_limiter: GuestRateLimiter, clock=time.time,
                 token_factory=None, ttl_seconds=CHALLENGE_TTL_SECONDS,
                 max_attempts=MAX_CHALLENGE_ATTEMPTS,
                 issue_limit=ISSUE_RATE_LIMIT,
                 issue_window_seconds=ISSUE_RATE_WINDOW_SECONDS,
                 verify_limit=VERIFY_RATE_LIMIT,
                 verify_window_seconds=VERIFY_RATE_WINDOW_SECONDS):
        if not callable(getattr(provider, "issue", None)) or not callable(
                getattr(provider, "verify", None)):
            raise TypeError("trusted challenge provider is required")
        if not callable(getattr(contact_resolver, "resolve_on_file_contact", None)):
            raise TypeError("trusted guest contact resolver is required")
        if not all(callable(getattr(store, name, None)) for name in (
                "create", "get", "activate", "begin_attempt", "consume", "revoke")):
            raise TypeError("atomic challenge store is required")
        if not callable(getattr(rate_limiter, "allow", None)):
            raise TypeError("trusted rate limiter is required")
        for value in (ttl_seconds, max_attempts, issue_limit, issue_window_seconds,
                      verify_limit, verify_window_seconds):
            if type(value) is not int or value < 1:
                raise ValueError("invalid challenge policy")
        if not callable(clock):
            raise TypeError("trusted clock is required")
        self.provider = provider
        self.contact_resolver = contact_resolver
        self.store = store
        self.rate_limiter = rate_limiter
        self.clock = clock
        self.token_factory = token_factory or (lambda: secrets.token_urlsafe(24))
        self.ttl_seconds = ttl_seconds
        self.max_attempts = max_attempts
        self.issue_limit = issue_limit
        self.issue_window_seconds = issue_window_seconds
        self.verify_limit = verify_limit
        self.verify_window_seconds = verify_window_seconds

    def _allow(self, keys, *, now, limit, window_seconds, failure_code):
        try:
            return self.rate_limiter.allow(
                keys, now=now, limit=limit, window_seconds=window_seconds)
        except Exception:
            raise GuestChallengeError(failure_code) from None

    def issue(self, subject, *, trusted_source_key):
        """Issue through the provider to a trusted on-file contact handle."""
        subject = _subject(subject)
        if not _nonempty(trusted_source_key, 512):
            raise GuestChallengeError("trusted_issue_context_required")
        now = self.clock()
        source_digest = _digest(trusted_source_key)
        allowed = self._allow(
            ("issue-source:" + source_digest,), now=now,
            limit=self.issue_limit, window_seconds=self.issue_window_seconds,
            failure_code="challenge_unavailable")
        if not allowed:
            raise GuestChallengeError("rate_limited")
        try:
            recipient_ref = self.contact_resolver.resolve_on_file_contact(subject)
        except Exception:
            raise GuestChallengeError("challenge_unavailable") from None
        if not _nonempty(recipient_ref, 512):
            raise GuestChallengeError("challenge_unavailable")
        now = self.clock()
        recipient_digest = _digest(recipient_ref)
        allowed = self._allow(
            ("issue-recipient:" + recipient_digest,),
            now=now, limit=self.issue_limit,
            window_seconds=self.issue_window_seconds,
            failure_code="challenge_unavailable")
        if not allowed:
            raise GuestChallengeError("rate_limited")
        challenge_id = self.token_factory()
        if not _nonempty(challenge_id, 256):
            raise GuestChallengeError("challenge_unavailable")
        record = GuestChallengeRecord(
            challenge_id=challenge_id, subject=subject,
            recipient_key_digest=recipient_digest,
            created_at=now, expires_at=now + self.ttl_seconds)
        try:
            stored = self.store.create(record)
        except Exception:
            raise GuestChallengeError("challenge_unavailable") from None
        if not stored:
            raise GuestChallengeError("challenge_unavailable")
        try:
            provider_reference = self.provider.issue(
                challenge_id=challenge_id, recipient_ref=recipient_ref,
                expires_at=record.expires_at)
            if not _nonempty(provider_reference, 512) or not self.store.activate(
                    challenge_id, provider_reference, self.clock()):
                raise RuntimeError("provider issuance was not activated")
        except Exception:
            try:
                self.store.revoke(challenge_id)
            except Exception:
                pass
            raise GuestChallengeError("challenge_unavailable") from None
        return IssuedGuestChallenge(challenge_id, record.expires_at)

    def verify_evidence(self, evidence):
        """Callable verifier for ``GuestSessionAuthority``.

        The request adapter adds only a server-derived rate key to evidence;
        all identity is loaded from the stored challenge record. Provider errors
        are sanitized and failed proofs consume one bounded challenge attempt.
        """
        if (not isinstance(evidence, ChallengeEvidence)
                or not _nonempty(evidence.challenge_id, 256)
                or not _nonempty(evidence.trusted_source_key, 512)
                or not isinstance(evidence.proof, str)
                or not _nonempty(evidence.proof, 1024)):
            raise GuestChallengeError("verification_required")
        source_digest = _digest(evidence.trusted_source_key)
        allowed = self._allow(
            ("verify-source:" + source_digest,), now=self.clock(),
            limit=self.verify_limit, window_seconds=self.verify_window_seconds,
            failure_code="verification_unavailable")
        if not allowed:
            raise GuestChallengeError("rate_limited")
        try:
            candidate = self.store.get(evidence.challenge_id)
        except Exception:
            raise GuestChallengeError("verification_unavailable") from None
        if candidate is None:
            raise GuestChallengeError("challenge_invalid")
        if self.clock() >= candidate.expires_at:
            try:
                self.store.begin_attempt(
                    evidence.challenge_id, self.clock(), self.max_attempts)
            except GuestChallengeError:
                raise
            except Exception:
                raise GuestChallengeError("verification_unavailable") from None
            raise GuestChallengeError("challenge_expired")
        allowed = self._allow(
            ("verify-recipient:" + candidate.recipient_key_digest,),
            now=self.clock(), limit=self.verify_limit,
            window_seconds=self.verify_window_seconds,
            failure_code="verification_unavailable")
        if not allowed:
            raise GuestChallengeError("rate_limited")
        try:
            record = self.store.begin_attempt(
                evidence.challenge_id, self.clock(), self.max_attempts)
        except GuestChallengeError:
            raise
        except Exception:
            raise GuestChallengeError("verification_unavailable") from None
        try:
            valid = self.provider.verify(
                provider_reference=record.provider_reference, proof=evidence.proof)
        except Exception:
            raise GuestChallengeError("verification_unavailable") from None
        if valid is not True:
            raise GuestChallengeError("invalid_challenge")
        try:
            consumed = self.store.consume(evidence.challenge_id, self.clock())
        except GuestChallengeError:
            raise
        except Exception:
            raise GuestChallengeError("verification_unavailable") from None
        return _subject(consumed.subject)
