// Client for the FastAPI backend (backend/main.py).
// - `npm run dev`: calls http://localhost:8000 directly (the backend's CORS allows the Vite origin).
// - built for hosting (`npm run build`): the backend serves this page, so it calls /api on its own site.
// Set VITE_API_URL to point somewhere else.
export const API_URL = (import.meta.env.VITE_API_URL ?? (import.meta.env.DEV ? "http://localhost:8000" : "")).replace(/\/$/, "");

// The hosted desk asks for a password (DESK_PASSWORD on the server). It's kept for this browser
// session only and sent with every API call.
const PW_KEY = "cc-desk-password";
export const deskPassword = {
  get: () => { try { return sessionStorage.getItem(PW_KEY) ?? ""; } catch { return ""; } },
  set: (v: string) => { try { sessionStorage.setItem(PW_KEY, v); } catch { /* storage blocked */ } },
  clear: () => { try { sessionStorage.removeItem(PW_KEY); } catch { /* storage blocked */ } },
};

/** Thrown when the server wants the desk password (HTTP 401). */
export class AuthError extends Error {}

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

export type Health = { mcp_ok: boolean; mcp_error?: string | null; model: string; api_key_set: boolean; auth_required?: boolean };

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(API_URL + path, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(deskPassword.get() ? { "X-Desk-Password": deskPassword.get() } : {}),
        ...(init?.headers ?? {}),
      },
    });
  } catch {
    throw new Error(API_URL
      ? `Can't reach the backend at ${API_URL}. Is it running? (cd backend && uvicorn main:app --reload --port 8000)`
      : "Can't reach the desk's server. It may be waking up; try again in a minute.");
  }
  if (res.status === 401) throw new AuthError("Desk password required.");
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
