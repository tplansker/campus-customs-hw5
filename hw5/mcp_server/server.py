"""Campus Customs MCP server (FastMCP) — the only way agents touch the shop database.

Every agent on the team gets its tools from this server. It reads and writes only the working
copy data/campus_customs_new.db (CAMPUS_DB_PATH); the original campus_customs.db is never opened.
Tools never invent data: they return rows from the database, or an explicit "not found".

Problem 3 tools (read-only):
- get_ticket       ticket retrieval: one ticket by id, with every record it links to
- filter_tickets   ticket filtering: tickets matching status / type / requester / sku / size / links
- search_database  database search: keyword search across the shop's tables

Run from the HW5 folder:
  .venv/bin/python -m mcp_server.server          streamable HTTP at http://127.0.0.1:8001/mcp (backend)
  .venv/bin/python -m mcp_server.server --stdio  stdio, launched by a vibe coder from .mcp.json

Shop rules enforced here (not just in prompts):
- "Today" is desk.date_today; overdue = due_date before that date.
- Every payment (invoice, rent, purchase order) needs human approval: agents can only create a
  pending approval.
- A vendor will not ship a new order while it has an open unpaid invoice.
- No negative balances: payment requests and payments are refused when cash is short (a DB
  trigger backs this up). No revenue is modeled, so cash only goes out.

Tools that move money or change prices never execute directly: they create a *pending
approval*. Only `execute_approval` (called by the backend after a human clicks Approve,
and hidden from the agents) actually pays, orders, or locks in a discount.
"""

from __future__ import annotations

import calendar
import json
import os
import re
from datetime import date, timedelta

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from shared.db import DB_PATH, connect, rows, shop_date

mcp = FastMCP(
    name="campus-customs",
    instructions=(
        "Tools for running the Campus Customs shop: tickets, inventory, vendors, cash, invoices, leases, "
        "approvals and customer messages. Only report what these tools return; never invent data."
    ),
)

APPROVAL_KINDS = ("payment", "purchase_order", "discount")


def _add_month(d: date) -> date:
    y, m = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def _ticket_exists(conn, ticket_id: int | None) -> None:
    if ticket_id is not None and not conn.execute("SELECT 1 FROM tickets WHERE id=?", (ticket_id,)).fetchone():
        raise ToolError(f"Ticket {ticket_id} does not exist.")


def _invoices(conn, where: str = "", args: tuple = ()) -> list[dict]:
    """Invoices with vendor name and overdue status relative to desk.date_today."""
    today = shop_date(conn)
    out = rows(conn.execute(
        "SELECT i.*, v.name AS vendor FROM invoices i JOIN vendors v ON v.id=i.vendor_id " + where + " ORDER BY i.due_date",
        args))
    for inv in out:
        days = (date.fromisoformat(today) - date.fromisoformat(inv["due_date"])).days
        inv["overdue"] = inv["status"] == "open" and days > 0
        inv["days_overdue"] = max(0, days) if inv["status"] == "open" else 0
    return out


def _vendor_open_invoices(conn, vendor_id: int) -> list[dict]:
    return _invoices(conn, "WHERE i.vendor_id=? AND i.status='open'", (vendor_id,))


def _balance(conn, account: str) -> float:
    r = conn.execute("SELECT balance FROM cash_accounts WHERE name=?", (account,)).fetchone()
    if not r:
        raise ToolError(f"Unknown cash account {account}.")
    return r["balance"]


def _pay(conn, *, kind: str, ref_id: int, amount: float, account: str, approved_by: str) -> float:
    """The ONLY place cash leaves the shop. Refuses rather than going negative. Returns new balance."""
    if amount <= 0:
        raise ToolError("Payment amount must be positive.")
    bal = _balance(conn, account)
    if amount > bal + 1e-9:
        raise ToolError(f"Insufficient funds: {account} has ${bal:,.2f}, payment is ${amount:,.2f}. Refused — balances may not go negative.")
    today = shop_date(conn)
    conn.execute("UPDATE cash_accounts SET balance=round(balance-?, 2), date=? WHERE name=?", (amount, today, account))
    conn.execute("INSERT INTO payments (kind, ref_id, amount, account, paid_at, approved_by) VALUES (?,?,?,?,?,?)",
                 (kind, ref_id, amount, account, today, approved_by))
    return round(bal - amount, 2)


def _create_approval(conn, ticket_id, kind, summary, amount, payload, requested_by) -> dict:
    _ticket_exists(conn, ticket_id)
    dup = conn.execute(
        "SELECT id FROM approvals WHERE ticket_id IS ? AND kind=? AND payload=? AND status='pending'",
        (ticket_id, kind, json.dumps(payload, sort_keys=True)),
    ).fetchone()
    if dup:
        return {"approval_id": dup["id"], "status": "pending", "note": "An identical request is already awaiting human approval."}
    cur = conn.execute(
        "INSERT INTO approvals (ticket_id, kind, summary, amount, payload, requested_by) VALUES (?,?,?,?,?,?)",
        (ticket_id, kind, summary, amount, json.dumps(payload, sort_keys=True), requested_by),
    )
    return {"approval_id": cur.lastrowid, "status": "pending", "note": "Queued for human approval on the dashboard. Nothing has been paid or changed yet."}


# ---------------------------------------------------------------- tickets / desk

