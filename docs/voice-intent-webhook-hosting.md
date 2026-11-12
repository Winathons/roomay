# ROOMAY Vapi intent-tool hosting (isolated, not yet deployed)

This document covers a **separate, non-mutating** Vapi Function tool webhook.
It is **not** the Remi YarnGPT TTS service. Do not reuse or overwrite the
existing Remi Railway endpoint, deployment variables, custom voice or test
assistant setup. This is a reviewable runtime scaffold, **not proof of hosting
or Vapi attachment**.

## Contract

- Entrypoint: `voice_adapter.tool_wsgi:application` in `Dockerfile.tool`
- Route: `POST /tool-calls`
- Authorization: `Authorization: Bearer <ROOMAY_VAPI_TOOL_BEARER_TOKEN>`
- Required environment variables: `ROOMAY_VAPI_TOOL_BEARER_TOKEN` (32+ chars)
- Optional: `ROOMAY_VAPI_TOOL_REQUESTS_PER_MINUTE` (default 60, 1–600).
- JSON message type: `tool-calls`. The Function tool is named
  `roomay_route_caller_intent`, with one string `utterance` argument.
- Valid response: Vapi's `{"results":[{"toolCallId":"...","result":"..."}]}`
  format (where `result` is serialized JSON text), or a sanitized `error`
  in place of `result`.
- Unknown method -> 405; wrong path -> 404; missing/mismatched bearer -> 401;
  malformed authorized input -> 400; bounded authenticated requests -> 200.

The service only classifies hotel/booking/room/service/human intent. It does
**not** check reservations, verify caller stays, save requests, dispatch staff,
transfer calls, look up prices, or contact an emergency responder. An apparent
room number or caller ID does not authorize any guest action.

## Offline image smoke (no external API)

With a working Docker Engine, run from repository root:

```powershell
$env:ROOMAY_RUN_DOCKER_TESTS = "1"
.\.venv\Scripts\python.exe -m unittest tests.test_voice_tool_docker_runtime -v
Remove-Item Env:ROOMAY_RUN_DOCKER_TESTS -ErrorAction SilentlyContinue
```

Without a working Docker engine, the code-level Dockerfile contract test runs
and runtime smoke is skipped; CI exercises both. Tests use synthetic hotel
phrases and local placeholder tokens.

## Owner-gated hosting procedure

1. Review this Dockerfile, tests, PR and separate provider bill limits.
2. Provision an **independent** HTTPS service. Set builder Dockerfile path to
   `Dockerfile.tool`. Do not alter TTS service or route.
3. Set an independent 32+-character random token through the service's secret
   manager, never inside GitHub, Vapi prompt, issue, logs or documentation.
4. Confirm service uses `/tool-calls` with unauthenticated 401 and an
   authenticated malformed-request 400 **without making a Vapi call**.
5. Configure a Vapi saved custom Bearer credential using that same token.
   Attach a `roomay_route_caller_intent` Function tool to the **isolated test
   assistant only**, point server URL to `https://<your-host>/tool-calls`.
   Verify the deployed Vapi assistant configuration through the REST GET, not
   merely the dashboard draft. Do not attach to the main production assistant.
6. Only after owner approval, make one controlled billable test call and verify
   Vapi `toolCallId` correlation, language choice, truthful fallback, and
   Railway logs without sensitive payloads.

This process-local replay cache and rate limiter assume one worker/instance.
Additional replicas require edge-level rate limiting and a shared replay
strategy. No hosted guest data access or external Workpeg Tables key should be
attempted from this service. The supported path for trusted guest requests is
tracked separately in WOR-61, WOR-62 and WOR-65.
