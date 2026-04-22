"""SessionStart hook — inject the project playbook + session profile as additionalContext."""

from __future__ import annotations

import json
import sys
from typing import Any

from claude_smart import context_format, hook, ids
from claude_smart.reflexio_adapter import Adapter

# Claude-smart's preferred extraction cadence — more frequent, smaller batches
# than reflexio's out-of-box 10/5. Applied idempotently to the reflexio server
# on every SessionStart via Adapter.apply_batch_defaults.
_CLAUDE_SMART_BATCH_SIZE = 5
_CLAUDE_SMART_BATCH_INTERVAL = 3


def handle(payload: dict[str, Any]) -> None:
    session_id = payload.get("session_id")
    cwd = payload.get("cwd") or None
    if not session_id:
        hook.emit_continue()
        return

    project_id = ids.resolve_project_id(cwd)
    adapter = Adapter()
    adapter.apply_batch_defaults(
        batch_size=_CLAUDE_SMART_BATCH_SIZE,
        batch_interval=_CLAUDE_SMART_BATCH_INTERVAL,
    )
    playbooks, profiles = adapter.fetch_both(
        project_id=project_id,
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
