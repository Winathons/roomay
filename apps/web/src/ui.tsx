import { createPortal } from "react-dom";
import { useEffect, useState, type ReactNode } from "react";
import { IconX, IconCheck, IconAlertTriangle, IconInfoCircle, IconWifiOff, IconLock, IconCircleCheck, IconCopy } from "@tabler/icons-react";
import { useStore, type WriteResult } from "./store";
import { minsSince, dur, type HK, type Room, type ReqStatus, type Request, type Occ, type DB, roomView, type ResStatus } from "./data";

export const initials = (n: string) => n.split(" ").map(x => x[0]).slice(0, 2).join("").toUpperCase();
export const shortName = (n: string) => { const [a, ...b] = n.split(" "); return b.length ? `${b.join(" ")}, ${a}` : a; }; // Mews: "Last, First"
export function Avatar({ name, size = 28 }: { name: string; size?: number }) { return <span className="avatar" style={{ width: size, height: size, fontSize: size < 28 ? 10 : 11 }} aria-hidden>{initials(name)}</span>; }

// ---------- status vocabulary (one word per state, used everywhere) ----------
export const HK_LABEL: Record<HK, string> = { dirty: "Dirty", clean: "Clean", inspected: "Inspected" };
export function HKChip({ hk, plain }: { hk: HK; plain?: boolean }) { return <span className={`chip s-${hk === "inspected" ? "insp" : hk}${plain ? " plain" : ""}`}>{HK_LABEL[hk]}</span>; }
export function BlockChip({ room }: { room: Room }) { if (!room.block) return null; return <span className={`chip s-${room.block.kind}`}>{room.block.kind === "oos" ? "Out of service" : "Out of order"}</span>; }
export const OCC_LABEL: Record<Occ, string> = { vacant: "Vacant", in_house: "In house", due_out: "Departs today", overdue: "Overdue", arriving: "Arrives today" };
export function OccChip({ occ }: { occ: Occ }) { const c = occ === "overdue" ? "urgent" : occ === "in_house" ? "house" : occ === "vacant" ? "neutral" : "today"; return <span className={`chip s-${c}`}>{OCC_LABEL[occ]}</span>; }
export function ReadyChip({ room, db }: { room: Room; db: DB }) { const v = roomView(room, db); if (!v.ready) return null; return <span className="chip s-insp noswatch" style={{ paddingLeft: 7 }}><IconCheck size={12} stroke={3} />Ready</span>; }
export const RES_LABEL: Record<ResStatus, string> = { pending: "Pending confirmation", confirmed: "Confirmed", checked_in: "Checked in", checked_out: "Checked out", cancelled: "Cancelled" };
export function ResChip({ s }: { s: ResStatus }) { return s === "pending" ? <span className="chip dash">Pending confirmation</span> : <span className={`chip s-${s === "confirmed" ? "today" : s === "checked_in" ? "house" : s === "cancelled" ? "oos" : "neutral"}`}>{RES_LABEL[s]}</span>; }
export const REQ_LABEL: Record<ReqStatus, string> = { received: "Received", assigned: "Assigned", acknowledged: "Acknowledged", in_progress: "In progress", resolved: "Resolved", escalated: "Escalated", cancelled: "Cancelled" };
export function ReqChip({ s }: { s: ReqStatus }) { const c = s === "resolved" ? "insp" : s === "escalated" ? "urgent" : s === "cancelled" ? "neutral" : s === "received" ? "neutral" : s === "in_progress" ? "navy" : "today"; return <span className={`chip s-${c}`}>{REQ_LABEL[s]}</span>; }

