# WOR-87 — Native Workpeg navigation and guest-route boundary

## What changed

The native router now has a useful unscoped `/` launch page, a business-scoped
workspace home at `/b/<business_id>`, and an explicit guest-access-unavailable
route at `/b/<business_id>/stay`. The existing business-scoped Reception routes
remain attached to the same authenticated, read-only `HotelData` reader. The
local QA server routes (`/__qa/`, `/stay`, `/staff/reception`, and
`/staff/housekeeping`) remain separate and are not registered in the Workpeg
router.

The business home links to Reception, the safe guest-access state, and Workpeg's
reserved built-in AI chat route. `workpeg.json` remains the existing `roomay`
namespace with no action declarations. The AI link is therefore a general
Workpeg chat only: it is not a Roomay tool, does not load hotel or guest facts,
and cannot create or report a Roomay request.

## Why `/b/<business_id>/stay` returned 404

The native Workpeg Router had only `/`, Reception, and Reception workspace
routes. It had no matching stay route. The similarly named `/stay` page belongs
to `tools.guest_chat_demo.py`, the isolated local QA HTTP application, so its
route was never part of the compiled Peg.

The new native stay route intentionally does not instantiate `HotelData`, call
the table reader, or use the offline guest identity contracts as if they were
connected authentication. It explains that Workpeg business sign-in is not a
verified guest stay, and that no private records were loaded and no request was
created. A guest invitation/contact challenge, revocation-aware session, and
authorized guest request/status adapter are still required before this screen
can show private stay data or accept an operation.

## Native route map

| Native Workpeg path | Behavior |
| --- | --- |
| `/` | Unscoped launch guidance. No business UUID is guessed or hardcoded. |
| `/b/<business_id>` | Workpeg `Scaffold` with the active business context, Reception navigation, guest-access status, and general Workpeg AI link. |
| `/b/<business_id>/reception` | Existing authenticated, read-only hotel snapshot and Reception UI. |
| `/b/<business_id>/reception/<workspace>` | Existing Reception workspace route. Only the supported filtered view is shown. |
| `/b/<business_id>/stay` | Safe guest-access unavailable state; no row access. |
| `/b/<business_id>/chats/new` | Workpeg-reserved built-in AI chat surface, not a custom Roomay action. |

Workpeg documents that `Scaffold` reads the active business from the `/b/<uuid>`
URL and supplies its own business switcher and Workpeg AI chrome. Its runtime
also reserves `/b/<business>/chats/*`. The manifest action section is how
Workpeg AI exposes Peg operations; this repository currently declares none.
Manifest actions are untrusted instructions to the model and are not equivalent
to guest authorization. No custom Roomay AI action or live AI-to-hotel workflow
was verified in this change.

## Workpeg AI and data boundary

The existing nine hotel/request tables remain owner-only (`700`). This change
does not alter `workpeg.json`, table schemas, permissions, the canonical data
reader, Workpeg actions, Functions, or hosted records. The AI chat must not be
given guest room, stay, request, or audit details. Verified hotel facts remain
unavailable until a trusted source-backed action is supported and installed;
structured guest request confirmation remains disconnected from a committed
Workpeg request plus audit readback.

Official platform references:

- [Workpeg UI routing and reference](https://developers.workpeg.com/docs/latest/reference/)
- [Workpeg architecture](https://developers.workpeg.com/docs/latest/architecture/)
- [Workpeg manifest and AI actions](https://developers.workpeg.com/docs/latest/manifest/)
- [Workpeg development installation](https://developers.workpeg.com/docs/latest/dev-install/)

The SDK's development-install command uses a real Workpeg session/API origin;
it is not an offline sandbox. The development installation isolates table
access under a per-business development namespace and may initialize that
development namespace. No authenticated development server was started as part
of this change. The primary checkout in the workspace is dirty and on a
different branch, so it was not modified or treated as the source for any
running server. Process command-line inspection was unavailable; the exact
checkout currently serving `roomay.dev.workpeg.com` could not be confirmed.

## Verification and manual acceptance

The compiled route test exercises the Workpeg router registration without
network access. It verifies the root, workspace, Reception, and guest routes;
checks that the guest route is separate from the private-data reader; checks
that it displays no guest/room records and claims no created request; and checks
that the Workpeg AI link targets the reserved `chats/new` route without claiming
custom Roomay actions.

To preview the branch, from PowerShell:

```powershell
Set-Location 'C:\Users\HomePC\Desktop\roomay-workspace\roomay-wor87-native-navigation'
& ..\.venv\Scripts\python.exe -m pip show workpeg
& ..\.venv\Scripts\workpeg.exe --version
& ..\.venv\Scripts\workpeg.exe ui build ui/
```

For a plain local compiler preview, run `& ..\.venv\Scripts\workpeg.exe ui
serve ui/` and open the URL printed by the CLI. It has no Workpeg account or
hotel-data session. To test the authenticated Workpeg dev-install origin, the
owner can use the existing reviewed procedure in
[`docs/wor-25-release.md`](wor-25-release.md), replacing its checkout path with
the path above. That procedure's `--fake-cloud` option talks to Workpeg using
the browser session and can initialize the per-business dev table namespace;
do not start it unless that dev-namespace behavior is separately acceptable.

When the owner runs the dev installation, open the printed origin, select the
approved Roomay AI development business, and verify:

1. `/` shows launch instructions without guessing a business.
2. `/b/<verified-business-id>` shows native navigation and the AI/guest-access
   limitations.
3. `/b/<verified-business-id>/reception` still loads the authenticated
   read-only snapshot, or fails closed if the snapshot cannot be read.
4. `/b/<verified-business-id>/stay` displays the safe unavailable state and
   does not show guest, room, request, or audit data.
5. `/b/<verified-business-id>/chats/new` opens Workpeg's built-in chat. Do not
   submit private hotel/guest details or treat an answer as a Roomay action.

No live Workpeg request, custom AI action, guest authentication, or hosted
mutation was performed for this acceptance.
