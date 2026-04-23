---
description: Flag the last turn as a correction so reflexio learns from it
allowed-tools: Bash(uv run:*)
argument-hint: [note]
---

Tag the user's previous turn as a correction for reflexio to learn from.
Run the bash command below and show its output verbatim.

!`uv run --project "$HOME/.reflexio/plugin-root" --quiet python -m claude_smart.cli tag "$ARGUMENTS"`
