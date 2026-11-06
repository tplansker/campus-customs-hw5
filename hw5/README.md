# Campus Customs — multi-agent shop operations (HW5)

An agent team runs the Campus Customs shop. Open tickets (a customer order, a rent notice, a bulk
discount request) land on a board. A Boss agent triages each one and delegates to its specialists, and
any agent can delegate to any other. Money moves and discounts wait for a human to approve them on
the dashboard.

```
React board (5173) ──HTTP──► FastAPI backend + agent team (8000) ──MCP──► MCP server (8001) ──► data/campus_customs_new.db
```

| Piece | Folder | What it does |
|---|---|---|
| MCP server | `mcp_server/` | 31 FastMCP tools over the shop database. Agents only reach the data through these tools. See `mcp_server/README.md`. |
| Backend | `backend/` | FastAPI (`main.py`) plus the PydanticAI agent team. `agents/` has one file per agent and the loop, `prompts/` has one prompt per agent, and `models.py` has the data types. |
| React board | `frontend/` | Vite + React + TypeScript dashboard. It calls the backend at `VITE_API_URL` (default `http://localhost:8000`). |
| Shared | `shared/db.py` | Finds the working database (`CAMPUS_DB_PATH`) for both processes. |
| Evidence | `output/` | `harness.md`, `mcp_smoke.json`, `desk_tickets.html`, `design.md`, `resolved_tickets.json`, `resolved_board.html`, `audit_trail.json`, `github_url.txt`. |

Every agent uses one model, **`gpt-6-luna`, called through Portkey** with `PORTKEY_API_KEY`.

## Databases (both are in this repo)

| File | Role |
|---|---|
| `data/campus_customs.db` | The **original** shop data. Nothing writes to it; it's the clean starting point. |
| `data/campus_customs_new.db` | The **working copy**. The MCP server and backend read and write only this file (`CAMPUS_DB_PATH`). It's committed in the state the Problem 9 run left it: all three tickets resolved, checking at $152.00. |

The code refuses to start if `CAMPUS_DB_PATH` points at the original.

## Setup (once)

Run these from this `hw5/` folder:

```bash
cp .env.example .env
```
Open `.env` and set `PORTKEY_API_KEY`. The real `.env` is in `.gitignore` and must never be committed.

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```
```bash
npm --prefix frontend install
```

## Run it

Use three terminals, all starting in this `hw5/` folder. Start them in this order.

### 1. Copy the original database to the working copy (when you need a clean run)

```bash
cp data/campus_customs.db data/campus_customs_new.db && chmod u+w data/campus_customs_new.db
```

`./reset_db.sh` does the same thing. Skip this step if you want to keep the current state, for
example to look at the finished Problem 9 run.

### 2. Start the MCP server

```bash
.venv/bin/python -m mcp_server.server
```

It serves the tools at `http://127.0.0.1:8001/mcp`. Leave it running. (`.mcp.json` lets a vibe coder
such as Claude Code start its own copy over stdio.)

### 3. Start the FastAPI backend

```bash
cd backend && ../.venv/bin/uvicorn main:app --reload --port 8000
```

The API is at `http://localhost:8000`, with interactive docs at `/docs`. If another app is already
using port 8000, stop it first.

### 4. Start the React board

```bash
cd frontend && npm run dev
```

Open the address Vite prints, usually `http://localhost:5173`. It moves to 5174 or higher if 5173 is busy.

### 5. Reset the database before a full three-ticket run

Always start a full run of tickets 101, 102 and 103 from the original data. Click **↺ Fresh start** in
the board's toolbar, or call the reset route:

```bash
curl -X POST http://localhost:8000/api/reset
```

Either one copies `campus_customs.db` over `campus_customs_new.db` (step 1), and checking goes back
to **$3,400.00**. Reset is refused while the agents are working. Then work the tickets:

1. Pick a ticket in the **Inbox** and click **Send to the crew ➤**. You can add a note for the Boss.
2. Watch the **Buddy List** and the **Instant Messages** transcript as agents delegate and use tools.
3. Approve or reject each payment, purchase order or discount under **Sign Here**. Approving is the
   only thing that moves cash, and the **Cash Register** drops when you do.
4. When all of a ticket's requests are decided, the Boss gets a follow-up run. The ticket is stamped
   **RESOLVED** when it's done, and the **Crew report** summarizes what each agent did.

`./start.sh` starts the MCP server, backend and board together. Ctrl-C stops all three.

## The team

| Agent | Role-specific MCP tools | Job |
|---|---|---|
| **Boss** | list_approvals, get_cash_position, list_vendors, add_ticket_note | Triages, routes work to specialists, weighs cash, and makes the final call (`resolved` / `awaiting_approval` / `needs_human`). |
| **Inventory** | check_stock, list_inventory, check_shortfall, plan_restock, fulfill_from_stock, receive_purchase_order, list_stock_movements, list_vendors, get_pricing, list_purchase_orders | Stock by SKU and size, shortfalls, restock vendors. |
| **Accounting** | get_cash_position, list_invoices, get_invoice, list_payments, get_pricing, calculate_margin, price_for_margin, plan_restock, list_vendors, request_payment, request_purchase_order, request_discount, list_approvals, list_purchase_orders | Cash, invoices and margins. Prepares payments, POs and quotes **for human approval**. |
| **Facilities** | list_leases, get_lease, get_cash_position, add_ticket_note | The physical shop, including the lease and rent. Hands costs to Accounting. |
| **Customer Service** | draft_customer_message, list_approvals | Drafts customer replies from teammates' facts. It has no stock, pricing or cash access. |

Every agent also gets `get_shop_date`, `get_ticket`, `filter_tickets`, `search_database` and
`delegate(to, task)`, which can reach any teammate. Limits on each run:
- delegation depth 3 and 16 delegations per ticket
- 20 model requests, 30 tool calls and 150k tokens per agent run, and 400k tokens per ticket

Every step is appended to `output/audit_trail.json`.

## Shop rules (enforced in the MCP server, not just the prompts)

| Rule | How it's enforced |
|---|---|
| `desk.date_today` (2026-08-31) is "today". | Overdue flags and all payment and PO dates use it. |
| Every payment needs human approval. | Agents only *request*. The backend-only `execute_approval` pays, and only when you click Approve. |
| A vendor won't ship while it has an unpaid invoice. | `request_purchase_order` refuses, and approval re-checks. |
| Not enough cash means the payment is refused. | Checked when a request is made and again at approval. A SQLite trigger blocks negative balances. |
| No revenue is modeled, so cash only goes down. | A second trigger blocks any balance increase. |
| Bills are paid from their own ticket, once. | Invoice 501 can only be requested from ticket 101, and duplicate pending payments are refused. |
| Never email customers or vendors. | There's no send tool. Drafts that reveal internal details (vendors, invoices, costs, margins, cash) are refused. |

More detail is in `output/harness.md`: tables, every tool, routes, the agent loop and the safety rules.

## API

`GET /api/tickets` · `POST /api/tickets/{id}/run {note?}` · `GET /api/events?after=N` ·
`POST /api/approvals/{id} {decision: approved|rejected}` · `GET /api/cash` · `POST /api/reset` ·
`GET /api/approvals` · `GET /api/board` · `POST /api/run-open` · `POST /api/reset-and-run` ·
`POST /api/messages/{id} {action: approve|discard, body?}` · `GET /api/health`
