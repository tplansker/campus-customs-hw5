"""Shared database access for the MCP server and the FastAPI backend.

Both processes read CAMPUS_DB_PATH (default data/campus_customs_new.db), which is the
*working copy*. The pristine data/campus_customs.db is only ever read by reset_working_db().
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import stat
from contextlib import contextmanager
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Nearest .env wins (load_dotenv never overrides a variable that is already set).
for folder in [PROJECT_ROOT, *PROJECT_ROOT.parents[:3]]:
    load_dotenv(folder / ".env")

ORIGINAL_DB = PROJECT_ROOT / "data" / "campus_customs.db"


def _resolve(path_str: str) -> Path:
    p = Path(path_str)
    return p if p.is_absolute() else (PROJECT_ROOT / p).resolve()


DB_PATH = _resolve(os.getenv("CAMPUS_DB_PATH", "data/campus_customs_new.db"))

if DB_PATH == ORIGINAL_DB.resolve():
    raise RuntimeError("CAMPUS_DB_PATH points at the original campus_customs.db; point it at the working copy.")

# Tables the original data does not have. Created on demand so a freshly reset copy works.
EXTRA_SCHEMA = """
CREATE TABLE IF NOT EXISTS approvals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id INTEGER,
    kind TEXT NOT NULL,              -- payment | purchase_order | discount
    summary TEXT NOT NULL,
    amount REAL,
    payload TEXT NOT NULL,           -- JSON
    requested_by TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',   -- pending | approved | rejected | failed
    decided_by TEXT,
    decision_note TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    decided_at TEXT
);
CREATE TABLE IF NOT EXISTS purchase_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id INTEGER,
    vendor_id INTEGER NOT NULL REFERENCES vendors(id),
    sku TEXT NOT NULL,
    size TEXT NOT NULL,
    qty INTEGER NOT NULL,
    unit_cost REAL NOT NULL,
    total REAL NOT NULL,
    ordered_at TEXT NOT NULL,        -- shop date (desk.date_today)
    eta TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ordered'
);
-- Safety net under the tools: cash can never go negative, and (no revenue modeled) never goes up.
CREATE TRIGGER IF NOT EXISTS cash_no_negative BEFORE UPDATE OF balance ON cash_accounts
WHEN NEW.balance < 0
BEGIN SELECT RAISE(ABORT, 'Insufficient funds: balance may not go negative'); END;
CREATE TRIGGER IF NOT EXISTS cash_only_goes_out BEFORE UPDATE OF balance ON cash_accounts
WHEN NEW.balance > OLD.balance
BEGIN SELECT RAISE(ABORT, 'No revenue is modeled: cash balances may only decrease'); END;
CREATE TABLE IF NOT EXISTS customer_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id INTEGER,
    recipient TEXT NOT NULL,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    drafted_by TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',     -- draft | approved | discarded  (never emailed)
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS stock_movements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id INTEGER,
    sku TEXT NOT NULL,
    size TEXT NOT NULL,
    delta INTEGER NOT NULL,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS agent_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT,
    ticket_id INTEGER,
    agent TEXT NOT NULL,
    kind TEXT NOT NULL,              -- run_started | thinking | tool_call | tool_result | delegate | reply | decision | error | human
    content TEXT NOT NULL,           -- JSON
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE TABLE IF NOT EXISTS ticket_runs (
    id TEXT PRIMARY KEY,
    ticket_id INTEGER NOT NULL,
    status TEXT NOT NULL,            -- running | done | error
    decision TEXT,
    summary TEXT,
    started_at TEXT NOT NULL DEFAULT (datetime('now')),
    finished_at TEXT
);
"""


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(EXTRA_SCHEMA)


@contextmanager
def connect():
    """Open the working DB, make sure extra tables exist, commit on success."""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        ensure_schema(conn)
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def rows(cur) -> list[dict]:
    return [dict(r) for r in cur.fetchall()]


def shop_date(conn: sqlite3.Connection) -> str:
    row = conn.execute("SELECT date_today FROM desk LIMIT 1").fetchone()
    return row["date_today"] if row else ""


def reset_working_db() -> None:
    """Overwrite the working copy with the untouched original."""
    shutil.copyfile(ORIGINAL_DB, DB_PATH)
    DB_PATH.chmod(DB_PATH.stat().st_mode | stat.S_IWUSR)
    with connect():
        pass
