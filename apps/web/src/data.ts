// Roomay prototype — synthetic hotel data. Illustrative only, never live Workpeg records.
// Mirrors Workpeg tables: room_types, rooms, guests, reservations, stays, stay_guests, room_blocks, service requests (+ audit).

export type HK = "dirty" | "clean" | "inspected";
export type BlockKind = "oos" | "ooo"; // Out of service (urgent, no check-in) · Out of order (long-term, not for sale)
export type Dept = "Housekeeping" | "Maintenance" | "Food & drink" | "Front desk";
export type ReqStatus = "received" | "assigned" | "acknowledged" | "in_progress" | "resolved" | "escalated" | "cancelled";
export type ResStatus = "pending" | "confirmed" | "checked_in" | "checked_out" | "cancelled";
export type Channel = "Chat" | "Voice" | "WhatsApp" | "Front desk" | "Web" | "Phone" | "Email" | "Walk-in" | "System";

export interface RoomType { id: string; name: string; short: string; capacity: number; rate: number }
export interface Block { kind: BlockKind; reason: string; since: number; by: string; until?: string; taskId?: string }
export interface Room { id: string; floor: number; typeId: string; hk: HK; block?: Block; features: string[] }
export interface Guest { id: string; name: string; phone: string }
export interface Hist { at: number; text: string; by?: string }
export interface Stay { id: string; resId: string; roomId: string; guestId: string; arrivedAt: number; departDay: number; status: "in_house" | "checked_out"; amountDue: number }
export interface Reservation { id: string; ref: string; guestId: string; typeId: string; roomId?: string; arrivalDay: number; nights: number; adults: number; status: ResStatus; source: Channel; eta: string; rate: number; note?: string; occupants: string[]; idChecked?: boolean; payment?: "none" | "deposit" | "paid"; audit: Hist[]; cancelReason?: string }
export interface Request { id: string; ref: string; kind: "guest" | "turnover" | "maintenance"; roomId: string; guestFirst?: string; dept: Dept; title: string; detail: string; status: ReqStatus; createdAt: number; targetMin: number; channel: Channel; assignee?: string; priority: "normal" | "urgent"; history: Hist[] }
export interface DB { rooms: Room[]; guests: Guest[]; stays: Stay[]; reservations: Reservation[]; requests: Request[]; seq: number; tk: number }

export const HOTEL = { name: "Ikoyi Court Hotel", short: "Ikoyi Court", checkOut: "11:00", checkIn: "14:00", inspectionRequired: false };
export const STAFF = { reception: "Amaka Obi", reception2: "Tunde Bakare", housekeeping: "Halima Bello", supervisor: "Grace Etim", maintenance: "Musa Kabiru" };

export const ROOM_TYPES: RoomType[] = [
  { id: "sq", name: "Standard Queen", short: "STQ", capacity: 2, rate: 65000 },
  { id: "dd", name: "Deluxe Double", short: "DLX", capacity: 2, rate: 85000 },
  { id: "ek", name: "Executive King", short: "EXK", capacity: 2, rate: 120000 },
  { id: "fs", name: "Family Suite", short: "FST", capacity: 4, rate: 160000 },
];
export const typeOf = (id: string) => ROOM_TYPES.find(t => t.id === id)!;

// ---------- clock: scenario starts at 10:42 today, then runs in real time ----------
const LOADED = Date.now();
const BASE = (() => { const d = new Date(); d.setHours(10, 42, 0, 0); return d.getTime(); })();
export const now = () => BASE + (Date.now() - LOADED);
export const MIN = 60_000;
export const ago = (m: number) => BASE - m * MIN;
export const hhmm = (t: number) => new Date(t).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
export const day = (offset: number, style: "short" | "long" = "short") => { const d = new Date(BASE); d.setDate(d.getDate() + offset); return d.toLocaleDateString("en-GB", style === "long" ? { weekday: "long", day: "numeric", month: "long" } : { weekday: "short", day: "numeric", month: "short" }); };
export const when = (t: number) => { const d = new Date(t), b = new Date(now()); return d.toDateString() === b.toDateString() ? hhmm(t) : d.toLocaleDateString("en-GB", { weekday: "short" }) + " " + hhmm(t); };
export const naira = (n: number) => "₦" + n.toLocaleString("en-NG");
export const minsSince = (t: number) => Math.max(0, Math.floor((now() - t) / MIN));
export const dur = (m: number) => (m < 60 ? `${m} min` : `${Math.floor(m / 60)} h${m % 60 ? " " + (m % 60) + " min" : ""}`);

