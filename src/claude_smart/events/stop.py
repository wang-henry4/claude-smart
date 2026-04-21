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
    """Scan the transcript JSONL for the most recent assistant text.

    Claude Code's transcript format writes one JSON object per line.
    Assistant messages are ``{"type": "assistant", "message": {"content":
    [{"type": "text", "text": "..."}, ...]}}``; tool-use and thinking
    blocks live alongside text blocks in the same message. We join every
    text block of the latest assistant message.

    Args:
        transcript_path: Absolute path from the hook payload, or None.

    Returns:
        str: Joined assistant text, or "" on any read/parse failure.
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
    for raw in reversed(lines):
        candidate = raw.strip()
        if not candidate:
            continue
        try:
            entry = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if entry.get("type") != "assistant":
            continue
        message = entry.get("message") or {}
        content = message.get("content")
        texts = _extract_text_blocks(content)
        if texts:
            return "\n\n".join(texts)
    return ""


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
