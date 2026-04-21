"""Dispatch table for Claude Code hook events.

The plugin's ``hook_entry.sh`` calls ``python -m claude_smart.hook <event>``
once per hook invocation. This module reads the hook JSON from stdin,
routes to the matching handler in ``claude_smart.events``, and makes sure
no unhandled exception ever propagates (that would break the user's
session).
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any, Callable

_LOGGER = logging.getLogger(__name__)


def _load_handlers() -> dict[str, Callable[[dict[str, Any]], None]]:
    from claude_smart.events import (
        post_tool,
        pre_tool,
        session_end,
        session_start,
        stop,
        user_prompt,
    )

    return {
        "session-start": session_start.handle,
        "user-prompt": user_prompt.handle,
        "pre-tool": pre_tool.handle,
        "post-tool": post_tool.handle,
        "stop": stop.handle,
        "session-end": session_end.handle,
    }


def _read_stdin_json() -> dict[str, Any]:
    """Parse stdin as JSON. Returns {} on empty or malformed input."""
    try:
        raw = sys.stdin.read()
    except Exception as exc:  # noqa: BLE001
        _LOGGER.debug("stdin read failed: %s", exc)
        return {}
    if not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        _LOGGER.debug("stdin JSON decode failed: %s", exc)
        return {}
    return parsed if isinstance(parsed, dict) else {}


def emit_continue() -> None:
    """Fallback stdout — tells Claude Code to keep going without injection."""
    sys.stdout.write(json.dumps({"continue": True, "suppressOutput": True}))
    sys.stdout.write("\n")


def main(argv: list[str] | None = None) -> int:
    """Entry point used by ``python -m claude_smart.hook`` and the console script."""
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        _LOGGER.warning("hook dispatcher called with no event name")
        emit_continue()
        return 0

    event = argv[0]
    payload = _read_stdin_json()
    handlers = _load_handlers()
    handler = handlers.get(event)
    if handler is None:
        _LOGGER.warning("unknown hook event: %s", event)
        emit_continue()
        return 0

    try:
        handler(payload)
    except Exception as exc:  # noqa: BLE001 — hooks must never crash the session.
        _LOGGER.exception("hook handler %s raised: %s", event, exc)
        emit_continue()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
