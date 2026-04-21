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

PROJECT_ROOT="$(cd "$HERE/../.." && pwd)"

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

cd "$PROJECT_ROOT"

echo "[claude-smart] initializing reflexio submodule..." >&2
if ! git submodule update --init --recursive reflexio >&2; then
  write_failure "git submodule update failed — is $PROJECT_ROOT a git checkout?"
fi

if ! command -v uv >/dev/null 2>&1; then
  write_failure "uv is not on PATH — install from https://docs.astral.sh/uv/"
fi

echo "[claude-smart] running uv sync..." >&2
if ! uv sync --quiet >&2; then
  write_failure "uv sync failed in $PROJECT_ROOT — run 'uv sync' there to diagnose"
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

# Pre-install + build the Next.js dashboard so SessionStart can boot it
# without the multi-minute first-run cost. dashboard-service.sh will retry
# the build lazily if either step is skipped or fails here.
DASHBOARD_DIR="$PROJECT_ROOT/dashboard"
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

echo "[claude-smart] install complete. Start reflexio with: uv run reflexio services start" >&2
echo '{"continue":true,"suppressOutput":true}'
