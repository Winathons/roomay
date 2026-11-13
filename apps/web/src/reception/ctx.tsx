import { createContext, useContext } from "react";
export type Page = "today" | "rooms" | "reservations" | "requests" | "guests";
export type SheetState = { t: "walkin"; later?: boolean } | { t: "edit"; resId: string } | { t: "checkin"; resId: string } | { t: "checkout"; stayId: string } | { t: "move"; stayId: string } | { t: "cancel"; resId: string } | { t: "request"; roomId?: string } | null;
export type PanelState = { t: "room"; id: string } | { t: "res"; id: string } | { t: "req"; id: string } | null;
export interface RecCtx { page: Page; go: (p: Page, filter?: string) => void; filter?: string; sheet: SheetState; open: (s: SheetState) => void; panel: PanelState; show: (p: PanelState) => void; cmd: () => void }
export const Rec = createContext<RecCtx | null>(null);
export const useRec = () => { const c = useContext(Rec); if (!c) throw new Error("no rec"); return c; };
