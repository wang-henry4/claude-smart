<h1 align="center">
  <br>
  claude-smart
  <br>
</h1>

<h4 align="center">Self-improving <a href="https://claude.com/claude-code" target="_blank">Claude Code</a> plugin — learns from your corrections, not just remembers them.</h4>

<p align="center">
  <a href="LICENSE">
    <img src="https://img.shields.io/badge/License-Apache%202.0-blue.svg" alt="License">
  </a>
  <a href="pyproject.toml">
    <img src="https://img.shields.io/badge/version-0.1.0-green.svg" alt="Version">
  </a>
  <a href="pyproject.toml">
    <img src="https://img.shields.io/badge/python-%3E%3D3.12-brightgreen.svg" alt="Python">
  </a>
  <a href="#installation">
    <img src="https://img.shields.io/badge/llm-claude%20code%20cli-purple.svg" alt="LLM">
  </a>
</p>

<p align="center">
  <a href="#quick-start">Quick Start</a> •
  <a href="#how-it-works">How It Works</a> •
  <a href="#installation">Installation</a> •
  <a href="#slash-commands">Slash Commands</a> •
  <a href="#configuration">Configuration</a> •
  <a href="#troubleshooting">Troubleshooting</a> •
  <a href="#license">License</a>
</p>

<p align="center">
  claude-smart turns your Claude Code corrections into durable rules that shape <i>future</i> sessions. Instead of replaying past observations as context, it distils them into a project playbook and per-session preferences — so Claude stops repeating the same mistakes and adapts to how your codebase actually wants to be written.
</p>

---

## Why Learning, Not Memory

Plain memory solutions preserve *what happened* — they re-inject transcripts, summaries, or observations from prior sessions. That works for continuity, but it has two real limits:

- **It grows with every session.** More memory means more tokens, more context dilution, and diminishing returns as Claude has to re-read a history it can't fully use.
- **It doesn't change behavior.** If you corrected Claude yesterday about a library choice, a test framework, a deployment region — a memory system *remembers the correction happened*, but Claude may still make the same default choice today because nothing updated its decision-making.

claude-smart takes a different approach: **extract, don't accumulate**. Each session's corrections and successful patterns are distilled by an LLM into two small, structured artifacts:

- **User profile** — short, session-scoped preferences Claude should respect right now.
- **Project playbook** — cross-session behavioral rules keyed to your project, with an explicit `trigger` (when the rule applies) and `rationale` (why). Rules are deduplicated, updated, and archived as they evolve.

The result is a compact, always-up-to-date set of instructions Claude reads at the start of every session — measured in *dozens* of tokens rather than thousands, and actually capable of changing behavior.

---

## Quick Start

```bash
# 1. Clone with the reflexio backend submodule
git clone --recurse-submodules https://github.com/ReflexioAI/claude-smart.git
cd claude-smart

# 2. Install dependencies (creates a uv-managed venv, pulls reflexio as a path dep)
uv sync

# 3. Turn on the local providers inside reflexio — no API key required at all
mkdir -p ~/.reflexio
grep -q '^CLAUDE_SMART_USE_LOCAL_CLI=' ~/.reflexio/.env 2>/dev/null \
  || echo 'CLAUDE_SMART_USE_LOCAL_CLI=1' >> ~/.reflexio/.env
grep -q '^CLAUDE_SMART_USE_LOCAL_EMBEDDING=' ~/.reflexio/.env 2>/dev/null \
  || echo 'CLAUDE_SMART_USE_LOCAL_EMBEDDING=1' >> ~/.reflexio/.env

# 4. Start the local reflexio backend (storage + search + extraction orchestrator)
uv run reflexio services start --only backend --no-reload

# 5. Install the plugin into Claude Code (project-level)
mkdir -p .claude && cat > .claude/settings.local.json <<'JSON'
{
  "extraKnownMarketplaces": {
    "claude-smart-local": {
      "source": { "source": "directory", "path": "." }
    }
  },
  "enabledPlugins": { "claude-smart@claude-smart-local": true }
}
JSON
```

