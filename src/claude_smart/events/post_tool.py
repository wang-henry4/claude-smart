"""PostToolUse hook — record the tool invocation and its outcome."""

from __future__ import annotations

import time
from typing import Any

from claude_smart import state


def _derive_status(tool_response: Any) -> str:
    """Classify the tool outcome as 'success' or 'error'.

    Claude Code's PostToolUse payload puts the tool response under
    ``tool_response``, which may be a dict (with an ``is_error`` / ``error``
    field) or a bare string. Unknown shapes default to success.
    """
    if isinstance(tool_response, dict):
        if tool_response.get("is_error") or tool_response.get("error"):
            return "error"
    return "success"


def handle(payload: dict[str, Any]) -> None:
    session_id = payload.get("session_id")
    tool_name = payload.get("tool_name") or ""
    if not session_id or not tool_name:
        return

    record = {
        "ts": int(time.time()),
        "role": "Assistant_tool",
        "tool_name": tool_name,
        "status": _derive_status(payload.get("tool_response")),
    }
    state.append(session_id, record)
