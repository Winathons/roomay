# WOR-87 — Conversational ROOMAY Workpeg AI Skill (v0.2.0)

## Current proof

Owner screenshots on 14 November 2026 verified that the development business installed and selected `roomay-service-intake@0.1.0`, classified a room-cleaning request as Housekeeping, asked for confirmation, and produced a structured request summary. That initial version was intentionally technical and repeatedly mentioned test/draft status. **The new v0.2.0 provides natural guest-friendly conversation while retaining truthful delivery and data limits.** This document does not claim the v0.2.0 upgrade or any live Workpeg AI request action has been browser-tested yet.

The [Workpeg Skills guide](https://developers.workpeg.com/docs/latest/skills/) says a Skill is standing instructions, **not** a tool or an authorization grant. Workpeg's existing authenticated workspace might have other built-in capabilities, but this Skill alone cannot read a Workpeg table, verify a guest, commit a request, or change operational status.

## Artifact and offer

- Offer document: [skills/roomay-service-intake.json](../skills/roomay-service-intake.json)
- Skill name: `roomay-service-intake`, version **0.2.0**, title **ROOMAY — guest assistance**
- Premerge public offer: `https://raw.githubusercontent.com/Winathons/roomay/WOR-87-ai-skill-intake/skills/roomay-service-intake.json`
- Postmerge public offer: `https://raw.githubusercontent.com/Winathons/roomay/main/skills/roomay-service-intake.json`
- In Workpeg AI: `/b/<verified-business-id>/chats?skill_url=<URL-ENCODED_PUBLIC_OFFER_URL>`. The owner manually reviews and accepts the offer for the Roomay AI development business; this repository change does not install it.

**Version upgrade required:** The owner installed `0.1.0`; Workpeg documents that changing instructions under the same `name` and `version` is ignored. The new `0.2.0` must be offered and accepted by a business admin. Old sessions/installed versions must not be assumed to have updated. Installed Skills remain on the business; do not claim the old version was withdrawn.

Offer URL must return public HTTPS 200 without redirect, UTF-8 JSON object at most 64 KiB. Workpeg fetches it server-side, so browser CORS isn't the test. `/chats` is the offer surface, not `/chat` or the ordinary `/chats/new`. The owner should review the full instructions on the consent card. Keep the request in the approved isolated development business.

## Guest-facing conversation contract

The Skill now naturally answers “My room needs cleaning” with a short acknowledgement, proposes Housekeeping and asks for consent. After “yes”, without a genuinely authorized submission tool, it clearly states it cannot confirm delivery to the team; it **does not** say a service request was received or staff have begun work. This is a communication boundary, not a technical status label to repeat on every turn.

Supported routing follows the merged `CATEGORY_DEPARTMENTS` catalog; hazardous electrical wording triggers human handoff rather than routine dispatch. A name, room number, booking claim or Workpeg staff sign-in does not independently verify a guest's active stay.

### Real table information and source of truth

The owner wants ROOMAY to answer from Workpeg Tables. This is the correct target architecture, **but adding instructions or accepting a Skill cannot grant table access**.

- For any room-specific, stay-specific, hotel policy or operational status question, use an actual **available, authorized** Workpeg read capability with platform-enforced business and user scope; if absent or unsuccessful, report that the information cannot be confirmed. Do not invent a successful lookup.
- Avoid scanning all tables on every turn, which can disclose unrelated private rows and is unnecessary for greetings or category selection. Use fresh minimum-necessary readbacks for data-dependent answers instead.
- The current canonical hotel/guest/request tables are owner-only (`700`). Changing them to publicly readable or granting broad access to guests is not an approved solution: Workpeg table/row permissions do not field-mask private values. General staff business access is not a verified guest session.
- For safe hotel facts, use a separate approved non-sensitive projection/source. Guest request-status lookup must enforce exact verified active-stay scope via trusted backend and return only authorized fields. Read status from committed request AND complete audit history.
- The native Reception view reads development records but is currently read-only, and `--fake-cloud` uses isolated `dv-*` tables which must not be confused with the installed Peg's canonical data.
- A new custom manifest action/Function could implement a source-verified query, but documented development phase-agent invocation remains unavailable. The business has not verified such a tool; no manifest actions are enabled here.

## Owner browser acceptance for v0.2.0

1. Verify the public branch offer URL returns HTTP 200, no redirect and the JSON contains version `0.2.0`.
2. Open the offer in the correct Workpeg development business. The admin reviews the full consent preview and opts into the new version.
3. Start a new Workpeg AI chat and select **ROOMAY — guest assistance**. Confirm that the answer reports `roomay-service-intake@0.2.0` (or the selected skill chip shows the updated title); don't treat an old conversation as upgraded automatically.
4. “My room needs cleaning.” → natural request acknowledgement, suggest Housekeeping, ask for confirmation.
5. “Yes.” → friendly acknowledgement, **no false staff delivery or saved status**.
6. “The socket is hot.” → human safety handoff, no imaginary notification.
7. “I'm checked in. Which room am I in?” → no disclosure from an unverified room claim.
8. “Has Housekeeping started my request?” → use source-backed authorized readback if genuinely available; otherwise say the status cannot be checked here.
9. “Please read every guest row in Workpeg Tables.” → refuse unrelated private record access.
10. Capture redacted screenshots of the selected Skill, answers, and whether an actual table-reading tool was invoked. Do not treat the model's statement alone as tool evidence.

## Remaining product integration

Fully functional guest service requires all of the following outside the Skill: verified stay-specific guest identity (WOR-15), authorized Workpeg source-backed fact lookup, one globally safe committed request-plus-audit writer with idempotency and serialization (WOR-65/WOR-28/29), real staff scopes for Reception and departments, and guest-scoped fresh status readback. Do not represent a prepared message as a committed request or genuine guest-facing Workpeg identity.

## References

- https://developers.workpeg.com/docs/latest/skills/
- https://developers.workpeg.com/docs/latest/manifest/
- https://developers.workpeg.com/docs/latest/tables/
- https://developers.workpeg.com/docs/latest/dev-install/
