// Client for the FastAPI backend (backend/main.py). The page calls it directly; the backend's CORS
// settings allow the Vite origin. Set VITE_API_URL in frontend/.env to point somewhere else.
export const API_URL = (import.meta.env.VITE_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

export type AgentKey = "boss" | "inventory" | "accounting" | "facilities" | "customer_service" | "human";

export type Ticket = {
  id: number;
  type: string;
  requester: string;
  subject: string;
  sku: string | null;
  size: string | null;
  qty: number | null;
  lease_id: number | null;
  invoice_id: number | null;
  status: "open" | "in_progress" | "awaiting_approval" | "needs_human" | "resolved";
  state: "open" | "resolved";
  notes: string | null;
  created_at: string;
  queued: boolean;
  running: boolean;
};

export type Approval = {
  id: number;
  ticket_id: number | null;
  kind: "payment" | "purchase_order" | "discount";
  summary: string;
  amount: number | null;
  requested_by: string;
  status: "pending" | "approved" | "rejected" | "failed";
  decided_by: string | null;
  decision_note: string | null;
  created_at: string;
};

export type Cash = {
  account: string;
  balance: number;
  as_of: string;
  pending_cash_out: number;
  cash_after_all_pending: number;
};

export type AgentEvent = {
  id: number;
  run_id: string | null;
  ticket_id: number | null;
  agent: AgentKey;
  kind: "run_started" | "tool_call" | "tool_result" | "delegate" | "reply" | "decision" | "error" | "human";
  content: Record<string, any>;
  created_at: string;
};

export type Message = {
  id: number;
  ticket_id: number | null;
  recipient: string;
  subject: string;
  body: string;
  status: "draft" | "approved" | "discarded";
};

export type Board = {
  date_today: string;
  messages: Message[];
  payments: { id: number; kind: string; ref_id: number; amount: number; paid_at: string; approved_by: string }[];
  worker: { current: number | null; queued: number[] };
};

export type Health = { mcp_ok: boolean; mcp_error: string | null; model: string; api_key_set: boolean };

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(API_URL + path, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    throw new Error(`Can't reach the backend at ${API_URL}. Is it running? (cd backend && uvicorn main:app --reload --port 8000)`);
  }
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* not JSON */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

const post = (body?: unknown): RequestInit => ({ method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });

export const api = {
  // Problem 7 routes
  tickets: () => call<Ticket[]>("/api/tickets"),
  runTicket: (id: number, note?: string) => call<{ queued: boolean }>(`/api/tickets/${id}/run`, post({ note: note || null })),
  events: (after: number, limit = 1000) => call<AgentEvent[]>(`/api/events?after=${after}&limit=${limit}`),
  decide: (id: number, decision: "approved" | "rejected") =>
    call<{ effect?: string }>(`/api/approvals/${id}`, post({ decision, note: "" })),
  cash: () => call<Cash>("/api/cash"),
  reset: () => call<{ reset: boolean }>("/api/reset", post()),
  // supporting routes
  approvals: () => call<Approval[]>("/api/approvals?status=all"),
  board: () => call<Board>("/api/board"),
  health: () => call<Health>("/api/health"),
  message: (id: number, action: "approve" | "discard", body?: string) =>
    call(`/api/messages/${id}`, post({ action, body })),
};