@mcp.tool()
def get_shop_date() -> dict:
    """Return the shop's current business date (use this as 'today' for due dates)."""
    with connect() as conn:
        return {"date_today": shop_date(conn)}


# ---------------------------------------------------------------- Problem 3: retrieval, filtering, search

TICKET_FILTERS = ("status", "type", "requester", "sku", "size")
# Tables search_database may read. Agent bookkeeping (agent_events, ticket_runs) is left out on purpose.
SEARCHABLE_TABLES = ("tickets", "inventory", "pricing", "vendors", "invoices", "leases", "cash_accounts",
                     "payments", "desk", "approvals", "purchase_orders", "customer_messages", "stock_movements")


def _distinct(conn, column: str) -> list:
    return [r[0] for r in conn.execute(f"SELECT DISTINCT {column} FROM tickets WHERE {column} IS NOT NULL ORDER BY 1")]


@mcp.tool()
def get_ticket(ticket_id: int) -> dict:
    """Ticket retrieval: one ticket by id, plus every record it links to.

    Returns the ticket row and, when present: its lease, its invoice (with vendor and overdue status
    against desk.date_today), the inventory and pricing rows for its sku/size, approval requests and
    drafted customer messages. Fails with "does not exist" for an unknown id; never guesses.
    """
    with connect() as conn:
        t = conn.execute("SELECT * FROM tickets WHERE id=?", (ticket_id,)).fetchone()
        if not t:
            ids = [r[0] for r in conn.execute("SELECT id FROM tickets ORDER BY id")]
            raise ToolError(f"Ticket {ticket_id} does not exist. Existing ticket ids: {ids}.")
        t = dict(t)
        t["date_today"] = shop_date(conn)
        if t.get("lease_id"):
            lease = conn.execute("SELECT * FROM leases WHERE id=?", (t["lease_id"],)).fetchone()
            t["lease"] = dict(lease) if lease else None
        if t.get("invoice_id"):
            inv = _invoices(conn, "WHERE i.id=?", (t["invoice_id"],))
            t["invoice"] = inv[0] if inv else None
        if t.get("sku"):
            stock_q, args = "SELECT * FROM inventory WHERE sku=?", [t["sku"]]
            if t.get("size"):
                stock_q += " AND size=?"
                args.append(t["size"])
            t["inventory"] = rows(conn.execute(stock_q, args))
            price = conn.execute("SELECT * FROM pricing WHERE sku=?", (t["sku"],)).fetchone()
            t["pricing"] = dict(price) if price else None
        t["approvals"] = rows(conn.execute("SELECT id, kind, summary, amount, status, decision_note FROM approvals WHERE ticket_id=?", (ticket_id,)))
        t["messages"] = rows(conn.execute("SELECT id, recipient, subject, status FROM customer_messages WHERE ticket_id=?", (ticket_id,)))
        return t


@mcp.tool()
def filter_tickets(status: str | None = None, type: str | None = None, requester: str | None = None,
                   sku: str | None = None, size: str | None = None,
                   has_invoice: bool | None = None, has_lease: bool | None = None) -> dict:
    """Ticket filtering: list tickets matching ALL the filters given (omit a filter to ignore it).

    status / type / sku / size match exactly (case-insensitive); requester matches part of the name.
    has_invoice / has_lease keep only tickets that do (true) or don't (false) link to an invoice / lease.
    With no filters, returns every ticket. Also returns the values that exist for status and type,
    so an unknown value comes back as zero matches rather than a guess.
    """
    clauses, args = [], []
    for col, val in (("status", status), ("type", type), ("sku", sku), ("size", size)):
        if val:
            clauses.append(f"lower({col}) = lower(?)")
            args.append(val.strip())
    if requester:
        clauses.append("lower(requester) LIKE lower(?)")
        args.append(f"%{requester.strip()}%")
    if has_invoice is not None:
        clauses.append("invoice_id IS NOT NULL" if has_invoice else "invoice_id IS NULL")
    if has_lease is not None:
        clauses.append("lease_id IS NOT NULL" if has_lease else "lease_id IS NULL")
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    with connect() as conn:
        found = rows(conn.execute(f"SELECT * FROM tickets{where} ORDER BY id", args))
        return {
            "filters": {k: v for k, v in dict(status=status, type=type, requester=requester, sku=sku, size=size,
                                              has_invoice=has_invoice, has_lease=has_lease).items() if v is not None},
            "count": len(found),
            "tickets": found,
            "known_statuses": _distinct(conn, "status"),
            "known_types": _distinct(conn, "type"),
        }