// ---------- seed ----------
const NAMES: [string, string][] = [
  ["Ada Okafor", "+234 803 555 0142"], ["Femi Lawal", "+234 805 210 4471"], ["Joy Okon", "+234 802 118 9034"], ["Sani Bako", "+234 809 664 2010"], ["Ibrahim Musa", "+234 806 774 1182"],
  ["Chidi Eze", "+234 803 900 2214"], ["Rasheed Ade", "+234 807 413 5560"], ["Hauwa Yusuf", "+234 810 220 3341"], ["Emeka Nwosu", "+234 813 090 7712"], ["Tolu Bello", "+234 802 771 6630"],
  ["Ngozi Adeyemi", "+234 805 330 1189"], ["Kabir Danjuma", "+234 818 442 9071"], ["Fatima Ibrahim", "+234 809 115 6620"], ["Ayo Lawson", "+234 803 662 0045"], ["Bisi Coker", "+234 806 551 2290"],
  ["Uche Obi", "+234 814 772 1093"], ["Zainab Aliyu", "+234 803 228 4450"], ["Kunle Ojo", "+234 805 901 3327"], ["Amina Garba", "+234 802 664 7788"], ["Segun Afolabi", "+234 809 330 8812"],
  ["Halima Sule", "+234 806 112 5534"], ["Tobi Adeleke", "+234 813 554 0091"], ["Grace Udo", "+234 807 228 3367"], ["Musa Garba", "+234 810 774 6620"], ["Ifeoma Nnaji", "+234 803 119 2245"],
  ["Yemi Alade", "+234 805 662 9014"], ["Kemi Adio", "+234 802 448 7710"], ["Peter Ekpo", "+234 806 404 2211"],
];
export function seed(): DB {
  const plan: [number, string[]][] = [
    [1, ["sq", "sq", "sq", "sq", "sq", "sq", "dd", "dd", "dd", "dd", "fs", "fs"]],
    [2, ["dd", "dd", "dd", "dd", "dd", "dd", "dd", "dd", "dd", "dd", "ek", "ek", "ek", "ek"]],
    [3, ["dd", "dd", "dd", "dd", "dd", "dd", "dd", "dd", "ek", "ek", "ek", "ek", "fs", "fs"]],
  ];
  const rooms: Room[] = [];
  for (const [floor, types] of plan) types.forEach((t, i) => rooms.push({ id: `${floor}${String(i + 1).padStart(2, "0")}`, floor, typeId: t, hk: "inspected", features: floor === 3 ? ["High floor"] : floor === 1 ? ["Step-free"] : ["Quiet side"] }));
  const set = (id: string, p: Partial<Room>) => Object.assign(rooms.find(r => r.id === id)!, p);
  ["206", "210", "110", "308", "305"].forEach(id => set(id, { hk: "dirty" }));
  ["208", "307", "105"].forEach(id => set(id, { hk: "clean" }));
  set("305", { block: { kind: "oos", reason: "AC leaking, water on floor", since: ago(127), by: STAFF.maintenance, taskId: "q-305" } });
  set("108", { hk: "dirty", block: { kind: "ooo", reason: "Bathroom refit", since: ago(60 * 26), by: "Hotel manager", until: "Fri" } });

  const guests: Guest[] = NAMES.map(([name, phone], i) => ({ id: "g" + i, name, phone }));
  const g = (name: string) => guests.find(x => x.name === name)!.id;
  const inHouse: [string, string, number, number][] = [
    ["204", "Ada Okafor", 2, 0], ["202", "Femi Lawal", 1, 0], ["203", "Joy Okon", 3, 85000], ["207", "Sani Bako", 2, 0], ["301", "Ibrahim Musa", -1, 170000], ["212", "Chidi Eze", 0, 0], ["209", "Rasheed Ade", 0, 42500],
    ["302", "Hauwa Yusuf", 4, 0], ["304", "Emeka Nwosu", 1, 0], ["101", "Bisi Coker", 2, 0], ["102", "Uche Obi", 0, 0], ["104", "Amina Garba", 3, 0], ["106", "Kunle Ojo", 1, 0], ["107", "Segun Afolabi", 2, 0],
    ["109", "Halima Sule", 0, 15000], ["111", "Tobi Adeleke", 5, 0], ["213", "Grace Udo", 2, 0], ["306", "Peter Ekpo", 1, 0], ["309", "Musa Garba", 3, 0], ["310", "Ifeoma Nnaji", 2, 0], ["312", "Yemi Alade", 1, 0], ["313", "Kemi Adio", 6, 0],
  ];
  const reservations: Reservation[] = [];
  const stays: Stay[] = [];
  let seq = 1030;
  inHouse.forEach(([roomId, name, depart, due], i) => {
    const room = rooms.find(r => r.id === roomId)!; const sofar = 1 + (i % 3);
    const rid = "r" + i;
    reservations.push({ id: rid, ref: "RMY-" + seq++, guestId: g(name), typeId: room.typeId, roomId, arrivalDay: -sofar, nights: Math.max(1, sofar + depart), adults: 1 + (i % 2), status: "checked_in", source: (["Web", "Phone", "WhatsApp", "Walk-in"] as Channel[])[i % 4], eta: "14:00", rate: typeOf(room.typeId).rate, occupants: i % 2 ? ["Second adult"] : [], idChecked: true, payment: due ? "deposit" : "paid", audit: [{ at: ago(60 * 24 * sofar), text: "Checked in", by: STAFF.reception }] });
    stays.push({ id: "s" + i, resId: rid, roomId, guestId: g(name), arrivedAt: ago(60 * 24 * sofar), departDay: depart, status: "in_house", amountDue: due });
  });
  const res = (p: Omit<Reservation, "ref" | "audit" | "occupants" | "rate">, audit: Hist[]) => reservations.push({ ...p, ref: "RMY-" + seq++, rate: typeOf(p.typeId).rate, occupants: [], audit });
  res({ id: "a1", guestId: g("Tolu Bello"), typeId: "dd", roomId: "210", arrivalDay: 0, nights: 2, adults: 2, status: "confirmed", source: "Phone", eta: "14:00", payment: "deposit" }, [{ at: ago(60 * 30), text: "Booked by phone, confirmed in 210", by: STAFF.reception2 }]);
  res({ id: "a2", guestId: g("Ngozi Adeyemi"), typeId: "dd", roomId: "201", arrivalDay: 0, nights: 1, adults: 1, status: "confirmed", source: "Web", eta: "15:30", payment: "none" }, [{ at: ago(60 * 50), text: "Requested online", by: "Guest" }, { at: ago(60 * 48), text: "Confirmed in 201", by: STAFF.reception }]);
  res({ id: "a3", guestId: g("Ayo Lawson"), typeId: "sq", roomId: "103", arrivalDay: 0, nights: 2, adults: 1, status: "confirmed", source: "WhatsApp", eta: "16:00", payment: "none" }, [{ at: ago(60 * 20), text: "Requested on WhatsApp", by: "Guest" }, { at: ago(60 * 19), text: "Confirmed in 103", by: STAFF.reception }]);
  res({ id: "a4", guestId: g("Kabir Danjuma"), typeId: "ek", arrivalDay: 0, nights: 3, adults: 2, status: "pending", source: "Web", eta: "18:00", note: "Quiet room please. Arriving late from Abuja.", payment: "none" }, [{ at: ago(95), text: "Requested online", by: "Guest" }]);
  res({ id: "a5", guestId: g("Fatima Ibrahim"), typeId: "fs", arrivalDay: 2, nights: 2, adults: 4, status: "pending", source: "WhatsApp", eta: "13:00", note: "Family of four. Needs a baby cot.", payment: "none" }, [{ at: ago(40), text: "Requested on WhatsApp", by: "Guest" }]);
  res({ id: "a6", guestId: g("Zainab Aliyu"), typeId: "dd", roomId: "214", arrivalDay: 0, nights: 1, adults: 2, status: "confirmed", source: "Phone", eta: "20:30", payment: "none" }, [{ at: ago(60 * 70), text: "Booked by phone, confirmed in 214", by: STAFF.reception2 }]);
  res({ id: "a7", guestId: g("Kunle Ojo"), typeId: "sq", arrivalDay: 3, nights: 1, adults: 1, status: "cancelled", source: "Web", eta: "15:00", payment: "none", cancelReason: "Guest changed travel plans" }, [{ at: ago(60 * 26), text: "Requested online", by: "Guest" }, { at: ago(60 * 5), text: "Cancelled: guest changed travel plans", by: STAFF.reception }]);

  let tk = 200;
  const T = (p: Omit<Request, "ref">): Request => ({ ...p, ref: "TCK-" + tk++ });
  const requests: Request[] = [
    T({ id: "q-204", kind: "guest", roomId: "204", guestFirst: "Ada", dept: "Housekeeping", title: "Iron and ironing board", detail: "Can I borrow an iron? I have a meeting at 2.", status: "acknowledged", createdAt: ago(18), targetMin: 15, channel: "Chat", assignee: STAFF.housekeeping, priority: "normal", history: [{ at: ago(18), text: "Received from guest chat" }, { at: ago(16), text: "Assigned to Housekeeping" }, { at: ago(11), text: "Acknowledged", by: STAFF.housekeeping }] }),
    T({ id: "q-309", kind: "guest", roomId: "309", guestFirst: "Musa", dept: "Maintenance", title: "AC not cooling", detail: "The air conditioner is blowing warm air.", status: "assigned", createdAt: ago(6), targetMin: 30, channel: "Voice", assignee: STAFF.maintenance, priority: "normal", history: [{ at: ago(6), text: "Received by voice" }, { at: ago(6), text: "Assigned to Maintenance" }] }),
    T({ id: "q-312", kind: "guest", roomId: "312", guestFirst: "Yemi", dept: "Maintenance", title: "AC rattling at night", detail: "Loud rattle from the AC unit.", status: "in_progress", createdAt: ago(52), targetMin: 60, channel: "WhatsApp", assignee: STAFF.maintenance, priority: "normal", history: [{ at: ago(52), text: "Received on WhatsApp" }, { at: ago(40), text: "Acknowledged", by: STAFF.maintenance }, { at: ago(25), text: "Work started", by: STAFF.maintenance }] }),
    T({ id: "q-305", kind: "maintenance", roomId: "305", dept: "Maintenance", title: "AC leak, room out of service", detail: "Water pooling under the split unit. Room blocked from sale.", status: "in_progress", createdAt: ago(127), targetMin: 240, channel: "System", assignee: STAFF.maintenance, priority: "urgent", history: [{ at: ago(127), text: "Reported. Room set to Out of service", by: STAFF.maintenance }, { at: ago(32), text: "Part ordered, due 16:00", by: STAFF.maintenance }] }),
    T({ id: "q-207", kind: "guest", roomId: "207", guestFirst: "Sani", dept: "Front desk", title: "Late checkout request", detail: "Can I keep the room until 2pm on my last day?", status: "received", createdAt: ago(3), targetMin: 20, channel: "Phone", priority: "normal", history: [{ at: ago(3), text: "Logged at front desk", by: STAFF.reception2 }] }),
    T({ id: "q-302", kind: "guest", roomId: "302", guestFirst: "Hauwa", dept: "Front desk", title: "Unclear request", detail: "The thing in the bathroom is making that noise again.", status: "received", createdAt: ago(9), targetMin: 10, channel: "Chat", priority: "normal", history: [{ at: ago(9), text: "Received from guest chat" }, { at: ago(9), text: "Team unclear. Sent to front desk to route." }] }),
    ...["210", "206", "110", "308"].map((id, i) => T({ id: "t-" + id, kind: "turnover", roomId: id, dept: "Housekeeping", title: "Departure clean", detail: id === "210" ? "Arrival at 14:00. Clean this room first." : "Guest checked out this morning.", status: i === 1 ? "in_progress" : "assigned", createdAt: ago(80 - i * 12), targetMin: id === "210" ? 120 : 180, channel: "System", assignee: STAFF.housekeeping, priority: id === "210" ? "urgent" : "normal", history: [{ at: ago(80 - i * 12), text: "Created at checkout" }, { at: ago(78 - i * 12), text: `Assigned to ${STAFF.housekeeping}` }] })),
    T({ id: "q-111", kind: "guest", roomId: "111", guestFirst: "Tobi", dept: "Housekeeping", title: "Extra pillows", detail: "Two firm pillows please.", status: "resolved", createdAt: ago(70), targetMin: 15, channel: "Chat", assignee: STAFF.housekeeping, priority: "normal", history: [{ at: ago(70), text: "Received from guest chat" }, { at: ago(58), text: "Delivered", by: STAFF.housekeeping }] }),
  ];
  return { rooms, guests, stays, reservations, requests, seq, tk };
}

