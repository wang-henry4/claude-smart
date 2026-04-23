# Architecture

Technical reference for how `claude-smart` wires Claude Code's lifecycle hooks to the [reflexio](https://github.com/ReflexioAI/reflexio) backend to produce the user profile and project playbook described in the [README](./README.md#how-it-works). If you're just using the plugin, the README is enough — this file is for people debugging, extending, or integrating with claude-smart.

## Core components

1. **5 lifecycle hooks** (`plugin/hooks/hooks.json`)
   - `SessionStart` — fetches the project playbook from reflexio and injects it as `additionalContext`.
   - `UserPromptSubmit` — buffers each user turn, heuristically flags corrections.
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
Next session → SessionStart → search_user_playbooks(agent_version=project_id)
              → additionalContext injected into Claude's system prompt
```

## Mapping to reflexio

| Reflexio field | claude-smart value |
| --- | --- |
| `user_id` | Claude Code `session_id` — scopes profiles to the current conversation |
| `agent_version` | `project_id` (git-toplevel basename) — stable across sessions, so playbooks accumulate project-wide |
| `session_id` | Claude Code `session_id` — for reflexio's deferred success evaluation |

Cross-session playbook retrieval uses `search_user_playbooks(agent_version=project_id, user_id=None)` — playbooks written from any prior session in this project surface for every future session.

## Extraction signals

Reflexio's playbook extractor only emits rules from two signals:

- **Correction SOPs** — the user rejected the agent's behavior (explicit `/tag`, or heuristically-detected corrective phrasing).
- **Success-path recipes** — completed tasks that produced concrete values, formulas, or tool sequences.

Identity/context facts (e.g. "I'm a data scientist", "we freeze merges Thursday") route to the **profile** only; they don't become playbook rules. This is intentional — see `reflexio/server/services/playbook/playbook_extractor.py` and the playbook prompt v4.0.0 for the full gating logic.
