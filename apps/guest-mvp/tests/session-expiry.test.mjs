import assert from "node:assert/strict";
import test from "node:test";
import { enforceSessionExpiry, parseSessionExpiry, scheduleSessionExpiry } from "../src/sessionExpiry.js";

const NOW = Date.parse("2026-11-14T12:00:00.000Z");

test("keeps a well-formed session active before its expiry", () => {
  const active = { state: "authenticated", expiresAt: "2026-11-14T12:00:01.000Z" };
  assert.equal(enforceSessionExpiry(active, NOW), active);
});

test("expires a session when its timestamp is reached", () => {
  const active = { state: "authenticated", expiresAt: "2026-11-14T12:00:00.000Z" };
  assert.deepEqual(enforceSessionExpiry(active, NOW), { state: "expired" });
});

test("fails closed for malformed or impossible timestamps", () => {
  for (const expiresAt of ["", "tomorrow", "2026-11-14", "2026-02-30T12:00:00Z", "2026-11-14T12:00:00+99:00", null, 42]) {
    assert.deepEqual(enforceSessionExpiry({ state: "authenticated", expiresAt }, NOW), { state: "expired" });
    assert.equal(parseSessionExpiry(expiresAt), null);
  }
});

test("accepts explicit UTC offsets and fractional seconds", () => {
  assert.equal(parseSessionExpiry("2026-11-14T13:00:00.500+01:00"), NOW + 500);
});

test("leaves unauthenticated statuses unchanged", () => {
  const expired = { state: "expired" };
  assert.equal(enforceSessionExpiry(expired, NOW), expired);
});

test("scheduled expiry fires at the deadline and can be cancelled", () => {
  let now = NOW;
  let scheduled;
  let expired = 0;
  const timer = scheduleSessionExpiry("2026-11-14T12:00:01.000Z", () => { expired += 1; }, {
    now: () => now,
    setTimeout: callback => { scheduled = callback; return 1; },
    clearTimeout: () => {},
  });

  now += 999;
  scheduled();
  assert.equal(expired, 0);
  now += 1;
  scheduled();
  assert.equal(expired, 1);
  scheduled();
  assert.equal(expired, 1);
  timer.cancel();
});

test("visibility recheck expires a session after the tab was suspended", () => {
  let now = NOW;
  let scheduled;
  let expired = false;
  const timer = scheduleSessionExpiry("2026-11-14T12:00:01.000Z", () => { expired = true; }, {
    now: () => now,
    setTimeout: callback => { scheduled = callback; return 1; },
    clearTimeout: () => {},
  });

  now += 1_500;
  timer.check();
  assert.equal(expired, true);
  scheduled();
  assert.equal(expired, true);
});