@mcp.tool()
def search_database(query: str, tables: list[str] | None = None, limit_per_table: int = 20) -> dict:
    """Database search: find rows whose text or number fields contain `query` (case-insensitive).

    Searches every column of the shop tables (tickets, inventory, pricing, vendors, invoices, leases,
    cash_accounts, payments, desk, approvals, purchase_orders, customer_messages, stock_movements),
    or only the `tables` given. Use it to find SKUs, names, vendors, landlords or ids you don't know
    yet. Returns matching rows grouped by table; an empty result means the data isn't in the database.
    """
    q = query.strip()
    if not q:
        raise ToolError("query must not be empty.")
    if tables:
        unknown = [t for t in tables if t not in SEARCHABLE_TABLES]
        if unknown:
            raise ToolError(f"Unknown or unsearchable table(s) {unknown}. Searchable: {list(SEARCHABLE_TABLES)}.")
        targets = list(tables)
    else:
        targets = list(SEARCHABLE_TABLES)
    limit = max(1, min(int(limit_per_table), 100))
    results: dict[str, list[dict]] = {}
    with connect() as conn:
        for table in targets:  # names come from the whitelist above, columns from SQLite itself
            cols = [r["name"] for r in conn.execute(f"PRAGMA table_info({table})")]
            if not cols:
                continue
            where = " OR ".join(f"CAST({c} AS TEXT) LIKE ? COLLATE NOCASE" for c in cols)
            hits = rows(conn.execute(f"SELECT * FROM {table} WHERE {where} LIMIT ?", [f"%{q}%"] * len(cols) + [limit]))
            if hits:
                results[table] = hits
    return {
        "query": q,
        "tables_searched": targets,
        "match_count": sum(len(v) for v in results.values()),
        "matches": results,
        "note": None if results else f"No rows contain '{q}'. Do not assume it exists.",
    }


# ---------------------------------------------------------------- tickets: notes

@mcp.tool()
def add_ticket_note(ticket_id: int, note: str, author: str) -> dict:
    """Append a short note to a ticket's notes field (keeps the original text)."""
    with connect() as conn:
        t = conn.execute("SELECT notes FROM tickets WHERE id=?", (ticket_id,)).fetchone()
        if not t:
            raise ToolError(f"Ticket {ticket_id} does not exist.")
        new = (t["notes"] or "") + f"\n[{author}] {note}"
        conn.execute("UPDATE tickets SET notes=? WHERE id=?", (new.strip(), ticket_id))
        return {"ok": True}


# ---------------------------------------------------------------- inventory

@mcp.tool()
def check_stock(sku: str, size: str | None = None) -> list[dict]:
    """Stock on hand for a SKU (optionally one size). Sizes: S, M, L, XL, or OS for one-size items."""
    with connect() as conn:
        q = "SELECT i.*, p.unit_cost, p.list_price FROM inventory i LEFT JOIN pricing p USING (sku) WHERE i.sku=?"
        args: list = [sku.upper()]
        if size:
            q += " AND i.size=?"
            args.append(size.upper())
        result = rows(conn.execute(q, args))
        if not result:
            raise ToolError(f"No inventory rows for sku={sku} size={size}.")
        return result


@mcp.tool()
def list_inventory(low_stock_threshold: int | None = None) -> list[dict]:
    """All inventory rows; pass low_stock_threshold to only return rows with qty at or below it."""
    with connect() as conn:
        if low_stock_threshold is not None:
            return rows(conn.execute("SELECT * FROM inventory WHERE qty<=? ORDER BY sku, size", (low_stock_threshold,)))
        return rows(conn.execute("SELECT * FROM inventory ORDER BY sku, size"))


@mcp.tool()
def check_shortfall(sku: str, size: str, qty_needed: int) -> dict:
    """Compare a requested quantity with stock on hand and report the shortfall (0 if fully covered)."""
    with connect() as conn:
        r = conn.execute("SELECT qty FROM inventory WHERE sku=? AND size=?", (sku.upper(), size.upper())).fetchone()
        if not r:
            raise ToolError(f"No inventory row for {sku} size {size}.")
        on_hand = r["qty"]
        return {"sku": sku.upper(), "size": size.upper(), "on_hand": on_hand, "needed": qty_needed,
                "can_fill_now": min(on_hand, qty_needed), "shortfall": max(0, qty_needed - on_hand)}


@mcp.tool()
def fulfill_from_stock(ticket_id: int, sku: str, size: str, qty: int) -> dict:
    """Pull units off the shelf for a customer order (decrements inventory). Fails if there is not enough stock."""
    if qty <= 0:
        raise ToolError("qty must be positive.")
    with connect() as conn:
        _ticket_exists(conn, ticket_id)
        r = conn.execute("SELECT qty FROM inventory WHERE sku=? AND size=?", (sku.upper(), size.upper())).fetchone()
        if not r:
            raise ToolError(f"No inventory row for {sku} size {size}.")
        if r["qty"] < qty:
            raise ToolError(f"Only {r['qty']} on hand for {sku} {size}; cannot pull {qty}.")
        conn.execute("UPDATE inventory SET qty=qty-? WHERE sku=? AND size=?", (qty, sku.upper(), size.upper()))
        conn.execute("INSERT INTO stock_movements (ticket_id, sku, size, delta, reason) VALUES (?,?,?,?,?)",
                     (ticket_id, sku.upper(), size.upper(), -qty, f"Fulfilled for ticket {ticket_id}"))
        return {"ok": True, "remaining": r["qty"] - qty}


@mcp.tool()
def list_vendors() -> list[dict]:
    """Vendors with specialty, lead time, open unpaid invoices, and whether they will ship.

    A vendor will NOT ship new product while it has any open unpaid invoice (can_ship=false):
    that invoice must be paid (with human approval) before a purchase order can be placed.
    """
    with connect() as conn:
        out = rows(conn.execute("SELECT * FROM vendors ORDER BY id"))
        for v in out:
            open_inv = _vendor_open_invoices(conn, v["id"])
            v["open_unpaid_invoices"] = [{"id": i["id"], "amount": i["amount"], "due_date": i["due_date"],
                                          "overdue": i["overdue"]} for i in open_inv]
            v["can_ship"] = not open_inv
        return out


