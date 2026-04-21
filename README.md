<p align="center">
  <img src="assets/claude-smart-icon.png" alt="claude-smart" width="140">
</p>

<h1 align="center">
  claude-smart
</h1>

<h4 align="center">The <a href="https://claude.com/claude-code" target="_blank">Claude Code</a> plugin that makes Claude Code self-improve as you use it — not by remembering past sessions, but by turning your corrections into rules it actually follows next time.</h4>

<p align="center">
  <a href="LICENSE">
    <img src="https://img.shields.io/badge/License-Apache%202.0-blue.svg" alt="License">
  </a>
  <a href="plugin/pyproject.toml">
    <img src="https://img.shields.io/badge/version-0.1.4-green.svg" alt="Version">
  </a>
  <a href="plugin/pyproject.toml">
    <img src="https://img.shields.io/badge/python-%3E%3D3.12-brightgreen.svg" alt="Python">
  </a>
  <a href="#quick-start">
    <img src="https://img.shields.io/badge/llm-claude%20code%20cli-purple.svg" alt="LLM">
  </a>
</p>

<p align="center">
  <a href="#quick-start">Quick Start</a> •
  <a href="#how-it-works">How It Works</a> •
  <a href="#slash-commands">Slash Commands</a> •
  <a href="#dashboard">Dashboard</a> •
  <a href="#configuration">Configuration</a> •
  <a href="#troubleshooting">Troubleshooting</a> •
  <a href="#license">License</a>
</p>

<p align="center">
  Every time you correct Claude Code, claude-smart turns that moment into a durable rule it follows from then on. No more re-explaining your stack, your conventions, or the same gotcha you flagged last week — Claude Code steadily adapts to how <i>your</i> codebase actually wants to be written, session after session.
</p>

