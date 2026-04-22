---
description: Delete ALL reflexio interactions, profiles, and user playbooks (destructive)
allowed-tools: Bash(uv run:*)
---

Run this bash command and show its output verbatim:

!`uv run --project "${CLAUDE_PLUGIN_ROOT:-$HOME/.claude/plugins/marketplaces/reflexioai/plugin}" --quiet python -m claude_smart.cli clear-all --yes`