# ---------------------------------------------------------------- pricing / accounting

@mcp.tool()
def get_pricing(sku: str) -> dict:
    """Unit cost and list price for a SKU."""
    with connect() as conn:
        r = conn.execute("SELECT * FROM pricing WHERE sku=?", (sku.upper(),)).fetchone()
        if not r:
            raise ToolError(f"No pricing for {sku}.")
        return dict(r)


@mcp.tool()
def calculate_margin(sku: str, unit_price: float, qty: int = 1) -> dict:
    """Gross margin if `qty` units of `sku` sell at `unit_price` each (compares with list price)."""
    with connect() as conn:
        r = conn.execute("SELECT * FROM pricing WHERE sku=?", (sku.upper(),)).fetchone()
        if not r:
            raise ToolError(f"No pricing for {sku}.")
        cost, lst = r["unit_cost"], r["list_price"]
        revenue = unit_price * qty
        profit = (unit_price - cost) * qty
        return {"sku": sku.upper(), "qty": qty, "unit_price": unit_price, "unit_cost": cost, "list_price": lst,
                "discount_pct": round(100 * (1 - unit_price / lst), 1), "revenue": round(revenue, 2),
                "gross_profit": round(profit, 2), "margin_pct": round(100 * profit / revenue, 1) if revenue else None}


@mcp.tool()
def get_cash_position() -> dict:
    """Cash balances, open invoices (with overdue flags), upcoming rent, and pending approval requests.

    No revenue is modeled: cash only goes out. Payments and purchase orders both spend cash.
    """
    with connect() as conn:
        accounts = rows(conn.execute("SELECT * FROM cash_accounts"))
        open_inv = _invoices(conn, "WHERE i.status='open'")
        leases = rows(conn.execute("SELECT id, space_name, landlord, monthly_rent, next_due FROM leases"))
        pending = rows(conn.execute("SELECT id, ticket_id, kind, summary, amount FROM approvals WHERE status='pending'"))
        total = round(sum(a["balance"] for a in accounts), 2)
        committed = round(sum(p["amount"] or 0 for p in pending if p["kind"] in ("payment", "purchase_order")), 2)
        return {"date_today": shop_date(conn), "accounts": accounts, "total_cash": total,
                "open_invoices": open_inv, "overdue_total": round(sum(i["amount"] for i in open_inv if i["overdue"]), 2),
                "leases": leases, "pending_approvals": pending, "pending_cash_out": committed,
                "cash_after_all_pending": round(total - committed, 2),
                "note": "No revenue is modeled; cash only goes out. Balances may never go negative."}


@mcp.tool()
def list_invoices(status: str | None = None) -> list[dict]:
    """Vendor invoices with overdue flags (vs desk.date_today), optionally filtered by status (open, paid)."""
    with connect() as conn:
        if status:
            return _invoices(conn, "WHERE i.status=?", (status,))
        return _invoices(conn)


@mcp.tool()
def list_payments() -> list[dict]:
    """Payments already made."""
    with connect() as conn:
        return rows(conn.execute("SELECT * FROM payments ORDER BY id"))


@mcp.tool()
def request_payment(ticket_id: int | None, kind: str, ref_id: int, amount: float, reason: str,
                    requested_by: str, account: str = "checking") -> dict:
    """Prepare a payment for HUMAN APPROVAL (does not pay). kind='invoice' (ref_id=invoice id) or 'rent' (ref_id=lease id)."""
    if kind not in ("invoice", "rent"):
        raise ToolError("kind must be 'invoice' or 'rent'.")
    with connect() as conn:
        if kind == "invoice":
            inv = conn.execute("SELECT * FROM invoices WHERE id=?", (ref_id,)).fetchone()
            if not inv:
                raise ToolError(f"Invoice {ref_id} does not exist.")
            if inv["status"] == "paid":
                raise ToolError(f"Invoice {ref_id} is already paid.")
            if amount > inv["amount"] + 1e-9:
                raise ToolError(f"Invoice {ref_id} is ${inv['amount']:,.2f}; cannot pay ${amount:,.2f}.")
            label = f"Pay invoice #{ref_id} (${amount:,.2f})"
        else:
            lease = conn.execute("SELECT * FROM leases WHERE id=?", (ref_id,)).fetchone()
            if not lease:
                raise ToolError(f"Lease {ref_id} does not exist.")
            label = f"Pay rent for {lease['space_name']} due {lease['next_due']} (${amount:,.2f})"
        # A bill belongs to the ticket that links it: work it there, not from another ticket.
        link_col = "invoice_id" if kind == "invoice" else "lease_id"
        owners = [r[0] for r in conn.execute(f"SELECT id FROM tickets WHERE {link_col}=?", (ref_id,))]
        if owners and ticket_id not in owners:
            raise ToolError(f"{'Invoice' if kind == 'invoice' else 'Lease'} {ref_id} belongs to ticket {owners[0]}; "
                            f"request its payment from that ticket, not ticket {ticket_id}.")
        for a in rows(conn.execute("SELECT id, ticket_id, payload FROM approvals WHERE kind='payment' AND status='pending'")):
            pl = json.loads(a["payload"])
            if pl.get("kind") == kind and pl.get("ref_id") == ref_id:
                return {"approval_id": a["id"], "status": "pending",
                        "note": f"A payment for this {kind} is already awaiting human approval (#{a['id']}, ticket {a['ticket_id']})."}
        bal = _balance(conn, account)
        if amount > bal + 1e-9:
            raise ToolError(f"Refused: {account} has ${bal:,.2f}, not enough for ${amount:,.2f}. Balances may not go negative.")
        payload = {"kind": kind, "ref_id": ref_id, "amount": round(amount, 2), "account": account}
        return _create_approval(conn, ticket_id, "payment", f"{label} — {reason}", amount, payload, requested_by)


