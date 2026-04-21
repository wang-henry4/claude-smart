# Developer Guide

Internal notes for maintainers of `claude-smart`. End-user install instructions live in [README.md](./README.md); this file covers the release loop.

## Repository layout

| Path | Purpose |
| --- | --- |
| `src/claude_smart/` | Python package — hook handler, CLI, reflexio adapter |
| `plugin/` | Claude Code plugin — hooks, slash commands, install script |
| `bin/claude-smart.js` | Node wrapper so `npx claude-smart install` works |
| `package.json` | npm manifest — only ships `bin/`, `README.md`, `LICENSE` |
| `pyproject.toml` | Python manifest — shipped to PyPI via `uv build` + `uv publish` |
| `.claude-plugin/plugin.json` | Plugin metadata read by Claude Code |
| `.claude-plugin/marketplace.json` | Marketplace entry — `claude plugin marketplace add` reads this |
| `reflexio/` | Submodule — Apache 2.0, storage + search + extraction backend |
| `Makefile` | Release automation |

## Versioning

`claude-smart` uses [semver](https://semver.org/). Four files carry the version and **must stay in lockstep** — if they drift, the npm wrapper, PyPI wheel, plugin metadata, and marketplace entry can claim different versions, and users see confusing mismatches in `claude plugin list` vs. `npm view claude-smart version`.

| File | Field |
| --- | --- |
| `package.json` | `.version` |
| `pyproject.toml` | `project.version` |
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

See the "One-command install" section of the README for the install flow that assumes option 2.

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

## Local testing without publishing

Install the plugin from a local directory so you don't need a GitHub push cycle:

```bash
# From another project where you want to test
mkdir -p .claude
cat > .claude/settings.local.json <<JSON
{
  "extraKnownMarketplaces": {
    "claude-smart-dev": {
      "source": { "source": "directory", "path": "/Users/yilu/repos/claude-smart" }
    }
  },
  "enabledPlugins": { "claude-smart@claude-smart-dev": true }
}
JSON
```

Restart Claude Code in that directory. Changes to `plugin/` are picked up on the next session; changes to `src/claude_smart/` are picked up on the next hook invocation (since hooks shell out via `uv run`).

You can also exercise the install CLIs against a local marketplace:

```bash
# Python path
uv run claude-smart install --source /Users/yilu/repos/claude-smart

# Node path
node bin/claude-smart.js install --source /Users/yilu/repos/claude-smart
```

## Tests

```bash
uv run pytest tests/ -q                    # claude-smart package tests
cd reflexio && uv run pytest tests/server/llm/ -q -o 'addopts='   # reflexio patch tests
```

Run both locally before `make release`. There's no CI gate today — the release flow trusts the maintainer.
