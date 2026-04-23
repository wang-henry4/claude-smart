"""PostToolUse hook — record the tool invocation and its outcome."""

from __future__ import annotations

import re
import time
from typing import Any

from claude_smart import ids, state

# Claude Code returns an ExitPlanMode tool_result for plan-mode approval /
# rejection instead of firing a UserPromptSubmit hook. Without synthesizing a
# User record here, reflexio sees no turn boundary after the plan and loses
# the approval/rejection-with-comment signal entirely.
_PLAN_APPROVAL_MARKER = "User has approved your plan"
_PLAN_REJECTION_MARKER = "The user doesn't want to proceed"
_PLAN_REJECTION_COMMENT_MARKER = "the user said:"

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


def _flatten_tool_response_text(response: Any) -> str:
    """Collapse a tool_response payload into a searchable text blob.

    Claude Code's PostToolUse hook hands us ``tool_response`` as either a
    bare string or a dict with ``content`` / ``text`` / ``output`` fields
    (the content field may itself hold a list of ``{type, text}`` blocks).
    We only need to scan for specific marker strings, so join everything
    we can reach; shape drift just means an extra empty scan.

    Args:
        response (Any): Raw ``tool_response`` from the hook payload.

    Returns:
        str: Concatenated text, or ``""`` when nothing recognizable is found.
    """
    if isinstance(response, str):
        return response
    if isinstance(response, dict):
        parts: list[str] = []
        for field in ("content", "text", "output"):
            value = response.get(field)
            if isinstance(value, str):
                parts.append(value)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, str):
                        parts.append(item)
                    elif isinstance(item, dict):
                        inner = item.get("text") or item.get("content")
                        if isinstance(inner, str):
                            parts.append(inner)
        return "\n".join(parts)
    return ""


def _synthesize_plan_decision_record(
    *, response_text: str, user_id: str, ts: int
) -> dict[str, Any] | None:
    """Build a User record mirroring the plan-mode approval/rejection.

    Claude Code's plan mode returns the user's approve/reject action as
    the tool_result for ``ExitPlanMode`` rather than firing UserPromptSubmit.
    When the user rejects with a comment, the comment is appended after
    ``the user said:`` — that comment is the actual correction signal
    reflexio needs, so we hoist it into the synthetic record's content.

    Args:
        response_text (str): Flattened tool_response text.
        user_id (str): Project id to stamp on the User record.
        ts (int): Unix timestamp.

    Returns:
        dict[str, Any] | None: A ``role: User`` record ready for
            ``state.append``, or ``None`` when the response doesn't match
            an approval or rejection marker.
    """
    if _PLAN_APPROVAL_MARKER in response_text:
        content = "Approved the plan."
    elif _PLAN_REJECTION_MARKER in response_text:
        _, sep, tail = response_text.partition(_PLAN_REJECTION_COMMENT_MARKER)
        comment = tail.strip() if sep else ""
        content = (
            f"Rejected the plan. Instead: {comment}" if comment else "Rejected the plan."
        )
    else:
        return None
    return {"ts": ts, "role": "User", "content": content, "user_id": user_id}


def handle(payload: dict[str, Any]) -> None:
    session_id = payload.get("session_id")
    tool_name = payload.get("tool_name") or ""
    if not session_id or not tool_name:
        return

    now = int(time.time())
    record = {
        "ts": now,
        "role": "Assistant_tool",
        "tool_name": tool_name,
        "tool_input": _redact(payload.get("tool_input") or {}),
        "status": _derive_status(payload.get("tool_response")),
    }
    state.append(session_id, record)

    if tool_name == "ExitPlanMode":
        user_record = _synthesize_plan_decision_record(
            response_text=_flatten_tool_response_text(payload.get("tool_response")),
            user_id=ids.resolve_project_id(payload.get("cwd")),
            ts=now,
        )
        if user_record is not None:
            state.append(session_id, user_record)
