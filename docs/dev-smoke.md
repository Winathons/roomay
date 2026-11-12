# Historical development table smoke test

> **Archived. Do not follow this as a current setup or provisioning guide.**
> The `/b/<business_id>/dev-smoke` route was removed from the production
> Workpeg router. The old instructions below were superseded by newer SDK
> behavior and must not be used to create or modify hosted tables/rows.

The owner previously used a development-only table screen to verify native
Workpeg table persistence. That screen is retained only as isolated source and
offline test material; it is not registered by [ui/main.py](../ui/main.py).
The owner later verified Roomay's nine-table fictional hotel data and a
read-only Reception view in the approved Roomay AI development business. Do
not recreate the smoke table or reseed those records.

For current use, see the [WOR-25 tester and release handoff](wor-25-release.md).
It covers the real installed Workpeg Reception app, the pinned SDK 0.152.0
`workpeg ui serve ui/ --fake-cloud` developer path, authenticated access,
read-only behavior, SDK dev-table isolation, and the incomplete release process.

## Historical evidence

- The diagnostic source had no automatic writes on mount; its write controls
  were explicit and owner-only.
- Its offline compiled tests mocked Workpeg responses and blocked network
  access. They did not establish hosted permissions or persistence.
- A previous owner run reported successful persistence checks for the
  fictional room-type row. This is historical owner evidence, not an
  instruction to repeat the setup.

Current SDK caution: `--fake-cloud` uses a real Workpeg origin and browser
session. SDK 0.152.0 refuses `WORKPEG_BIND_HOST` in this mode, chooses its own
loopback binding on port 443, and scopes dev-page tables separately. Do not
reuse old commands containing `WORKPEG_BIND_HOST`, `--peg-namespace`, or a
non-443 port. Never publish credentials or use customer data.

