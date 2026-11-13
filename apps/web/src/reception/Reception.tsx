import { useCallback, useEffect, useMemo, useState } from "react";
import { IconAlertTriangle, IconBed, IconBuildingCommunity, IconCalendarEvent, IconChevronDown, IconClock, IconHelpCircle, IconLayoutDashboard, IconLock, IconLogin, IconMessageCircle, IconRefresh, IconSearch, IconUsers, IconWifiOff } from "@tabler/icons-react";
import { useStore } from "../store";
import { HOTEL, STAFF, day, hhmm, now, isOpen, isLate } from "../data";
import { Avatar, Empty } from "../ui";
import { Rec, type Page, type SheetState, type PanelState } from "./ctx";
import { Today } from "./Today";
import { Rooms } from "./Rooms";
import { Reservations } from "./Reservations";
import { Requests } from "./Requests";
import { Guests } from "./Guests";
import { Panel } from "./Panel";
import { Sheets } from "./Sheets";
import { CommandMenu } from "./Command";

const NAV: { id: Page; label: string; icon: typeof IconBed }[] = [
  { id: "today", label: "Today", icon: IconLayoutDashboard }, { id: "rooms", label: "Rooms", icon: IconBed },
  { id: "reservations", label: "Reservations", icon: IconCalendarEvent }, { id: "requests", label: "Requests", icon: IconMessageCircle }, { id: "guests", label: "Guests", icon: IconUsers },
];

