"""UserPromptSubmit hook — buffer the user turn for later publish to reflexio."""

from __future__ import annotations

import time
from typing import Any

from claude_smart import state


def handle(payload: dict[str, Any]) -> None:
    session_id = payload.get("session_id")
    prompt = payload.get("prompt") or ""
    if not session_id or not prompt:
        return
    state.append(
        session_id,
        {
            "ts": int(time.time()),
            "role": "User",
            "content": prompt,
        },
    )