Restart Claude Code in this workspace. The first time you correct Claude on something project-specific (*"no, don't use pytest-asyncio — use anyio with trio"*), a playbook rule will be extracted. Every subsequent session in the project starts with that rule injected — automatically, without you asking.

---

## Key Features

- 🧠 **Learn, don't just remember** — Corrections become structured, deduplicated rules, not transcript replays.
- 🎯 **Two-tier scope** — Per-session profiles for the current conversation; cross-session playbooks for the whole project.
- 🔌 **Fully local — no external API keys needed** — Generation runs through your local `claude` CLI; semantic search runs on an in-process ONNX embedder (all-MiniLM-L6-v2). The whole stack works offline.
- 🔎 **Hybrid search** — Playbooks and profiles are indexed with vector + BM25 search for fast, robust retrieval.
- 📥 **Automatic hook ingestion** — `SessionStart`, `UserPromptSubmit`, `PostToolUse`, `Stop`, `SessionEnd` all wired up; you don't run anything manually.
- 🏷️ **Correction-aware** — Corrective phrasings (`"no, don't"`, `"actually"`, `"stop"`, `"wrong"`) are detected and weighted during extraction.
- 🧪 **Offline resilience** — If the reflexio backend is down, hooks buffer to disk; the next successful publish drains them.
- 🧰 **Three slash commands** — `/show`, `/learn`, `/tag` for on-demand control.

---

## How It Works

**Core components:**

1. **5 lifecycle hooks** (`plugin/hooks/hooks.json`)
   - `SessionStart` — fetches the project playbook from reflexio and injects it as `additionalContext`.
   - `UserPromptSubmit` — buffers each user turn, heuristically flags corrections.
   - `PostToolUse` — records tool invocations for later extraction.
   - `Stop` — finalizes the assistant turn from the transcript, publishes to reflexio.
   - `SessionEnd` — flushes the remaining buffer with `force_extraction=True`.
2. **Local state buffer** — JSONL per session at `~/.claude-smart/sessions/{session_id}.jsonl`. Offline-safe.
3. **Reflexio backend** (submodule at `reflexio/`) — SQLite storage, hybrid search, profile/playbook extraction, dedup, status lifecycle (`CURRENT` → `ARCHIVED`). Runs on `localhost:8081`.
4. **Claude Code LLM provider** — a LiteLLM custom provider registered inside reflexio. Every generation call (extraction, update, dedup, evaluation) subprocesses `claude -p --output-format json`, so no OpenAI/Anthropic key is needed for the learning loop.
5. **Three slash commands** — `/show`, `/learn`, `/tag`.

**Data flow:**

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

**Mapping to reflexio:**

| Reflexio field | claude-smart value |
| --- | --- |
| `user_id` | Claude Code `session_id` — scopes profiles to the current conversation |
| `agent_version` | `project_id` (git-toplevel basename) — stable across sessions, so playbooks accumulate project-wide |
| `session_id` | Claude Code `session_id` — for reflexio's deferred success evaluation |

Cross-session playbook retrieval uses `search_user_playbooks(agent_version=project_id, user_id=None)` — playbooks written from any prior session in this project surface for every future session.

---

## Installation

### One-command install

If you just want the plugin wired into Claude Code (marketplace added, plugin installed, `~/.reflexio/.env` seeded with the local-provider flags), run **one** of:

```bash
# uvx — pulls the Python package straight from git, no clone required
uvx --from git+https://github.com/ReflexioAI/claude-smart claude-smart install

# npx — same thing via the published npm wrapper
npx claude-smart install
```

Both do the same three things:

1. `claude plugin marketplace add ReflexioAI/claude-smart`
2. `claude plugin install claude-smart@yilu`
3. Append `CLAUDE_SMART_USE_LOCAL_CLI=1` and `CLAUDE_SMART_USE_LOCAL_EMBEDDING=1` to `~/.reflexio/.env` (idempotent).

You still need to start the reflexio backend yourself the first time (`uv run reflexio services start --only backend --no-reload` from a clone of this repo). Everything else — submodule init, `uv sync` — runs inside Claude Code's `Setup` hook on first session.