// time against target: words first, bar second, never colour alone
export function Sla({ q, compact }: { q: Request; compact?: boolean }) {
  useStore();
  if (q.status === "resolved") return <span className="sla muted">Done</span>;
  if (q.status === "cancelled") return <span className="sla muted">Closed</span>;
  const m = minsSince(q.createdAt), late = m > q.targetMin, pct = Math.min(1, m / q.targetMin);
  const col = late ? "var(--urgent-sw)" : pct > .75 ? "var(--ooo-sw)" : "var(--navy)";
  return <span className="sla" style={{ color: late ? "var(--urgent)" : "var(--text-2)", fontWeight: late ? 600 : 400 }} title={`Target ${q.targetMin} min`}>
    {!compact && <span className="bar-mini" aria-hidden><i style={{ width: `${pct * 100}%`, background: col }} /></span>}
    {late ? `${dur(m - q.targetMin)} over` : `${dur(m)} of ${q.targetMin} min`}
  </span>;
}

export function Seg<T extends string>({ value, onChange, items, label }: { value: T; onChange: (v: T) => void; items: { v: T; label: string; n?: number; icon?: ReactNode }[]; label: string }) {
  return <div className="seg" role="radiogroup" aria-label={label}>{items.map(i => <button key={i.v} role="radio" aria-checked={value === i.v} className={value === i.v ? "on" : ""} onClick={() => onChange(i.v)}>{i.icon}{i.label}{i.n !== undefined && <span className="n">{i.n}</span>}</button>)}</div>;
}
export function Tabs<T extends string>({ value, onChange, items }: { value: T; onChange: (v: T) => void; items: { v: T; label: string; n?: number }[] }) {
  return <div className="tabs" role="tablist">{items.map(i => <button key={i.v} role="tab" aria-selected={value === i.v} className={value === i.v ? "on" : ""} onClick={() => onChange(i.v)}>{i.label}{i.n !== undefined && <span className="n">{i.n}</span>}</button>)}</div>;
}

export function Sheet({ title, sub, onClose, children, footer, steps, step }: { title: ReactNode; sub?: ReactNode; onClose: () => void; children: ReactNode; footer?: ReactNode; steps?: string[]; step?: number }) {
  useEffect(() => { const k = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); }; window.addEventListener("keydown", k); return () => window.removeEventListener("keydown", k); }, [onClose]);
  return createPortal(<>
    <div className="scrim" onClick={onClose} />
    <section className="sheet" role="dialog" aria-modal="true" aria-label={typeof title === "string" ? title : "Task"}>
      <header className="sheet-h"><div style={{ flex: 1, minWidth: 0 }}>
        <h2 className="h-page" style={{ fontSize: 20, lineHeight: "26px" }}>{title}</h2>{sub && <div className="muted" style={{ marginTop: 2 }}>{sub}</div>}
        {steps && <div className="steps" aria-label={`Step ${step} of ${steps.length}`}>{steps.map((s, i) => <span key={s} className={i + 1 === step ? "on" : i + 1 < (step || 0) ? "done" : ""}><i>{i + 1 < (step || 0) ? <IconCheck size={11} stroke={3} /> : i + 1}</i>{s}</span>)}</div>}
      </div><button className="icon-btn" onClick={onClose} aria-label="Close"><IconX /></button></header>
      <div className="sheet-b">{children}</div>
      {footer && <footer className="sheet-f">{footer}</footer>}
    </section>
  </>, document.body);
}

// button with a real pending state while the write is in flight
export function SaveBtn({ onClick, children, kind = "primary", disabled, className = "", size }: { onClick: () => Promise<unknown> | void; children: ReactNode; kind?: string; disabled?: boolean; className?: string; size?: "sm" | "touch" }) {
  const [busy, setBusy] = useState(false);
  return <button className={`btn ${kind}${size ? " " + size : ""} ${className}`} disabled={disabled || busy} aria-busy={busy} onClick={async () => { setBusy(true); try { await onClick(); } finally { setBusy(false); } }}>{busy ? <><span className="spin" aria-hidden />Saving…</> : children}</button>;
}

