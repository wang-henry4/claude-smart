"""PostToolUse hook — record the tool invocation and its outcome."""

from __future__ import annotations

import re
import time
from typing import Any

from claude_smart import state

# Tool inputs are persisted locally and later published to reflexio, so we
# apply a conservative redaction pass at ingestion time. Chosen to avoid
# false positives over maximal coverage — the dashboard shows these
# verbatim, and users noticing a masked command is far less surprising
# than a masked `LOG_LEVEL=INFO`.
_MAX_STR_LEN = 4096
_SECRET_ASSIGNMENT = re.compile(
    r"(?P<key>[A-Z][A-Z0-9_]{2,})=(?P<quote>['\"]?)"
    r"(?P<value>[A-Za-z0-9+/=_\-]{20,})(?P=quote)"
)


def _looks_like_secret(value: str) -> bool:
    """Heuristic: mixed-case letters plus digits suggest a high-entropy token."""
    has_lower = any(c.islower() for c in value)
    has_upper = any(c.isupper() for c in value)
    has_digit = any(c.isdigit() for c in value)
    return has_lower and has_upper and has_digit


def _mask_secrets(text: str) -> str:
    def sub(match: "re.Match[str]") -> str:
        value = match.group("value")
        if not _looks_like_secret(value):
            return match.group(0)
        key = match.group("key")
        quote = match.group("quote")
        return f"{key}={quote}<redacted:{len(value)}>{quote}"

    return _SECRET_ASSIGNMENT.sub(sub, text)


def _redact_string(value: str) -> str:
    masked = _mask_secrets(value)
    if len(masked) > _MAX_STR_LEN:
        return masked[:_MAX_STR_LEN] + "…(truncated)"
    return masked


def _redact(tool_input: dict[str, Any]) -> dict[str, Any]:
    """Redact obvious secrets and truncate oversized string values.

    Only top-level string values are inspected — nested dicts/lists and
    non-string scalars pass through unchanged. Claude Code tool payloads
    are flat in practice (Bash.command, Edit.file_path, etc.), so deeper
    recursion isn't worth the false-positive surface.

    Args:
        tool_input (dict[str, Any]): Raw ``tool_input`` from the PostToolUse
            payload.

    Returns:
        dict[str, Any]: New dict with redaction applied.
    """
    return {
        k: _redact_string(v) if isinstance(v, str) else v for k, v in tool_input.items()
    }


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
        "tool_input": _redact(payload.get("tool_input") or {}),
        "status": _derive_status(payload.get("tool_response")),
    }
    state.append(session_id, record)
