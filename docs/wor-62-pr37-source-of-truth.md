# WOR-62 — PR #37 request/audit source-of-truth decision

**Status: decision proposed, NOT approved.** Owner approval and Workpeg authorization evidence are required before enabling a public guest flow or merging PR #37 as a functioning integration. This document records the two possible **mutually exclusive** writer strategies; it does not claim one is implemented end to end.

## Observed facts (12 November 2026)

1. The existing Workpeg Reception Peg displays its **Workpeg-owned** service-request and audit tables with owner-only `700` permissions. Its staff permissions and live write/readback are not verified.
2. Draft PR #37 has transactional request/audit writes **in its own PostgreSQL database**, plus a separate FastAPI guest/staff view. Its default Workpeg hotel snapshot reader is deliberately unavailable and returns sanitized `503 hotel_records_unavailable`; the old `WORKPEG_PK` external Tables reader has been removed.
3. Workpeg directly clarified that a developer `WORKPEG_PK` is for developer/publishing work, **not** a standalone server Tables credential. In-Peg UI reads use an authenticated user session; an invoked Function receives a **short-lived, invocation-scoped** token and business context. No supported authenticated external guest/Vapi → Function invocation contract has been supplied. OIDC identifies staff; it is **not** a Tables credential.
4. PostgreSQL 16 CI can validate local SQL transactions, audit ordering, row locks and concurrent retries. It **cannot** establish Workpeg authorization, an actual receptionist queue or shared hotel-data authority.

## Decision required from owner + vendor

| Choice | Authoritative request/audit writer | Staff experience | What must be proven before enabling |
| --- | --- | --- | --- |
| **A — Workpeg canonical (preferred if vendor supports it)** | Exactly one authorized Workpeg Function/row-write path writes *both* request and audit with verified guest/stay scope | Existing Workpeg Reception and department views read the same committed rows | Vendor-approved external invocation, actor/business signature, token expiry/replay control, least privilege, atomic/reconcilable request+audit, pagination, fresh readback, guest own-status, cross-role denial |
| **B — PostgreSQL canonical (only with approved staff projection)** | Exactly one FastAPI/PostgreSQL writer with committed audit, retries, durable operation identity | A **securely deployed, authenticated** FastAPI staff inbox replaces the operational Workpeg request list, **or** a vendor-approved read-only projection surfaces PostgreSQL in Workpeg | Workpeg hotel snapshot read authorization (or an owner-approved independent canonical hotel/stay authority), real registered OIDC callback, authenticated external staff view/role checks, guest confirmation + durable audit, explicit history/migration policy, no mismatched Workpeg queue |

Do **not** use both as independently authoritative operational writers, or silently copy eventually consistent records and call them one live queue. A post-save asynchronous hook alone does not prove atomic request/audit or delivery. No platform hook creates an external caller authorization entrypoint by itself.

**Recommended decision sequence:** request Workpeg's formal supported external invocation/bridge contract; if approved, review choice A and implement its actual reconciliation. If unavailable, ask the owner whether choice B and replacing/bridging the native receptionist queue is acceptable for this hackathon, including any Workpeg-native requirements. Record explicit owner acceptance in WOR-62 before changing PR #37's persistence architecture.

## Minimal end-to-end acceptance (whichever option is approved)

A synthetic **verified active stay** and approved guest session (not room number/ANI/QR alone) → explicit request confirmation → one authorized committed request + audit event → **separate authenticated** receptionist session sees the same request → correct department acknowledges/resolves → original guest sees the status after independent reload → replay/duplicate, wrong-business, wrong-department, expired/revoked stay, room transfer, and partial-write denial all pass.

For either option, trace one canonical `request_id`, `operation_id`, `business_id`, `hotel_id`, `stay_id`, authorization scope, commit/audit sequence, readback and timestamp in a **sanitized** verification record. Store no bearer secrets, real guest personal data, images of IDs or provider credentials in GitHub/Linear logs.

## Current disposition

- **PR #37 stays draft.** PostgreSQL is an isolated, offline-tested prototype: no externally authorized hotel snapshot reader, no real Workpeg staff request queue, no verified OIDC client registration or public deployment. No fake 200/success state should replace sanitized 503 for unavailable integration.
- WOR-61 and WOR-62 remain In Progress until the owner approves one strategy and real Workpeg supported invocation/OIDC is demonstrated. WOR-65 starts only after that choice is actionable.
- No Workpeg table permissions, data, Functions, public endpoints or production secrets may be changed as an implied side effect of merging documentation or running PostgreSQL integration tests.