export function Reception({ page: initial }: { page: Page }) {
  const { db, data, setData } = useStore();
  const [page, setPage] = useState<Page>(initial);
  const [filter, setFilter] = useState<string | undefined>();
  const [sheet, open] = useState<SheetState>(null);
  const [panel, show] = useState<PanelState>(null);
  const [cmd, setCmd] = useState(false);
  useEffect(() => { setPage(initial); show(null); }, [initial]);
  useEffect(() => { document.querySelector(".scroll")?.scrollTo({ top: 0 }); }, [page]);
  const go = useCallback((p: Page, f?: string) => { setFilter(f); show(null); setPage(p); if (window.location.hash !== `#/reception/${p}`) window.location.hash = `#/reception/${p}`; }, []);

  useEffect(() => {
    const k = (e: KeyboardEvent) => {
      const typing = (e.target as HTMLElement)?.closest("input, textarea, select");
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setCmd(v => !v); }
      else if (!typing && e.key === "/") { e.preventDefault(); setCmd(true); }
      else if (!typing && !sheet && !cmd && e.key.toLowerCase() === "n" && !e.metaKey && !e.ctrlKey) open({ t: "walkin" });
      else if (e.key === "Escape" && panel && !sheet && !cmd) show(null);
    };
    window.addEventListener("keydown", k); return () => window.removeEventListener("keydown", k);
  }, [sheet, panel, cmd]);

  const counts = useMemo(() => ({ reservations: db.reservations.filter(r => r.status === "pending").length, requests: db.requests.filter(q => q.kind !== "turnover" && isOpen(q)).length, late: db.requests.some(q => q.kind !== "turnover" && isLate(q)) }), [db]);
  const ctx = { page, go, filter, sheet, open, panel, show, cmd: () => setCmd(true) };
  const title = NAV.find(n => n.id === page)!.label;
  const blocked = data === "loading" || data === "empty" || data === "401" || data === "403" || data === "400" || data === "timeout";

  return (
    <Rec.Provider value={ctx}>
      <div className="shell">
        <aside className="side" aria-label="Main">
          <div className="side-brand"><span className="mark">R</span><span className="wordmark">ROOMAY</span></div>
          <button className="prop" aria-label="Switch property"><Avatar name="Ikoyi Court" size={26} /><span className="prop-txt" style={{ flex: 1, minWidth: 0 }}><b className="ellipsis">{HOTEL.name}</b><span style={{ fontSize: 12, color: "#8C94A3" }}>Front desk</span></span><IconChevronDown className="prop-txt" size={15} /></button>
          <nav className="nav">{NAV.map(n => { const c = n.id === "reservations" ? counts.reservations : n.id === "requests" ? counts.requests : 0; return (
            <button key={n.id} className={`nav-i${page === n.id ? " on" : ""}`} aria-current={page === n.id ? "page" : undefined} onClick={() => go(n.id)}><n.icon /><span className="nav-t">{n.label}</span>{c > 0 && !blocked && <span className={`n${n.id === "requests" && counts.late ? " alert" : ""}`}>{c}</span>}</button>); })}</nav>
          <div className="nav-sec">Help</div>
          <nav className="nav" style={{ paddingTop: 0 }}><button className="nav-i" onClick={() => { localStorage.removeItem("roomay-hints"); go("today"); }}><IconHelpCircle /><span className="nav-t">Getting started</span></button></nav>
          <div className="side-foot"><Avatar name={STAFF.reception} /><span className="me-txt" style={{ minWidth: 0 }}><span style={{ display: "block", color: "#fff", fontSize: 13, fontWeight: 500 }}>{STAFF.reception}</span><span style={{ fontSize: 12, color: "#8C94A3" }}>Receptionist</span></span></div>
        </aside>

        <div className="work">
          <header className="top">
            <h1 className="h-page" style={{ fontSize: 18 }}>{title}</h1>
            <span className="muted hide-sm num" style={{ fontSize: 13 }}>{page === "today" ? hhmm(now()) : `${day(0)} · ${hhmm(now())}`}</span>
            <span style={{ flex: 1 }} />
            <button className="search" onClick={() => setCmd(true)} aria-label="Search guests, rooms and actions"><IconSearch /><span>Search guests, rooms, actions</span><span className="kbd">/</span></button>
            {data === "403" || data === "401" || data === "400" || data === "timeout" ? <span className="source err"><i /><span>Not connected</span></span>
              : data === "offline" ? <span className="source"><IconWifiOff size={14} /><span>Offline · last data {hhmm(now() - 4 * 60000)}</span></span>
              : data === "stale" ? <span className="source"><IconClock size={14} /><span>Last updated {hhmm(now() - 30 * 60000)}</span></span>
              : <span className="source" title="This prototype uses invented records. It is not connected to a live Workpeg business."><i /><span>Synthetic preview · not live data</span></span>}
          </header>
          {data === "offline" && <div className="alert neutral" style={{ borderRadius: 0, borderWidth: "0 0 1px 0" }}><IconWifiOff /><div style={{ flex: 1 }}><b>You're offline.</b> You can still look things up. Check-ins, check-outs and other changes are paused until the connection is back. Nothing is queued.</div><button className="btn secondary sm" onClick={() => setData("synthetic")}><IconRefresh />Retry</button></div>}
          {data === "stale" && <div className="alert warn" style={{ borderRadius: 0, borderWidth: "0 0 1px 0" }}><IconClock /><div style={{ flex: 1 }}><b>This may be out of date.</b> Roomay couldn't refresh for 30 minutes (last update {hhmm(now() - 30 * 60000)}). Check a room before giving it to a guest.</div><button className="btn secondary sm" onClick={() => setData("synthetic")}><IconRefresh />Refresh</button></div>}
          {data === "partial" && <div className="alert warn" style={{ borderRadius: 0, borderWidth: "0 0 1px 0" }}><IconAlertTriangle /><div style={{ flex: 1 }}><b>Some information didn't load.</b> Rooms and stays are up to date, but guest requests timed out. Request counts below may be incomplete.</div><button className="btn secondary sm" onClick={() => setData("synthetic")}><IconRefresh />Retry requests</button></div>}
          <div className="body">
            <div className="scroll">
              {blocked ? <DataState /> : <>
                {page === "today" && <Today />}{page === "rooms" && <Rooms />}{page === "reservations" && <Reservations />}{page === "requests" && <Requests />}{page === "guests" && <Guests />}
              </>}
            </div>
            {!blocked && <Panel />}
          </div>
        </div>
      </div>
      <nav className="mnav" aria-label="Main">{NAV.map(n => { const c = n.id === "requests" ? counts.requests : n.id === "reservations" ? counts.reservations : 0; return <button key={n.id} className={page === n.id ? "on" : ""} onClick={() => go(n.id)} aria-current={page === n.id ? "page" : undefined}><n.icon />{n.label === "Reservations" ? "Bookings" : n.label}{c > 0 && !blocked && <span className="n">{c}</span>}</button>; })}</nav>
      {!blocked && <Sheets />}
      {cmd && <CommandMenu onClose={() => setCmd(false)} />}
    </Rec.Provider>
  );
}

// truthful app states (WOR-37 / WOR-45 / lead review): nothing is rendered as data unless data loaded
function DataState() {
  const { data, setData } = useStore();
  if (data === "loading") return <div className="page" aria-busy="true" aria-label="Loading">
    <div className="kpis">{Array.from({ length: 8 }, (_, i) => <div className="kpi" key={i}><div className="skel" style={{ height: 12, width: "60%" }} /><div className="skel" style={{ height: 22, width: 40, marginTop: 8 }} /><div className="skel" style={{ height: 10, width: "70%", marginTop: 8 }} /></div>)}</div>
    <div className="box" style={{ marginTop: 16 }}>{Array.from({ length: 6 }, (_, i) => <div key={i} style={{ display: "flex", gap: 16, padding: "14px 16px", borderTop: i ? "1px solid var(--line)" : 0 }}><div className="skel" style={{ height: 14, width: 160 }} /><div className="skel" style={{ height: 14, width: 60 }} /><div className="skel" style={{ height: 14, flex: 1 }} /></div>)}</div>
    <p className="cap" style={{ marginTop: 12 }}>Loading rooms and stays from Workpeg… Counts stay hidden until they arrive, so nothing shows as 0 by mistake.</p></div>;
  if (data === "empty") return <Empty icon={<IconBuildingCommunity />} title="No rooms set up yet" body="Roomay needs your room types and rooms before you can take walk-ins or bookings. A manager sets this up once, in about 10 minutes." action={<div style={{ display: "flex", gap: 8 }}><button className="btn secondary">Ask a manager to set up</button><button className="btn primary" disabled title="Only managers can add rooms">Add room types</button></div>} />;
  if (data === "401") return <Empty icon={<IconLogin />} title="You've been signed out" body="Your Workpeg session ended. Sign in again to continue. You'll come back to this page." action={<button className="btn primary" onClick={() => setData("synthetic")}>Sign in with Workpeg</button>} />;
  if (data === "400") return <Empty icon={<IconBuildingCommunity />} title="Workpeg doesn't recognise this hotel" body="The request was rejected (400 · unknown namespace). You may have the wrong business selected. Nothing was changed." action={<div style={{ display: "flex", gap: 8, alignItems: "center" }}><button className="btn secondary">Switch hotel</button><button className="btn primary" onClick={() => setData("synthetic")}><IconRefresh />Try again</button><span className="cap mono">Ref 400-unknown-namespace</span></div>} />;
  if (data === "timeout") return <Empty icon={<IconClock />} title="Workpeg is taking too long" body="The request timed out after 20 seconds. The connection may be slow. Nothing was changed, and no counts are shown until data arrives." action={<button className="btn primary" onClick={() => setData("synthetic")}><IconRefresh />Try again</button>} />;
  return <Empty icon={<IconLock />} title="Roomay can't reach this hotel's records" body="Workpeg refused the request (403 · dev-origin-refused, reason: closed). No hotel data is shown. Nothing was changed. This needs a fix on the Workpeg side; your team lead has the details." action={<div style={{ display: "flex", gap: 8, alignItems: "center" }}><button className="btn secondary" onClick={() => setData("synthetic")}><IconRefresh />Try again</button><span className="cap mono">Ref 403-dev-origin-refused</span></div>} />;
}
