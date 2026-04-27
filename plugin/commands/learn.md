---
description: Flag the last turn as a correction so reflexio learns from it
allowed-tools: Bash(uv run:*)
argument-hint: [note]
---

Flag the user's previous turn as a correction and force reflexio to run extraction on this session's interactions now.
Run the bash command below and show its output verbatim.

!`uv run --project "$HOME/.reflexio/plugin-root" --quiet python -m claude_smart.cli learn "$ARGUMENTS"`
