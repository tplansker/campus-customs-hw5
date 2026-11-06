# Campus Customs Agent Harness

This file describes how the Campus Customs agent team is wired: the data it works on, the tools it
uses, and the rules it follows. Later sections are added as the project grows.

## Database

The agents work on `data/campus_customs_new.db`, a working copy of the original
`data/campus_customs.db`. Nothing writes to the original. Resetting copies it back over the working
copy, so the tickets can be worked again from the starting state.

### Tables in the original data

| Table | Fields | Why it matters for the agents |
|---|---|---|
| `desk` | `date_today`, `notes` | It's the shop's "today" (2026-08-31). Every agent judges overdue and due-soon against this date, never the real calendar. |
| `tickets` | `id`, `type`, `requester`, `subject`, `sku`, `size`, `qty`, `lease_id` → leases, `invoice_id` → invoices, `status`, `notes`, `created_at` | These are the work queue. The Boss reads each ticket, and its links tell the Boss which specialists to involve. |
| `inventory` | `sku`, `size`, `qty`, `name`, `location` (primary key `sku` + `size`) | Inventory checks stock for each SKU and size here, finds shortfalls, and pulls stock for orders. |
| `pricing` | `sku`, `unit_cost`, `list_price` | Accounting uses it to work out margins and keep discounts above cost. Inventory and Accounting use `unit_cost` to price purchase orders. |
| `vendors` | `id`, `name`, `specialty`, `lead_days` | Inventory picks a restock vendor by specialty and lead time. A vendor with an open invoice won't ship until that invoice is paid. |
| `invoices` | `id`, `vendor_id` → vendors, `amount`, `due_date`, `status`, `description` | Accounting finds overdue bills here (a `due_date` before `desk.date_today`). An open invoice blocks that vendor from shipping. |
| `leases` | `id`, `space_name`, `landlord`, `monthly_rent`, `next_due`, `notes` | Facilities confirms rent amounts and due dates. Paying rent moves `next_due` forward one month. |
| `cash_accounts` | `name`, `balance`, `date` | This is the only cash the shop has, and no revenue comes in. Every payment is checked against it, and the balance can never go negative. |
| `payments` | `id`, `kind`, `ref_id`, `amount`, `account`, `paid_at`, `approved_by` | This is the record of money that actually left the shop. A row is written only after a human approves the payment. |

### Tables the system adds

These are created automatically in the working copy (see `shared/db.py`). They don't exist in the
original data.

| Table | Fields | Why it matters for the agents |
|---|---|---|
| `approvals` | `id`, `ticket_id`, `kind`, `summary`, `amount`, `payload`, `requested_by`, `status`, `decided_by`, `decision_note`, `created_at`, `decided_at` | Agents can only request payments, purchase orders and discounts. Each request waits here until a human approves or rejects it on the dashboard. |
| `purchase_orders` | `id`, `ticket_id`, `vendor_id`, `sku`, `size`, `qty`, `unit_cost`, `total`, `ordered_at`, `eta`, `status` | These are approved restock orders, paid up front, with an ETA of the shop date plus the vendor's lead days. |
| `customer_messages` | `id`, `ticket_id`, `recipient`, `subject`, `body`, `drafted_by`, `status`, `created_at` | Customer Service saves drafts here. They are never emailed, and a human approves or discards them on the board. |
| `stock_movements` | `id`, `ticket_id`, `sku`, `size`, `delta`, `reason`, `created_at` | This is an audit trail of every inventory change the agents make. |
| `agent_events` | `id`, `run_id`, `ticket_id`, `agent`, `kind`, `content`, `created_at` | Every tool call, delegation, reply and decision is logged here, and the dashboard's live activity feed reads from it. |
| `ticket_runs` | `id`, `ticket_id`, `status`, `decision`, `summary`, `started_at`, `finished_at` | It holds one row per time the team works a ticket, including the Boss's final call shown on each ticket card. |

### How the tables link

```
tickets ──invoice_id──► invoices ──vendor_id──► vendors
   │  └──lease_id────► leases
   └──sku + size─────► inventory (sku, size)   └──sku──► pricing
approvals / customer_messages / agent_events / ticket_runs ──ticket_id──► tickets
payments.ref_id ──► invoices.id | leases.id | purchase_orders.id   (depending on payments.kind)
```

