"""PreToolUse hook — just-in-time playbook + profile inject before a mutating tool.

Fires only for tools listed in ``hooks.json``'s PreToolUse matcher
(Edit/Write/NotebookEdit/Bash). Composes a query from the tool call,
runs playbook + profile search in parallel, and injects the top hits as
``hookSpecificOutput.additionalContext`` so Claude sees relevant rules
immediately before executing the action.
"""

from __future__ import annotations

import json
import sys
from typing import Any

from claude_smart import context_format, hook, ids, query_compose
from claude_smart.reflexio_adapter import Adapter

_TOP_K = 5


def handle(payload: dict[str, Any]) -> None:
    """PreToolUse dispatcher — never raises; degrades to ``emit_continue``."""
    session_id = payload.get("session_id")
    tool_name = payload.get("tool_name")
    tool_input = payload.get("tool_input") or {}
    if not session_id or not tool_name:
        hook.emit_continue()
        return

    query = query_compose.from_tool_call(tool_name, tool_input)
    if not query:
        hook.emit_continue()
        return

    project_id = ids.resolve_project_id(payload.get("cwd"))
    playbooks, profiles = Adapter().search_both(
        project_id=project_id,
        query=query,
        top_k=_TOP_K,
    )
    markdown = context_format.render_inline(
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
                    "hookEventName": "PreToolUse",
                    "additionalContext": markdown,
                }
            }
        )
    )
    sys.stdout.write("\n")