// ---------- derived room view (occupancy, housekeeping and maintenance stay separate) ----------
export type Occ = "vacant" | "in_house" | "due_out" | "overdue" | "arriving";
export function roomView(room: Room, db: DB) {
  const stay = db.stays.find(s => s.roomId === room.id && s.status === "in_house");
  const arrival = db.reservations.find(r => r.roomId === room.id && r.arrivalDay === 0 && r.status === "confirmed");
  const occ: Occ = stay ? (stay.departDay < 0 ? "overdue" : stay.departDay === 0 ? "due_out" : "in_house") : arrival ? "arriving" : "vacant";
  const ready = !room.block && !stay && room.hk !== "dirty" && (!HOTEL.inspectionRequired || room.hk === "inspected");
  const guest = stay ? db.guests.find(x => x.id === stay.guestId) : arrival ? db.guests.find(x => x.id === arrival.guestId) : undefined;
  const open = db.requests.filter(q => q.roomId === room.id && q.kind === "guest" && isOpen(q));
  return { stay, arrival, occ, ready, guest, open };
}
export const isOpen = (q: Request) => q.status !== "resolved" && q.status !== "cancelled";
export const isLate = (q: Request) => isOpen(q) && minsSince(q.createdAt) > q.targetMin;

// rooms a reservation could go into, with plain reasons for every exclusion (Roomay Assurance)
export function eligibleRooms(db: DB, r: { id?: string; typeId: string; arrivalDay: number; nights: number; adults: number; note?: string }, readyNow: boolean) {
  const ok: { room: Room; score: number; why: string[] }[] = []; const out: { room: Room; why: string }[] = [];
  for (const room of db.rooms.filter(x => x.typeId === r.typeId)) {
    const v = roomView(room, db);
    if (room.block) { out.push({ room, why: room.block.kind === "oos" ? `Out of service: ${room.block.reason.toLowerCase()}` : `Out of order until ${room.block.until}` }); continue; }
    if (v.stay && (v.stay.departDay > r.arrivalDay || v.stay.departDay < 0)) { out.push({ room, why: v.stay.departDay < 0 ? "Guest overdue, still in room" : `Occupied until ${day(v.stay.departDay)}` }); continue; }
    const clash = db.reservations.find(x => x.id !== r.id && x.roomId === room.id && (x.status === "confirmed" || x.status === "pending") && x.arrivalDay < r.arrivalDay + r.nights && r.arrivalDay < x.arrivalDay + x.nights);
    if (clash) { out.push({ room, why: `Reserved ${clash.arrivalDay === 0 ? "today" : day(clash.arrivalDay)} for another guest` }); continue; }
    if (readyNow && (room.hk === "dirty" || v.stay)) { out.push({ room, why: v.stay ? "Guest leaving today, not cleaned yet" : "Not cleaned yet" }); continue; }
    const why: string[] = []; let score = 0;
    if (room.hk === "inspected") { why.push("Inspected"); score += 2; } else if (room.hk === "clean") { why.push("Clean"); score += 1; } else { why.push("Needs cleaning before arrival"); score -= 1; }
    if (v.open.length) { why.push(`Open issue: ${v.open[0].title}`); score -= 3; }
    if (/quiet/i.test(r.note || "") && room.features.includes("Quiet side")) { why.push("Quiet side"); score += 2; }
    if (db.requests.some(q => q.roomId.startsWith(String(room.floor)) && isOpen(q) && /AC/.test(q.title)) && room.floor === 3) { why.push("Floor has open AC issues"); score -= 1; }
    ok.push({ room, score, why });
  }
  ok.sort((a, b) => b.score - a.score || a.room.id.localeCompare(b.room.id));
  return { ok, out };
}