## MCP Server

`mcp_server/server.py` is a **FastMCP** server called `campus-customs`. It's the only way any agent
touches the database: agents never run SQL themselves. It serves streamable HTTP at
`http://127.0.0.1:8001/mcp` and opens only the working copy named by `CAMPUS_DB_PATH`
(`data/campus_customs_new.db`).

All tools follow the same rule: **never invent data.** Each one returns rows from the database or
fails with a clear message (for example "Ticket 999 does not exist. Existing ticket ids: […]"). The
model sees that message and can correct itself.

### Problem 3 tools: shared by every agent

| Tool | Inputs | What it returns |
|---|---|---|
| `get_ticket` | `ticket_id` | **Ticket retrieval.** One ticket, plus everything it links to: its invoice (with vendor and overdue status against `desk.date_today`), its lease, the inventory and pricing rows for its SKU and size, and its approvals and drafts. |
| `filter_tickets` | `status`, `type`, `requester`, `sku`, `size`, `has_invoice`, `has_lease` (all optional) | **Ticket filtering.** Tickets that match every filter given, plus the statuses and types that actually exist, so an unknown value returns 0 matches rather than a guess. |
| `search_database` | `query`, `tables` (optional), `limit_per_table` | **Database search.** A keyword search across every column of 13 shop tables, with matches grouped by table. No match returns "Do not assume it exists." Table names come from a fixed list and the search text is passed in safely, so a query can't inject SQL. |

Every agent also gets `get_shop_date`, which returns the shop's "today".

### The three tools and the tickets they unlock

#### 1. Ticket retrieval: `get_ticket`

- **Tables it reads:**
  - `tickets` for the ticket itself
  - `invoices` and `vendors` through `invoice_id`
  - `leases` through `lease_id`
  - `inventory` and `pricing` through `sku` and `size`
  - `approvals` and `customer_messages` through `ticket_id`
  - `desk` for today's date
- **Tickets it unlocks:**
  - **101:** shows invoice 501 ($840, 3 days overdue, Bulldog Print Co) and 0 white tees in size S.
  - **102:** shows lease 1 ($2,400 rent due 2026-09-02).
  - **103:** shows 8 navy hoodies in size M on hand and the $22 cost / $58 list price.
- **Why it's the right tool:** A direct retrieval tool is essential because it lets the agent pull
  the complete, factual history of a specific ticket by its unique ID, without hallucinating details.

#### 2. Ticket filtering: `filter_tickets`

- **Tables it reads:** `tickets`.
- **Tickets it unlocks:**
  - **101, 102 and 103:** `status="open"` returns all three, so the Boss knows what's on the board.
  - **101:** `has_invoice=true` isolates the ticket with a bill attached.
  - **102:** `has_lease=true` isolates the rent notice.
  - **103:** `type="price_override"` isolates the discount request.
- **Why it's the right tool:** A filtering tool is necessary because it lets the agent gather and
  organize multiple tickets by specific criteria, such as isolating only unresolved issues or
  putting urgent requests first.

#### 3. Database search: `search_database`

- **Tables it reads:** `tickets`, `inventory`, `pricing`, `vendors`, `invoices`, `leases`,
  `cash_accounts`, `payments`, `desk`, `approvals`, `purchase_orders`, `customer_messages`,
  `stock_movements`.
- **Tickets it unlocks:**
  - **101:** searching "Bulldog" finds Bulldog Print Co and the tee, without needing to know the vendor's id.
  - **102:** searching "Elm City" connects the requester to the landlord on lease 1.
  - **103:** searching "hoodie" finds every hoodie size and its stock.
- **Why it's the right tool:** A keyword search tool gives the agent the flexibility to find relevant
  records when it doesn't know the exact ID, by scanning the database for specific Campus Customs issues.

### Every MCP tool and the tables it uses

The server has 31 tools. 28 are for agents and 3 are backend-only. **(w)** marks a table the tool
writes; every other table is only read. Tools marked **new** were added so the team can work the open
tickets.

