import type { AgentEvent, AgentKey } from "./api";

// Each agent is an AIM-style "buddy": a screen name, a color, and an icon. The color and icon follow
// the agent everywhere (buddy list, transcript, crew report), so you can tell who's talking at a glance.
export type Persona = { key: AgentKey; role: string; screen: string; color: string; icon: string; away: string };

export const PERSONAS: Record<AgentKey, Persona> = {
  boss: { key: "boss", role: "Boss", screen: "HandsomeDan96", color: "#00356b", icon: "dan", away: "Running the floor. Beat Harvard." },
  inventory: { key: "inventory", role: "Inventory", screen: "StockRoom96", color: "#5b2a9e", icon: "📦", away: "Counting hoodies in the back room." },
  accounting: { key: "accounting", role: "Accounting", screen: "TheLedger96", color: "#0a6b38", icon: "🧾", away: "Every cent accounted for." },
  facilities: { key: "facilities", role: "Facilities", screen: "WrenchCrew96", color: "#b35400", icon: "🔧", away: "Keeping Chapel St. standing." },
  customer_service: { key: "customer_service", role: "Customer Service", screen: "FrontDesk96", color: "#007c89", icon: "💬", away: "Taking the heat, nicely." },
  human: { key: "human", role: "You", screen: "You", color: "#0b1a33", icon: "✍️", away: "" },
};

export const TEAM: AgentKey[] = ["boss", "inventory", "accounting", "facilities", "customer_service"];

const TOOL_VERBS: Record<string, string> = {
  get_ticket: "pulled up the ticket",
  filter_tickets: "scanned the board",
  search_database: "searched the records",
  get_shop_date: "checked today's date",
  check_stock: "checked the shelves",
  check_shortfall: "counted the shortfall",
  list_inventory: "walked the stockroom",
  plan_restock: "planned a restock",
  list_vendors: "called around to vendors",
  list_purchase_orders: "checked incoming orders",
  receive_purchase_order: "logged a delivery",
  list_stock_movements: "reconciled the counts",
  fulfill_from_stock: "pulled stock for the order",
  get_pricing: "looked up the price",
  calculate_margin: "ran the margin",
  price_for_margin: "worked out a safe price",
  get_cash_position: "checked the cash drawer",
  list_invoices: "went through the invoices",
  get_invoice: "pulled the ledger entry",
  list_payments: "checked past payments",
  request_payment: "prepared a payment for you to sign",
  request_purchase_order: "prepared a purchase order for you to sign",
  request_discount: "prepared a discount quote for you to sign",
  list_approvals: "checked what's waiting on you",
  list_leases: "opened the lease file",
  get_lease: "read the lease",
  add_ticket_note: "added a note to the ticket",
  draft_customer_message: "drafted a customer message",
};

export const toolVerb = (tool: string) => TOOL_VERBS[tool] ?? `used ${tool}`;

/** Which agents are mid-task in a run: delegated to and not yet replied. The Boss is busy while the run is. */
export function busyAgents(runEvents: AgentEvent[], running: boolean): Set<AgentKey> {
  const busy = new Set<AgentKey>();
  if (!running) return busy;
  busy.add("boss");
  const open: Partial<Record<AgentKey, number>> = {};
  for (const e of runEvents) {
    if (e.kind === "delegate") open[e.content.to as AgentKey] = (open[e.content.to as AgentKey] ?? 0) + 1;
    if (e.kind === "reply" || e.kind === "error") open[e.agent] = Math.max(0, (open[e.agent] ?? 0) - 1);
  }
  (Object.keys(open) as AgentKey[]).forEach((k) => (open[k] ?? 0) > 0 && busy.add(k));
  return busy;
}

/** Events of a ticket's most recent agent run. */
export function latestRun(events: AgentEvent[], ticketId: number): AgentEvent[] {
  let runId: string | null = null;
  for (let i = events.length - 1; i >= 0; i--) {
    const e = events[i];
    if (e.ticket_id === ticketId && e.kind === "run_started") {
      runId = e.run_id;
      break;
    }
  }
  return runId ? events.filter((e) => e.run_id === runId) : [];
}

export type CrewLine = {
  agent: AgentKey;
  tools: [string, number][];
  askedBy: AgentKey[];
  askedOthers: AgentKey[];
  made: string[];
  said: string;
};

/** A short per-agent summary of a ticket's runs, built only from their events. */
export function crewReport(run: AgentEvent[]): CrewLine[] {
  const lines = new Map<AgentKey, CrewLine>();
  const line = (a: AgentKey) => {
    if (!lines.has(a)) lines.set(a, { agent: a, tools: [], askedBy: [], askedOthers: [], made: [], said: "" });
    return lines.get(a)!;
  };
  const counts = new Map<AgentKey, Map<string, number>>();
  for (const e of run) {
    if (e.agent === "human") continue;
    if (e.kind === "tool_call") {
      const m = counts.get(e.agent) ?? new Map<string, number>();
      m.set(e.content.tool, (m.get(e.content.tool) ?? 0) + 1);
      counts.set(e.agent, m);
      line(e.agent);
    } else if (e.kind === "tool_result" && e.content.ok) {
      const r = String(e.content.result ?? "");
      const ap = r.match(/"approval_id":\s*(\d+)/);
      const msg = r.match(/"message_id":\s*(\d+)/);
      if (ap && e.content.tool.startsWith("request_")) line(e.agent).made.push(`approval #${ap[1]}`);
      if (msg) line(e.agent).made.push(`draft #${msg[1]}`);
    } else if (e.kind === "delegate") {
      const to = e.content.to as AgentKey;
      if (!line(e.agent).askedOthers.includes(to)) line(e.agent).askedOthers.push(to);
      if (!line(to).askedBy.includes(e.agent)) line(to).askedBy.push(e.agent);
    } else if (e.kind === "reply") {
      // keep the most substantive thing each agent reported across runs
      const t = String(e.content.text ?? "");
      if (t.length >= line(e.agent).said.length || !line(e.agent).said) line(e.agent).said = t;
    } else if (e.kind === "decision") {
      line("boss").said = String(e.content.decision ?? "");
    }
  }
  counts.forEach((m, a) => (line(a).tools = [...m.entries()]));
  lines.forEach((l) => (l.made = [...new Set(l.made)]));
  return TEAM.filter((a) => lines.has(a)).map((a) => lines.get(a)!);
}

export const money = (n: number | null | undefined) =>
  n == null ? "—" : n.toLocaleString("en-US", { style: "currency", currency: "USD" });

export const plain = (md: string) => md.replace(/\*\*|__|`/g, "").replace(/^#+\s*/gm, "");
