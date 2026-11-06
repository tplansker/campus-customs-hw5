# Campus Customs — multi-agent shop operations

An agent team runs the Campus Customs shop. Open tickets (customer orders, rent notices, unpaid
bills, discount requests) land on a board. A Boss agent triages each one and delegates to its
specialists, and any agent can delegate to any other. Money moves and discounts wait for a human
to approve them on the dashboard.

```
React dashboard (5173) ──/api──► FastAPI backend + agent team (8000) ──MCP──► MCP server (8001) ──► data/campus_customs_new.db
```

| Piece | Folder | What it does |
|---|---|---|
| MCP server | `mcp_server/server.py` | 31 FastMCP tools over the shop DB: tickets, stock, vendors, pricing/margins, cash, invoices, purchase orders, leases, approvals, customer drafts. Agents only reach the database through these tools. |
| Backend | `backend/` | FastAPI + PydanticAI. `agents/` holds one file per agent plus the team loop, `prompts/` holds one prompt file per agent, and `models.py` holds the data types. `main.py` runs tickets one at a time in a background worker and exposes the board, the event feed, approvals, messages and reset. |
| Dashboard | `frontend/` | Vite + React + TypeScript: the "Back Office" desk. Ticket inbox, live AIM-style agent transcript, buddy list, crew report, cash register and Sign Here approvals. It calls the backend at `VITE_API_URL` (default `http://localhost:8000`). Design notes are in `output/design.md`. |
| Shared | `shared/db.py` | Resolves `CAMPUS_DB_PATH` for both processes and adds the extra tables (approvals, messages, events, runs). |

## The team

| Agent | Tools (via MCP) | Typical job |
|---|---|---|
| **boss** | list_approvals, get_cash_position, list_vendors, add_ticket_note (every agent also gets get_ticket, filter_tickets, search_database, get_shop_date) | Reads the ticket, delegates, weighs cash, and returns a structured final call (`resolved` / `awaiting_approval` / `needs_human`). |
| **inventory** | check_stock, list_inventory, check_shortfall, fulfill_from_stock, list_vendors, get_pricing | Stock by SKU/size, shortfalls, which vendor restocks. |
| **accounting** | get_cash_position, list_invoices, list_payments, calculate_margin, request_payment, request_purchase_order, request_discount, … | Cash, invoices, margins; prepares payments, POs and discount quotes **for approval**. |
| **facilities** | list_leases, get_lease, get_cash_position, add_ticket_note | Leases and rent; hands rent payments to accounting. |
| **customer_service** | draft_customer_message, check_stock, get_pricing, list_approvals | Drafts messages to requesters for a human to send. |

**Full connectivity:** every agent has a `delegate(to, task)` tool that can reach any teammate,
including the boss. Two limits stop loops: a chain can be at most 3 hops deep, and a ticket run can
use at most 16 delegations.

**Human in the loop:** `request_*` tools only create a *pending approval*. The `execute_approval`
tool is filtered out of every agent's toolset. Only the backend calls it, and only when you click
Approve. On approval:
- an invoice payment deducts cash, adds a row to `payments`, and marks the invoice `paid`
- a rent payment deducts cash, adds a row to `payments`, and moves `leases.next_due` forward one month
- a purchase order is paid up front: it deducts cash, adds a `payments` row (kind `purchase_order`),
  and adds a `purchase_orders` row with the ETA (shop date + vendor lead days)
- a discount locks in the quote (no cash moves)

Once you have decided every approval on a ticket, the ticket goes back to the boss for a follow-up
run. That's how "invoice paid → vendor can ship → request the PO" happens.

## Shop rules (enforced in the MCP server, not just the prompts)

