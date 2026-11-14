export type Department = "Housekeeping" | "Maintenance" | "Food & drink" | "Front desk";
export interface Triage { dept: Department; title: string; priority: "normal" | "urgent"; targetMin: number; confident: boolean; sensitive?: "safety" | "payment" | "privacy" }

// Deterministic demonstration rules; this is not WorkPeg AI or an operational routing system.
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
