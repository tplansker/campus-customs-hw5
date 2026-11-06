"""Append-only audit trail: output/audit_trail.json.

One JSON object per agent-loop step (model request, model response, tool call, tool result,
delegation, reply, decision, error, human action). The file is a JSON array that only ever grows:
each append reads it, adds the new entry and replaces the file atomically. Resetting the database
does not touch it.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

AUDIT_PATH = Path(__file__).resolve().parents[2] / "output" / "audit_trail.json"
_lock = threading.Lock()


def _load() -> list:
    try:
        data = json.loads(AUDIT_PATH.read_text(encoding="utf-8") or "[]")
    except FileNotFoundError:
        return []
    except json.JSONDecodeError:
        # Never overwrite a file we can't parse; keep it and start a sibling copy.
        AUDIT_PATH.rename(AUDIT_PATH.with_suffix(f".corrupt-{datetime.now():%Y%m%d%H%M%S}.json"))
        return []
    return data if isinstance(data, list) else [data]


def audit(entry: dict[str, Any]) -> None:
    """Append one entry. Safe across the concurrent tool calls of one process."""
    with _lock:
        entries = _load()
        entry = {"seq": (entries[-1].get("seq", len(entries)) + 1) if entries else 1,
                 "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"), **entry}
        entries.append(entry)
        AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=AUDIT_PATH.parent, prefix=".audit_", suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(entries, f, indent=1, default=str)
            f.write("\n")
        os.chmod(tmp, 0o644)  # mkstemp creates 0600; keep the audit file readable like other outputs
        os.replace(tmp, AUDIT_PATH)
