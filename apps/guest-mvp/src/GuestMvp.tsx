import { useEffect, useState, type FormEvent } from "react";
import { IconAlertTriangle, IconLock, IconShieldCheck } from "@tabler/icons-react";
import {
  unavailableGuestAccessAdapter,
  type GuestAccessAdapter,
  type GuestSessionStatus,
} from "./guestAccess";
import type { ComponentType } from "react";
import { enforceSessionExpiry, scheduleSessionExpiry } from "./sessionExpiry.js";

type Props = { accessAdapter?: GuestAccessAdapter };

const statusMessage: Partial<Record<GuestSessionStatus["state"], string>> = {
  invalid: "That verification code could not be confirmed. Check it and try again.",
  expired: "Your guest session expired. Verify your stay again to continue.",
  revoked: "This guest session is no longer active. Verify your stay again or contact reception.",
  rate_limited: "Too many attempts. Please contact reception for help.",
};

export function GuestMvp({ accessAdapter = unavailableGuestAccessAdapter }: Props) {
  const [status, setStatus] = useState<GuestSessionStatus>({ state: "unavailable" });
  const [checking, setChecking] = useState(true);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [Preview, setPreview] = useState<ComponentType<{ onExit: () => void }> | null>(null);

  const refreshStatus = async () => {
    setChecking(true);
    try {
      setStatus(enforceSessionExpiry(await accessAdapter.getSessionStatus()));
    } catch {
      setStatus({ state: "unavailable" });
    } finally {
      setChecking(false);
    }
  };

  useEffect(() => {
    let current = true;
    setChecking(true);
    accessAdapter.getSessionStatus().then(
      value => { if (current) setStatus(enforceSessionExpiry(value)); },
      () => { if (current) setStatus({ state: "unavailable" }); },
    ).finally(() => { if (current) setChecking(false); });
    return () => { current = false; };
  }, [accessAdapter]);

  useEffect(() => {
    if (status.state !== "authenticated") return;
    const expiryTimer = scheduleSessionExpiry(status.expiresAt, () => setStatus({ state: "expired" }));
    const checkAfterVisibilityChange = () => {
      if (document.visibilityState === "visible") expiryTimer.check();
    };

    document.addEventListener("visibilitychange", checkAfterVisibilityChange);
    return () => {
      expiryTimer.cancel();
      document.removeEventListener("visibilitychange", checkAfterVisibilityChange);
    };
  }, [status]);

  const verify = async (event: FormEvent) => {
    event.preventDefault();
    if (!code.trim() || busy) return;
    setBusy(true);
    try {
      setStatus(enforceSessionExpiry(await accessAdapter.verify({ response: code.trim() })));
    } catch {
      setStatus({ state: "unavailable" });
    } finally {
      setCode("");
      setBusy(false);
    }
  };

  const logout = async () => {
    setBusy(true);
    try {
      await accessAdapter.logout();
      setStatus({ state: "unauthenticated" });
    } catch {
      setStatus({ state: "unavailable" });
    } finally {
      setBusy(false);
    }
  };

  const openPreview = async () => {
    if (!import.meta.env.DEV) return;
    const module = await import("./GuestPreview");
    setPreview(() => module.GuestPreview);
  };

  if (Preview) return <Preview onExit={() => { setPreview(null); void refreshStatus(); }} />;

  const needsCode = status.state === "unauthenticated" || status.state === "invalid"
    || status.state === "expired" || status.state === "revoked";

  return <div className="roomay-guest-mvp" style={{ display: "flex", flexDirection: "column", height: "100%" }}>
    <div className="m-top">
      <div style={{ flex: 1, minWidth: 0 }}>
        <div className="m-title">Secure guest access</div>
        <div className="cap">Verified stay required</div>
      </div>
      <span className="chip s-insp noswatch"><IconShieldCheck size={13} />Private</span>
    </div>
    <div className="m-scroll" style={{ padding: 20, display: "flex", flexDirection: "column", gap: 16, background: "var(--surface)" }}>
      {checking ? <p role="status" className="ink2">Checking guest access…</p> : <>
        {status.state === "unavailable" && <div className="alert warn" role="alert">
          <IconAlertTriangle size={18} /><div><b>Guest verification is unavailable.</b> No guest identity or stay details were loaded. Please contact reception for assistance.</div>
        </div>}
        {status.state === "authenticated" && <div className="alert info" role="status">
          <IconShieldCheck size={18} /><div><b>Guest session verified.</b> Guest AI and request operations are not connected here. Contact reception for assistance.</div>
        </div>}
        {needsCode && <form onSubmit={verify} style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div><h2 className="h-page">Your room, one conversation.</h2>
            <p className="ink2" style={{ marginTop: 8 }}>Enter the verification code provided by reception.</p></div>
          <div className="f"><label htmlFor="guest-access-code">Stay verification code</label>
            <input id="guest-access-code" className="in" value={code} onChange={event => setCode(event.target.value)}
              autoComplete="one-time-code" maxLength={128} aria-describedby="guest-access-help" required disabled={busy} />
            <span id="guest-access-help" className="cap">Your code is sent only to the configured guest-access adapter.</span>
          </div>
          {statusMessage[status.state] && <div className="alert err" role="alert"><IconAlertTriangle size={18} /><div>{statusMessage[status.state]}</div></div>}
          <button className="btn primary touch block" disabled={!code.trim() || busy}>{busy ? "Checking…" : "Verify stay"}</button>
        </form>}
        {status.state === "rate_limited" && <div className="alert err" role="alert"><IconAlertTriangle size={18} /><div>{statusMessage.rate_limited}</div></div>}
        {status.state === "authenticated" && <>
          <p className="cap">Session expiry: {new Date(status.expiresAt).toLocaleString()}</p>
          <button className="btn secondary touch block" onClick={logout} disabled={busy}>Sign out</button>
          <button className="btn ghost" onClick={() => void refreshStatus()} disabled={busy}>Check session again</button>
        </>}
        {status.state === "unavailable" && <>
          <div className="note"><IconLock size={15} /> No verification code was accepted and no session was created.</div>
          <button className="btn secondary touch block" onClick={() => void refreshStatus()}>Try again</button>
          {import.meta.env.DEV && <button className="btn ghost" onClick={() => void openPreview()}>Open the offline UI preview</button>}
        </>}
      </>}
    </div>
  </div>;
}
