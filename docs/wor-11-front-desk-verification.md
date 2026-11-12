# WOR-11 — verified front-desk walk-in check-in (offline Phase B)

**No live booking or hotel write occurs in this implementation.** The established `domain/reservation_commands.py` already provides offline pending walk-in reservation, authorized room confirmation, check-in (stay + occupant rows), and partial-write reconciliation. This phase adds a review gate before physical walk-in check-in is planned.

## Front-desk review contract

`domain/front_desk_checkin.py` introduces `FrontDeskVerification`, `prepare_verified_walk_in_check_in`, and `reconcile_verified_check_in_readback`.

- An authenticated **receptionist/manager/owner** must independently verify the guest's identity **in person**, confirm contact, review the agreed rate and understand payment disposition before staff attempts check-in. The reviewed primary guest must match the confirmed `walk_in` reservation, and every occupant must be an already verified guest in the same booked party.
- Accepted payment dispositions are `provider_paid` only if supported by a **verified provider callback**, `payment_deferred` only if hotel policy authorizes pay-later, or `no_payment_due` only if verified hotel policy allows it. The current pure module **does not verify callback signatures, hotel policies or provider payments**. A future trusted server must derive the evidence from secure, authoritative sources. A guest claim, payment screenshot, voice transcript, QR code, and browser-supplied booleans cannot satisfy that trust boundary.
- Time-limited review: reviewed by the same trusted actor who authorizes check-in, before actual check-in and no more than 30 minutes before the attempted check-in time. The authoritative clock must come from the trusted server, not browser fields.
- The plan reuses existing `prepare_check_in` checks for fresh same-business hotel snapshot, mandatory serialization, confirmed assigned reservation, occupancy, dirty/maintenance/disabled room safety, hotel-local date, valid occupants and deterministic stay IDs. No guest is checked in simply because a QR code was scanned; advance/prepaid QR admission is a separate owner-proposed feature requiring server-side single-use token verification.
- The plan contains **only** stay/occupant proposals, proof-of-review metadata and an audit **intent**. It does not copy guest contact details, national ID numbers/scans or payment screenshots. `persisted=False` always.
- Reconciliation requires exact matching durable operation signature and an independently committed audit record **plus** all expected stay/occupant rows. Missing evidence, partial rows, or disagreement blocks a success report and requires manual reconciliation.

## Platform and schema gates

The existing Workpeg hotel tables don't contain agreed rate, payment state, ID review, or check-in audit metadata. Introducing them as browser-only flags would be misleading. Before enabling a real check-in writer, the owner must approve privacy-safe, authoritative rate/payment and review/audit storage, payment provider webhook verification and staff membership/role checks; the supported Workpeg adapter must serialize competing confirmations, atomically commit or explicitly reconcile pending reservations, stays, occupants and audit events, and validate reload in a separate authenticated session.

The current `WriteContext` and `FrontDeskVerification` objects **are not authentication**; only a trusted adapter may construct them from verified server-side evidence. The existing Workpeg UI provides no proven transactional/unique/conditional-write primitive, so real requests must remain pending rather than claim occupancy without hosted proof. No sensitive identity documents are stored. See WOR-61/62/28/11 for the remaining integration and source-of-truth blockers.

## Verification

```bash
python -m unittest tests.test_front_desk_checkin tests.test_reservation_commands -v
python -m unittest discover -s tests -v
python -m compileall -q ui function domain tests
workpeg ui build ui/
python -m unittest tests.test_release_candidate -v
```

Synthetic coverage includes verified multiple occupants, denied identity/contact/rate and screenshot payments, stale and cross-actor reviews, absent trusted business/serialization, blocked/dirty rooms, deterministic replay and committed-audit readback. Full WOR-11 stays **In Progress** until actual persisted reservation + active stay, room board update, staff permissions, trusted payment/identity review and non-duplicating retries are verified on Workpeg.
