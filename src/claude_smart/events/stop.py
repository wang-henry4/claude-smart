"""Stop hook — finalize the current assistant turn, publish to reflexio."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from claude_smart import ids, publish, state

_LOGGER = logging.getLogger(__name__)


def _read_last_assistant_text(transcript_path: str | None) -> str:
    """Scan the transcript JSONL for the full current-turn assistant text.

    Claude Code's transcript format writes one JSON object per line, and a
    single assistant turn is split across many ``{"type": "assistant"}``
    entries — one each for thinking, tool_use, and text blocks. Tool
    results land as ``{"type": "user", "message": {"content": [{"type":
    "tool_result", ...}]}}`` interleaved between them. To capture the
    complete response, walk backward from the end collecting text blocks
    from every assistant entry until we hit the user turn that started
    this exchange (a user entry whose content is not purely tool_results).

    Args:
        transcript_path: Absolute path from the hook payload, or None.

    Returns:
        str: Joined assistant text across the whole turn, or "" on failure.
    """
    if not transcript_path:
        return ""
    path = Path(transcript_path)
    if not path.is_file():
        return ""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        _LOGGER.debug("transcript read failed: %s", exc)
        return ""
    groups: list[list[str]] = []
    for raw in reversed(lines):
        candidate = raw.strip()
        if not candidate:
            continue
        try:
            entry = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        entry_type = entry.get("type")
        if entry_type == "assistant":
            message = entry.get("message") or {}
            texts = _extract_text_blocks(message.get("content"))
            if texts:
                groups.append(texts)
        elif _is_user_turn_boundary(entry):
            break
    parts = [t for group in reversed(groups) for t in group]
    return "\n\n".join(parts)


def _is_user_turn_boundary(entry: dict[str, Any]) -> bool:
    """True if ``entry`` is the user message that opened the current turn.

    Tool results are delivered as ``type: user`` entries whose content is a
    list of ``tool_result`` blocks — those continue the assistant turn and
    must not be treated as a boundary. A real user message has string
    content or contains at least one non-``tool_result`` block.
    """
    if entry.get("type") != "user":
        return False
    message = entry.get("message") or {}
    content = message.get("content")
    if isinstance(content, str):
        return True
    if isinstance(content, list):
        return any(
            isinstance(block, dict) and block.get("type") != "tool_result"
            for block in content
        )
    return False


def _extract_text_blocks(content: Any) -> list[str]:
    if isinstance(content, str):
        return [content]
    if not isinstance(content, list):
        return []
    out: list[str] = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            text = block.get("text")
            if isinstance(text, str) and text:
                out.append(text)
    return out


def handle(payload: dict[str, Any]) -> None:
    session_id = payload.get("session_id")
    if not session_id:
        return

    # Always append an Assistant record, even when the turn emitted only
    # tool calls and no text. ``state.unpublished_slice`` folds any
    # buffered ``Assistant_tool`` records into this turn's ``tools_used``;
    # without this placeholder, those tools would be misattributed to the
    # next assistant turn.
    assistant_text = _read_last_assistant_text(payload.get("transcript_path"))
    state.append(
        session_id,
        {
            "ts": int(time.time()),
            "role": "Assistant",
            "content": assistant_text,
        },
    )

    project_id = ids.resolve_project_id(payload.get("cwd"))
    publish.publish_unpublished(
        session_id=session_id, project_id=project_id, force_extraction=False
    )