@mcp.tool()
def request_purchase_order(ticket_id: int | None, vendor_id: int, sku: str, size: str, qty: int, reason: str,
                           requested_by: str, unit_cost: float | None = None) -> dict:
    """Prepare a restock purchase order for HUMAN APPROVAL (does not order or pay).

    The PO is paid up front when approved, so it spends cash. Refused if the vendor has an open
    unpaid invoice (vendors won't ship until it is paid) or if cash cannot cover it.
    unit_cost defaults to the SKU's pricing cost.
    """
    if qty <= 0:
        raise ToolError("qty must be positive.")
    with connect() as conn:
        v = conn.execute("SELECT * FROM vendors WHERE id=?", (vendor_id,)).fetchone()
        if not v:
            raise ToolError(f"Vendor {vendor_id} does not exist.")
        if not conn.execute("SELECT 1 FROM inventory WHERE sku=? AND size=?", (sku.upper(), size.upper())).fetchone():
            raise ToolError(f"Unknown item {sku} size {size}.")
        cost = unit_cost if unit_cost is not None else conn.execute("SELECT unit_cost FROM pricing WHERE sku=?", (sku.upper(),)).fetchone()["unit_cost"]
        total = round(cost * qty, 2)
        blocking = _vendor_open_invoices(conn, vendor_id)
        if blocking:
            ids = ", ".join(f"#{i['id']} ${i['amount']:,.2f} due {i['due_date']}" for i in blocking)
            raise ToolError(f"{v['name']} will not ship while invoice(s) {ids} are unpaid. Get the invoice payment approved first, then request the PO.")
        bal = _balance(conn, "checking")
        if total > bal + 1e-9:
            raise ToolError(f"Refused: checking has ${bal:,.2f}, not enough for a ${total:,.2f} PO.")
        payload = {"vendor_id": vendor_id, "sku": sku.upper(), "size": size.upper(), "qty": qty, "unit_cost": cost}
        summary = f"PO to {v['name']}: {qty}× {sku.upper()} {size.upper()} @ ${cost:.2f} = ${total:,.2f} (lead {v['lead_days']}d) — {reason}"
        return _create_approval(conn, ticket_id, "purchase_order", summary, total, payload, requested_by)


@mcp.tool()
def request_discount(ticket_id: int, sku: str, qty: int, unit_price: float, reason: str, requested_by: str) -> dict:
    """Prepare a discounted price quote for HUMAN APPROVAL. Run calculate_margin first."""
    with connect() as conn:
        p = conn.execute("SELECT * FROM pricing WHERE sku=?", (sku.upper(),)).fetchone()
        if not p:
            raise ToolError(f"No pricing for {sku}.")
        if unit_price < p["unit_cost"]:
            raise ToolError(f"${unit_price:.2f} is below unit cost ${p['unit_cost']:.2f}; that sells at a loss.")
        pct = round(100 * (1 - unit_price / p["list_price"]), 1)
        payload = {"sku": sku.upper(), "qty": qty, "unit_price": round(unit_price, 2), "list_price": p["list_price"]}
        summary = f"Quote {qty}× {sku.upper()} at ${unit_price:.2f} ({pct}% off ${p['list_price']:.2f}) = ${unit_price * qty:,.2f} — {reason}"
        return _create_approval(conn, ticket_id, "discount", summary, round(unit_price * qty, 2), payload, requested_by)


@mcp.tool()
def list_approvals(status: str | None = "pending") -> list[dict]:
    """Approval requests (default: pending ones)."""
    with connect() as conn:
        if status:
            return rows(conn.execute("SELECT * FROM approvals WHERE status=? ORDER BY id", (status,)))
        return rows(conn.execute("SELECT * FROM approvals ORDER BY id"))


@mcp.tool()
def list_purchase_orders() -> list[dict]:
    """Purchase orders already placed (paid) with vendor, quantity and ETA."""
    with connect() as conn:
        return rows(conn.execute("SELECT po.*, v.name AS vendor FROM purchase_orders po JOIN vendors v ON v.id=po.vendor_id ORDER BY po.id"))


@mcp.tool()
def get_invoice(invoice_id: int) -> dict:
    """One vendor invoice: amount, due date, status, overdue days (vs desk.date_today), vendor, and payments made against it."""
    with connect() as conn:
        inv = _invoices(conn, "WHERE i.id=?", (invoice_id,))
        if not inv:
            ids = [r[0] for r in conn.execute("SELECT id FROM invoices ORDER BY id")]
            raise ToolError(f"Invoice {invoice_id} does not exist. Existing invoice ids: {ids}.")
        out = inv[0]
        out["vendor_lead_days"] = conn.execute("SELECT lead_days FROM vendors WHERE id=?", (out["vendor_id"],)).fetchone()[0]
        out["payments"] = rows(conn.execute("SELECT * FROM payments WHERE kind='invoice' AND ref_id=?", (invoice_id,)))
        out["paid_so_far"] = round(sum(x["amount"] for x in out["payments"]), 2)
        return out