| Tool | Tables | Used by | Purpose |
|---|---|---|---|
| `get_shop_date` | desk | all agents | The shop's "today". |
| `get_ticket` | tickets, invoices, vendors, leases, inventory, pricing, approvals, customer_messages, desk | all agents | Ticket retrieval, with every linked record. |
| `filter_tickets` | tickets | all agents | Ticket filtering by status, type, requester, SKU, size or links. |
| `search_database` | the 13 shop tables (not agent_events or ticket_runs) | all agents | Keyword search when the ID isn't known. |
| `add_ticket_note` | tickets (w) | boss, facilities | Add a note to a ticket (the original text is kept). |
| `check_stock` | inventory, pricing | inventory | Stock for a SKU, or for one size. |
| `list_inventory` | inventory | inventory | All stock, or only items at or below a threshold. |
| `check_shortfall` | inventory | inventory | How many can be filled now and how many are short. |
| `fulfill_from_stock` | inventory (w), stock_movements (w), tickets | inventory | Pull stock for an order. Refused if there isn't enough. |
| `list_vendors` | vendors, invoices, desk | boss, inventory, accounting | Lead times, open unpaid invoices, `can_ship`. |
| `get_pricing` | pricing | inventory, accounting | Unit cost and list price. |
| `calculate_margin` | pricing | accounting | Discount %, revenue and margin at a proposed price. |
| `price_for_margin` **new** | pricing | accounting | The lowest price that keeps a target margin (default 40%), so a bulk discount can be proposed (#103). |
| `get_cash_position` | cash_accounts, invoices, vendors, leases, approvals, desk | boss, accounting, facilities | Cash, overdue bills, rent, pending outflows, cash left if everything is approved. |
| `list_invoices` | invoices, vendors, desk | accounting | Invoices with overdue flags. |
| `get_invoice` **new** | invoices, vendors, payments, desk | accounting | The exact ledger entry for one invoice, plus payments made against it (#101). |
| `list_payments` | payments | accounting | Payments already made. |
| `request_payment` | invoices, leases, cash_accounts, tickets, approvals (w) | accounting | Request an invoice or rent payment for approval (#101, #102). Refused if cash can't cover it. |
| `request_purchase_order` | vendors, invoices, inventory, pricing, cash_accounts, tickets, approvals (w) | accounting | Request a restock PO for approval. Refused if the vendor is blocked or cash is short. |
| `request_discount` | pricing, tickets, approvals (w) | accounting | Request a discount quote for approval (#103). Refused below cost. |
| `list_approvals` | approvals | boss, accounting, customer_service | Approval requests and their status. |
| `plan_restock` **new** | inventory, pricing, vendors, invoices, cash_accounts, approvals, desk | inventory, accounting | Shortfall, cost, each vendor's `can_ship` and ETA, and whether cash covers it (#101, #103). Orders nothing. |
| `list_purchase_orders` | purchase_orders, vendors | inventory, accounting | POs placed, with ETAs. |
| `receive_purchase_order` **new** | purchase_orders (w), inventory (w), stock_movements (w), desk | inventory | Log an incoming shipment. Refused before the ETA or if the PO was already received. |
| `list_stock_movements` **new** | stock_movements | inventory | History of every stock change, so physical counts can be matched to the system. |
| `list_leases` | leases | facilities | All leases. |
| `get_lease` | leases, payments, desk | facilities | One lease: rent, next due date, days until due (#102). |
| `draft_customer_message` | customer_messages (w), tickets | customer_service | Save a draft. It is never emailed. |
| `execute_approval` (backend-only) | approvals (w), cash_accounts (w), payments (w), invoices (w), leases (w), purchase_orders (w), vendors, desk | backend, after a human clicks Approve | The only tool that moves money. |
| `set_ticket_status` **new** (backend-only) | tickets (w) | backend | Moves a ticket on the board after a run or an approval. |
| `review_customer_message` **new** (backend-only) | customer_messages (w) | backend, after a human clicks Approve draft or Discard | Approve or discard a draft. Nothing is sent. |

**One path to the data.** Agents get shop facts only from these MCP tools. Each agent's toolset is
filtered from one MCP connection, and the three backend-only tools are never included. The backend
also changes shop data only through MCP (`execute_approval`, `set_ticket_status`,
`review_customer_message`). The backend writes directly only to its own bookkeeping tables
(`agent_events`, `ticket_runs`) and reads directly only to draw the dashboard.

## Agent Team

Five PydanticAI agents run Campus Customs. All of them use **one model, `gpt-6-luna`, called through
Portkey** (`https://api.portkey.ai/v1`) with `PORTKEY_API_KEY`. `backend/agents/config.py` refuses to
build any agent if `OPENAI_MODEL` names a different model.

| Agent | File | Prompt | Output | Role-specific MCP tools |
|---|---|---|---|---|
| Boss | `backend/agents/boss.py` | `backend/prompts/boss.md` | `BossDecision` (structured) | list_approvals, get_cash_position, list_vendors, add_ticket_note |
| Inventory | `backend/agents/inventory.py` | `backend/prompts/inventory.md` | text | check_stock, list_inventory, check_shortfall, fulfill_from_stock, list_vendors, get_pricing, list_purchase_orders, plan_restock, receive_purchase_order, list_stock_movements |
| Accounting | `backend/agents/accounting.py` | `backend/prompts/accounting.md` | text | get_cash_position, list_invoices, get_invoice, list_payments, get_pricing, calculate_margin, price_for_margin, plan_restock, list_vendors, request_payment, request_purchase_order, request_discount, list_approvals, list_purchase_orders |
| Facilities | `backend/agents/facilities.py` | `backend/prompts/facilities.md` | text | list_leases, get_lease, get_cash_position, add_ticket_note |
| Customer Service | `backend/agents/customer_service.py` | `backend/prompts/customer_service.md` | text | draft_customer_message, list_approvals (no stock, pricing or cash tools: it asks Inventory and Accounting) |

Every agent also gets the shared tools (`get_shop_date`, `get_ticket`, `filter_tickets`,
`search_database`) and the `delegate` tool.

### Agent prompts

Each `backend/prompts/<agent>.md` starts with **Your role**: the prompt written for that agent, word for
word. That's followed by **How you work here**, which maps the role onto this shop's MCP tools and the
rules the server enforces. Three points in the roles needed reconciling with the system:

- **Accounting "authorizing payouts":** here that means preparing a pending approval. Only a human moves money.
- **Facilities:** its role is the physical premises, but it also owns the Chapel Street lease and rent
  notice. Accounting prepares the rent payment.
- **Customer Service has "no direct access to the vault or the back room":** its stock, pricing and cash
  tools were removed, so it delegates to Inventory and Accounting.

### Files

- `backend/prompts/_team_rules.md`: rules every agent shares (team roster, shop rules, never invent
  data). It's joined with that agent's own `<agent>.md` file to make the agent's instructions.
- `backend/agents/base.py`: `AgentSpec` (name, role, tools, output type) and the function that
  assembles the instructions.
- `backend/agents/tools.py`: the single MCP connection, filtered down to each agent's tools. It also
  logs every tool call to `agent_events` and sets attribution fields (`requested_by`, `drafted_by`)
  from the agent actually making the call.
- `backend/agents/team.py`: builds the agents, the `delegate` tool and `work_ticket` (the loop).
- `backend/models.py`: the data types: `AgentName`, `TeamDeps` (per-run context), `BossDecision`,
  ticket and event kinds, and the API request bodies.

### The agent loop and full connectivity

1. `work_ticket(id)` starts the **Boss** with the ticket ID.
2. Inside each agent, PydanticAI runs the loop: call the model, run the tools it asks for, and repeat
   until the agent returns its output. `run_agent` steps through that loop node by node
   (`agent.iter`), so each step is audited.
3. Any agent can call `delegate(to, task)` to run **any** other teammate, the Boss included. The
   teammate gets a child `TeamDeps` (one step deeper, chain extended), runs its own loop, and its
   reply comes back as the tool result.
4. The Boss returns a `BossDecision`. The backend sets the ticket's status from it and from any
   pending approvals.

| Loop limit | Value | Why |
|---|---|---|
| `MAX_DEPTH` | 3 | Stops endless chains like boss → accounting → boss → … |
| `MAX_DELEGATIONS` | 16 per ticket run | Caps the total handoffs across every agent on one ticket. |
| `RUN_LIMITS` | 20 model requests, 30 tool calls, 150,000 tokens per agent run | Stops a single agent from looping on its tools. |
| `MAX_TICKET_TOKENS` | 400,000 tokens per ticket run, all agents together | Once it's spent, no new delegations start. |
| `MAX_OUTPUT_TOKENS` | 4,000 per model response | Caps how much any one model response can generate. |
| Self-delegation | refused | An agent must use its own tools. |

When a limit is hit, the delegating agent gets an explanation back rather than a crash.

### Verified run

This was a full run of tickets 101–103 from a freshly reset database (2026-11-06):
- It made 63 gpt-6-luna calls through Portkey, with 0 errors.
- **Delegations seen:**
  - Boss to every specialist.
  - Accounting → Inventory and Facilities → Accounting, so specialists handed work to each other.
  - Inventory → Boss, so a specialist reached the Boss.
- **Results:**
  - 3 approval requests were left pending: invoice #501 ($840), rent ($2,400), and a hoodie
    discount quote.
  - Customer Service saved drafts.
  - No restock PO was requested, because Bulldog Print Co is blocked until invoice #501 is paid.
  - No money moved: cash stayed at $3,400.

## Audit Trail

`output/audit_trail.json` is a JSON array of every agent-loop step. It's **append-only**: each step
is added to the end, and the file is never wiped, not by a new run and not by a database reset. It
is written by `backend/agents/audit.py`, which rewrites the file atomically so it stays valid JSON.

Every entry has `seq` (sequential across the file), `ts` (UTC), `run_id`, `ticket_id`, `agent` and
`kind`. Agent steps also record `depth`, `chain` (for example `["boss", "facilities", "accounting"]`)
and `step`, the position within that agent's run.

| `kind` | Extra fields |
|---|---|
| `run_started` | The Boss's opening prompt, including any human note. |
| `agent_started` | `model` and the task the agent was given. |
| `model_request` | What was sent: the prompt, tool returns or retry parts. |
| `model_response` | `model`, `finish_reason`, `input_tokens`, `output_tokens`, `ticket_tokens_so_far`, the `tool_calls` it asked for (with arguments), and its text. |
| `tool_call` / `tool_result` | MCP tool name, arguments, result or error, and `ok`. |
| `delegate` / `reply` | Who handed what task to whom, and the answer that came back. |
| `agent_finished` | Requests, tool calls, tokens, and the agent's output. |
| `decision` | The Boss's `outcome`, `decision` and `summary`, plus the ticket's total tokens and delegations. |
| `error` | Exceptions and limit hits. |
| `human` | Approvals, rejections and draft decisions, with their effect (for example "Paid invoice #501 $840.00 …"). |

In the first audited full run (2026-11-06), the three tickets produced 338 entries, using 41k, 48k
and 99k tokens. Approving invoice #501 then added 163 more entries: the human step and the Boss's
follow-up run, which requested the $8 restock PO. All earlier entries were kept.

## Safety

### Guardrails for real customers and real money

1. **A human approves every cash movement.** Agents can only *request* payments, POs and discounts.
   The one tool that moves money (`execute_approval`) is backend-only and runs only when a person
   clicks Approve. In production, add sign-in for approvers, two-person approval above a dollar
   threshold, and a daily payout cap.
2. **Hard limits in code, not just in prompts.** The MCP server refuses:
   - overdrafts and requests larger than the bill
   - POs to a vendor with an unpaid invoice
   - quotes below cost
   - receiving stock before its ETA
   - paying a bill from a ticket it isn't linked to (invoice 501 can only be paid from ticket 101),
     and requesting a duplicate payment that's already pending
   - customer drafts that reveal internal details (see guardrail 5)

   SQLite triggers back this up: cash can never go negative or increase.
3. **Least privilege.** Each agent sees only its role's tools, and no agent can run SQL or reach the
   database except through MCP. Customer Service has no stock, pricing or cash tools. Its shared read
   tools are also scoped in the MCP hook (`backend/agents/tools.py`):
   - `search_database` only searches `tickets` and `customer_messages`.
   - `get_ticket` returns without the invoice, inventory, pricing and lease records.

   So it has to ask Inventory and Accounting for those facts.
4. **No unattended outbound contact.** There's no email or send tool. Customer drafts wait on the
   board for a person, and agents are told never to contact customers, landlords or vendors.
5. **Internal details never reach a customer.** `draft_customer_message` refuses a draft that mentions
   any of:
   - vendor or landlord names
   - supplier invoices, overdue bills, costs, margins, price floors, cash, POs or approval numbers
   - an internal dollar amount (a unit cost, an invoice amount or the cash balance)

   The refusal says what to remove, so Customer Service rewrites the draft. The prompts give the same
   rule: customers get availability, the list price or an approved price, and the next step. This
   guard was added after a run's draft told a customer about the shop's overdue $840 supplier invoice.
6. **Never invent data.** Every tool returns real rows or an explicit "does not exist" or "no
   matches". Prompts require agents to cite tool results with IDs. Attribution fields such as
   `requested_by` are set from the calling agent, not trusted from the model.
7. **Audit everything.** The append-only audit trail and the dashboard's live feed record every step.
   In production, also ship the audit log to write-once storage.
8. **Protect secrets and customer data.** The API key stays in `.env`, which isn't committed. Logged
   tool results are truncated. In production, also redact customer contact details from the audit log.
9. **A human's reasons reach the agents.** When a human rejects a request, the rejection note goes
   into the Boss's follow-up run. A manager note on **Run** steers a re-run. In Problem 9, the Boss
   was told to quote only the 8 hoodies in stock and to close #101 once the restock was ordered.
   The agents act on those notes but still can't approve anything themselves.
10. **A password before anyone can touch the hosted desk.** When it's deployed, `DESK_PASSWORD` gates
    every `/api` route except `/api/health`:
    - Without the `X-Desk-Password` header a request gets a 401 after a one-second delay, so nobody can
      read the board, run agents (and spend the Portkey key), reset the data or approve a payment.
    - The check is constant-time.
    - The board asks for the password once per browser session (`sessionStorage`) and never stores it
      for longer.
    - On a public host, `/api/health` stops showing the server's file paths.
11. **Reversible by design.** Agents work on `campus_customs_new.db`. The original is read-only and can
   be restored at any time with Reset.

### Limits that keep token use in check

| Limit | Value |
|---|---|
| Model requests / tool calls / tokens per agent run | 20 / 30 / 150,000 (`RUN_LIMITS`) |
| Tokens per ticket run, all agents | 400,000 (`MAX_TICKET_TOKENS`) |
| Output tokens per model response | 4,000 (`MAX_OUTPUT_TOKENS`) |
| Delegation depth / delegations per ticket | 3 / 16 |
| Tool output stored per step | Truncated at about 1,500–2,000 characters in the feed and audit |
| Search results | `search_database` returns at most 100 rows per table (20 by default) |
| Concurrency | One ticket at a time (a single worker), so runs never pile up |
| Model | One model only, `gpt-6-luna`; any other name is refused |

In the audited run the busiest ticket used 99k tokens and the largest single agent run used 16k,
so the limits leave about 4× headroom while stopping runaway loops.

## Backend Routes

`backend/main.py` is the FastAPI app the dashboard calls. Start the MCP server first, then start the
backend from the `backend/` folder:

```bash
cd backend
uvicorn main:app --reload --port 8000
```

The backend serves http://localhost:8000, with interactive docs at `/docs`. Every route is under `/api`:

| Route | What it does |
|---|---|
| `GET /api/tickets` | Every ticket, marked `open` or `resolved` (`state`), plus its board status and whether it's queued or running. |
| `POST /api/tickets/{id}/run` | Runs the agent team on that ticket. Body is optional: `{"note": "…"}` for the Boss. 404 for an unknown ID, 409 if the ticket is resolved or already queued. |
| `GET /api/events?after=N&limit=200` | Recent agent events: what each agent said (delegations, replies, the Boss's decision) and which tools it called. Pass the last ID you have as `after` to get only newer events when the board refreshes. |
| `POST /api/approvals/{id}` | A human approves or rejects a prepared payment or purchase order (`{"decision": "approved"}`). It's the **only** route that changes cash. It's refused if cash can't cover the request or it was already decided. |
| `GET /api/cash` | The current checking balance from `cash_accounts`, plus pending outflows and the cash left if everything is approved. |
| `POST /api/reset` | Resets the working database to the original values for a fresh run. Refused while agents are working. |
| `GET /api/approvals?status=pending` | The approval requests the agents prepared. Use `status=all` for every request. |
| `GET /api/board` | Everything the dashboard draws in one call: tickets, approvals, drafts, cash, invoices, leases, payments, POs, inventory and the worker queue. |
| `POST /api/run-open` | Queues every open ticket. |
| `POST /api/reset-and-run` | Resets the database, then runs every ticket (a full fresh run). |
| `POST /api/messages/{id}` | Approves (optionally with edited text) or discards a customer draft. Nothing is emailed. |
| `GET /api/health` | Database path, whether the MCP server is reachable, the model (`gpt-6-luna`), and whether the API key is set. |

The first six routes are the ones this problem asked for. The rest support the dashboard.

Verified 2026-11-06 (run on port 8020 because 8000 was in use; otherwise the same command):
- Reset, then `/tickets` showed 3 open tickets and `/cash` showed $3,400.
- Running ticket 102 created rent approval #1.
- `/events` returned the run's tool calls and replies.
- Approving #1 changed cash to $1,000, and approving it again was refused.
- The ticket resolved, and a final reset restored $3,400.

## Dashboard

`frontend/` is the React + Vite + TypeScript board (start it with `npm run dev` in `frontend/`). It
calls the backend directly at `VITE_API_URL` (default `http://localhost:8000`), and the backend
allows any `localhost` / `127.0.0.1` origin. Design notes are in `output/design.md`.

| Panel | Route(s) used | What it does |
|---|---|---|
| Inbox | `GET /api/tickets` | All three tickets with status pills, plus a RESOLVED stamp once resolved. `?ticket=ID` opens one directly. |
| Case file | `POST /api/tickets/{id}/run` | Ticket facts, and **Send to the crew ➤** with an optional note for the Boss. |
| Crew report | `GET /api/events` | The Boss's latest call, plus one line per agent across all of the ticket's runs: what it said, what it created, who it asked, and its tools. |
| Instant Messages | `GET /api/events?after=N` | The live, AIM-style transcript: handoffs, replies, tool use, "is typing…", and human actions. |
| Buddy List | `GET /api/events`, `GET /api/board` | Which agents are on the clock and what each is doing right now. |
| Cash Register | `GET /api/cash`, `GET /api/board` | The checking balance as an LCD readout that rolls down after an approved payment, with a receipt tape of payments. |
| Sign Here | `GET /api/approvals`, `POST /api/approvals/{id}` | Pending requests drawn as checks, showing the cash left after each. **Approve** is the only path that moves money. |
| Outbox | `GET /api/board`, `POST /api/messages/{id}` | Customer drafts (never emailed), with Approve draft or Discard. |
| Toolbar | `GET /api/health`, `POST /api/reset` | MCP and model status, the shop date, and **Fresh start** (a reset). |

## Problem 9: resolving all three tickets

This was a full run from a freshly reset database. Checking went **$3,400.00 → $152.00**, which
matches `cash_accounts`.

| Ticket | Runs | Human actions | Cash | Result |
|---|---|---|---|---|
| #101 tee | 4 | Approved #1 (invoice 501, $840) and #2 (PO, $8). Manager note to close. Discarded 2 duplicate drafts. | −$848.00 | Resolved: bill paid, restock ordered (ETA 9/5), customer drafted |
| #102 rent | 2 | Approved #3 (rent, $2,400) | −$2,400.00 | Resolved: rent paid, next due 10-02 |
| #103 hoodies | 3 | Rejected #4 (quote for 20), with a note. Approved #5 (8 × $36.67 = $293.36). Discarded 2 outdated drafts. | $0.00 | Resolved: quote for the 8 in stock; the 12 can't be supplied |

- **Evidence:**
  - `output/desk_tickets.html` (Actual sections and the Cash tab)
  - `output/resolved_tickets.json`
  - `output/resolved_board.html` (screenshots of the React board)
  - `output/audit_trail.json`, entries 1621–2327 (707 entries appended)
- **Two fixes came out of this run:**
  - a payment can only be requested from the ticket its bill is linked to
  - a human's rejection note is passed into the follow-up run
