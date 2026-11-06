"""MCP tool wiring: one connection to the Campus Customs MCP server, filtered per agent, with logging."""

from __future__ import annotations

import json
from functools import cache
from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.mcp import MCPToolset

from backend.agents.audit import audit
from backend.agents.config import MCP_URL
from backend.models import TeamDeps
from shared.db import connect

# Every agent gets the Problem 3 read tools (ticket retrieval, ticket filtering, database search).
SHARED_TOOLS = frozenset({"get_shop_date", "get_ticket", "filter_tickets", "search_database"})

# Arguments the server uses for attribution. They're filled in from the calling agent, never trusted from the model.
ATTRIBUTION_ARGS = ("requested_by", "drafted_by", "author")


def emit(run_id: str | None, ticket_id: int | None, agent: str, kind: str, _deps: TeamDeps | None = None,
         _feed: bool = True, **content: Any) -> None:
    """Record one step: append it to output/audit_trail.json and (for the live feed) to agent_events."""
    entry: dict[str, Any] = {"run_id": run_id, "ticket_id": ticket_id, "agent": agent, "kind": kind}
    if _deps is not None:
        _deps.step += 1
        entry.update(depth=_deps.depth, chain=_deps.chain, step=_deps.step)
    audit({**entry, **{k: _bounded(v) for k, v in content.items()}})
    if _feed:
        with connect() as conn:
            conn.execute(
                "INSERT INTO agent_events (run_id, ticket_id, agent, kind, content) VALUES (?,?,?,?,?)",
                (run_id, ticket_id, agent, kind, json.dumps(content, default=str)),
            )


def _short(value: Any, limit: int = 1500) -> str:
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    return text if len(text) <= limit else text[:limit] + " …"


def _bounded(value: Any, limit: int = 2000) -> Any:
    """Keep structured values as JSON for the audit; only oversized ones become a truncated string."""
    if isinstance(value, str):
        try:  # tool args / results often arrive as JSON text
            value = json.loads(value)
        except ValueError:
            return _short(value, limit)
    return value if len(json.dumps(value, default=str)) <= limit else _short(value, limit)


# Customer Service works the front of house only. The shared read tools are scoped for it, so it can't
# reach back-room data (stock, costs, vendor invoices, cash, leases) and has to ask teammates instead.
CUSTOMER_FACING_TABLES = ["tickets", "customer_messages"]
BACK_ROOM_TICKET_FIELDS = ("invoice", "inventory", "pricing", "lease")
SCOPED_AGENTS = {"customer_service"}


def _scope_args(agent: str, name: str, args: dict[str, Any]) -> None:
    if agent in SCOPED_AGENTS and name == "search_database":
        asked = args.get("tables") or CUSTOMER_FACING_TABLES
        args["tables"] = [t for t in asked if t in CUSTOMER_FACING_TABLES] or CUSTOMER_FACING_TABLES


def _scope_result(agent: str, name: str, result: Any) -> Any:
    if agent in SCOPED_AGENTS and name == "get_ticket":
        data = json.loads(result) if isinstance(result, str) else result
        if isinstance(data, dict):
            data = {k: v for k, v in data.items() if k not in BACK_ROOM_TICKET_FIELDS}
            data["back_room_details"] = "withheld: ask Inventory (stock) or Accounting (prices, billing)"
            return data
    return result


async def _log_tool_call(ctx: RunContext[TeamDeps], call_tool, name: str, args: dict[str, Any]):
    d = ctx.deps
    for k in ATTRIBUTION_ARGS:
        if k in args:
            args[k] = d.agent
    _scope_args(d.agent, name, args)
    emit(d.run_id, d.ticket_id, d.agent, "tool_call", _deps=d, tool=name, args=args)
    try:
        result = _scope_result(d.agent, name, await call_tool(name, args))
    except Exception as exc:
        emit(d.run_id, d.ticket_id, d.agent, "tool_result", _deps=d, tool=name, ok=False, result=str(exc))
        raise
    emit(d.run_id, d.ticket_id, d.agent, "tool_result", _deps=d, tool=name, ok=True, result=_short(result))
    return result


@cache
def mcp_toolset() -> MCPToolset:
    return MCPToolset(MCP_URL, process_tool_call=_log_tool_call)


def toolset_for(role_tools: frozenset[str]):
    """The MCP tools one agent may see: the shared tools plus its role tools. execute_approval is never included."""
    allowed = SHARED_TOOLS | role_tools
    return mcp_toolset().filtered(lambda ctx, td: td.name in allowed)