@mcp.tool()
def plan_restock(sku: str, size: str, qty_needed: int) -> dict:
    """Restock plan for a shortfall: units short, cost at unit_cost, every vendor's can_ship / lead time /
    blocking invoices, and whether cash covers the order after pending outflows. Read-only: it orders nothing."""
    if qty_needed <= 0:
        raise ToolError("qty_needed must be positive.")
    with connect() as conn:
        item = conn.execute("SELECT i.qty, i.name, p.unit_cost FROM inventory i JOIN pricing p USING (sku) WHERE i.sku=? AND i.size=?",
                            (sku.upper(), size.upper())).fetchone()
        if not item:
            raise ToolError(f"No inventory/pricing row for {sku} size {size}.")
        short = max(0, qty_needed - item["qty"])
        today = shop_date(conn)
        vendors = []
        for v in rows(conn.execute("SELECT * FROM vendors ORDER BY id")):
            blocking = _vendor_open_invoices(conn, v["id"])
            vendors.append({"vendor_id": v["id"], "name": v["name"], "specialty": v["specialty"], "lead_days": v["lead_days"],
                            "can_ship": not blocking,
                            "blocking_invoices": [{"id": b["id"], "amount": b["amount"], "overdue": b["overdue"]} for b in blocking],
                            "eta_if_ordered_today": (date.fromisoformat(today) + timedelta(days=v["lead_days"])).isoformat()})
        cash = round(sum(r[0] for r in conn.execute("SELECT balance FROM cash_accounts")), 2)
        pending = round(sum(r[0] or 0 for r in conn.execute(
            "SELECT amount FROM approvals WHERE status='pending' AND kind IN ('payment','purchase_order')")), 2)
        cost = round(short * item["unit_cost"], 2)
        return {"sku": sku.upper(), "size": size.upper(), "name": item["name"], "on_hand": item["qty"], "needed": qty_needed,
                "shortfall": short, "unit_cost": item["unit_cost"], "restock_cost": cost, "date_today": today,
                "cash_on_hand": cash, "pending_cash_out": pending, "cash_after_pending": round(cash - pending, 2),
                "affordable_after_pending": cost <= cash - pending, "vendors": vendors,
                "note": "Vendor specialty is free text; match it to the item yourself. Nothing has been ordered."}


@mcp.tool()
def price_for_margin(sku: str, qty: int, target_margin_pct: float = 40.0) -> dict:
    """The lowest unit price that keeps gross margin at target_margin_pct (from unit_cost), with the matching
    discount off list price. Use it to propose a bulk discount instead of guessing one."""
    if not 0 <= target_margin_pct < 100:
        raise ToolError("target_margin_pct must be between 0 and 100.")
    with connect() as conn:
        p = conn.execute("SELECT * FROM pricing WHERE sku=?", (sku.upper(),)).fetchone()
        if not p:
            raise ToolError(f"No pricing for {sku}.")
        floor = round(p["unit_cost"] / (1 - target_margin_pct / 100), 2)
        price = min(floor, p["list_price"])
        return {"sku": sku.upper(), "qty": qty, "unit_cost": p["unit_cost"], "list_price": p["list_price"],
                "target_margin_pct": target_margin_pct, "min_unit_price": price,
                "max_discount_pct": round(100 * (1 - price / p["list_price"]), 1),
                "total_at_min_price": round(price * qty, 2), "total_at_list": round(p["list_price"] * qty, 2)}


@mcp.tool()
def list_stock_movements(sku: str | None = None) -> list[dict]:
    """Every recorded stock change (orders pulled, POs received), optionally for one SKU. Use it to reconcile counts."""
    with connect() as conn:
        if sku:
            return rows(conn.execute("SELECT * FROM stock_movements WHERE sku=? ORDER BY id", (sku.upper(),)))
        return rows(conn.execute("SELECT * FROM stock_movements ORDER BY id"))


@mcp.tool()
def receive_purchase_order(po_id: int) -> dict:
    """Log an incoming shipment: add a paid PO's units to inventory. Refused before its ETA (vs desk.date_today)
    or if it was already received, so stock is never added for goods that have not arrived."""
    with connect() as conn:
        po = conn.execute("SELECT * FROM purchase_orders WHERE id=?", (po_id,)).fetchone()
        if not po:
            raise ToolError(f"Purchase order {po_id} does not exist.")
        if po["status"] != "ordered":
            raise ToolError(f"PO {po_id} is already {po['status']}.")
        today = shop_date(conn)
        if today < po["eta"]:
            raise ToolError(f"PO {po_id} is due {po['eta']}; today is {today}. Goods have not arrived, so stock was not changed.")
        conn.execute("UPDATE inventory SET qty=qty+? WHERE sku=? AND size=?", (po["qty"], po["sku"], po["size"]))
        conn.execute("INSERT INTO stock_movements (ticket_id, sku, size, delta, reason) VALUES (?,?,?,?,?)",
                     (po["ticket_id"], po["sku"], po["size"], po["qty"], f"Received PO {po_id}"))
        conn.execute("UPDATE purchase_orders SET status='received' WHERE id=?", (po_id,))
        qty = conn.execute("SELECT qty FROM inventory WHERE sku=? AND size=?", (po["sku"], po["size"])).fetchone()[0]
        return {"po_id": po_id, "received": po["qty"], "sku": po["sku"], "size": po["size"], "on_hand_now": qty}


