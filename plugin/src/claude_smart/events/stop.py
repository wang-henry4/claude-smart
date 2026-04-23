"""Stop hook — finalize the current assistant turn, publish to reflexio."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from claude_smart import cs_cite, ids, publish, state

_LOGGER = logging.getLogger(__name__)


# Stop fires immediately after Claude Code logs the final assistant message,
# and at tight gaps (<~10 ms observed) the transcript write hasn't propagated
# before our read. Retry briefly when the scan returns empty — note the cost
# is paid on *every* tool-only turn too (we can't tell those apart from a
# flush race), so keep the total budget small: 100 ms worst case.
_TRANSCRIPT_RETRY_DELAYS_S = (0.03, 0.07)


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
    text = _scan_transcript_for_assistant_text(path)
    if text:
        return text
    for delay in _TRANSCRIPT_RETRY_DELAYS_S:
        time.sleep(delay)
        text = _scan_transcript_for_assistant_text(path)
        if text:
            return text
    return ""


def _iter_current_turn_assistant_entries(path: Path) -> list[dict[str, Any]]:
    """Return assistant transcript entries for the in-progress turn, oldest first.

    Reads the JSONL transcript once and walks it backward, collecting every
    ``type: assistant`` entry until a real user message is reached (a user
    entry whose content is not purely ``tool_result`` blocks — those continue
    the assistant turn). Restores chronological order before returning so
    callers can consume left-to-right.

    Args:
        path (Path): Absolute path to the transcript JSONL.

    Returns:
        list[dict[str, Any]]: Parsed assistant entries in the order Claude
            emitted them. Empty on read failure or if the transcript has
            no assistant entries in the current turn.
    """
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        _LOGGER.debug("transcript read failed: %s", exc)
        return []
    entries: list[dict[str, Any]] = []
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
            entries.append(entry)
        elif _is_user_turn_boundary(entry):
            break
    entries.reverse()
    return entries


def _scan_transcript_for_assistant_text(path: Path) -> str:
    parts: list[str] = []
    for entry in _iter_current_turn_assistant_entries(path):
        message = entry.get("message") or {}
        parts.extend(_extract_text_blocks(message.get("content")))
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
    """Return assistant-visible text from a transcript content list.

    Picks up plain ``type: "text"`` blocks and the ``plan`` payload of
    ``ExitPlanMode`` tool_use blocks. Plan mode emits the plan as a
    tool_use argument rather than a text block, so without the second
    branch the plan is silently dropped from the published turn.
    """
    if isinstance(content, str):
        return [content]
    if not isinstance(content, list):
        return []
    out: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        btype = block.get("type")
        if btype == "text":
            text = block.get("text")
            if isinstance(text, str) and text:
                out.append(text)
        elif btype == "tool_use" and block.get("name") == "ExitPlanMode":
            plan = (block.get("input") or {}).get("plan")
            if isinstance(plan, str) and plan:
                out.append(f"Plan:\n{plan}")
    return out


def _scan_transcript_for_cs_cite_ids(path: Path) -> list[str]:
    """Scan the current assistant turn for ``cs-cite`` Bash tool_use calls.

    Collects citation ids from every matching Bash ``tool_use`` block in
    the current turn. Multiple calls are merged; order follows Claude's
    emission order (earliest first).

    Args:
        path (Path): Absolute path to the transcript JSONL.

    Returns:
        list[str]: Rank ids (e.g. ``"r1-ab12"``, ``"p2-cd34"``) in
            emission order. Empty when no ``cs-cite`` call is found.
    """
    out: list[str] = []
    for entry in _iter_current_turn_assistant_entries(path):
        message = entry.get("message") or {}
        out.extend(_extract_cs_cite_ids(message.get("content")))
    return out


def _extract_cs_cite_ids(content: Any) -> list[str]:
    """Return citation ids from all Bash ``cs-cite`` tool_use blocks in ``content``."""
    if not isinstance(content, list):
        return []
    out: list[str] = []
    for block in content:
        if not isinstance(block, dict) or block.get("type") != "tool_use":
            continue
        if block.get("name") != "Bash":
            continue
        tool_input = block.get("input") or {}
        command = tool_input.get("command")
        if not isinstance(command, str):
            continue
        out.extend(cs_cite.parse_citation_command(command))
    return out


def _resolve_cited_items(session_id: str, cited_ids: list[str]) -> list[dict[str, Any]]:
    """Map citation ids to ``{id, kind, title}`` entries via the session registry.

    Unknown ids (Claude hallucinations, or items injected in a newer
    session than this hook can see) are dropped. Duplicate ids within
    one turn collapse to a single entry — the user-facing badge row
    doesn't need the multiplicity.
    """
    if not cited_ids:
        return []
    registry = state.read_injected(session_id)
    seen: set[str] = set()
    resolved: list[dict[str, Any]] = []
    for cid in cited_ids:
        if cid in seen:
            continue
        entry = registry.get(cid)
        if not entry:
            continue
        seen.add(cid)
        item: dict[str, Any] = {
            "id": entry.get("id", cid),
            "kind": entry.get("kind", ""),
            "title": entry.get("title", ""),
        }
        real_id = entry.get("real_id")
        if real_id:
            item["real_id"] = real_id
        resolved.append(item)
    return resolved


def handle(payload: dict[str, Any]) -> None:
    session_id = payload.get("session_id")
    if not session_id:
        return

    # Always append an Assistant record, even when the turn emitted only
    # tool calls and no text. ``state.unpublished_slice`` folds any
    # buffered ``Assistant_tool`` records into this turn's ``tools_used``;
    # without this placeholder, those tools would be misattributed to the
    # next assistant turn.
    transcript_path = payload.get("transcript_path")
    assistant_text = _read_last_assistant_text(transcript_path)
    project_id = ids.resolve_project_id(payload.get("cwd"))

    cited_items: list[dict[str, Any]] = []
    if transcript_path:
        path = Path(transcript_path)
        if path.is_file():
            cited_ids = _scan_transcript_for_cs_cite_ids(path)
            cited_items = _resolve_cited_items(session_id, cited_ids)

    record: dict[str, Any] = {
        "ts": int(time.time()),
        "role": "Assistant",
        "content": assistant_text,
        "user_id": project_id,
    }
    if cited_items:
        record["cited_items"] = cited_items
    state.append(session_id, record)
    publish.publish_unpublished(
        session_id=session_id,
        project_id=project_id,
        force_extraction=False,
        skip_aggregation=True,
    )