For a manual, step-by-step walkthrough, see below.

### Prerequisites

| Tool | Purpose |
| --- | --- |
| [Claude Code](https://claude.com/claude-code) | The host CLI — also used as the LLM backend for extraction |
| [uv](https://docs.astral.sh/uv/) | Python package manager (Python 3.12+) |
| `git` | Needed to clone with submodules and to derive the project id |

> **No external API keys needed.** Generation runs through your local `claude` CLI (via a LiteLLM custom provider). Embeddings run through an in-process ONNX model (`all-MiniLM-L6-v2`, bundled by `chromadb`). Both are opt-in; when enabled, reflexio refuses to fall back to paid APIs.

### Step 1 — Clone the repository (with the reflexio submodule)

```bash
git clone --recurse-submodules https://github.com/ReflexioAI/claude-smart.git
cd claude-smart

# If you forgot --recurse-submodules
git submodule update --init --recursive
```

### Step 2 — Install Python dependencies

```bash
uv sync
```

This creates `.venv/`, pulls `reflexio-ai` as a path dependency from the `reflexio/` submodule, and registers the `claude-smart` and `claude-smart-hook` console scripts.

### Step 3 — Enable the local providers in reflexio

Two env flags turn on the local generation backend (Claude Code CLI) and the local embedder (in-process ONNX). Both live in `~/.reflexio/.env`:

```bash
mkdir -p ~/.reflexio
grep -q '^CLAUDE_SMART_USE_LOCAL_CLI=' ~/.reflexio/.env 2>/dev/null \
  || echo 'CLAUDE_SMART_USE_LOCAL_CLI=1' >> ~/.reflexio/.env
grep -q '^CLAUDE_SMART_USE_LOCAL_EMBEDDING=' ~/.reflexio/.env 2>/dev/null \
  || echo 'CLAUDE_SMART_USE_LOCAL_EMBEDDING=1' >> ~/.reflexio/.env
```

On first use, the embedder downloads the ~80 MB ONNX model once and caches it at `~/.cache/chroma/onnx_models/`. Subsequent starts reuse the cache and stay offline.

### Step 4 — Start the reflexio backend

Run this from the **claude-smart repo root** (not the `reflexio/` subdir) so that `uv run` uses the claude-smart venv — which already has `chromadb` installed for the local embedder and `reflexio-ai` available as a path dep with the `reflexio` CLI script registered:

```bash
uv run reflexio services start --only backend --no-reload
```

You should see a log line like:

```
Registered claude-code LiteLLM provider (cli=/path/to/claude)
Local embedding provider enabled (model=local/minilm-l6-v2)
Auto-detected LLM providers (priority order): ['claude-code', 'local']
Primary provider for generation: claude-code
Embedding provider: local
Application startup complete.
```

Health check:

```bash
curl http://localhost:8081/health
# {"status":"healthy"}
```

Leave this running in a separate terminal. Stop it later with:

```bash
uv run reflexio services stop
```

### Step 5 — Install the plugin into Claude Code

**Project-level (recommended while you evaluate):**

```bash
mkdir -p .claude
cat > .claude/settings.local.json <<JSON
{
  "extraKnownMarketplaces": {
    "claude-smart-local": {
      "source": { "source": "directory", "path": "$PWD" }
    }
  },
  "enabledPlugins": { "claude-smart@claude-smart-local": true }
}
JSON
```

**User-level (all projects):**

Put the same JSON into `~/.claude/settings.json`, using an absolute path for the marketplace `path`.

Restart Claude Code. On the next session start you should see reflexio logs show a `search_user_playbooks` call — that's the SessionStart hook fetching the (currently empty) playbook.

### Step 6 — Sanity check

Inside Claude Code:

```
/show
```

On a fresh project you'll see `_No playbook or profiles yet for project `<name>`._` — correct. Have a conversation, include at least one genuine correction (`"no, don't use X — use Y"`), then:

```
/learn
```

That forces immediate extraction. Run `/show` again after ~20–30 seconds; the extracted rule should appear.

---

## Slash Commands

| Command | What it does |
| --- | --- |
| `/show` | Print the current project playbook plus the current session's user profiles (same markdown that `SessionStart` injects). Use it to audit what rules and preferences Claude is being told to follow. |
| `/learn` | Force reflexio to run extraction *now* on the current session's unpublished interactions. Without this, extraction runs at the end of the session or on reflexio's batch interval. |
| `/tag [note]` | Tag the most recent turn as a correction, for cases the automatic heuristic missed. The note becomes the correction description the extractor sees. |

---

## Configuration

### Environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `CLAUDE_SMART_USE_LOCAL_CLI` | `0` | Set to `1` in `~/.reflexio/.env` to route generation through the local `claude` CLI. |
| `CLAUDE_SMART_USE_LOCAL_EMBEDDING` | `0` | Set to `1` to use the in-process ONNX embedder (requires `chromadb`). |
| `CLAUDE_SMART_CLI_PATH` | `shutil.which("claude")` | Override the path to the `claude` binary. |
| `CLAUDE_SMART_CLI_TIMEOUT` | `120` | Per-call subprocess timeout (seconds). Raise for slow prompts. |
| `CLAUDE_SMART_STATE_DIR` | `~/.claude-smart/sessions/` | Where the per-session JSONL buffer lives. |
| `REFLEXIO_URL` | `http://localhost:8081/` | Point the plugin at a non-local reflexio backend. |

### Where data lives

| Path | What |
| --- | --- |
| `~/.reflexio/data/reflexio.db` | Source of truth — profiles, user_playbooks, interactions, FTS5 indexes, and vec0 embedding tables (plus `.db-shm` / `.db-wal` WAL sidecars). Inspect with `sqlite3`. |
| `~/.reflexio/.env` | Provider config — `CLAUDE_SMART_USE_LOCAL_CLI`, `CLAUDE_SMART_USE_LOCAL_EMBEDDING`, any optional API keys. |
| `~/.claude-smart/sessions/{session_id}.jsonl` | Per-session buffer. User turns, assistant turns, tool invocations, `{"published_up_to": N}` watermarks. Safe to inspect and safe to delete — everything past the latest watermark has already been written to reflexio's DB. |
| `~/.cache/chroma/onnx_models/all-MiniLM-L6-v2/` | Cached ONNX weights (~86 MB, downloaded once). Delete to force a re-download. |

### Scope: profile vs. playbook

- **Profile** (`user_id = session_id`) — session-scoped preferences. Does not persist across sessions, but *is* reinjected if you resume the same session (`/resume`, `/clear`, `/compact`).
- **Playbook** (`agent_version = project_id`) — cross-session. Every session in the same project — identified by git-toplevel basename — sees the accumulated playbook.

### Embeddings

claude-smart uses an in-process ONNX embedder (Chroma's `all-MiniLM-L6-v2`, 384-dim, zero-padded to reflexio's 512-dim schema). The model weights are downloaded on first use (~80 MB, cached under `~/.cache/chroma/onnx_models/`) — after that, no network calls for embedding. Runtime cost is a few milliseconds per short document on CPU.

If you still want to use a cloud embedding provider (OpenAI, Gemini, etc.), omit `CLAUDE_SMART_USE_LOCAL_EMBEDDING` and set the corresponding API key in `~/.reflexio/.env` — reflexio will fall back to its standard provider-priority chain.

---

## How the Claude Code Provider Works

claude-smart ships a small patch to reflexio (`reflexio/server/llm/providers/claude_code_provider.py`) that registers a LiteLLM `CustomLLM` named `claude-code`. Every time reflexio wants to generate, evaluate, or dedup, it ends up in `litellm.completion(model="claude-code/default", ...)` — which routes to our handler. The handler:

1. Splits LiteLLM's messages into `(system_prompt, dialogue)`.
2. Subprocesses `claude -p --output-format json --append-system-prompt "<system>"` with the dialogue on stdin.
3. Parses the JSON stdout into a LiteLLM `ModelResponse` with populated usage tokens.

Registration is opt-in (`CLAUDE_SMART_USE_LOCAL_CLI=1`) and idempotent, so enabling it does not affect users who still want OpenAI/Anthropic — reflexio's normal provider-priority chain stays intact.

---

## Troubleshooting

**SessionStart injects nothing after a correction.**
Extraction is async by default. Run `/learn` to force it, wait ~20–30s, then run `/show` — no new session needed. `/show` shows whether the rule was actually extracted.

**Reflexio refuses to boot with "no embedding-capable provider".**
Check that `CLAUDE_SMART_USE_LOCAL_EMBEDDING=1` is in `~/.reflexio/.env` *and* that `chromadb` is installed in the venv (`uv run python -c "import chromadb"` should print nothing). If you'd rather use a cloud embedder instead, drop the env flag and set `OPENAI_API_KEY` or `GEMINI_API_KEY` in the same file.

**`claude-smart` doesn't see my interactions.**
Check `~/.claude-smart/sessions/`. If your current session's JSONL has no `User`/`Assistant` rows, the plugin isn't receiving hook events — verify `.claude/settings.local.json` has the right path and that `enabledPlugins` is `true`.

**Hooks appear to time out.**
Each hook is capped at 15–60s. If you see long pauses, check `uv` is on PATH (hooks shell out to `uv run`). Set `CLAUDE_SMART_CLI_TIMEOUT=180` to give the LLM provider more headroom.

**A different LLM is being used.**
Reflexio's provider priority is `claude-code > local > anthropic > gemini > ... > openai`. If you have `CLAUDE_SMART_USE_LOCAL_CLI=1` *and* an Anthropic key set, claude-code still wins for generation; `local` sits above openai/gemini for embeddings. Check the startup log line `Primary provider for generation: <name>` and `Embedding provider: <name>` to confirm.

**I want to wipe everything and start over.**
```bash
rm -rf ~/.claude-smart/sessions/
rm -rf ~/.reflexio/data/           # reflexio SQLite store
```

---

## Dashboard (web UI)

A Next.js management UI lives in [`dashboard/`](dashboard/). Use it to browse
local session buffers, inspect extracted user profiles, edit and archive
project playbooks, and tweak the claude-smart environment. It connects to the
same reflexio backend the plugin uses, so run that first.

```bash
# 1. reflexio backend on :8081 (see Step 4 above)
uv run reflexio services start --only backend --no-reload

# 2. install and run the dashboard
cd dashboard
npm install
npm run dev   # http://localhost:3001
```

The dashboard reads `~/.claude-smart/sessions/*.jsonl` directly (server-side)
for in-flight session transcripts and proxies everything else through reflexio.
All state lives where the CLI already keeps it — the dashboard does not
introduce a second source of truth.

---

## Development

Run the test suite:

```bash
# reflexio patch unit tests
cd reflexio
uv run pytest tests/server/llm/ -q -o 'addopts='

# claude-smart package tests
cd ..
uv run pytest tests/ -q
```

Exercise a hook handler directly (useful for debugging without a live Claude Code session):

```bash
echo '{"session_id":"dev-1","source":"startup","cwd":"'"$PWD"'"}' \
  | uv run python -m claude_smart.hook session-start
```

---

## License

This project is licensed under the **Apache License 2.0**. The bundled `reflexio/` submodule is also Apache 2.0. Claude Code is Anthropic's and not covered by this license.

See the [LICENSE](LICENSE) file for details.

---

## Support

- **Issues**: open one on GitHub describing the symptom and include the reflexio startup log (stdout of `uv run reflexio services start`) and the relevant lines of `~/.claude-smart/sessions/{session_id}.jsonl`.
- **Architecture notes**: see the plan file in `.claude/plans/` (if present), which walks through each design decision and the rationale.

---

**Built on** [reflexio](https://github.com/ReflexioAI/reflexio) · **Runs on** [Claude Code](https://claude.com/claude-code) · **Written in** Python 3.12+
