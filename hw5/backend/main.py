"""Campus Customs FastAPI backend: the API the React dashboard calls.

Start it from the backend/ folder (the MCP server must be running first, on MCP_URL,
default http://127.0.0.1:8001/mcp):

    cd backend
    uvicorn main:app --reload --port 8000

Then the API is at http://localhost:8000 (interactive docs at /docs).

Tickets are worked one at a time by a background worker so two tickets never race for the same cash.
Shop data is read and changed through the MCP server; only run bookkeeping (agent_events, ticket_runs)
and the dashboard's read-only views touch the database directly.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Started from backend/, the project root (which holds the `backend` and `shared` packages) is not on the
# import path yet. Add it so `uvicorn main:app` works from backend/ as well as `backend.main:app` from root.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import asyncio
import json
import logging
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from backend.agents import MCP_URL, MODEL_NAME, emit, mcp_toolset, work_ticket
from backend.models import ApprovalDecision, MessageAction, RunRequest
from shared.db import DB_PATH, connect, reset_working_db, rows, shop_date

log = logging.getLogger("campus_customs")
logging.basicConfig(level=logging.INFO)

class Worker:
    def __init__(self) -> None:
        self.queue: asyncio.Queue[tuple[int, str | None]] = asyncio.Queue()
        self.queued: list[int] = []
        self.current: int | None = None
        self.task: asyncio.Task | None = None

    def enqueue(self, ticket_id: int, note: str | None) -> bool:
        if ticket_id in self.queued or ticket_id == self.current:
            return False
        self.queued.append(ticket_id)
        self.queue.put_nowait((ticket_id, note))
        return True

    @property
    def busy(self) -> bool:
        return self.current is not None or bool(self.queued)

    async def loop(self) -> None:
        while True:
            ticket_id, note = await self.queue.get()
            if ticket_id in self.queued:
                self.queued.remove(ticket_id)
            else:
                continue  # dropped by a reset
            self.current = ticket_id
            try:
                await run_one(ticket_id, note)
            finally:
                self.current = None


worker = Worker()


async def mcp_call(tool: str, args: dict):
    """Shop data changes go through the MCP server (same tools/rules as the agents), never direct SQL."""
    async with mcp_toolset() as ts:
        return await ts.direct_call_tool(tool, args)


async def set_ticket_status(ticket_id: int, status: str) -> None:
    await mcp_call("set_ticket_status", {"ticket_id": ticket_id, "status": status})


async def pending_approvals(ticket_id: int) -> int:
    t = await mcp_call("get_ticket", {"ticket_id": ticket_id})
    return sum(1 for a in t["approvals"] if a["status"] == "pending")


async def run_one(ticket_id: int, note: str | None) -> None:
    run_id = uuid.uuid4().hex[:10]
    with connect() as conn:
        conn.execute("INSERT INTO ticket_runs (id, ticket_id, status) VALUES (?,?,'running')", (run_id, ticket_id))
    await set_ticket_status(ticket_id, "in_progress")
    try:
        decision = await work_ticket(ticket_id, run_id, note)
    except Exception as exc:  # model/MCP failure: put the ticket back on the board
        log.exception("Run %s for ticket %s failed", run_id, ticket_id)
        emit(run_id, ticket_id, "boss", "error", message=f"{type(exc).__name__}: {exc}")
        with connect() as conn:
            conn.execute("UPDATE ticket_runs SET status='error', summary=?, finished_at=datetime('now') WHERE id=?",
                         (f"{type(exc).__name__}: {exc}", run_id))
        await set_ticket_status(ticket_id, "open")
        return

    pending = await pending_approvals(ticket_id)
    status = "awaiting_approval" if pending else ("needs_human" if decision.outcome == "needs_human" else "resolved")
    await set_ticket_status(ticket_id, status)
    with connect() as conn:  # run bookkeeping (not shop data)
        conn.execute("UPDATE ticket_runs SET status='done', decision=?, summary=?, finished_at=datetime('now') WHERE id=?",
                     (decision.decision, decision.summary, run_id))


@asynccontextmanager
async def lifespan(app: FastAPI):
    with connect() as conn:  # creates extra tables; marks runs cut off by a restart
        conn.execute("UPDATE ticket_runs SET status='error', summary='Backend restarted' WHERE status='running'")
    try:  # any ticket left mid-run by a crash goes back to open (through MCP)
        stuck = await mcp_call("filter_tickets", {"status": "in_progress"})
        for t in stuck["tickets"]:
            await set_ticket_status(t["id"], "open")
    except Exception as exc:
        log.warning("Could not recover in-progress tickets via MCP (is the MCP server running?): %s", exc)
    worker.task = asyncio.create_task(worker.loop())
    log.info("DB: %s | MCP: %s | model: %s", DB_PATH, MCP_URL, MODEL_NAME)
    yield
    worker.task.cancel()


app = FastAPI(title="Campus Customs Ops", lifespan=lifespan)
# Let the Vite dashboard call these routes from the browser. Vite serves on http://localhost:5173 and moves
# to the next port (5174, 5175, ...) when that one is busy, so any local port is allowed, but only from this machine.
app.add_middleware(CORSMiddleware, allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
                   allow_methods=["GET", "POST"], allow_headers=["Content-Type"])


# ---------------------------------------------------------------- read

@app.get("/api/tickets")
async def tickets():
    """The tickets on the board, each marked open or resolved (plus its detailed board status)."""
    found = await mcp_call("filter_tickets", {})
    return [{**t, "state": "resolved" if t["status"] == "resolved" else "open",
             "queued": t["id"] in worker.queued, "running": t["id"] == worker.current}
            for t in found["tickets"]]


@app.get("/api/cash")
async def cash():
    """The current checking balance from cash_accounts."""
    position = await mcp_call("get_cash_position", {})
    checking = next((a for a in position["accounts"] if a["name"] == "checking"), None)
    if checking is None:
        raise HTTPException(404, "No checking account in cash_accounts")
    return {"account": "checking", "balance": checking["balance"], "as_of": checking["date"],
            "pending_cash_out": position["pending_cash_out"], "cash_after_all_pending": position["cash_after_all_pending"]}


@app.get("/api/approvals")
async def approvals(status: str | None = "pending"):
    """Approval requests the agents prepared (pending by default; status=all for every one)."""
    return await mcp_call("list_approvals", {"status": None if status == "all" else status})


@app.get("/api/health")
async def health():
    import os
    mcp_ok, mcp_error = True, None
    try:
        async with mcp_toolset() as ts:
            await ts.list_tools()
    except Exception as exc:
        mcp_ok, mcp_error = False, f"{type(exc).__name__}: {exc}"
    return {"db_path": str(DB_PATH), "mcp_url": MCP_URL, "mcp_ok": mcp_ok, "mcp_error": mcp_error,
            "model": MODEL_NAME, "api_key_set": bool(os.getenv("PORTKEY_API_KEY", "").strip())}


@app.get("/api/board")
def board():
    with connect() as conn:
        tickets = rows(conn.execute("SELECT * FROM tickets ORDER BY id"))
        runs = rows(conn.execute("SELECT * FROM ticket_runs ORDER BY started_at"))
        latest = {r["ticket_id"]: r for r in runs}
        for t in tickets:
            t["latest_run"] = latest.get(t["id"])
        approvals = rows(conn.execute("SELECT * FROM approvals ORDER BY id DESC"))
        for a in approvals:
            a["payload"] = json.loads(a["payload"])
        return {
            "date_today": shop_date(conn),
            "tickets": tickets,
            "approvals": approvals,
            "messages": rows(conn.execute("SELECT * FROM customer_messages ORDER BY id DESC")),
            "cash": rows(conn.execute("SELECT * FROM cash_accounts")),
            "invoices": rows(conn.execute("SELECT i.*, v.name AS vendor FROM invoices i JOIN vendors v ON v.id=i.vendor_id ORDER BY i.id")),
            "leases": rows(conn.execute("SELECT * FROM leases")),
            "payments": rows(conn.execute("SELECT * FROM payments ORDER BY id DESC")),
            "purchase_orders": rows(conn.execute("SELECT po.*, v.name AS vendor FROM purchase_orders po JOIN vendors v ON v.id=po.vendor_id ORDER BY po.id")),
            "inventory": rows(conn.execute("SELECT i.*, p.unit_cost, p.list_price FROM inventory i LEFT JOIN pricing p USING (sku) ORDER BY sku, size")),
            "worker": {"current": worker.current, "queued": list(worker.queued)},
        }


@app.get("/api/events")
def events(after: int = 0, limit: int = 200):
    """Recent agent events: what each agent said (delegations, replies, decisions) and which tools it called.

    after=0 returns the most recent `limit` events; after=<last id seen> returns only newer ones, so the
    board can refresh by polling with the last id it has.
    """
    limit = max(1, min(limit, 1000))
    with connect() as conn:
        if after <= 0:
            out = rows(conn.execute("SELECT * FROM (SELECT * FROM agent_events ORDER BY id DESC LIMIT ?) ORDER BY id", (limit,)))
        else:
            out = rows(conn.execute("SELECT * FROM agent_events WHERE id>? ORDER BY id LIMIT ?", (after, limit)))
    for e in out:
        e["content"] = json.loads(e["content"])
    return out


# ---------------------------------------------------------------- actions

@app.post("/api/tickets/{ticket_id}/run")
def run_ticket(ticket_id: int, body: RunRequest | None = None):
    """Run the agent team on one ticket (queued; it starts as soon as the worker is free)."""
    with connect() as conn:
        t = conn.execute("SELECT status FROM tickets WHERE id=?", (ticket_id,)).fetchone()
    if not t:
        raise HTTPException(404, f"Ticket {ticket_id} not found")
    if t["status"] == "resolved":
        raise HTTPException(409, "Ticket is already resolved")
    if not worker.enqueue(ticket_id, body.note if body else None):
        raise HTTPException(409, "Ticket is already queued or running")
    return {"queued": True}


@app.post("/api/run-open")
def run_open():
    with connect() as conn:
        ids = [r["id"] for r in conn.execute("SELECT id FROM tickets WHERE status='open' ORDER BY id")]
    queued = [i for i in ids if worker.enqueue(i, None)]
    return {"queued": queued}


@app.post("/api/approvals/{approval_id}")
async def decide(approval_id: int, body: ApprovalDecision):
    """A human approves or rejects a request the agents prepared. Approving a payment or purchase order is
    the only thing that changes cash (through the MCP server's execute_approval); it is refused if cash
    can't cover it."""
    try:
        result = await mcp_call("execute_approval", {
            "approval_id": approval_id, "decision": body.decision, "decided_by": "human", "note": body.note})
    except Exception as exc:
        raise HTTPException(400, str(exc).replace("Error executing tool execute_approval: ", ""))

    approvals = await mcp_call("list_approvals", {"status": None})
    a = next(x for x in approvals if x["id"] == approval_id)
    tid = a["ticket_id"]
    emit(None, tid, "human", "human", action=body.decision, approval_id=approval_id,
         summary=a["summary"], effect=result.get("effect") if isinstance(result, dict) else str(result))
    if tid is not None:
        t = await mcp_call("get_ticket", {"ticket_id": tid})
        decided = t["approvals"]
        if all(d["status"] != "pending" for d in decided) and t["status"] == "awaiting_approval":
            # Hand the ticket back to the boss: an approval may unblock the next step
            # (e.g. invoice paid -> vendor can ship -> PO), or a rejection needs a new plan.
            lines = "; ".join(f"#{d['id']} {d['kind']} {d['status']}: {d['summary'][:120]}"
                              + (f" (human's note: {d['decision_note']})" if d["status"] == "rejected" and d.get("decision_note") else "")
                              for d in decided)
            follow_up = (f"The human has decided every approval on this ticket ({lines}). Re-check the shop state, "
                         "request any next step that is now unblocked (it still needs approval), or close the ticket.")
            await set_ticket_status(tid, "open")
            worker.enqueue(tid, follow_up)
    return result


@app.post("/api/messages/{message_id}")
async def message_action(message_id: int, req: MessageAction):
    """Approve or discard a draft. Nothing is ever emailed: approved drafts stay on the board."""
    try:
        r = await mcp_call("review_customer_message", {"message_id": message_id, "action": req.action, "body": req.body})
    except Exception as exc:
        raise HTTPException(409, str(exc).replace("Error executing tool review_customer_message: ", ""))
    emit(None, r["ticket_id"], "human", "human", action=f"message_{r['status']}", message_id=message_id,
         summary=r["summary"])
    return {"id": message_id, "status": r["status"]}


@app.post("/api/reset")
def reset():
    """Restore the working database from the original campus_customs.db (refused while agents are working)."""
    if worker.busy:
        raise HTTPException(409, "Agents are still working; wait for the queue to finish before resetting.")
    reset_working_db()
    return {"reset": True, "db_path": str(DB_PATH)}


@app.post("/api/reset-and-run")
def reset_and_run():
    """Full run: restore the original data first, then queue every open ticket."""
    reset()
    return run_open()
