const RFC3339_TIMESTAMP = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d+)?(Z|([+-])(\d{2}):(\d{2}))$/;

/** Return a finite expiry instant only for an explicit RFC 3339 timestamp. */
export function parseSessionExpiry(value) {
  if (typeof value !== "string") return null;
  const parts = RFC3339_TIMESTAMP.exec(value);
  if (!parts) return null;
  const [, yearText, monthText, dayText, hourText, minuteText, secondText, , , offsetHourText, offsetMinuteText] = parts;
  const year = Number(yearText);
  const month = Number(monthText);
  const day = Number(dayText);
  const hour = Number(hourText);
  const minute = Number(minuteText);
  const second = Number(secondText);
  const daysInMonth = [31, ((year % 4 === 0 && year % 100 !== 0) || year % 400 === 0) ? 29 : 28,
    31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1];
  if (year < 1 || month < 1 || month > 12 || day < 1 || day > daysInMonth
      || hour > 23 || minute > 59 || second > 59
      || (offsetHourText !== undefined && (Number(offsetHourText) > 23 || Number(offsetMinuteText) > 59))) {
    return null;
  }
  const expiry = Date.parse(value);
  return Number.isFinite(expiry) ? expiry : null;
}

/** Never expose an authenticated UI state for a malformed or elapsed expiry. */
export function enforceSessionExpiry(status, now = Date.now()) {
  if (status.state !== "authenticated") return status;
  const expiry = parseSessionExpiry(status.expiresAt);
  return expiry === null || expiry <= now ? { state: "expired" } : status;
}

/** Schedule an expiry and expose a check for when a suspended tab becomes active. */
export function scheduleSessionExpiry(expiresAt, onExpire, clock = {}) {
  const expiry = parseSessionExpiry(expiresAt);
  if (expiry === null) {
    onExpire();
    return { check: () => {}, cancel: () => {} };
  }

  const now = clock.now ?? Date.now;
  const setTimer = clock.setTimeout ?? globalThis.setTimeout.bind(globalThis);
  const clearTimer = clock.clearTimeout ?? globalThis.clearTimeout.bind(globalThis);
  let timer;
  let cancelled = false;
  const check = () => {
    if (cancelled) return;
    clearTimer(timer);
    const remaining = expiry - now();
    if (remaining <= 0) {
      cancelled = true;
      onExpire();
    } else {
      timer = setTimer(check, Math.min(remaining, 2_147_000_000));
    }
  };
  timer = setTimer(check, Math.min(expiry - now(), 2_147_000_000));
  return {
    check,
    cancel() {
      cancelled = true;
      clearTimer(timer);
    },
  };
}
