#!/usr/bin/env bash
# Run once on plugin install. Pulls the reflexio submodule, syncs the
# Python env, and flips on the claude-code LiteLLM provider in reflexio's
# .env so extraction works with no external API key.
#
# On failure, writes the reason to ~/.claude-smart/install-failed so
# hook_entry.sh can short-circuit and surface a user-visible message
# instead of silently no-op'ing every session.
set -eu

HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
. "$HERE/_lib.sh"
claude_smart_source_login_path

PLUGIN_ROOT="$(cd "$HERE/.." && pwd)"
REPO_ROOT="$(cd "$HERE/../.." && pwd)"

MARKER_DIR="$HOME/.claude-smart"
FAILURE_MARKER="$MARKER_DIR/install-failed"
mkdir -p "$MARKER_DIR"
rm -f "$FAILURE_MARKER"

write_failure() {
  printf '%s\n' "$1" > "$FAILURE_MARKER"
  echo "[claude-smart] install failed: $1" >&2
  echo '{"continue":true,"suppressOutput":true}'
  exit 0
}

# Dev-mode only: when running from a git checkout, pull the reflexio
# submodule so tests/benchmarks can use its sources. In install mode the
# plugin lives under ~/.claude/plugins/cache and reflexio-ai resolves
# from PyPI instead. The guard checks for both `.git` and `.gitmodules`
# at REPO_ROOT to distinguish a dev checkout from a marketplace cache
# (where REPO_ROOT has neither).
if [ -d "$REPO_ROOT/.git" ] && [ -f "$REPO_ROOT/.gitmodules" ]; then
  echo "[claude-smart] initializing reflexio submodule..." >&2
  if ! (cd "$REPO_ROOT" && git submodule update --init --recursive reflexio) >&2; then
    echo "[claude-smart] WARNING: git submodule update failed; continuing with PyPI reflexio-ai" >&2
  fi
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "[claude-smart] uv not found — installing from astral.sh..." >&2
  if ! curl -LsSf https://astral.sh/uv/install.sh | sh >&2; then
    write_failure "uv install failed — install manually from https://docs.astral.sh/uv/"
  fi
  claude_smart_prepend_astral_bins
  if ! command -v uv >/dev/null 2>&1; then
    UV_FOUND=""
    for candidate in "$HOME/.local/bin/uv" "$HOME/.cargo/bin/uv" "$HOME/bin/uv"; do
      if [ -x "$candidate" ]; then
        UV_FOUND="$candidate"
        break
      fi
    done
    if [ -n "$UV_FOUND" ]; then
      write_failure "uv installed at $UV_FOUND — add its parent directory to PATH in your shell rc"
    else
      write_failure "uv install reported success but binary not found — install manually from https://docs.astral.sh/uv/"
    fi
  fi
fi

cd "$PLUGIN_ROOT"
echo "[claude-smart] running uv sync..." >&2
if ! uv sync --quiet >&2; then
  write_failure "uv sync failed in $PLUGIN_ROOT — run 'uv sync' there to diagnose"
fi

# Reflexio's CLI reads ~/.reflexio/.env (see reflexio/cli/env_loader.py);
# append our two opt-in flags there so `reflexio services start` picks
# them up regardless of which directory the user runs it from.
REFLEXIO_ENV="$HOME/.reflexio/.env"
mkdir -p "$(dirname "$REFLEXIO_ENV")"
touch "$REFLEXIO_ENV"
if ! grep -q '^CLAUDE_SMART_USE_LOCAL_CLI=' "$REFLEXIO_ENV"; then
  printf '\n# Route reflexio generation through the local Claude Code CLI\nCLAUDE_SMART_USE_LOCAL_CLI=1\n' >> "$REFLEXIO_ENV"
  echo "[claude-smart] appended CLAUDE_SMART_USE_LOCAL_CLI=1 to $REFLEXIO_ENV" >&2
