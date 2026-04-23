#!/usr/bin/env bash
# Start backend + dashboard (idempotent), wait briefly for dashboard to come
# up, print statuses, then open http://localhost:3001 in the default browser.
#
# Exists so the /claude-smart:dashboard slash command can invoke a single
# plain `bash <script>` with no inline $(...) or ${...:-...} expansion in
# the command string — Claude Code's permission checker rejects those.
set -eu

HERE="$(cd "$(dirname "$0")" && pwd)"
SCRIPTS="$HERE"

bash "$SCRIPTS/backend-service.sh" start >/dev/null 2>&1 || true
bash "$SCRIPTS/dashboard-service.sh" start >/dev/null 2>&1 || true

status="not running"
for _ in 1 2 3 4 5 6 7 8 9 10; do
    status=$(bash "$SCRIPTS/dashboard-service.sh" status)
    [ "$status" != "not running" ] && break
    sleep 0.3
done

backend_status=$(bash "$SCRIPTS/backend-service.sh" status)
echo "backend:   $backend_status"
echo "dashboard: $status"

python3 -m webbrowser "http://localhost:3001" && echo "Opened http://localhost:3001"
