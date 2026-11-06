# Campus Customs MCP Server

This is the toolbox for the Campus Customs agent team. Built with **FastMCP**, it's the only way
any agent (boss, inventory, accounting, facilities, customer service) reads or changes shop data.
Agents call its tools and never touch the database directly. Every tool returns real rows from the
database, or a clear "not found". Tools never invent data.

## Database

It uses **`data/campus_customs_new.db`**, the working copy, which is set by `CAMPUS_DB_PATH` in
`.env`. The original `data/campus_customs.db` is never opened, so it stays available for resetting
the working copy (`./reset_db.sh`). The server refuses to start if `CAMPUS_DB_PATH` points at the
original.

## The three core tools

| Tool | What it does |
|---|---|
| `get_ticket(ticket_id)` | **Ticket retrieval:** one ticket by ID, plus its linked invoice, vendor, lease, inventory, pricing, approvals and drafts. |
| `filter_tickets(status, type, requester, sku, size, has_invoice, has_lease)` | **Ticket filtering:** every ticket that matches the filters given (for example all `open` tickets, or only rent notices). |
| `search_database(query, tables?)` | **Database search:** a keyword search across the shop's tables, for when the exact ID isn't known. |

These three are read-only, and every agent gets them, along with `get_shop_date`.

## All tools (31)

| Group | Tools |
|---|---|
| Shared (every agent) | `get_shop_date`, `get_ticket`, `filter_tickets`, `search_database` |
| Tickets | `add_ticket_note` |
| Inventory | `check_stock`, `list_inventory`, `check_shortfall`, `fulfill_from_stock`, `plan_restock`, `receive_purchase_order`, `list_stock_movements`, `list_purchase_orders` |
| Vendors & pricing | `list_vendors`, `get_pricing`, `calculate_margin`, `price_for_margin` |
| Cash & invoices | `get_cash_position`, `list_invoices`, `get_invoice`, `list_payments` |
| Approval requests (create a pending approval; never move money) | `request_payment`, `request_purchase_order`, `request_discount`, `list_approvals` |
| Facilities | `list_leases`, `get_lease` |
| Customer service | `draft_customer_message` (drafts only, never sent) |
| Backend-only (hidden from every agent) | `execute_approval`, `set_ticket_status`, `review_customer_message` |

`../output/harness.md` covers each tool's tables, which agents use it, and the shop rules it enforces.

## Run

From the HW5 folder:

```bash
.venv/bin/python -m mcp_server.server           # HTTP at http://127.0.0.1:8001/mcp (used by the backend)
.venv/bin/python -m mcp_server.server --stdio   # stdio (used by the vibe coder)
```

## Connect a vibe coder

`../.mcp.json` registers the server as `campus-customs`. Claude Code reads that file when a session
starts in the HW5 folder, launches the server over stdio, and asks you once to approve it. After
that, the tools show up as `mcp__campus-customs__get_ticket` and so on.

## Smoke test

`smoke_test.py` replays each vibe-coder prompt's tool call through the same `.mcp.json` connection.
It checks the output against `data/campus_customs_new.db` with its own SQL and writes
`../output/mcp_smoke.json`.

```bash
.venv/bin/python -m mcp_server.smoke_test output/mcp_smoke_cases.json
```
