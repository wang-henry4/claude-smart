# Shared helpers for claude-smart plugin scripts. Source, do not execute.

# Claude Code hooks run with a minimal non-interactive PATH that often omits
# nvm/asdf/brew shims where `npm`, `uv`, etc. live. Pull the user's login-shell
# PATH the same way claude-mem does so hook-spawned scripts find them without
# the user having to mutate their global PATH. Best-effort — failures silent.
claude_smart_source_login_path() {
  if [ -n "${SHELL:-}" ] && [ -x "$SHELL" ]; then
    if _SHELL_PATH="$("$SHELL" -lc 'printf %s "$PATH"' 2>/dev/null)"; then
      [ -n "$_SHELL_PATH" ] && export PATH="$_SHELL_PATH:$PATH"
    fi
  fi
}
