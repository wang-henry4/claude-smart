---
description: Restart the reflexio backend and dashboard to pick up new changes
allowed-tools: Bash(uv run:*)
---

Run this bash command and show its output verbatim:

!`uv run --project "$HOME/.reflexio/plugin-root" --quiet python -m claude_smart.cli restart`