# ---------------------------------------------------------------- facilities

@mcp.tool()
def list_leases() -> list[dict]:
    """All leases with landlord, monthly rent and next due date."""
    with connect() as conn:
        return rows(conn.execute("SELECT * FROM leases ORDER BY id"))


@mcp.tool()
def get_lease(lease_id: int) -> dict:
    """One lease, plus days until rent is due relative to the shop date and past rent payments."""
    with connect() as conn:
        l = conn.execute("SELECT * FROM leases WHERE id=?", (lease_id,)).fetchone()
        if not l:
            raise ToolError(f"Lease {lease_id} does not exist.")
        l = dict(l)
        today = shop_date(conn)
        l["days_until_due"] = (date.fromisoformat(l["next_due"]) - date.fromisoformat(today)).days if today else None
        l["rent_payments"] = rows(conn.execute("SELECT * FROM payments WHERE kind='rent' AND ref_id=?", (lease_id,)))
        return l


# ---------------------------------------------------------------- customer service

INTERNAL_TERMS = re.compile(
    r"\b(invoices?|suppliers?|vendors?|margins?|unit[- ]costs?|cost price|our costs?|wholesale|cash|"
    r"bank balance|account balance|checking account|overdue|price floor|floor price|floor of|margin[- ]guided|"
    r"purchase orders?|POs?|ledger|approval #?\d+)\b", re.IGNORECASE)


def _money_values(text: str) -> set[float]:
    return {round(float(m.replace(",", "")), 2) for m in re.findall(r"\$\s?(\d[\d,]*(?:\.\d{1,2})?)", text)}


def _internal_details(conn, text: str) -> list[str]:
    """Internal business facts that must never appear in a customer message."""
    found = sorted({m.group(0).lower() for m in INTERNAL_TERMS.finditer(text)})
    lowered = text.lower()
    names = [r[0] for r in conn.execute("SELECT name FROM vendors")] + [r[0] for r in conn.execute("SELECT landlord FROM leases")]
    found += [f"name '{n}'" for n in names if n.lower() in lowered]
    list_prices = {round(r[0], 2) for r in conn.execute("SELECT list_price FROM pricing")}
    internal = ({round(r[0], 2): "unit cost" for r in conn.execute("SELECT unit_cost FROM pricing")}
                | {round(r[0], 2): "invoice amount" for r in conn.execute("SELECT amount FROM invoices")}
                | {round(r[0], 2): "cash balance" for r in conn.execute("SELECT balance FROM cash_accounts")})
    found += [f"${v:,.2f} ({internal[v]})" for v in sorted(_money_values(text)) if v in internal and v not in list_prices]
    return found


@mcp.tool()
def draft_customer_message(ticket_id: int, recipient: str, subject: str, body: str, drafted_by: str) -> dict:
    """Save a DRAFT message to a customer/requester. Nothing is emailed or sent: drafts stay on the board for a human.

    Refused if it reveals internal business details: vendors or landlords, supplier invoices, costs, margins,
    price floors, cash, purchase orders or approval numbers. Tell the customer what they need (availability,
    list price or an approved price, next step) and say anything unconfirmed is "being confirmed".
    """
    with connect() as conn:
        _ticket_exists(conn, ticket_id)
        leaks = _internal_details(conn, f"{subject}\n{body}")
        if leaks:
            raise ToolError("Draft refused: it reveals internal business details a customer must not see: "
                            + "; ".join(leaks) + ". Rewrite it without them.")
        cur = conn.execute(
            "INSERT INTO customer_messages (ticket_id, recipient, subject, body, drafted_by) VALUES (?,?,?,?,?)",
            (ticket_id, recipient, subject, body, drafted_by),
        )
        return {"message_id": cur.lastrowid, "status": "draft"}


# ---------------------------------------------------------------- human-only

@mcp.tool()
def set_ticket_status(ticket_id: int, status: str) -> dict:
    """BACKEND ONLY (hidden from agents): move a ticket on the board."""
    allowed = ("open", "in_progress", "awaiting_approval", "needs_human", "resolved")
    if status not in allowed:
        raise ToolError(f"status must be one of {allowed}.")
    with connect() as conn:
        _ticket_exists(conn, ticket_id)
        conn.execute("UPDATE tickets SET status=? WHERE id=?", (status, ticket_id))
        return {"ticket_id": ticket_id, "status": status}


