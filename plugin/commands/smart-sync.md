---
description: Force reflexio to run extraction on this session's interactions now
allowed-tools: Bash(uv run:*)
---

Run this bash command and show its output verbatim:

!`uv run --project "$(git rev-parse --show-toplevel 2>/dev/null || pwd)" --quiet python -m claude_smart.cli sync`
