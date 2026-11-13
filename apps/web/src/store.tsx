import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { seed, now, STAFF, triage, typeOf, type DB, type Request, type ReqStatus, type Dept, type HK, type Block, type Channel, type Reservation } from "./data";

// ---------- prototype scenario controls (drive every refusal / failure state from the dock) ----------
export type Outcome = "ok" | "conflict" | "fail" | "unknown" | "denied" | "duplicate";
export type DataState = "synthetic" | "loading" | "empty" | "401" | "403" | "offline" | "400" | "timeout" | "partial" | "stale";
export type WriteResult = { ok: true; ref?: string; note?: string } | { ok: false; kind: Exclude<Outcome, "ok"> | "offline"; ref?: string };
export interface Toast { id: number; title: string; body?: string; tone?: "ok" | "info" | "warn"; undo?: () => void }

interface Store {
  db: DB; tick: number; toasts: Toast[];
  outcome: Outcome; setOutcome: (o: Outcome) => void; data: DataState; setData: (d: DataState) => void;
  toast: (t: Omit<Toast, "id">) => void; dismiss: (id: number) => void;
  createBooking: (p: { name: string; phone: string; typeId: string; roomId: string; nights: number; adults: number; occupants: string[]; payment: "none" | "deposit" | "paid"; source: Channel; arrivalDay?: number; eta?: string }) => Promise<WriteResult & { resId?: string }>;
  editBooking: (resId: string, arrivalDay: number, nights: number, roomId: string) => Promise<WriteResult>;
  checkIn: (resId: string, roomId: string) => Promise<WriteResult>;
  checkOut: (stayId: string) => Promise<WriteResult>;
  changeRoom: (stayId: string, toRoom: string, reason: string) => Promise<WriteResult>;
  confirm: (resId: string, roomId: string) => Promise<WriteResult>;
  cancel: (resId: string, reason: string) => Promise<WriteResult>;
  extend: (stayId: string, nights: number) => Promise<WriteResult>;
  setHK: (roomId: string, hk: HK, by: string) => Promise<WriteResult>;
  setBlock: (roomId: string, block: Block | undefined, by: string) => Promise<WriteResult>;
  advance: (reqId: string, to: ReqStatus, by: string, note?: string) => Promise<WriteResult>;
  route: (reqId: string, dept: Dept, by: string) => Promise<WriteResult>;
  createRequest: (p: { roomId: string; guestFirst?: string; text: string; channel: Channel; dept?: Dept; title?: string }) => Promise<WriteResult & { req?: Request }>;
  requestBooking: (p: { name: string; phone: string; typeId: string; arrivalDay: number; nights: number; adults: number; note?: string }) => Promise<WriteResult>;
  findSaved: (ref: string) => string | null;
  reset: () => void;
}
const Ctx = createContext<Store | null>(null);
export const useStore = () => { const c = useContext(Ctx); if (!c) throw new Error("no store"); return c; };
const clone = (d: DB): DB => JSON.parse(JSON.stringify(d));
const wait = (ms: number) => new Promise(r => setTimeout(r, ms));
type BC = { __roomayBC?: BroadcastChannel };
let tid = 1;

