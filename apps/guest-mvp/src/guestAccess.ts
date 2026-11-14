/**
 * Provider-neutral boundary for guest verification and session status.
 *
 * A trusted adapter must keep session credentials in a Secure, HttpOnly,
 * SameSite cookie or equivalent server-side channel. Its browser API returns
 * status only; bearer tokens and guest/business/stay/room IDs never enter this
 * type. No WorkPeg URL or unsupported platform API is assumed here.
 */
export type GuestSessionStatus =
  | { state: "authenticated"; expiresAt: string }
  | { state: "unauthenticated" }
  | { state: "invalid" }
  | { state: "expired" }
  | { state: "revoked" }
  | { state: "rate_limited" }
  | { state: "unavailable" };

export type GuestChallengeSubmission = { response: string };

export interface GuestAccessAdapter {
  /** Revalidate the server-held session after page load or before protected UI. */
  getSessionStatus(): Promise<GuestSessionStatus>;
  /** Verify a challenge response; identity and room scope are server-derived. */
  verify(submission: GuestChallengeSubmission): Promise<GuestSessionStatus>;
  /** Revoke the server-held session and clear its protected cookie. */
  logout(): Promise<void>;
}

/**
 * Default until a reviewed trusted server boundary is connected. It performs
 * no network request and can never authenticate a guest.
 */
export const unavailableGuestAccessAdapter: GuestAccessAdapter = {
  async getSessionStatus() {
    return { state: "unavailable" };
  },
  async verify() {
    return { state: "unavailable" };
  },
  async logout() {},
};
