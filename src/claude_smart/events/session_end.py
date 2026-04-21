"""SessionEnd hook — flush any remaining interactions with force_extraction=True."""

from __future__ import annotations

from typing import Any

from claude_smart import ids, publish


def handle(payload: dict[str, Any]) -> None:
    session_id = payload.get("session_id")
    if not session_id:
        return
    project_id = ids.resolve_project_id(payload.get("cwd"))
    publish.publish_unpublished(
        session_id=session_id, project_id=project_id, force_extraction=True
    )
