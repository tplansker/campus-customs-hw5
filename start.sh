#!/bin/sh
# Start MCP server (8001), backend (8000) and dashboard (localhost:5173). Ctrl-C stops all three.
cd "$(dirname "$0")"
MCP_PORT=${MCP_PORT:-8001}; BACKEND_PORT=${BACKEND_PORT:-8000}
for p in $MCP_PORT $BACKEND_PORT; do
  if lsof -nP -iTCP:$p -sTCP:LISTEN >/dev/null 2>&1; then
    echo "Port $p is already in use (pid $(lsof -t -iTCP:$p -sTCP:LISTEN | tr '\n' ' ')). Stop it first."; exit 1
  fi
done

PIDS=""
cleanup() {
  trap - INT TERM EXIT
  echo "Stopping Campus Customs (pids $PIDS)..."
  for pid in $PIDS; do pkill -TERM -P "$pid" 2>/dev/null; kill -TERM "$pid" 2>/dev/null; done
  wait
}
trap cleanup INT TERM EXIT

.venv/bin/python -m mcp_server.server & PIDS="$PIDS $!"
sleep 2
(cd backend && exec ../.venv/bin/uvicorn main:app --port "$BACKEND_PORT") & PIDS="$PIDS $!"
VITE_API_URL="http://localhost:$BACKEND_PORT" npm --prefix frontend run dev & PIDS="$PIDS $!"
echo "Dashboard: http://localhost:5173 (or the next free port Vite prints)"
wait
