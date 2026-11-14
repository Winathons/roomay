import type { GuestSessionStatus } from "./guestAccess";

export function parseSessionExpiry(value: string): number | null;
export function enforceSessionExpiry(status: GuestSessionStatus, now?: number): GuestSessionStatus;
export function scheduleSessionExpiry(
  expiresAt: string,
  onExpire: () => void,
  clock?: { now?: () => number; setTimeout?: typeof setTimeout; clearTimeout?: typeof clearTimeout },
): { check: () => void; cancel: () => void };
