# WOR-64 — Verified hotel facts for Workpeg AI

## Implemented boundary

`domain/hotel_facts.py` adds a pure read-only resolver for the bounded topics
Wi-Fi, room air-conditioner instructions, television instructions, approved
hotel policy, and Reception contact. It returns only the exact value mapped by
a server-owned `FactSourcePolicy`; missing, stale, duplicate, malformed,
out-of-scope, and provider-failure cases return one fixed guest-safe fallback.
Guest room facts pass through the existing complete hotel-snapshot and active
registered-stay authorization checks. A room number or AI-supplied room claim
cannot establish that scope. The result excludes Workpeg row/table IDs, guest
identifiers, source metadata, and exception text.

The test source mapping and value in `tests/test_hotel_facts.py` are opaque
contract sentinels only. They are not hotel content, an example password, a
seed, or a claim about the Roomay AI business.

## Current source-data gap

The canonical `domain.workpeg_adapter.table_contracts()` definitions do not
contain Wi-Fi, room-device instructions, property policies, or Reception
contact fields. Current guest/stay contracts describe identity and occupancy,
not approved property guidance. No source mapping is therefore enabled in the
application, no manifest action was added, and this resolver is not wired to a
live Workpeg reader. The authenticated Reception snapshot alone cannot answer
these questions. Until an approved source is identified and read permissions
and guest scope are verified, production answers must remain unavailable.

Do not add these facts to unrelated operational records or provision a new
table as part of this issue. Any future Workpeg source/fields need a separate
schema review, owner approval, privacy classification and hosted read test.

## Workpeg AI read actions and safety decision

The installed Workpeg UI SDK is `0.152.0`; its package includes
`workpeg.ui.actions_manifest` validation for declarative actions. Current
official documentation describes table-operation actions such as
`{"risk":"read","via":{"table":"…","operation":"list",…}}`.
Workpeg executes these directly as the asking person through that person's
table-permission path. `list` returns rows (with optional paging/filtering),
and declared list filters are supplied as tool arguments. That is a supported
read mechanism, not a guarantee that returned data is scoped to an active
guest stay. A model-selected filter or room number is not authorization.

The registered Roomay tables are owner-only (`700`). The owner can read them;
the separate Member denial is previously verified at the UI level. No guest
access grant or supported Workpeg AI context binding to a verified active stay
has been established. A declarative list action on `rooms`, `guests`,
`reservations`, or `stays` would not be safe for guest guidance and is not
declared. Functions are associated with supported save-hook/action paths; this
issue does not invent a public read endpoint or use a Function as one.

The pinned SDK's validator and current docs were inspected, but no hosted AI
action was invoked. The resolver's `AccessContext` is a domain input, not Workpeg
authentication. Only a trusted adapter may construct it from an authenticated
Workpeg session and a fresh canonical snapshot. The resolver is not a substitute
for that adapter or for Workpeg's server-side permissions.

## Required integration sequence

1. Owner approves a canonical, non-operational source for hotel and room
   guidance, its fields, retention, sensitivity and table-level permissions.
2. Yusuf's WOR-77 shared contract defines the versioned external shape; this
   Python resolver remains the policy implementation and should be aligned to
   that contract rather than duplicating DTO schemas.
3. A trusted Workpeg-supported adapter reads only that source with complete
   pagination, business/Peg validation, snapshot freshness and a verified
   hotel-to-business mapping.
4. For room-specific facts, the server revalidates the guest's live session,
   active stay, registered occupant and current room assignment on every
   answer. It does not accept model/browser-supplied room or guest IDs.
5. A reviewed per-field allowlist maps approved Workpeg source columns to the
   bounded `FactTopic` values. Do not pass guest, reservation, request, audit,
   credential, or arbitrary free-text fields to the model.
6. Add the Workpeg AI action only when the platform can enforce this binding
   without exposing broader table rows. Keep it read-only and test owner,
   Member, guest, cross-business, expired-session and changed-room denials.
7. Verify responses against authorized live reads and show the fixed fallback
   for missing/stale information. Offline tests do not constitute a live AI
   acceptance test.

Availability, prices, bookings, payments and reservation confirmation are
outside WOR-64 and must never be inferred from these facts.

## Verification boundary

Unit tests exercise the resolver with a synthetic hotel occupancy snapshot and
an opaque, test-only source sentinel. They verify authorization, allowlisted
provenance, freshness, duplicate refusal, safe fallback, and sanitized reader
failure. They do not contact Workpeg or provide real hotel facts. No Workpeg
AI conversation, live table read, guest authorization, or hosted permission
behavior is claimed as verified by this change.

Official references: [Workpeg manifest actions](https://developers.workpeg.com/docs/latest/manifest/),
[Workpeg Tables & Rows](https://developers.workpeg.com/docs/latest/tables/),
[Workpeg Functions](https://developers.workpeg.com/docs/latest/functions/).
