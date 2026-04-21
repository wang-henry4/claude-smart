---
description: Flag the last turn as a correction so reflexio learns from it
allowed-tools: Bash(uv run:*)
argument-hint: [note]
---

Tag the user's previous turn as a correction for reflexio to learn from.
Run the bash command below and show its output verbatim.

!`_R="${CLAUDE_PLUGIN_ROOT:-$(python3 -c "import json,os; print(json.load(open(os.path.expanduser('~/.claude/plugins/installed_plugins.json')))['plugins']['claude-smart@reflexioai'][0]['installPath'])" 2>/dev/null)}"; uv run --project "$_R" --quiet python -m claude_smart.cli tag "$ARGUMENTS"`
