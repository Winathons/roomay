# Workpeg SDK 0.152.0 compatibility

## Blank page and JavaScript MIME types

The compiled Roomay root route is registered at `/` and builds the expected
reception availability message. The blank page reported on Windows occurs
before the route can run: Workpeg SDK 0.152.0's development static handler
calls `SimpleHTTPRequestHandler.guess_type()` for files in its built site.
That delegates `.js` detection to Python's `mimetypes` database. In the
verified Python 3.13.5 Windows environment, `mimetypes.guess_type("app.js")`
returns `text/plain`. The same handler serves both `app.js` and
`workpeg-runtime.js` with that type, while Workpeg also sends
`X-Content-Type-Options: nosniff`. Chrome correctly refuses to execute either
file. Their bodies are the compiled JavaScript bundles, not error responses.

This is a Workpeg SDK/Windows MIME integration defect, not evidence of a route
or Workpeg authentication failure. A local offline regression exercises the
SDK's static handler against both compiled bundles and verifies MIME headers
and response bodies after applying the compatibility mapping.

For an owner-run browser retest after review, use the project interpreter and
the wrapper (do not start this as part of CI or Codex work):

```powershell
..\.venv\Scripts\python.exe tools\workpeg_serve_compat.py ui/ --fake-cloud
```

The wrapper registers Python's standard `text/javascript` type for `.js` in
the server process, then invokes the Workpeg CLI's existing `ui serve`
workflow. It does not disable MIME enforcement, change response security
headers, patch installed SDK files, provision data, or change the Peg
namespace. The authenticated development server remains owner-operated and
must be used only after confirming the intended development business.

Please send Workpeg support the SDK version, Python version, Windows version,
the `mimetypes.guess_type("app.js")` result, and the two response headers
(`Content-Type: text/plain`, `X-Content-Type-Options: nosniff`) with the
observation that `app.js` and `workpeg-runtime.js` bodies contain compiled
JavaScript. Ask that the handler use an explicit JavaScript MIME mapping or
ship a cross-platform mapping.

## Compiled controller tests

SDK 0.152.0 emits application class declarations inside a top-level block in
`app.js`. The old Node harness appended a reference to `DevSmoke` or
`HotelData` after that block, where those class names are intentionally out of
scope. Tests now capture the actual compiled load callback and obtain the
controller through the generated mount or router registration. They continue
to execute compiled code with network access forbidden.

## Limits

Offline verification establishes generated routes, controller behavior, and
the local SDK handler's MIME behavior. It does not prove that the authenticated
Workpeg development page renders in Chrome, that a business is authorized, or
that hosted tables persist. The owner must repeat the browser test and inspect
the Console and Network response headers after this PR is reviewed. WOR-28
remains open until authenticated Workpeg verification succeeds.