export function StoreProvider({ children }: { children: ReactNode }) {
  const [db, setDb] = useState<DB>(() => seed());
  const [tick, setTick] = useState(0);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [outcome, setOutcome] = useState<Outcome>("ok");
  const [data, setData] = useState<DataState>("synthetic");
  const dbRef = useRef(db); dbRef.current = db;
  const outRef = useRef(outcome); outRef.current = outcome;
  const dataRef = useRef(data); dataRef.current = data;

  useEffect(() => { const i = setInterval(() => setTick(t => t + 1), 15_000); return () => clearInterval(i); }, []);
  useEffect(() => {
    if (!("BroadcastChannel" in window)) return;
    const bc = new BroadcastChannel("roomay-v2");
    bc.onmessage = e => { if (e.data?.type === "db") setDb(e.data.db); };
    (window as unknown as BC).__roomayBC = bc; return () => bc.close();
  }, []);
  const publish = (d: DB) => (window as unknown as BC).__roomayBC?.postMessage({ type: "db", db: d });
  const commit = useCallback((fn: (d: DB) => void) => { const next = clone(dbRef.current); fn(next); dbRef.current = next; setDb(next); publish(next); return next; }, []);
  const restore = (s: DB) => () => { dbRef.current = s; setDb(s); publish(s); };

  const dismiss = useCallback((id: number) => setToasts(t => t.filter(x => x.id !== id)), []);
  const toast = useCallback((t: Omit<Toast, "id">) => { const id = tid++; setToasts(x => [...x.slice(-2), { ...t, id }]); setTimeout(() => dismiss(id), 6000); }, [dismiss]);

  // one simulated network write. Scenario is one-shot: it applies to the next save, then returns to "ok".
  const write = useCallback(async (fn: (d: DB) => string | void, sideOnConflict?: (d: DB) => void): Promise<WriteResult> => {
    if (dataRef.current === "offline") return { ok: false, kind: "offline" };
    await wait(700);
    const o = outRef.current; if (o !== "ok") setOutcome("ok");
    if (o === "denied") return { ok: false, kind: "denied" };
    if (o === "fail") return { ok: false, kind: "fail" };
    if (o === "conflict") { if (sideOnConflict) commit(sideOnConflict); return { ok: false, kind: "conflict" }; }
    const box: { ref?: string } = {}; commit(d => { box.ref = fn(d) || undefined; });
    if (o === "unknown") return { ok: false, kind: "unknown", ref: box.ref };
    if (o === "duplicate") return { ok: false, kind: "duplicate", ref: box.ref };
    return { ok: true, ref: box.ref };
  }, [commit]);

  const api = useMemo<Store>(() => ({
    db, tick, toasts, outcome, setOutcome, data, setData, toast, dismiss,
    findSaved(ref) { const d = dbRef.current; const r = d.reservations.find(x => x.ref === ref); if (r) return `${r.ref} is saved · ${r.status === "checked_in" ? "checked in" : r.status} · room ${r.roomId ?? "unassigned"}`; const q = d.requests.find(x => x.ref === ref); return q ? `${q.ref} is saved · ${q.status.replace("_", " ")}` : null; },
    async createBooking(p) {
      let resId = "";
      const r = await write(d => {
        const gid = "g" + Date.now(); d.guests.push({ id: gid, name: p.name, phone: p.phone });
        resId = "w" + Date.now(); const ref = "RMY-" + d.seq++;
        d.reservations.push({ id: resId, ref, guestId: gid, typeId: p.typeId, roomId: p.roomId, arrivalDay: p.arrivalDay ?? 0, nights: p.nights, adults: p.adults, status: "confirmed", source: p.source, eta: p.eta ?? "Now", rate: typeOf(p.typeId).rate, occupants: p.occupants, payment: p.payment, audit: [{ at: now(), text: p.arrivalDay ? `${p.source} booking in ${p.roomId}` : `Walk-in booked in ${p.roomId}`, by: STAFF.reception }] });
        return ref;
      }, d => { const og = { id: "gx" + Date.now(), name: "Ifeanyi Okoro", phone: "+234 803 700 1188" }; d.guests.push(og); d.reservations.push({ id: "x" + Date.now(), ref: "RMY-" + d.seq++, guestId: og.id, typeId: p.typeId, roomId: p.roomId, arrivalDay: 0, nights: p.nights, adults: 1, status: "confirmed", source: "Phone", eta: "Now", rate: typeOf(p.typeId).rate, occupants: [], audit: [{ at: now(), text: `Booked in ${p.roomId}`, by: STAFF.reception2 }] }); });
      return { ...r, resId };
    },
    async requestBooking(p) {
      return write(d => {
        const gid = "g" + Date.now(); d.guests.push({ id: gid, name: p.name, phone: p.phone }); const ref = "RMY-" + d.seq++;
        d.reservations.push({ id: "p" + Date.now(), ref, guestId: gid, typeId: p.typeId, arrivalDay: p.arrivalDay, nights: p.nights, adults: p.adults, status: "pending", source: "Web", eta: "14:00", rate: typeOf(p.typeId).rate, note: p.note || undefined, occupants: [], payment: "none", audit: [{ at: now(), text: "Requested on the hotel website", by: "Guest" }] });
        return ref;
      });
    },
    async checkIn(resId, roomId) {
      const before = clone(dbRef.current);
      const r = await write(d => {
        const res = d.reservations.find(x => x.id === resId)!; res.status = "checked_in"; res.roomId = roomId; res.idChecked = true; res.audit.push({ at: now(), text: `Checked in to ${roomId}`, by: STAFF.reception });
        d.stays.push({ id: "s" + Date.now(), resId, roomId, guestId: res.guestId, arrivedAt: now(), departDay: res.nights, status: "in_house", amountDue: res.payment === "paid" ? 0 : res.rate * res.nights });
        return res.ref;
      }, d => { const room = d.rooms.find(x => x.id === roomId)!; room.hk = "dirty"; });
      if (r.ok) { const res = before.reservations.find(x => x.id === resId)!; const g = before.guests.find(x => x.id === res.guestId)!; toast({ title: `${g.name} checked in to ${roomId}`, body: `${res.ref} · My Stay invite sent by SMS`, tone: "ok", undo: restore(before) }); }
      return r;
    },
    async checkOut(stayId) {
      const before = clone(dbRef.current); const s = before.stays.find(x => x.id === stayId)!; const g = before.guests.find(x => x.id === s.guestId)!;
      const r = await write(d => {
        const st = d.stays.find(x => x.id === stayId)!; st.status = "checked_out"; st.amountDue = 0;
        const res = d.reservations.find(x => x.id === st.resId); if (res) { res.status = "checked_out"; res.audit.push({ at: now(), text: "Checked out", by: STAFF.reception }); }
        d.rooms.find(x => x.id === st.roomId)!.hk = "dirty";
        d.requests.forEach(q => { if (q.roomId === st.roomId && q.kind === "guest" && q.status !== "resolved" && q.status !== "cancelled") { q.status = "cancelled"; q.history.push({ at: now(), text: "Closed at checkout" }); } });
        d.requests.unshift({ id: "t-" + st.roomId + Date.now(), ref: "TCK-" + d.tk++, kind: "turnover", roomId: st.roomId, dept: "Housekeeping", title: "Departure clean", detail: "Guest checked out just now.", status: "assigned", createdAt: now(), targetMin: 180, channel: "System", assignee: STAFF.housekeeping, priority: "normal", history: [{ at: now(), text: "Created at checkout" }, { at: now(), text: `Assigned to ${STAFF.housekeeping}` }] });
        return res?.ref;
      });
      if (r.ok) toast({ title: `${g.name} checked out of ${s.roomId}`, body: `Room ${s.roomId} is now Dirty · cleaning task sent`, tone: "ok", undo: restore(before) });
      return r;
    },
    async changeRoom(stayId, toRoom, reason) {
      const before = clone(dbRef.current); const s = before.stays.find(x => x.id === stayId)!; const g = before.guests.find(x => x.id === s.guestId)!;
      const r = await write(d => {
        const st = d.stays.find(x => x.id === stayId)!; const from = st.roomId; st.roomId = toRoom;
        const res = d.reservations.find(x => x.id === st.resId); if (res) { res.roomId = toRoom; res.audit.push({ at: now(), text: `Moved ${from} → ${toRoom}: ${reason}`, by: STAFF.reception }); }
        d.rooms.find(x => x.id === from)!.hk = "dirty";
        d.requests.forEach(q => { if (q.roomId === from && q.kind === "guest" && q.status !== "resolved") q.roomId = toRoom; });
        d.requests.unshift({ id: "t-" + from + Date.now(), ref: "TCK-" + d.tk++, kind: "turnover", roomId: from, dept: "Housekeeping", title: "Departure clean", detail: `Guest moved to ${toRoom}.`, status: "assigned", createdAt: now(), targetMin: 180, channel: "System", assignee: STAFF.housekeeping, priority: "normal", history: [{ at: now(), text: "Created after room change" }] });
        return res?.ref;
      }, d => { d.rooms.find(x => x.id === toRoom)!.hk = "dirty"; });
      if (r.ok) toast({ title: `${g.name} moved ${s.roomId} → ${toRoom}`, body: `Room ${s.roomId} is now Dirty`, tone: "ok", undo: restore(before) });
      return r;
    },
    async confirm(resId, roomId) {
      const before = clone(dbRef.current); const res0 = before.reservations.find(x => x.id === resId)!; const g = before.guests.find(x => x.id === res0.guestId)!;
      const r = await write(d => { const res = d.reservations.find(x => x.id === resId)!; res.status = "confirmed"; res.roomId = roomId; res.audit.push({ at: now(), text: `Confirmed in ${roomId}`, by: STAFF.reception }); return res.ref; },
        d => { const og = { id: "gy" + Date.now(), name: "Bola Ige", phone: "+234 805 700 4410" }; d.guests.push(og); d.reservations.push({ id: "x" + Date.now(), ref: "RMY-" + d.seq++, guestId: og.id, typeId: res0.typeId, roomId, arrivalDay: res0.arrivalDay, nights: res0.nights, adults: 1, status: "confirmed", source: "Phone", eta: "17:00", rate: res0.rate, occupants: [], audit: [{ at: now(), text: `Booked in ${roomId}`, by: STAFF.reception2 }] }); });
      if (r.ok) toast({ title: `${res0.ref} confirmed in ${roomId}`, body: `${g.name} will be told via ${res0.source}`, tone: "ok", undo: restore(before) });
      return r;
    },
    async cancel(resId, reason) {
      const before = clone(dbRef.current); const res0 = before.reservations.find(x => x.id === resId)!;
      const r = await write(d => { const res = d.reservations.find(x => x.id === resId)!; res.status = "cancelled"; res.cancelReason = reason; res.audit.push({ at: now(), text: `Cancelled: ${reason}`, by: STAFF.reception }); return res.ref; });
      if (r.ok) toast({ title: `${res0.ref} cancelled`, body: res0.roomId ? `Room ${res0.roomId} released for these dates` : "No room was held", tone: "info", undo: restore(before) });
      return r;
    },
    async editBooking(resId, arrivalDay, nights, roomId) {
      const before = clone(dbRef.current); const res0 = before.reservations.find(x => x.id === resId)!;
      const r = await write(d => { const res = d.reservations.find(x => x.id === resId)!; const was = `${res.arrivalDay}/${res.nights}/${res.roomId}`; res.arrivalDay = arrivalDay; res.nights = nights; res.roomId = roomId; res.audit.push({ at: now(), text: `Dates or room changed (${was} → ${arrivalDay}/${nights}/${roomId})`, by: STAFF.reception }); return res.ref; },
        d => { const og = { id: "gz" + Date.now(), name: "Ifeanyi Okoro", phone: "+234 803 700 1188" }; d.guests.push(og); d.reservations.push({ id: "x" + Date.now(), ref: "RMY-" + d.seq++, guestId: og.id, typeId: res0.typeId, roomId, arrivalDay, nights, adults: 1, status: "confirmed", source: "Phone", eta: "17:00", rate: res0.rate, occupants: [], audit: [{ at: now(), text: `Booked in ${roomId}`, by: STAFF.reception2 }] }); });
      if (r.ok) toast({ title: `${res0.ref} updated`, body: `Room ${roomId}, ${nights} night${nights > 1 ? "s" : ""}`, tone: "ok", undo: restore(before) });
      return r;
    },
    async extend(stayId, nights) {
      const before = clone(dbRef.current);
      const r = await write(d => { const s = d.stays.find(x => x.id === stayId)!; s.departDay = Math.max(s.departDay, 0) + nights; const res = d.reservations.find(x => x.id === s.resId); if (res) { res.nights += nights; res.audit.push({ at: now(), text: `Extended ${nights} night`, by: STAFF.reception }); } return res?.ref; });
      if (r.ok) toast({ title: "Stay extended by 1 night", tone: "ok", undo: restore(before) });
      return r;
    },
    async setHK(roomId, hk, by) {
      return write(d => { d.rooms.find(x => x.id === roomId)!.hk = hk;
        if (hk !== "dirty") d.requests.forEach(q => { if (q.roomId === roomId && q.kind === "turnover" && q.status !== "resolved") { q.status = "resolved"; q.history.push({ at: now(), text: `Marked ${hk}`, by }); } }); });
    },
    async setBlock(roomId, block, by) {
      const before = clone(dbRef.current);
      const r = await write(d => { const room = d.rooms.find(x => x.id === roomId)!; const prev = room.block; room.block = block;
        if (!block) { d.requests.forEach(q => { if ((q.id === "q-" + roomId || q.id === prev?.taskId) && q.status !== "resolved") { q.status = "resolved"; q.history.push({ at: now(), text: "Repair verified. Block released", by }); } });
          if (room.hk === "dirty") d.requests.unshift({ id: "t-" + roomId + Date.now(), ref: "TCK-" + d.tk++, kind: "turnover", roomId, dept: "Housekeeping", title: "Clean after repair", detail: "Maintenance finished. Clean before the room goes back on sale.", status: "assigned", createdAt: now(), targetMin: 120, channel: "System", assignee: STAFF.housekeeping, priority: "normal", history: [{ at: now(), text: `Created when ${by.split(" ")[0]} released the room` }] }); } });
      if (r.ok) toast({ title: block ? `Room ${roomId} set to ${block.kind === "oos" ? "Out of service" : "Out of order"}` : `Room ${roomId} released`, body: block ? "It won't be offered for check-in" : "Still needs cleaning before it's ready", tone: "info", undo: restore(before) });
      return r;
    },
    async advance(reqId, to, by, note) {
      return write(d => { const q = d.requests.find(x => x.id === reqId)!; q.status = to; if (to !== "escalated" && to !== "received") q.assignee = q.assignee || by;
        const L: Record<ReqStatus, string> = { received: "Reopened", assigned: "Assigned", acknowledged: "Acknowledged", in_progress: "On the way", resolved: "Resolved", escalated: "Escalated to front desk", cancelled: "Cancelled" };
        q.history.push({ at: now(), text: L[to] + (note ? `: ${note}` : ""), by });
        if (q.kind === "turnover" && to === "resolved") d.rooms.find(x => x.id === q.roomId)!.hk = "clean";
        return q.ref; });
    },
    async route(reqId, dept, by) {
      return write(d => { const q = d.requests.find(x => x.id === reqId)!; q.dept = dept; q.status = "assigned"; q.assignee = dept === "Housekeeping" ? STAFF.housekeeping : dept === "Maintenance" ? STAFF.maintenance : undefined; if (q.title === "Unclear request") q.title = dept === "Maintenance" ? "Bathroom noise" : q.title; q.history.push({ at: now(), text: `Routed to ${dept}`, by }); return q.ref; });
    },
    async createRequest(p) {
      const tr = triage(p.text); let req: Request | undefined;
      const r = await write(d => {
        const dept = p.dept || tr.dept;
        req = { id: "q-" + Date.now(), ref: "TCK-" + d.tk++, kind: "guest", roomId: p.roomId, guestFirst: p.guestFirst, dept, title: p.title || tr.title, detail: p.text, status: dept === "Front desk" ? "received" : "assigned", createdAt: now(), targetMin: tr.targetMin, channel: p.channel, assignee: dept === "Housekeeping" ? STAFF.housekeeping : dept === "Maintenance" ? STAFF.maintenance : undefined, priority: tr.priority, history: [{ at: now(), text: `Received from ${p.channel === "Voice" ? "voice" : p.channel === "Front desk" ? "front desk" : "guest chat"}` }, ...(dept !== "Front desk" ? [{ at: now(), text: `Assigned to ${dept}` }] : [])] };
        d.requests.unshift(req); return req.ref;
      });
      return { ...r, req };
    },
    reset() { const s = seed(); dbRef.current = s; setDb(s); publish(s); setOutcome("ok"); setData("synthetic"); toast({ title: "Prototype data reset", tone: "info" }); },
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }), [db, tick, toasts, outcome, data]);
  return <Ctx.Provider value={api}>{children}</Ctx.Provider>;
}

export const resGuest = (db: DB, r: Reservation) => db.guests.find(g => g.id === r.guestId)!;
