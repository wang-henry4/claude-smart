"""SessionStart hook — inject the project playbook + session profile as additionalContext."""

from __future__ import annotations

import json
import sys
from typing import Any

from claude_smart import context_format, hook, ids
from claude_smart.reflexio_adapter import Adapter


def handle(payload: dict[str, Any]) -> None:
    session_id = payload.get("session_id")
    cwd = payload.get("cwd") or None
    if not session_id:
        hook.emit_continue()
        return

    project_id = ids.resolve_project_id(cwd)
    playbooks, profiles = Adapter().fetch_both(
        project_id=project_id,
        session_id=session_id,
    )

    markdown = context_format.render(
        project_id=project_id,
        playbooks=playbooks,
        profiles=profiles,
    )
    if not markdown:
        hook.emit_continue()
        return

    sys.stdout.write(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": markdown,
                }
            }
        )
    )
    sys.stdout.write("\n")