@mcp.tool()
def review_customer_message(message_id: int, action: str, body: str | None = None) -> dict:
    """HUMAN ONLY (hidden from agents): approve (optionally with edited text) or discard a draft. Nothing is ever emailed."""
    if action not in ("approve", "discard"):
        raise ToolError("action must be 'approve' or 'discard'.")
    status = "approved" if action == "approve" else "discarded"
    with connect() as conn:
        m = conn.execute("SELECT * FROM customer_messages WHERE id=?", (message_id,)).fetchone()
        if not m:
            raise ToolError(f"Message {message_id} does not exist.")
        if m["status"] != "draft":
            raise ToolError(f"Message {message_id} is already {m['status']}.")
        conn.execute("UPDATE customer_messages SET status=?, body=COALESCE(?, body) WHERE id=?", (status, body, message_id))
        return {"id": message_id, "ticket_id": m["ticket_id"], "status": status,
                "summary": f"{m['subject']} -> {m['recipient']}"}

@mcp.tool()
def execute_approval(approval_id: int, decision: str, decided_by: str, note: str = "") -> dict:
    """HUMAN ONLY (hidden from agents): approve or reject a pending request and apply its effect."""
    if decision not in ("approved", "rejected"):
        raise ToolError("decision must be 'approved' or 'rejected'.")
    with connect() as conn:
        a = conn.execute("SELECT * FROM approvals WHERE id=?", (approval_id,)).fetchone()
        if not a:
            raise ToolError(f"Approval {approval_id} does not exist.")
        if a["status"] != "pending":
            raise ToolError(f"Approval {approval_id} is already {a['status']}.")
        today = shop_date(conn)
        effect = "Rejected; nothing changed."
        if decision == "approved":
            p = json.loads(a["payload"])
            if a["kind"] == "payment":
                if p["kind"] == "invoice":
                    inv = conn.execute("SELECT status, amount FROM invoices WHERE id=?", (p["ref_id"],)).fetchone()
                    if inv["status"] == "paid":
                        raise ToolError(f"Invoice #{p['ref_id']} is already paid.")
                    new_bal = _pay(conn, kind="invoice", ref_id=p["ref_id"], amount=p["amount"], account=p["account"], approved_by=decided_by)
                    if p["amount"] >= inv["amount"] - 1e-9:
                        conn.execute("UPDATE invoices SET status='paid' WHERE id=?", (p["ref_id"],))
                    else:
                        conn.execute("UPDATE invoices SET amount=round(amount-?, 2) WHERE id=?", (p["amount"], p["ref_id"]))
                    effect = f"Paid invoice #{p['ref_id']} ${p['amount']:,.2f} from {p['account']}; balance ${new_bal:,.2f}."
                else:
                    new_bal = _pay(conn, kind="rent", ref_id=p["ref_id"], amount=p["amount"], account=p["account"], approved_by=decided_by)
                    due = conn.execute("SELECT next_due FROM leases WHERE id=?", (p["ref_id"],)).fetchone()["next_due"]
                    nxt = _add_month(date.fromisoformat(due)).isoformat()
                    conn.execute("UPDATE leases SET next_due=? WHERE id=?", (nxt, p["ref_id"]))
                    effect = f"Paid rent ${p['amount']:,.2f}; next due {nxt}; balance ${new_bal:,.2f}."
            elif a["kind"] == "purchase_order":
                vendor = conn.execute("SELECT name, lead_days FROM vendors WHERE id=?", (p["vendor_id"],)).fetchone()
                blocking = _vendor_open_invoices(conn, p["vendor_id"])
                if blocking:
                    raise ToolError(f"{vendor['name']} still has unpaid invoice(s) {', '.join('#' + str(i['id']) for i in blocking)}; they will not ship. Approve that payment first.")
                eta = (date.fromisoformat(today) + timedelta(days=vendor["lead_days"])).isoformat()
                total = round(p["unit_cost"] * p["qty"], 2)
                cur = conn.execute(
                    "INSERT INTO purchase_orders (ticket_id, vendor_id, sku, size, qty, unit_cost, total, ordered_at, eta) VALUES (?,?,?,?,?,?,?,?,?)",
                    (a["ticket_id"], p["vendor_id"], p["sku"], p["size"], p["qty"], p["unit_cost"], total, today, eta))
                new_bal = _pay(conn, kind="purchase_order", ref_id=cur.lastrowid, amount=total, account="checking", approved_by=decided_by)
                effect = f"PO #{cur.lastrowid} paid to {vendor['name']} ${total:,.2f}; {p['qty']}x {p['sku']} {p['size']} ETA {eta}; balance ${new_bal:,.2f}."
            elif a["kind"] == "discount":
                effect = f"Quote locked: {p['qty']}x {p['sku']} at ${p['unit_price']:.2f}."
        conn.execute(
            "UPDATE approvals SET status=?, decided_by=?, decision_note=?, decided_at=datetime('now') WHERE id=?",
            (decision, decided_by, note or effect, approval_id),
        )
        return {"approval_id": approval_id, "status": decision, "effect": effect}


if __name__ == "__main__":
    import sys

    if "--stdio" in sys.argv:
        # Launched by a vibe coder from .mcp.json. stdout carries the MCP protocol, so log to stderr only.
        print(f"Campus Customs MCP server on stdio  (db: {DB_PATH})", file=sys.stderr, flush=True)
        mcp.run(transport="stdio", show_banner=False)
    else:
        # Used by the FastAPI backend and its agent team.
        port = int(os.getenv("MCP_PORT", "8001"))
        print(f"Campus Customs MCP server on http://127.0.0.1:{port}/mcp  (db: {DB_PATH})", flush=True)
        mcp.run(transport="http", host="127.0.0.1", port=port, path="/mcp", show_banner=False)
