---
description: Flag the last turn as a correction so reflexio learns from it
allowed-tools: Bash(uv run:*)
argument-hint: [note]
---

Tag the user's previous turn as a correction for reflexio to learn from.
Run the bash command below and show its output verbatim.

!`uv run --project "$(git rev-parse --show-toplevel 2>/dev/null || pwd)" --quiet python -m claude_smart.cli tag "$ARGUMENTS"`