<p align="center">
  <b>Head-to-head vs <code>claude-mem</code></b> (LLM-judged on how well each system's reinjected context matches the expected rule): claude-smart is <b>~2.7× more accurate overall</b>, <b>stops Claude from repeating mistakes you've already corrected</b> where claude-mem only recalls that they happened, and is <b>3× better at turning past events into future-facing rules</b> — see <a href="benchmarks/memory_comparison/EXPERIMENT.md">EXPERIMENT.md</a> for details.
</p>

---

## Why Learning, Not Memory

Plain memory solutions re-inject transcripts or summaries from prior sessions — useful for continuity, but purely informative. claude-smart extracts *rules* from those sessions instead. Four ways that changes what Claude Code can do for you:

- **Actionable, not just informative.** Memory logs *what happened*; learning produces *rules to follow* that change the next decision.
  > *e.g.* you told Claude to stop running `npm test` without `--run` because it hangs on watch mode. **Memory** recalls "user was annoyed about npm test hanging". **Learning** writes the rule *"always pass `--run` to `npm test` in this repo — default watch mode blocks CI"* and applies it next session.
- **Preferences, not events.** Memory records literal facts; learning abstracts the *why* into rules that generalize.
  > *e.g.* you reject Jest in favor of Vitest once. **Memory** stores that single choice. **Learning** derives *"prefer ESM-native test runners for this TypeScript monorepo"* — which also covers the next framework decision (e.g. picking `tsx` over `ts-node`) without waiting for the same correction to repeat.
- **Carries across sessions and workspaces.** Playbooks are keyed to the project and surface in every future session against that repo.
- **Compact.** Distilled, deduplicated rules stay in dozens of tokens — not thousands — even as the project grows.

claude-smart's approach: **extract, don't accumulate**. Corrections and successful patterns are distilled into two artifacts — a session-scoped **user profile** and a cross-session **project playbook** (each rule with explicit `trigger` and `rationale`, deduplicated and archived as they evolve) — and reinjected at the start of every session.

---

## Quick Start

```bash
npx claude-smart install     # or: uvx claude-smart install
```

Or run the equivalent marketplace commands directly inside Claude Code:

```text
/plugin marketplace add ReflexioAI/claude-smart
/plugin install claude-smart@reflexioai
```

Then restart Claude Code.

To uninstall: `/plugin uninstall claude-smart@reflexioai`.

Developing the plugin itself? See [DEVELOPER.md](./DEVELOPER.md#developing-locally).

---

## Key Features

- 🧠 **Learn, don't just remember** — Corrections become structured, deduplicated rules, not transcript replays.
- ⚡ **Fully automatic learning** — Every user turn, tool call, and assistant response is captured via lifecycle hooks and extracted into rules without you running anything.
- 📈 **Compounds with every session** — Rules auto-merge, supersede, and archive as your project evolves — the playbook sharpens with use instead of bloating.
  > *e.g.* you correct the same `npm test --run` gotcha twice → **claude-smart** consolidates them into one stronger rule. Later you switch the policy to `pnpm test` → the old rule is archived and the new one supersedes it, no manual cleanup.
- 🎯 **Two-tier scope** — Per-session profiles for the current conversation; cross-session playbooks for the whole project.
- 🔌 **No external API call** — semantic search runs on an in-process ONNX embedder (all-MiniLM-L6-v2), and all data (profiles, playbooks, interaction buffers) is stored locally on your machine (`~/.reflexio/` and `~/.claude-smart/`).
- 🔎 **Hybrid search** — Playbooks and profiles are indexed with vector + BM25 search for fast, robust retrieval.
- 🧪 **Offline resilience** — If the reflexio backend is down, hooks buffer to disk; the next successful publish drains them.
- 🧰 **Manual correction tag** — `/claude-smart:tag` flags the last turn as a correction so the extractor weights it heavily.

---

## Slash Commands

| Command | What it does |
| --- | --- |
| `/show` | Print the current project playbook plus the current session's user profiles (same markdown that `SessionStart` injects). Use it to audit what rules and preferences Claude is being told to follow. |
| `/learn` | Force reflexio to run extraction *now* on the current session's unpublished interactions. Without this, extraction runs at the end of the session or on reflexio's batch interval. |
| `/tag [note]` | Tag the most recent turn as a correction, for cases the automatic heuristic missed. The note becomes the correction description the extractor sees. |

---

## Dashboard

A Next.js web UI lives in [`plugin/dashboard/`](plugin/dashboard/) for browsing session buffers, inspecting user profiles, and editing project playbooks. It auto-starts alongside the backend — just open **http://localhost:3001**.

---

## How It Works

As you work, claude-smart builds two things and hands them back to Claude at the start of every new session:

### Your user profile — *who you are, this session*

A quick sketch of how you want to work right now — your stack, your role, small preferences you've dropped into the conversation. Scoped to the current session, so it doesn't follow you into unrelated projects.

> *Examples:*
> - *Uses pnpm, not npm.*
> - *Prefers terse answers, no trailing summaries.*
> - *Backend engineer — explain frontend code with backend analogues.*

### The project playbook — *durable rules, every session*

A growing list of **rules for this project**, pulled from every session you've ever run in it. Each rule says when it applies and why it exists.

> *Examples:*
> - *Always pass `--run` to `npm test` — default watch mode hangs CI.*
> - *Use a real Postgres for integration tests, not mocks — mocks once hid a broken migration.*
> - *Prefer ESM-native test runners in this monorepo.*

Rules clean themselves up: correct the same thing twice and they merge; change your mind later and the old one is archived.

### How it runs

1. You have a normal Claude Code session.
2. claude-smart quietly watches your turns, tool calls, and Claude's replies — flagging corrections automatically (or anything you `/tag`).
3. When the session ends (or you run `/learn`), it turns what happened into profile entries and playbook rules.
4. Next session, both get injected into Claude's system prompt. Run `/show` any time to see what Claude is being told.

No chat, no prompts to rewrite, no config files to groom. Everything runs on your machine.

See [ARCHITECTURE.md](./ARCHITECTURE.md) for the hooks, data flow, and reflexio details.

---

## Configuration

### Environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `CLAUDE_SMART_USE_LOCAL_CLI` | `0` (installer sets `1`) | Route generation through the local `claude` CLI. Written to `~/.reflexio/.env` by `claude-smart install`. |
| `CLAUDE_SMART_USE_LOCAL_EMBEDDING` | `0` (installer sets `1`) | Use the in-process ONNX embedder (requires `chromadb`). Written to `~/.reflexio/.env` by `claude-smart install`. |
| `CLAUDE_SMART_CLI_PATH` | `shutil.which("claude")` | Override the path to the `claude` binary. |
| `CLAUDE_SMART_CLI_TIMEOUT` | `120` | Per-call subprocess timeout (seconds). Raise for slow prompts. |
| `CLAUDE_SMART_STATE_DIR` | `~/.claude-smart/sessions/` | Where the per-session JSONL buffer lives. |
| `CLAUDE_SMART_BACKEND_AUTOSTART` | `1` | Set to `0` to stop the SessionStart hook from spawning the reflexio backend on `localhost:8081`. |
| `CLAUDE_SMART_DASHBOARD_AUTOSTART` | `1` | Set to `0` to stop the SessionStart hook from spawning the Next.js dashboard on `localhost:3001`. |
| `CLAUDE_SMART_BACKEND_STOP_ON_END` | `0` | Set to `1` to tear down the backend at `SessionEnd` instead of leaving it long-lived. |
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

## Troubleshooting

**SessionStart injects nothing after a correction.**
Extraction is async by default. Run `/learn` to force it, wait ~20–30s, then run `/show` — no new session needed. `/show` shows whether the rule was actually extracted.

**Reflexio refuses to boot with "no embedding-capable provider".**
Check that `CLAUDE_SMART_USE_LOCAL_EMBEDDING=1` is in `~/.reflexio/.env` *and* that `chromadb` is installed in the venv (`uv run --project plugin python -c "import chromadb"` should print nothing). If you'd rather use a cloud embedder instead, drop the env flag and set `OPENAI_API_KEY` or `GEMINI_API_KEY` in the same file.

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

## License

This project is licensed under the **Apache License 2.0**. The bundled `reflexio/` submodule is also Apache 2.0. Claude Code is Anthropic's and not covered by this license.

See the [LICENSE](LICENSE) file for details.

---

## Support

- **Issues**: open one on GitHub describing the symptom and include the reflexio backend log (`~/.claude-smart/backend.log`) and the relevant lines of `~/.claude-smart/sessions/{session_id}.jsonl`.

---

**Built on** [reflexio](https://github.com/ReflexioAI/reflexio) · **Runs on** [Claude Code](https://claude.com/claude-code) · **Written in** Python 3.12+