fi
if ! grep -q '^CLAUDE_SMART_USE_LOCAL_EMBEDDING=' "$REFLEXIO_ENV"; then
  printf '# Use the in-process ONNX embedder (chromadb) — no API key for semantic search\nCLAUDE_SMART_USE_LOCAL_EMBEDDING=1\n' >> "$REFLEXIO_ENV"
  echo "[claude-smart] appended CLAUDE_SMART_USE_LOCAL_EMBEDDING=1 to $REFLEXIO_ENV" >&2
fi

if ! command -v claude >/dev/null 2>&1; then
  echo "[claude-smart] WARNING: 'claude' CLI not on PATH — reflexio extractors will have no LLM until it's installed" >&2
fi

# Allowlist cs-cite globally so Claude's citation Bash calls don't pop a
# permission prompt mid-turn. Idempotent: no-ops when the entry is already
# present. Uses Python to preserve the rest of settings.json intact.
CLAUDE_SETTINGS="$HOME/.claude/settings.json"
mkdir -p "$(dirname "$CLAUDE_SETTINGS")"
if python3 - "$CLAUDE_SETTINGS" <<'PY' >&2
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
entry = "Bash(cs-cite:*)"
data: dict = {}
if path.is_file():
    try:
        data = json.loads(path.read_text() or "{}")
    except json.JSONDecodeError:
        print(
            f"[claude-smart] WARNING: {path} is not valid JSON; skipping cs-cite allowlist",
            file=sys.stderr,
        )
        sys.exit(2)
def _warn_and_exit(reason: str) -> None:
    print(
        f"[claude-smart] WARNING: {path} {reason}; skipping cs-cite allowlist",
        file=sys.stderr,
    )
    sys.exit(2)

if not isinstance(data, dict):
    _warn_and_exit("top-level is not a JSON object")
permissions = data.setdefault("permissions", {})
if not isinstance(permissions, dict):
    _warn_and_exit("'permissions' is not a JSON object")
allow = permissions.setdefault("allow", [])
if not isinstance(allow, list):
    _warn_and_exit("'permissions.allow' is not a JSON array")
if entry in allow:
    sys.exit(1)  # already present — convey via exit code so shell can skip the log
allow.append(entry)
path.write_text(json.dumps(data, indent=2) + "\n")
sys.exit(0)
PY
then
  echo "[claude-smart] added Bash(cs-cite:*) to $CLAUDE_SETTINGS permissions.allow" >&2
fi

# Pre-install + build the Next.js dashboard so SessionStart can boot it
# without the multi-minute first-run cost. dashboard-service.sh will retry
# the build lazily if either step is skipped or fails here.
DASHBOARD_DIR="$PLUGIN_ROOT/dashboard"
if [ -d "$DASHBOARD_DIR" ]; then
  if command -v npm >/dev/null 2>&1; then
    echo "[claude-smart] installing dashboard dependencies..." >&2
    if (cd "$DASHBOARD_DIR" && npm install --silent --no-fund --no-audit >&2); then
      echo "[claude-smart] building dashboard..." >&2
      # Trap INT/TERM so a killed build (e.g., Setup hit a hook timeout)
      # doesn't leave a partial .next that dashboard-service.sh can't
      # detect as broken. The trap runs in the current shell; unset it
      # once the build step returns.
      trap 'rm -rf "$DASHBOARD_DIR/.next"; exit 130' INT TERM
      if ! (cd "$DASHBOARD_DIR" && npm run build >&2); then
        rm -rf "$DASHBOARD_DIR/.next"
        echo "[claude-smart] WARNING: dashboard build failed; rerun plugin Setup to retry" >&2
      fi
      trap - INT TERM
    else
      echo "[claude-smart] WARNING: dashboard npm install failed; dashboard will be unavailable" >&2
    fi
  else
    echo "[claude-smart] WARNING: npm not on PATH — dashboard will be unavailable" >&2
  fi
fi

echo "[claude-smart] install complete. Backend and dashboard auto-start on session start." >&2
echo '{"continue":true,"suppressOutput":true}'
