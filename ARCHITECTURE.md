# Architecture

Technical reference for how `claude-smart` wires Claude Code's lifecycle hooks to the [reflexio](https://github.com/ReflexioAI/reflexio) backend to produce the user profile and project playbook described in the [README](./README.md#how-it-works). If you're just using the plugin, the README is enough — this file is for people debugging, extending, or integrating with claude-smart.

## Core components

1. **6 lifecycle hooks** (`plugin/hooks/hooks.json`)
   - `SessionStart` — fetches the playbook from reflexio and injects it as `additionalContext`.
   - `UserPromptSubmit` — buffers each user turn, heuristically flags corrections, and searches reflexio with the prompt text to inject matching profile/playbook hits as `additionalContext`.
   - `PreToolUse` — searches reflexio keyed on the first line of the tool-call text (Bash command, Edit `new_string`, etc.) and injects top matches as `additionalContext`.
   - `PostToolUse` — records tool invocations for later extraction.
   - `Stop` — finalizes the assistant turn from the transcript, publishes to reflexio.
   - `SessionEnd` — flushes the remaining buffer with `force_extraction=True`.
2. **Local state buffer** — JSONL per session at `~/.claude-smart/sessions/{session_id}.jsonl`. Offline-safe.
3. **Reflexio backend** (submodule at `reflexio/`) — SQLite storage, hybrid search, profile/playbook extraction, dedup, status lifecycle (`CURRENT` → `ARCHIVED`). Runs on `localhost:8071`.
4. **Claude Code LLM provider** — a LiteLLM custom provider registered inside reflexio. Every generation call (extraction, update, dedup, evaluation) subprocesses `claude -p --output-format json`, so no OpenAI/Anthropic key is needed for the learning loop.

## Data flow

```
Claude Code session
  ├─ UserPromptSubmit ─┐
  ├─ PostToolUse  ─────┤  → JSONL buffer ─→ Stop ─→ reflexio publish_interaction
  └─ Stop         ─────┘                              │
                                                      ▼
                                        ┌─────────────────────────┐
                                        │ reflexio extractors     │
                                        │  (run via claude -p)    │
                                        │  → profiles + playbooks │
                                        └────────────┬────────────┘
                                                     │
                                                     ▼
Next session → SessionStart → search_user_playbooks (no agent_version/user_id filter)
              → additionalContext injected into Claude's system prompt
```

## Mapping to reflexio

| Reflexio field | claude-smart value |
| --- | --- |
| `user_id` | `project_id` (git-toplevel basename) — scopes profiles to the current project |
| `agent_version` | `project_id` on *write*; no filter on *read* — playbooks are tagged by project for provenance but retrieved globally |
| `session_id` | Claude Code `session_id` — for reflexio's deferred success evaluation |

Playbook retrieval is global: `fetch_playbooks` / `search_playbooks` in `plugin/src/claude_smart/reflexio_adapter.py` call `search_user_playbooks` with no `agent_version` / `user_id` filter, so every playbook written on this machine surfaces for every future session regardless of project.

## Extraction signals

Reflexio's playbook extractor only emits rules from two signals:

- **Correction SOPs** — the user rejected the agent's behavior (explicit `/learn`, or heuristically-detected corrective phrasing).
- **Success-path recipes** — completed tasks that produced concrete values, formulas, or tool sequences.

Identity/context facts (e.g. "I'm a data scientist", "we freeze merges Thursday") route to the **profile** only; they don't become playbook rules. This is intentional — see `reflexio/server/services/playbook/playbook_extractor.py` and the playbook prompt v4.0.0 for the full gating logic.
