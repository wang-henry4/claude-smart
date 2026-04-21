"""Detect hook invocations that come from reflexio calling itself.

The ``claude-code`` LiteLLM provider (see
``reflexio.server.llm.providers.claude_code_provider._run_cli``) shells
out to the ``claude`` CLI to answer extractor prompts. That subprocess
is a full Claude Code invocation, so it fires *our* hooks too — and
without a guard, the Stop hook publishes the extractor's own system
prompt (``"You are a detector for AGENT LEARNING SIGNALS..."``) back
into reflexio as a user interaction. Reflexio then trains on its own
internals.

Two detection signals, OR'd:
  - Env var ``CLAUDE_SMART_INTERNAL=1``, set by the provider before
    spawning ``claude`` — propagates to all hook scripts spawned by
    that child. This is the primary, reliable signal.
  - ``payload.cwd`` resolves inside the reflexio submodule. Catches
    direct invocations of ``claude`` from inside reflexio (manual
    debugging, future internal callers) that forget to set the env.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

_ENV_MARKER = "CLAUDE_SMART_INTERNAL"

# Reflexio submodule lives at <repo>/reflexio; anchor relative to this
# file (<repo>/src/claude_smart/internal_call.py) so the check follows
# the real checkout if the repo is relocated.
_THIS_DIR = Path(__file__).resolve().parent
_REFLEXIO_DIR = _THIS_DIR.parents[1] / "reflexio"


def is_internal_invocation(payload: dict[str, Any]) -> bool:
    """True if this hook fire originated from reflexio's own LLM provider.

    Args:
        payload (dict[str, Any]): Parsed Claude Code hook payload. Only
            ``cwd`` is inspected.

    Returns:
        bool: True when the env marker is set or ``cwd`` points inside
            the reflexio submodule. False otherwise, including when
            ``cwd`` is missing or unresolvable.
    """
    if os.environ.get(_ENV_MARKER) == "1":
        return True
    cwd = payload.get("cwd")
    if not cwd:
        return False
    try:
        resolved = Path(cwd).resolve()
    except OSError:
        return False
    try:
        resolved.relative_to(_REFLEXIO_DIR)
    except ValueError:
        return False
    return True
