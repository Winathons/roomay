"""Offline tests for provider-neutral guest challenge orchestration."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import unittest

from domain.fixtures import synthetic_hotel, uid
from domain.guest_access import ChallengeEvidence, GuestSubject, GuestSessionError
from domain.guest_access import GuestSessionAuthority, ResolvedGuestStay
from domain.guest_challenges import (
    GuestChallengeError, GuestChallengeService, InMemoryGuestChallengeStore,
    InMemoryGuestRateLimiter,
)


class FakeClock:
    def __init__(self):
        self.now = 1_800_000_000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class FakeChallengeProvider:
    def __init__(self):
        self.issued = []
        self.valid_proof = "correct-code"
        self.verify_barrier = None
        self.fail_issue = False
        self.fail_verify = False

    def issue(self, *, challenge_id, recipient_ref, expires_at):
        if self.fail_issue:
            raise RuntimeError("provider delivery detail must not escape")
        self.issued.append((challenge_id, recipient_ref, expires_at))
        return "provider-ref-" + challenge_id

    def verify(self, *, provider_reference, proof):
        if self.verify_barrier is not None:
            self.verify_barrier.wait(timeout=2)
        if self.fail_verify:
            raise RuntimeError("provider response detail must not escape")
        return provider_reference.startswith("provider-ref-") and proof == self.valid_proof


class FakeGuestContactResolver:
    def __init__(self):
        self.subjects = []

    def resolve_on_file_contact(self, subject):
        self.subjects.append(subject)
        return "on-file-contact-ref"


class GuestChallengeServiceTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.provider = FakeChallengeProvider()
        self.contact_resolver = FakeGuestContactResolver()
        self.store = InMemoryGuestChallengeStore()
        self.limiter = InMemoryGuestRateLimiter()
        self.sequence = 0

        def token_factory():
            self.sequence += 1
            return f"challenge-id-with-enough-entropy-{self.sequence}"

        self.subject = GuestSubject(
            uid("conversation-business"), uid("conversation-hotel"),
            uid("Guest C"), uid("stay"), uid("205"),
        )
        self.service = GuestChallengeService(
            provider=self.provider, contact_resolver=self.contact_resolver,
            store=self.store, rate_limiter=self.limiter,
            clock=self.clock, token_factory=token_factory,
        )

    def issue(self, *, source="trusted-client-1"):
        return self.service.issue(
            self.subject, trusted_source_key=source)

    def evidence(self, challenge, proof="correct-code", source="trusted-client-1"):
        return ChallengeEvidence(
            challenge_id=challenge.challenge_id, proof=proof,
            trusted_source_key=source,
        )

    def test_issue_keeps_recipient_proof_and_subject_behind_server_ports(self):
        challenge = self.issue()
        self.assertEqual(challenge.expires_at, self.clock.now + 300)
        self.assertEqual(len(self.provider.issued), 1)
        self.assertEqual(self.provider.issued[0][1], "on-file-contact-ref")
        self.assertEqual(self.contact_resolver.subjects, [self.subject])
        record = self.store.get(challenge.challenge_id)
        self.assertEqual(record.subject, self.subject)
        self.assertEqual(record.state, "active")
        self.assertEqual(record.attempts, 0)
        self.assertNotEqual(record.recipient_key_digest, "on-file-contact-ref")
        self.assertNotIn("correct-code", repr(record))
        self.assertNotIn("on-file-contact-ref", repr(challenge))

    def test_verified_identity_comes_from_challenge_record(self):
        challenge = self.issue()
        resolved = self.service.verify_evidence(self.evidence(challenge))
        self.assertEqual(resolved, self.subject)
        self.assertEqual(self.store.get(challenge.challenge_id).state, "consumed")
        with self.assertRaises(GuestChallengeError) as error:
            self.service.verify_evidence(self.evidence(challenge))
        self.assertEqual(error.exception.code, "challenge_replayed")

    def test_authority_issues_session_only_for_challenge_bound_active_stay(self):
        challenge = self.issue()
        business, hotel = uid("conversation-business"), uid("conversation-hotel")
        guest, stay, room = uid("Guest C"), uid("stay"), uid("205")
        snapshot = synthetic_hotel()

        def resolve(_subject):
            return ResolvedGuestStay(
                business_id=business, record_business_id=business,
                hotel_id=hotel, trusted_snapshot_hotel_id=hotel,
                guest_id=guest, stay_id=stay, room_id=room,
                snapshot=snapshot, staff_directory=[], existing_requests=[],
            )

        authority = GuestSessionAuthority(
            verify_evidence=self.service.verify_evidence, resolve_stay=resolve,
            clock=self.clock, token_factory=lambda: "opaque-session-token-with-test-entropy",
        )
        token = authority.complete_challenge(self.evidence(challenge))
        record, grant = authority.resolve_for_action(token)
        self.assertEqual(record.stay_id, stay)
        self.assertEqual(grant.scope.room_id, room)

    def test_checkout_or_room_change_between_issue_and_verify_prevents_session(self):
        challenge = self.issue()
        business, hotel = uid("conversation-business"), uid("conversation-hotel")
        guest, stay = uid("Guest C"), uid("stay")
        snapshot = synthetic_hotel()
        room = uid("204")
        snapshot["stays"][0]["room_id"] = room
        next(row for row in snapshot["reservations"]
             if row["entity_id"] == uid("in-house"))["room_id"] = room

        def resolve(_subject):
            return ResolvedGuestStay(
                business_id=business, record_business_id=business,
                hotel_id=hotel, trusted_snapshot_hotel_id=hotel,
                guest_id=guest, stay_id=stay, room_id=room,
                snapshot=snapshot, staff_directory=[], existing_requests=[],
            )

        authority = GuestSessionAuthority(
            verify_evidence=self.service.verify_evidence, resolve_stay=resolve,
            clock=self.clock, token_factory=lambda: "opaque-session-token-with-test-entropy",
        )
        with self.assertRaises(GuestSessionError) as error:
            authority.complete_challenge(self.evidence(challenge))
        self.assertEqual(error.exception.code, "stay_scope_changed")
        self.assertEqual(self.store.get(challenge.challenge_id).state, "consumed")

    def test_checkout_between_issue_and_redemption_prevents_session(self):
        challenge = self.issue()
        business, hotel = uid("conversation-business"), uid("conversation-hotel")
        guest, stay, room = uid("Guest C"), uid("stay"), uid("205")
        snapshot = synthetic_hotel()
        snapshot["stays"][0].update(
            status="checked_out", checked_out_at="2026-11-08T12:00:00+01:00")
        snapshot["stay_guests"][0]["left_at"] = "2026-11-08T12:00:00+01:00"

        def resolve(_subject):
            return ResolvedGuestStay(
                business_id=business, record_business_id=business,
                hotel_id=hotel, trusted_snapshot_hotel_id=hotel,
                guest_id=guest, stay_id=stay, room_id=room,
                snapshot=snapshot, staff_directory=[], existing_requests=[],
            )

        authority = GuestSessionAuthority(
            verify_evidence=self.service.verify_evidence, resolve_stay=resolve,
            clock=self.clock, token_factory=lambda: "opaque-session-token-with-test-entropy",
        )
        with self.assertRaises(GuestSessionError) as error:
            authority.complete_challenge(self.evidence(challenge))
        self.assertEqual(error.exception.code, "active_registered_stay_required")
        self.assertEqual(self.store.get(challenge.challenge_id).state, "consumed")

    def test_replacement_stay_between_issue_and_redemption_prevents_session(self):
        challenge = self.issue()
        business, hotel = uid("conversation-business"), uid("conversation-hotel")
        guest, room = uid("Guest C"), uid("205")
        replacement_stay = uid("replacement-stay")
        snapshot = synthetic_hotel()
        snapshot["stays"][0]["entity_id"] = replacement_stay
        snapshot["stay_guests"][0]["stay_id"] = replacement_stay

        def resolve(_subject):
            return ResolvedGuestStay(
                business_id=business, record_business_id=business,
                hotel_id=hotel, trusted_snapshot_hotel_id=hotel,
                guest_id=guest, stay_id=replacement_stay, room_id=room,
                snapshot=snapshot, staff_directory=[], existing_requests=[],
            )

        authority = GuestSessionAuthority(
            verify_evidence=self.service.verify_evidence, resolve_stay=resolve,
            clock=self.clock, token_factory=lambda: "opaque-session-token-with-test-entropy",
        )
        with self.assertRaises(GuestSessionError) as error:
            authority.complete_challenge(self.evidence(challenge))
        self.assertEqual(error.exception.code, "stay_scope_changed")
        self.assertEqual(self.store.get(challenge.challenge_id).state, "consumed")

    def test_invalid_proofs_consume_bounded_attempts(self):
        service = GuestChallengeService(
            provider=self.provider, contact_resolver=self.contact_resolver,
            store=self.store, rate_limiter=self.limiter,
            clock=self.clock, token_factory=self.service.token_factory,
            max_attempts=2, verify_limit=20,
        )
        challenge = service.issue(self.subject, trusted_source_key="source-a")
        for _ in range(2):
            with self.assertRaises(GuestChallengeError) as error:
                service.verify_evidence(self.evidence(challenge, proof="wrong"))
            self.assertEqual(error.exception.code, "invalid_challenge")
        with self.assertRaises(GuestChallengeError) as error:
            service.verify_evidence(self.evidence(challenge))
        self.assertEqual(error.exception.code, "challenge_attempt_limit")
        self.assertEqual(self.store.get(challenge.challenge_id).attempts, 2)

    def test_expired_challenge_cannot_be_verified(self):
        challenge = self.issue()
        self.clock.advance(300)
        with self.assertRaises(GuestChallengeError) as error:
            self.service.verify_evidence(self.evidence(challenge))
        self.assertEqual(error.exception.code, "challenge_expired")
        self.assertEqual(self.store.get(challenge.challenge_id).state, "expired")

    def test_verification_is_single_winner_under_concurrent_valid_attempts(self):
        challenge = self.issue()
        self.provider.verify_barrier = Barrier(2)
        evidence = self.evidence(challenge)
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(self.service.verify_evidence, evidence) for _ in range(2)]
            outcomes = []
            for future in futures:
                try:
                    outcomes.append(future.result(timeout=3))
                except GuestChallengeError as error:
                    outcomes.append(error.code)
        self.assertEqual(outcomes.count(self.subject), 1)
        self.assertEqual(outcomes.count("challenge_replayed"), 1)

    def test_server_source_rate_limit_applies_across_distinct_challenges(self):
        service = GuestChallengeService(
            provider=self.provider, contact_resolver=self.contact_resolver,
            store=self.store, rate_limiter=self.limiter,
            clock=self.clock, token_factory=self.service.token_factory,
            verify_limit=1,
        )
        first = service.issue(self.subject, trusted_source_key="issuer")
        second = service.issue(self.subject, trusted_source_key="issuer")
        with self.assertRaises(GuestChallengeError) as first_error:
            service.verify_evidence(self.evidence(first, proof="wrong", source="same-client"))
        self.assertEqual(first_error.exception.code, "invalid_challenge")
        with self.assertRaises(GuestChallengeError) as second_error:
            service.verify_evidence(self.evidence(second, proof="correct-code", source="same-client"))
        self.assertEqual(second_error.exception.code, "rate_limited")
        self.assertEqual(self.store.get(second.challenge_id).attempts, 0)

    def test_recipient_rate_limit_applies_across_distinct_sources(self):
        service = GuestChallengeService(
            provider=self.provider, contact_resolver=self.contact_resolver,
            store=self.store, rate_limiter=self.limiter,
            clock=self.clock, token_factory=self.service.token_factory,
            verify_limit=1,
        )
        first = service.issue(self.subject, trusted_source_key="issuer")
        second = service.issue(self.subject, trusted_source_key="issuer")
        with self.assertRaises(GuestChallengeError):
            service.verify_evidence(self.evidence(first, proof="wrong", source="source-one"))
        with self.assertRaises(GuestChallengeError) as error:
            service.verify_evidence(self.evidence(second, source="source-two"))
        self.assertEqual(error.exception.code, "rate_limited")
        self.assertEqual(self.store.get(second.challenge_id).attempts, 0)

    def test_issue_rate_limit_applies_to_trusted_source_and_on_file_contact(self):
        service = GuestChallengeService(
            provider=self.provider, contact_resolver=self.contact_resolver,
            store=self.store, rate_limiter=self.limiter,
            clock=self.clock, token_factory=self.service.token_factory,
            issue_limit=1,
        )
        service.issue(self.subject, trusted_source_key="same-issuer")
        with self.assertRaises(GuestChallengeError) as error:
            service.issue(self.subject, trusted_source_key="same-issuer")
        self.assertEqual(error.exception.code, "rate_limited")
        self.assertEqual(len(self.provider.issued), 1)

    def test_issue_and_verify_provider_outages_fail_closed(self):
        self.provider.fail_issue = True
        with self.assertRaises(GuestChallengeError) as issue_error:
            self.issue()
        self.assertEqual(issue_error.exception.code, "challenge_unavailable")
        self.assertEqual(self.store.get("challenge-id-with-enough-entropy-1").state, "revoked")

        self.provider.fail_issue = False
        challenge = self.issue()
        self.provider.fail_verify = True
        with self.assertRaises(GuestChallengeError) as verify_error:
            self.service.verify_evidence(self.evidence(challenge))
        self.assertEqual(verify_error.exception.code, "verification_unavailable")
        self.assertEqual(self.store.get(challenge.challenge_id).attempts, 1)

    def test_untrusted_issue_scope_or_missing_trusted_rate_key_is_rejected(self):
        with self.assertRaises(GuestChallengeError) as error:
            self.service.issue({"guest_id": "browser-claim"}, trusted_source_key="source")
        self.assertEqual(error.exception.code, "trusted_guest_scope_required")
        with self.assertRaises(GuestChallengeError) as error:
            self.service.issue(
                GuestSubject(self.subject.business_id, self.subject.hotel_id, self.subject.guest_id),
                trusted_source_key="source",
            )
        self.assertEqual(error.exception.code, "trusted_guest_scope_required")
        with self.assertRaises(GuestChallengeError) as error:
            self.service.issue(self.subject, trusted_source_key="")
        self.assertEqual(error.exception.code, "trusted_issue_context_required")
        challenge = self.issue()
        with self.assertRaises(GuestSessionError) as error:
            self.service.verify_evidence(ChallengeEvidence(challenge.challenge_id, "correct-code"))
        self.assertEqual(error.exception.code, "verification_required")

    def test_rate_limiter_and_challenge_store_fail_closed_at_capacity(self):
        store = InMemoryGuestChallengeStore(max_records=1)
        limiter = InMemoryGuestRateLimiter(max_keys=10)
        service = GuestChallengeService(
            provider=self.provider, contact_resolver=self.contact_resolver,
            store=store, rate_limiter=limiter,
            clock=self.clock, token_factory=self.service.token_factory,
        )
        challenge = service.issue(self.subject, trusted_source_key="source-a")
        with self.assertRaises(GuestChallengeError) as error:
            service.issue(self.subject, trusted_source_key="source-b")
        self.assertEqual(error.exception.code, "challenge_unavailable")
        self.assertEqual(store.get(challenge.challenge_id).state, "active")

        bounded_limiter = InMemoryGuestRateLimiter(max_keys=1)
        self.assertTrue(bounded_limiter.allow(("first",), now=1, limit=1, window_seconds=60))
        self.assertFalse(bounded_limiter.allow(("second",), now=1, limit=1, window_seconds=60))


if __name__ == "__main__":
    unittest.main()