// ---------- Roomay triage (prototype rules; production uses Workpeg AI + human confirmation) ----------
export interface Triage { dept: Dept; title: string; priority: "normal" | "urgent"; targetMin: number; confident: boolean; sensitive?: "safety" | "payment" | "privacy" }
export function triage(text: string): Triage {
  const t = text.toLowerCase();
  if (/(fire|smoke|gas|spark|flood|blood|injur|faint|unconscious|emergency)/.test(t)) return { dept: "Front desk", title: "Urgent safety issue", priority: "urgent", targetMin: 2, confident: true, sensitive: "safety" };
  if (/(refund|charge|bill|pay|card|money|discount)/.test(t)) return { dept: "Front desk", title: "Billing question", priority: "normal", targetMin: 15, confident: true, sensitive: "payment" };
  if (/(who is in|another room|room \d{3}.*guest)/.test(t)) return { dept: "Front desk", title: "Question about another room", priority: "normal", targetMin: 15, confident: true, sensitive: "privacy" };
  if (/(towel|pillow|blanket|sheet|soap|toilet paper|tissue|clean my|bath mat|toiletr|slipper|iron)/.test(t)) {
    const what = /towel/.test(t) ? "Extra towels" : /pillow/.test(t) ? "Extra pillows" : /iron/.test(t) ? "Iron and ironing board" : /clean/.test(t) ? "Room cleaning" : /blanket|sheet/.test(t) ? "Extra bedding" : "Toiletries";
    return { dept: "Housekeeping", title: what, priority: "normal", targetMin: 15, confident: true };
  }
  if (/(\bac\b|air ?con|aircon|cool|too hot|heat|light|bulb|\btv\b|remote|shower|tap|leak|wifi|wi-fi|socket|power|door|key ?card|toilet)/.test(t)) {
    const what = /(\bac\b|air|cool|heat|hot)/.test(t) ? "AC problem" : /(shower|tap|leak|toilet)/.test(t) ? "Plumbing problem" : /(wifi|wi-fi)/.test(t) ? "Wi-Fi not working" : /(light|bulb|power|socket)/.test(t) ? "Electrical problem" : /(\btv\b|remote)/.test(t) ? "TV not working" : "Door or key card problem";
    return { dept: "Maintenance", title: what, priority: /leak/.test(t) ? "urgent" : "normal", targetMin: /leak/.test(t) ? 15 : 30, confident: true };
  }
  if (/(food|breakfast|lunch|dinner|eat|drink|tea|coffee|menu|jollof|suya|bottle|water)/.test(t)) return { dept: "Food & drink", title: /water/.test(t) ? "Drinking water" : "Food or drink order", priority: "normal", targetMin: 25, confident: true };
  if (/(checkout|check out|late|extend|taxi|airport|wake|person|reception|human|someone)/.test(t)) return { dept: "Front desk", title: /late|checkout|check out/.test(t) ? "Late checkout request" : /taxi|airport/.test(t) ? "Transport request" : "Wants to speak to someone", priority: "normal", targetMin: 10, confident: true };
  return { dept: "Front desk", title: "Unclear request", priority: "normal", targetMin: 10, confident: false };
}