// one consistent explanation for every non-success write
export function WriteAlert({ r, what, conflict, onRetry }: { r: WriteResult | null; what: string; conflict?: string; onRetry?: () => void }) {
  const { findSaved, toast } = useStore();
  const [checked, setChecked] = useState<string | null>(null);
  if (!r || r.ok) return null;
  if (r.kind === "unknown") return <div className="alert warn" role="alert"><IconAlertTriangle /><div style={{ flex: 1 }}><b>We couldn't confirm this saved.</b> The connection dropped before Workpeg replied. Don't submit again. Check first, so the guest isn't {what} twice.
    <div style={{ marginTop: 8, display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}><button className="btn secondary sm" onClick={() => setChecked(r.ref ? findSaved(r.ref) || "Not found. It's safe to try again." : "Not found. It's safe to try again.")}>Check status</button>{checked && <span style={{ fontWeight: 500 }}>{checked}</span>}</div></div></div>;
  if (r.kind === "duplicate") return <div className="alert info" role="status"><IconCopy /><div><b>Already saved.</b> This was submitted twice. Roomay kept one record{r.ref ? <>: <span className="mono">{r.ref}</span></> : null}. Nothing else changed.</div></div>;
  if (r.kind === "conflict") return <div className="alert err" role="alert"><IconAlertTriangle /><div><b>Someone else changed this first.</b> {conflict || "Another receptionist saved a change a moment ago."} Nothing of yours was saved. The list below is refreshed.</div></div>;
  if (r.kind === "denied") return <div className="alert err" role="alert"><IconLock /><div><b>Your role can't do this.</b> Workpeg refused the change (403). Ask a manager to do it or to update your role.</div></div>;
  if (r.kind === "offline") return <div className="alert neutral" role="alert"><IconWifiOff /><div><b>You're offline.</b> Nothing was sent. Reconnect, then try again.</div></div>;
  return <div className="alert err" role="alert"><IconAlertTriangle /><div style={{ flex: 1 }}><b>Couldn't save.</b> Nothing was changed. Check the connection and try again.{onRetry && <div style={{ marginTop: 8 }}><button className="btn secondary sm" onClick={() => { toast({ title: "Retrying…", tone: "info" }); onRetry(); }}>Try again</button></div>}</div></div>;
}

export function Toasts() {
  const { toasts, dismiss } = useStore();
  return <div className="toasts" role="status" aria-live="polite">{toasts.map(t => (
    <div className="toast" key={t.id}>{t.tone === "info" ? <IconInfoCircle style={{ color: "#B8C6D9" }} /> : t.tone === "warn" ? <IconAlertTriangle style={{ color: "#F3B13B" }} /> : <IconCircleCheck />}
      <div className="b"><div style={{ fontWeight: 500 }}>{t.title}</div>{t.body && <small>{t.body}</small>}</div>
      {t.undo && <button onClick={() => { t.undo!(); dismiss(t.id); }}>Undo</button>}</div>))}</div>;
}

export function Empty({ icon, title, body, action }: { icon: ReactNode; title: string; body: string; action?: ReactNode }) {
  return <div className="state"><span className="ico">{icon}</span><h3 className="h-sec">{title}</h3><p>{body}</p>{action}</div>;
}
export function Opt({ on, onClick, radio, children, disabled }: { on: boolean; onClick: () => void; radio?: boolean; children: ReactNode; disabled?: boolean }) {
  return <button type="button" role={radio ? "radio" : "checkbox"} aria-checked={on} className={`opt${on ? " on" : ""}`} onClick={onClick} disabled={disabled}><span className={`tick${radio ? " radio" : ""}`}>{on && !radio && <IconCheck />}</span><span style={{ flex: 1, minWidth: 0 }}>{children}</span></button>;
}
export function Stepper({ value, set, min, max, label }: { value: number; set: (n: number) => void; min: number; max: number; label: string }) {
  return <div className="stepper" role="group" aria-label={label}><button onClick={() => set(Math.max(min, value - 1))} disabled={value <= min} aria-label={`Fewer ${label}`}>−</button><span>{value}</span><button onClick={() => set(Math.min(max, value + 1))} disabled={value >= max} aria-label={`More ${label}`}>+</button></div>;
}
