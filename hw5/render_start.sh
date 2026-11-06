#!/bin/sh
# Hosted start (Render): MCP server in the background, then the FastAPI backend, which also serves
# the built React board. One public URL; the MCP server stays private on 127.0.0.1.
# Locally you can try it with:  PORT=8030 DESK_PASSWORD=test ./render_start.sh
set -e
cd "$(dirname "$0")"
PY=python
[ -x .venv/bin/python ] && PY="$(pwd)/.venv/bin/python"
MCP_PORT=${MCP_PORT:-8001}
export MCP_URL="http://127.0.0.1:$MCP_PORT/mcp"

chmod u+w data/campus_customs_new.db 2>/dev/null || true

MCP_PORT=$MCP_PORT "$PY" -m mcp_server.server &
MCP_PID=$!
trap 'kill $MCP_PID 2>/dev/null' EXIT INT TERM

# Wait (up to 30s) for the MCP server to accept connections before the backend starts.
"$PY" - "$MCP_PORT" <<'PY'
import socket, sys, time
port = int(sys.argv[1])
for _ in range(60):
    try:
        socket.create_connection(("127.0.0.1", port), timeout=1).close()
        sys.exit(0)
    except OSError:
        time.sleep(0.5)
sys.exit("MCP server did not start")
PY

cd backend
"$PY" -m uvicorn main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips '*'