| Rule | Where it's enforced |
|---|---|
| `desk.date_today` is "today". Overdue means the due date is before it. | `get_shop_date`, and the `overdue` / `days_overdue` fields on every invoice. Payment and PO dates use the shop date. |
| Every payment needs human approval. | Agents only have `request_*`. `execute_approval` is hidden from them. |
| A vendor won't ship while it has an open unpaid invoice. | `list_vendors` shows `can_ship`. `request_purchase_order` refuses, and `execute_approval` re-checks before paying a PO. |
| Not enough cash means the payment is refused. No negative balances. | Checked when a request is made and again at approval. A SQLite trigger also aborts any negative balance. |
| No revenue is modeled, so cash only goes out. | Nothing adds cash. A second trigger aborts any balance increase. |
| Never email customers or vendors. | There's no send tool. Drafts stay on the board, and **Approve draft** only marks them approved. |

## Shop data at the start (shop date 2026-08-31)

- Cash is $3,400.
- Invoice 501 from Bulldog Print Co is $840 and 3 days overdue, which blocks any new orders from that vendor.
- Rent of $2,400 is due 9/2.
- Paying the invoice and the rent comes to $3,240, which leaves $160 for any restock.

Every tool call, delegation, reply and decision is logged to `agent_events` and streams to the dashboard.

## Databases

- `data/campus_customs.db` is the **original**. It's read-only and nothing writes to it.
- `data/campus_customs_new.db` is the **working copy**. `CAMPUS_DB_PATH` points both the MCP server
  and the backend here, and the code refuses to start if it points at the original.
- To start over, click **Reset data** in the dashboard or run `./reset_db.sh`. For a full run, use
  **Reset & run all**, which always restores the original values before the agents start.

## Setup (once)

The database files aren't in git. Unzip the course `data.zip` into this folder so you have
`data/campus_customs.db`, then make the working copy with `./reset_db.sh`.

```bash
cp .env.example .env        # add PORTKEY_API_KEY (a parent-folder .env also works)
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
npm --prefix frontend install
```

Every agent (boss and all four specialists) uses one model, `gpt-6-luna`, called through Portkey
(`https://api.portkey.ai/v1`) with `PORTKEY_API_KEY`. The model name is set once, by `OPENAI_MODEL`.

`requirements.txt` uses `pydantic-ai-slim[openai,mcp]`. The `mcp` extra is a deliberate exception
to the slim-only rule because the agents need it to call the MCP server.

## Run

```bash
./start.sh
```

Then open http://localhost:5173 (Vite prints the port; it moves to 5174+ if 5173 is busy). Ctrl-C stops all three processes. You can also start them separately
from the HW5 folder:

```bash
.venv/bin/python -m mcp_server.server                 # MCP on :8001/mcp
cd backend && ../.venv/bin/uvicorn main:app --reload --port 8000   # backend (from backend/)
cd frontend && npm run dev                            # dashboard (calls http://localhost:8000)
```

The backend runs on port 8000. If another app (for example the Lecture 10 backend) is already using 8000, stop it first.

## Using it

1. Click **Reset & run all** for a full run from the original data, or **Run agents** on a single
   ticket. Use **+ note** to give the boss guidance.
2. Watch the team strip and the **Live activity** feed: tool calls, delegations (`Boss → Accounting`),
   replies, and the boss's final call.
3. Approve or reject requests in **Approvals**. Each card shows the cash that would remain, or says it
   will be refused. When a ticket's requests are all decided, the boss gets a follow-up run, which may
   queue the next step or close the ticket.
4. Review and edit the customer drafts, then click **Approve draft** or **Discard**. Nothing is ever emailed.

## API

The routes are listed with one line each in `output/harness.md` (Backend Routes), and interactive
docs are at http://localhost:8000/docs.

`GET /api/tickets` · `POST /api/tickets/{id}/run {note?}` · `GET /api/events?after=N` ·
`POST /api/approvals/{id} {decision: approved|rejected}` · `GET /api/cash` · `POST /api/reset` ·
`GET /api/approvals` · `GET /api/board` · `POST /api/run-open` · `POST /api/reset-and-run` ·
`POST /api/messages/{id} {action: approve|discard, body?}` · `GET /api/health`
