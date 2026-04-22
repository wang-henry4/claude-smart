# Developer Guide

Internal notes for maintainers of `claude-smart`. End-user install instructions live in [README.md](./README.md); this file covers the release loop.

## Repository layout

| Path | Purpose |
| --- | --- |
| `plugin/` | Claude Code plugin — hooks, slash commands, install script, and the Python package |
| `plugin/src/claude_smart/` | Python package — hook handler, CLI, reflexio adapter |
| `plugin/bin/` | User-invoked helper scripts (e.g. `cs-cite`) installed into `~/.claude-smart/bin/` at runtime |
| `plugin/pyproject.toml` | Python manifest — shipped to PyPI via `uv build --project plugin` |
| `tests/` | Pytest suite for the Python package (run via `uv run --project plugin pytest tests/ -q` from repo root) |
| `bin/claude-smart.js` | Node wrapper so `npx claude-smart install` works |
| `package.json` | npm manifest — only ships `bin/`, `README.md`, `LICENSE` |
| `.claude-plugin/plugin.json` | Plugin metadata read by Claude Code |
| `.claude-plugin/marketplace.json` | Marketplace entry — `claude plugin marketplace add` reads this |
| `reflexio/` | Submodule — Apache 2.0, storage + search + extraction backend |
| `plugin/dashboard/` | Next.js management UI for interactions, profiles, playbooks, configuration |
| `Makefile` | Release automation |

## Environment variables

Tunables read by the plugin at runtime. Most users don't need to touch these — the installer writes the local-provider flags to `~/.reflexio/.env` and sensible defaults cover the rest.

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

## Scope: profile vs. playbook

Both profiles and playbooks are project-scoped (since the 88cb150 refactor), identified by the git-toplevel basename of the working directory. What differs is the extractor channel and the shape of the record:

- **Profile** (reflexio's `user_id = project_id`) — personal preferences ("prefers anyio over asyncio"). Free-form bullets.
- **Playbook** (reflexio's `agent_version = project_id`) — project-specific rules with trigger and rationale ("when writing a script, use pathlib — os.path is error-prone").

## Dashboard

A standalone Next.js app at `plugin/dashboard/` that gives a visual view of what
claude-smart has learned:

- **Interactions** — session list + transcript reader backed by
  `~/.claude-smart/sessions/*.jsonl` (read server-side in
  `plugin/dashboard/app/api/sessions/route.ts`).
- **Profiles / Playbooks** — reflexio data fetched via a proxy route
  (`plugin/dashboard/app/api/reflexio/[...path]/route.ts`) that forwards to the URL
  configured in the top bar; defaults to `http://localhost:8081`.
- **Configure** — reads and writes `~/.reflexio/.env`, but only the known
  claude-smart keys. Unknown keys (API secrets, user additions) are preserved
  on write and never returned to the browser.

Stack mirrors `reflexio/docs/` exactly (Next.js 16, Tailwind v4, shadcn
base-nova, Base UI primitives, Lucide icons, `next-themes`). Runs on port
3001 so it can coexist with reflexio's docs site on 3000.

```bash
cd plugin/dashboard
npm install
npm run dev     # http://localhost:3001
npm run build
npm run lint
```

**Next.js 16 caveat** — the same one reflexio/docs flags: APIs and
conventions differ from anything pre-16. Before touching route handlers or
dynamic-param types, consult `plugin/dashboard/node_modules/next/dist/docs/`.

## Versioning

`claude-smart` uses [semver](https://semver.org/). Four files carry the version and **must stay in lockstep** — if they drift, the npm wrapper, PyPI wheel, plugin metadata, and marketplace entry can claim different versions, and users see confusing mismatches in `claude plugin list` vs. `npm view claude-smart version`.

| File | Field |
| --- | --- |
| `package.json` | `.version` |
| `plugin/pyproject.toml` | `project.version` |
| `.claude-plugin/plugin.json` | `.version` |
| `.claude-plugin/marketplace.json` | `.plugins[0].version` |

Don't edit these by hand — use `make bump`.

## Release flow

### Prerequisites — one-time setup

1. **npm**: `npm login` (writes a token to `~/.npmrc`).
2. **PyPI**: create a project-scoped token at <https://pypi.org/manage/account/token/> and export it:
   ```bash
   export UV_PUBLISH_TOKEN=pypi-AgEN...
   ```
   Persist it in your shell rc if you release frequently.
3. **git**: push access to `origin` for the tag push at the end of `make release`.

### Every release

```bash
# 1. Make sure you're on a clean main (no staged/unstaged edits).
git checkout main
git pull --ff-only

# 2. Dry-run to confirm what will ship (optional but cheap).
make publish-dry
#   → npm: tarball ~13 KB, 4 files: bin/claude-smart.js, LICENSE, README.md, package.json
#   → PyPI: dist/ contains a wheel + sdist

# 3. One-shot release. Bumps, commits, tags v$VERSION, publishes to both
#    registries, pushes the commit and tag.
make release VERSION=0.1.1
```

`make release` runs these steps in order and aborts on the first failure:

1. `check-version` — regex-validates `VERSION` as semver.
2. `check-clean` — refuses to run with a dirty working tree.
3. `bump` — rewrites the four version strings.
4. `git add` + `git commit -m "Release v$VERSION"`.
5. `git tag -a v$VERSION`.
6. `publish-npm` → `npm publish --access public`.
7. `publish-pypi` → `rm -rf dist/ && uv build && uv publish`.
8. `git push --follow-tags`.

Because publish happens **before** the push, a registry failure (e.g. auth expired) leaves the commit and tag local — you can fix the cause and re-run `make publish && git push --follow-tags` without re-bumping.

### Partial / advanced flows

```bash
# Just bump the version. Useful when you want to edit CHANGELOG, amend the
# commit message, or split the bump across branches.
make bump VERSION=0.1.1
git diff                                          # inspect
git commit -am "Release v0.1.1"
git tag -a v0.1.1 -m "Release v0.1.1"
make publish                                      # both registries
git push --follow-tags

# Only one registry (e.g. if the other published successfully and you're retrying).
make publish-npm
make publish-pypi

# Preview without uploading anything.
make publish-dry
```

`make help` prints the full target list.

### How users pick up the new release

Once published, end users update to the latest version with either:

```bash
npx claude-smart update     # or: uvx claude-smart update
```

Both wrap `claude plugin update claude-smart@reflexioai`. Users restart Claude Code to apply.

## Pre-release checklist

Before running `make release`:

- [ ] `README.md` reflects any user-visible changes.
- [ ] Hook behavior, CLI flags, env vars are unchanged — or a migration note is in the README.
- [ ] `plugin/hooks/hooks.json` and `plugin/commands/*.md` render correctly in a local Claude Code session (smoke test: install from a local `directory` marketplace, start a session, run `/show`).
- [ ] `reflexio` submodule is at the pinned SHA you want to ship against. Bump it explicitly if needed:
  ```bash
  cd reflexio && git pull && cd .. && git add reflexio && git commit -m "Bump reflexio submodule"
  ```
- [ ] `npm publish --dry-run` tarball is still ~13 KB / 4 files — if it's larger, `files` in `package.json` is letting extra content through.
- [ ] If you touched `pyproject.toml` dependencies, `uv build` succeeds locally and the wheel's `METADATA` doesn't carry a `file://` path dep (common failure when `[tool.uv.sources]` leaks into the published wheel).

## Common failures and fixes

**`npm publish` fails with `403 Forbidden`.**
Usually means the version already exists. Check `npm view claude-smart versions`. npm does not allow re-uploading the same version — bump and re-release.

**`uv publish` fails with `400 File already exists`.**
Same as above for PyPI. Bump and re-release.

**`uv build` produces a wheel that fails to install with `No matching distribution found for reflexio-ai`.**
The `[tool.uv.sources]` override in `pyproject.toml` points `reflexio-ai` to a local path — fine for local dev, fatal for a published wheel. Either:
1. Publish `reflexio-ai` to PyPI first, then remove the `[tool.uv.sources]` block before `make release`, or
2. Drop `reflexio-ai` from the published package's `dependencies` and keep the install-time bootstrap (`plugin/scripts/smart-install.sh`) responsible for installing it inside the Claude Code plugin directory.

See README's "Step 1 — Install the plugin" section for the install flow that assumes option 2.

**`make release` committed and tagged but `npm publish` failed after.**
`publish` runs before `git push --follow-tags`, so nothing was pushed. Fix the cause (auth, network, registry), then:
```bash
make publish           # retry both, or publish-npm / publish-pypi individually
git push --follow-tags
```
If you need to *unwind* the local commit and tag:
```bash
git tag -d v$VERSION
git reset --hard HEAD~1
```

**`make bump` left `.bak` files behind.**
A sed failure mid-run can leave `*.bak` siblings. Safe to delete:
```bash
rm -f package.json.bak pyproject.toml.bak .claude-plugin/*.bak
```

## Developing locally

For iterating on claude-smart itself — editing hooks, the Python package, the reflexio patch, or the install CLIs — install from a clone and point Claude Code at your working copy. This is the setup end users *don't* need; the `npx`/`uvx` install flow in the README covers them.

### Step 1 — Clone with the reflexio submodule

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

Creates `.venv/`, pulls `reflexio-ai` as a path dep from `reflexio/`, and registers the `claude-smart` and `claude-smart-hook` console scripts.

### Step 3 — Enable the local providers in reflexio

```bash
mkdir -p ~/.reflexio
grep -q '^CLAUDE_SMART_USE_LOCAL_CLI=' ~/.reflexio/.env 2>/dev/null \
  || echo 'CLAUDE_SMART_USE_LOCAL_CLI=1' >> ~/.reflexio/.env
grep -q '^CLAUDE_SMART_USE_LOCAL_EMBEDDING=' ~/.reflexio/.env 2>/dev/null \
  || echo 'CLAUDE_SMART_USE_LOCAL_EMBEDDING=1' >> ~/.reflexio/.env
```

(Equivalent to what the published install wrapper does for end users.) On first use the embedder downloads the ~80 MB ONNX model once to `~/.cache/chroma/onnx_models/`.

### Step 4 — Start the reflexio backend

Run from the `plugin/` directory (where `pyproject.toml` and `uv.lock` live) so that `uv run` uses the claude-smart venv — which already has `chromadb` installed for the local embedder and `reflexio-ai` available with the `reflexio` CLI script registered:

```bash
cd plugin && uv run reflexio services start --only backend --no-reload
```

Expected log lines:

```
Registered claude-code LiteLLM provider (cli=/path/to/claude)
Local embedding provider enabled (model=local/minilm-l6-v2)
Auto-detected LLM providers (priority order): ['claude-code', 'local']
Primary provider for generation: claude-code
Embedding provider: local
Application startup complete.
```

Health check: `curl http://localhost:8081/health` → `{"status":"healthy"}`. Stop with `uv run reflexio services stop`.

### Step 5 — Pick an install mode: local working copy vs. remote marketplace

`claude-smart` can be loaded two ways, and you can only have **one enabled at a time**. Claude Code merges `enabledPlugins` across user + project scopes, so enabling both spawns duplicate slash commands, duplicate SessionStart hooks, and a race on ports 8081 / 3001.

| Mode | `enabledPlugins` key | Source | Use when |
| --- | --- | --- | --- |
| **Local** | `claude-smart@claude-smart-local` | `directory` → this repo | Iterating on plugin code, hooks, dashboard, or reflexio submodule |
| **Remote** | `claude-smart@reflexioai` | GitHub `ReflexioAI/claude-smart` | Smoke-testing a published release; using the plugin in unrelated projects |

#### Mode A — test the local working copy (recommended for dev in this repo)

Write a project-scoped `.claude/settings.local.json` that adds a `directory` marketplace and disables the remote so it can't shadow the local copy:

```bash
mkdir -p .claude
cat > .claude/settings.local.json <<JSON
{
  "extraKnownMarketplaces": {
    "claude-smart-local": {
      "source": { "source": "directory", "path": "$PWD" }
    }
  },
  "enabledPlugins": {
    "claude-smart@claude-smart-local": true,
    "claude-smart@reflexioai": false
  }
}
JSON
```

The `"claude-smart@reflexioai": false` line explicitly overrides whatever is in `~/.claude/settings.json` for this project only — without it, both copies load side-by-side.

**User-level** variant (all projects use the local copy): put the same JSON into `~/.claude/settings.json` with an absolute path, and drop the `@reflexioai: false` line since there's nothing to shadow anymore.

Restart Claude Code. Changes to `plugin/` are picked up on the next session; changes to `plugin/src/claude_smart/` are picked up on the next hook invocation (hooks shell out via `uv run`, so editing the Python package takes effect immediately without a restart).

Edits to the `reflexio/` submodule or `plugin/dashboard/` source are **not** picked up automatically — the SessionStart hook leaves the backend (port 8081) and the dashboard's `npm run start` against prebuilt `.next/` (port 3001) long-lived across sessions. Use the built-in restart command:

```
/claude-smart:restart          # inside Claude Code
claude-smart restart           # from the shell
```

Runs `backend-service.sh stop` and `dashboard-service.sh stop`, then `npm run build` in `plugin/dashboard/`, then starts both services again. Flags: `--skip-backend`, `--skip-dashboard`, `--no-rebuild` for partial restarts (e.g. `--no-rebuild` when only the reflexio Python source changed).

#### Mode B — test the published remote plugin

The remote marketplace is declared once at the user level:

```bash
# ~/.claude/settings.json
{
  "extraKnownMarketplaces": {
    "reflexioai": { "source": { "source": "github", "repo": "ReflexioAI/claude-smart" } }
  },
  "enabledPlugins": { "claude-smart@reflexioai": true }
}
```

In any repo **without** a local marketplace override, that's all you need. Pull the latest published version with either:

```bash
npx claude-smart update
# or, directly:
claude plugin update claude-smart@reflexioai
```

To force Mode B inside *this* repo (e.g. to verify a release candidate behaves the same way end users will see it), flip the project-scoped file:

```jsonc
// .claude/settings.local.json
{
  "enabledPlugins": {
    "claude-smart@claude-smart-local": false,
    "claude-smart@reflexioai": true
  }
}
```

Restart Claude Code.

#### Verifying which mode is live

Inside Claude Code, `/plugin` lists enabled plugins with their marketplace suffix. You should see **exactly one** `claude-smart@...` entry — if you see two, the scopes are stacking.

From the shell, inspect both scopes directly:

```bash
jq '.enabledPlugins' ~/.claude/settings.json
jq '.enabledPlugins' .claude/settings.local.json 2>/dev/null
```

And confirm the loaded plugin's on-disk location:

```bash
ls -la ~/.claude/plugins/cache/reflexioai/claude-smart/    # Mode B only
ls -la "$PWD/plugin"                                       # Mode A source of truth
```

### Step 6 — Sanity check

Inside Claude Code:

```
/show
```

On a fresh project: `_No playbook or profiles yet for project `<name>`._`. Have a conversation, correct Claude on something (e.g. `"no, don't use X — use Y"`), then run `/learn`. After ~20–30 seconds, `/show` will surface the new rule.

### Exercising the install CLIs against a local marketplace

Useful when you're modifying the `install` subcommand itself and want to test without re-publishing:

```bash
# Python path
uv run --project plugin claude-smart install --source $PWD

# Node path
node bin/claude-smart.js install --source $PWD
```

Both accept either a GitHub `owner/repo` ref or an absolute path to a local directory containing `.claude-plugin/marketplace.json`.

## Tests

```bash
uv run --project plugin pytest tests/ -q   # claude-smart package tests (from repo root)
cd reflexio && uv run pytest tests/server/llm/ -q -o 'addopts='   # reflexio patch tests
```

Run both locally before `make release`. There's no CI gate today — the release flow trusts the maintainer.

### Exercising a hook handler directly

Useful for debugging without a live Claude Code session:

```bash
echo '{"session_id":"dev-1","source":"startup","cwd":"'"$PWD"'"}' \
  | uv run --project plugin python -m claude_smart.hook session-start
```
