"""Smoke test for the three Problem 3 MCP tools -> output/mcp_smoke.json.

Run from the HW5 folder:
    .venv/bin/python -m mcp_server.smoke_test output/mcp_smoke_cases.json

The cases file lists what was asked in the vibe coder and which tool call that prompt produced:
    [{"prompt": "...", "tool": "get_ticket", "arguments": {"ticket_id": 101}}, ...]

For each case this script:
  1. launches the server exactly as .mcp.json does (stdio) and calls the tool, and
  2. re-derives the answer straight from data/campus_customs_new.db with independent SQL,
then records the prompt, tool name, tool output, and whether the output matches the database.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from fastmcp import Client

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "campus_customs_new.db"
OUT = ROOT / "output" / "mcp_smoke.json"


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)  # read-only: the check never changes data
    conn.row_factory = sqlite3.Row
    return conn


def one(conn, sql, args=()):
    r = conn.execute(sql, args).fetchone()
    return dict(r) if r else None


def check_get_ticket(out: dict, args: dict) -> list[dict]:
    with db() as conn:
        tid = args["ticket_id"]
        t = one(conn, "SELECT * FROM tickets WHERE id=?", (tid,))
        if t is None:  # the right answer is "not found", never a made-up ticket
            ids = [r[0] for r in conn.execute("SELECT id FROM tickets ORDER BY id")]
            err = str(out.get("error", "")) if isinstance(out, dict) else ""
            return [{"check": f"SELECT * FROM tickets WHERE id={tid} returns no row, so the tool must refuse",
                     "expected": {"ticket_found": False, "existing_ticket_ids": ids},
                     "actual": {"ticket_found": "does not exist" not in err,
                                "existing_ticket_ids": ids if str(ids) in err else err}}]
        checks = [{"check": f"tickets row id={tid}", "expected": t,
                   "actual": {k: out.get(k) for k in t} if t else None}]
        if t and t["invoice_id"]:
            inv = one(conn, "SELECT * FROM invoices WHERE id=?", (t["invoice_id"],))
            checks.append({"check": f"invoices row id={t['invoice_id']}", "expected": inv,
                           "actual": {k: (out.get("invoice") or {}).get(k) for k in inv}})
        if t and t["lease_id"]:
            lease = one(conn, "SELECT * FROM leases WHERE id=?", (t["lease_id"],))
            checks.append({"check": f"leases row id={t['lease_id']}", "expected": lease,
                           "actual": {k: (out.get("lease") or {}).get(k) for k in lease}})
        if t and t["sku"]:
            stock = [dict(r) for r in conn.execute("SELECT * FROM inventory WHERE sku=? AND size=?", (t["sku"], t["size"]))]
            checks.append({"check": f"inventory {t['sku']} {t['size']}", "expected": stock, "actual": out.get("inventory")})
            price = one(conn, "SELECT * FROM pricing WHERE sku=?", (t["sku"],))
            checks.append({"check": f"pricing {t['sku']}", "expected": price, "actual": out.get("pricing")})
    return checks


def check_filter_tickets(out: dict, args: dict) -> list[dict]:
    clauses, params = [], []
    for col in ("status", "type", "sku", "size"):
        if args.get(col):
            clauses.append(f"lower({col}) = lower(?)")
            params.append(args[col])
    if args.get("requester"):
        clauses.append("lower(requester) LIKE lower(?)")
        params.append(f"%{args['requester']}%")
    for flag, col in (("has_invoice", "invoice_id"), ("has_lease", "lease_id")):
        if args.get(flag) is not None:
            clauses.append(f"{col} IS {'NOT ' if args[flag] else ''}NULL")
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    with db() as conn:
        expected = [dict(r) for r in conn.execute(f"SELECT * FROM tickets{where} ORDER BY id", params)]
    return [{"check": f"SELECT * FROM tickets{where}", "params": params,
             "expected": expected, "actual": out.get("tickets")}]


def check_search_database(out: dict, args: dict) -> list[dict]:
    q = args["query"].strip().lower()
    checks = []
    with db() as conn:
        for table in out.get("tables_searched", []):
            expected = []
            for r in conn.execute(f"SELECT * FROM {table}"):  # brute force: scan every row in Python
                if any(v is not None and q in str(v).lower() for v in dict(r).values()):
                    expected.append(dict(r))
            actual = out.get("matches", {}).get(table, [])
            if expected or actual:
                checks.append({"check": f"rows in {table} containing '{args['query']}'",
                               "expected": expected[: args.get("limit_per_table", 20)], "actual": actual})
        if not checks:
            checks.append({"check": f"no row in any searched table contains '{args['query']}'",
                           "expected": 0, "actual": out.get("match_count")})
    return checks


CHECKS = {"get_ticket": check_get_ticket, "filter_tickets": check_filter_tickets,
          "search_database": check_search_database}


def same(expected, actual) -> bool:
    # Floats like 840.0 can come back as 840 over JSON; compare through one normalization.
    norm = lambda x: json.loads(json.dumps(x, default=str), parse_float=float, parse_int=float)
    return norm(expected) == norm(actual)


async def main(cases_path: str) -> None:
    cases = json.loads(Path(cases_path).read_text())
    config = json.loads((ROOT / ".mcp.json").read_text())
    results = []
    async with Client(config) as client:  # same stdio launch the vibe coder uses
        for case in cases:
            res = await client.call_tool(case["tool"], case["arguments"], raise_on_error=False)
            if res.is_error:  # record the tool's refusal as evidence instead of crashing
                output = {"error": " ".join(getattr(c, "text", "") for c in res.content).strip()}
            else:
                output = res.structured_content if res.structured_content is not None else res.data
                output = output.get("result", output) if isinstance(output, dict) and set(output) == {"result"} else output
            checks = CHECKS[case["tool"]](output, case["arguments"])
            for c in checks:
                c["match"] = same(c["expected"], c["actual"])
            results.append({
                "prompt": case["prompt"],
                "tool": case["tool"],
                "arguments": case["arguments"],
                "tool_output": output,
                "db_verification": {"database": "data/campus_customs_new.db",
                                    "all_match": all(c["match"] for c in checks), "checks": checks},
            })
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "server": {"name": "campus-customs", "framework": "FastMCP", "connection": ".mcp.json (stdio)"},
        "database": "data/campus_customs_new.db",
        "all_tools_match_database": all(r["db_verification"]["all_match"] for r in results),
        "results": results,
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2, default=str) + "\n")
    for r in results:
        print(f"{r['tool']:16} match={r['db_verification']['all_match']}  <- {r['prompt'][:60]}")
    print("wrote", OUT.relative_to(ROOT))


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))
