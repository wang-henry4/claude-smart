---
description: Force reflexio to run extraction on this session's interactions now
allowed-tools: Bash(uv run:*)
---

Run this bash command and show its output verbatim:

!`_R="${CLAUDE_PLUGIN_ROOT:-$(python3 -c "import json,os; print(json.load(open(os.path.expanduser('~/.claude/plugins/installed_plugins.json')))['plugins']['claude-smart@reflexioai'][0]['installPath'])" 2>/dev/null)}"; uv run --project "$_R" --quiet python -m claude_smart.cli learn`
