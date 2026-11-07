# WOR-25 UI-only release candidate

This is a release-preparation and owner-handoff document. It is not evidence
that Roomay has been published, reviewed, installed, or connected to hosted
Workpeg tables.

## Candidate boundary

The candidate is the compiled `ui/dist/` artifact produced from `ui/main.py`
with Workpeg SDK `0.149.1`. Its manifest preserves the approved Peg identity:

```json
{
  "namespace": "roomay"
}
```

The official manifest documentation says a Peg without a Function omits both
`function` and `runtime`. Roomay's release router calls only authenticated
browser-side table reads. It has no Function action or table hook, so the
generated `function/` scaffold remains in source control for historical or
future work but is not part of the manifest contract.

## Reproducible local verification

From the repository root on the release candidate commit:

```powershell
git status --short --branch
.\.venv\Scripts\python.exe -m pip show workpeg
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m compileall -q ui function domain tests
.\.venv\Scripts\workpeg.exe ui build ui/
.\.venv\Scripts\workpeg.exe doctor . --offline
git diff --check
```

`tests/test_release_candidate.py` compiles a fresh temporary artifact and
checks the artifact itself, not only the Python router. It requires exactly the
home route and `/b/[business_id]/reception`; permits only `get_tables` and
`get_rows` Workpeg table helpers; and rejects diagnostic routes, development
table identifiers, Function actions, known fixture guests, token-shaped data,
private keys, and `WORKPEG_PK`.

The tracked diagnostic modules and synthetic fixtures are test/development
source. They are not imported by `ui/main.py` and do not appear in compiled
`app.js`. The release route does not provision tables, seed records, book,
check in, assign rooms, or mutate service requests.

## SDK 0.149.1 packaging and publishing support

Verified from the pinned CLI, installed package, and official Workpeg docs:

| Capability | SDK 0.149.1 status |
| --- | --- |
| Compile Python UI to `index.html`, `app.js`, runtime, chrome and styles | Supported: `workpeg ui build ui/` |
| Choose default CDN chrome with bundled fallback or byte-pinned bundled chrome | Supported: `--chrome auto` (default) or `--chrome bundled` |
| Build/run/submit a Function | Supported, but not used by this candidate |
| Upload public static assets to the Peg CDN | Supported: `workpeg cdn submit`; requires `WORKPEG_PK` |
| Scaffold a whole project | Supported: `workpeg project create` |
| Submit a complete UI + manifest + optional Function project | **Unsupported:** `workpeg project submit` does not exist |
| Create a PegStore release from the compiled UI | **No documented SDK 0.149.1 command** |
| Review or approve a complete Peg release | **No documented SDK 0.149.1 command** |
| Install a Peg into a business | **No documented SDK 0.149.1 command** |

The architecture documentation describes platform packaging between Registry /
CDN and PegStore, and lists the PegStore submission workflow and `project
submit` as roadmap work. A CDN upload is public asset distribution; it must not
be presented as a complete, reviewed, installable Peg release.

Official references:

- <https://developers.workpeg.com/docs/latest/manifest/>
- <https://developers.workpeg.com/docs/latest/projects/>
- <https://developers.workpeg.com/docs/latest/functions/>
- <https://developers.workpeg.com/docs/latest/architecture/>
- <https://developers.workpeg.com/docs/latest/cdn/>

The default `auto` UI build loads Workpeg's current official chrome CDN first
and includes the pinned SDK's bundled chrome as fallback. An owner may instead
choose `--chrome bundled` for a byte-pinned deployment, but that distribution
choice must be confirmed with Workpeg before the release artifact is uploaded.

## Owner and Workpeg handoff

No command below is authorized by this document. Before any cloud action, an
authorized Roomay owner must obtain the exact supported dashboard or Workpeg
engineering procedure for:

1. uploading the compiled UI and `workpeg.json` as one release;
2. confirming whether a UI-only release can be reviewed without a Function;
3. associating that release with the approved `roomay` Peg in PegStore;
4. selecting and approving an immutable version;
5. installing only into the isolated **Roomay AI** development business; and
6. confirming whether that installation resolves `Unknown peg namespace
   'roomay'` for authenticated staff-session table helpers.

The owner must separately approve token generation, secret storage, any CDN or
Function submission, release creation, review request, installation, table
provisioning and hosted data writes. `WORKPEG_PK` is a publishing/backend secret
and must never enter browser code, Git, CI logs, issue comments, screenshots or
the compiled artifact.

After an authorized installation, WOR-28 must still prove authenticated table
creation/read/update/reload and permissions using synthetic records in the
isolated business. The current offline build cannot satisfy that acceptance
gate.
