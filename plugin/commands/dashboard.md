---
description: Open the claude-smart dashboard (http://localhost:3001) in the browser, starting the backend and dashboard if they aren't running
allowed-tools: Bash(bash:*)
---

Run this bash command and show its output verbatim:

!`bash -c 'PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$HOME/.claude/plugins/marketplaces/reflexioai/plugin}"; SCRIPTS="$PLUGIN_ROOT/scripts"; bash "$SCRIPTS/backend-service.sh" start >/dev/null 2>&1 || true; bash "$SCRIPTS/dashboard-service.sh" start >/dev/null 2>&1 || true; for _ in 1 2 3 4 5 6 7 8 9 10; do status=$(bash "$SCRIPTS/dashboard-service.sh" status); [ "$status" != "not running" ] && break; sleep 0.3; done; echo "backend:   $(bash "$SCRIPTS/backend-service.sh" status)"; echo "dashboard: $status"; python3 -m webbrowser "http://localhost:3001" && echo "Opened http://localhost:3001"'`
