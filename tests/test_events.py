"""Tests for the per-event hook handlers."""

from __future__ import annotations

import io
import json
import sys
from typing import Any

import pytest

from claude_smart import state
from claude_smart.events import post_tool, session_start, stop


# -----------------------------------------------------------------------------
# post_tool
# -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "tool_response, expected",
    [
        ({"is_error": True}, "error"),
        ({"error": "boom"}, "error"),
        ({"ok": True}, "success"),
        ("plain string output", "success"),
        (None, "success"),
    ],
)
def test_post_tool_status_derivation(session_dir, tool_response, expected) -> None:
    post_tool.handle(
        {
            "session_id": "s1",
            "tool_name": "Bash",
            "tool_response": tool_response,
        }
    )
    records = state.read_all("s1")
    assert records[0]["status"] == expected


def test_post_tool_drops_payload_without_session_or_tool(session_dir) -> None:
    post_tool.handle({"tool_name": "Bash"})
    post_tool.handle({"session_id": "s1"})
    assert state.read_all("s1") == []


# -----------------------------------------------------------------------------
# stop — always appends an Assistant record (Option A)
# -----------------------------------------------------------------------------


def _write_transcript(tmp_path, entries):
    path = tmp_path / "transcript.jsonl"
    path.write_text("\n".join(json.dumps(e) for e in entries) + "\n")
    return path


def test_stop_appends_assistant_text_from_transcript(
    session_dir, tmp_path, monkeypatch
) -> None:
    transcript = _write_transcript(
        tmp_path,
        [
            {"type": "user", "message": {"content": "hi"}},
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "thinking", "text": "hmm"},
                        {"type": "text", "text": "hello there"},
                    ]
                },
            },
        ],
    )
    monkeypatch.setattr(
        "claude_smart.publish.publish_unpublished",
        lambda **_: ("nothing", 0),
    )
    stop.handle({"session_id": "s1", "transcript_path": str(transcript)})
    records = state.read_all("s1")
    assert records[-1] == {
        "role": "Assistant",
        "content": "hello there",
        "ts": records[-1]["ts"],
    }


def test_stop_appends_empty_assistant_record_when_turn_was_tools_only(
    session_dir, tmp_path, monkeypatch
) -> None:
    """Option A: tool-only assistant turn still gets a placeholder record."""
    transcript = _write_transcript(
        tmp_path,
        [
            {
                "type": "assistant",
                "message": {"content": [{"type": "tool_use", "name": "Bash"}]},
            }
        ],
    )
    monkeypatch.setattr(
        "claude_smart.publish.publish_unpublished",
        lambda **_: ("nothing", 0),
    )
    stop.handle({"session_id": "s1", "transcript_path": str(transcript)})
    records = state.read_all("s1")
    assert any(r.get("role") == "Assistant" and r.get("content") == "" for r in records)


def test_stop_without_session_is_noop(session_dir) -> None:
    stop.handle({})
    assert state.read_all("s1") == []


# -----------------------------------------------------------------------------
# session_start — emit_continue when nothing to render
# -----------------------------------------------------------------------------


def test_session_start_emits_continue_without_session_id(
    session_dir, monkeypatch
) -> None:
    buf = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buf)
    session_start.handle({})
    assert json.loads(buf.getvalue().strip()) == {
        "continue": True,
        "suppressOutput": True,
    }


def test_session_start_emits_continue_when_no_playbook_or_profile(
    session_dir, monkeypatch
) -> None:
    class StubAdapter:
        def fetch_both(self, **_kw):
            return ([], [])

    monkeypatch.setattr(
        "claude_smart.events.session_start.Adapter", lambda *a, **kw: StubAdapter()
    )
    buf = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buf)
    session_start.handle({"session_id": "s1", "source": "startup"})
    assert json.loads(buf.getvalue().strip()) == {
        "continue": True,
        "suppressOutput": True,
    }


def test_session_start_emits_additional_context_when_playbook_present(
    session_dir, monkeypatch
) -> None:
    class Stub:
        def fetch_both(self, **_kw):
            return (
                [
                    {
                        "content": "use pathlib",
                        "trigger": "file ops",
                        "rationale": "safer",
                    }
                ],
                [],
            )

    monkeypatch.setattr(
        "claude_smart.events.session_start.Adapter", lambda *a, **kw: Stub()
    )
    monkeypatch.setattr(
        "claude_smart.events.session_start.ids.resolve_project_id",
        lambda *_a, **_kw: "demo",
    )
    buf = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buf)
    session_start.handle({"session_id": "s1", "source": "startup"})
    payload = json.loads(buf.getvalue().strip())
    assert payload["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert "use pathlib" in payload["hookSpecificOutput"]["additionalContext"]


def test_session_start_fetches_both_on_every_source(session_dir, monkeypatch) -> None:
    """Used to skip profile fetch unless source ∈ {resume,clear,compact}; now always both."""
    calls: list[dict[str, Any]] = []

    class Stub:
        def fetch_both(self, **kwargs):
            calls.append(kwargs)
            return ([], [])

    monkeypatch.setattr(
        "claude_smart.events.session_start.Adapter", lambda *a, **kw: Stub()
    )
    monkeypatch.setattr(
        "claude_smart.events.session_start.ids.resolve_project_id",
        lambda *_a, **_kw: "demo",
    )
    buf = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buf)
    for source in ("startup", "resume", "clear", "compact"):
        session_start.handle({"session_id": "s1", "source": source})
    assert len(calls) == 4
    for kw in calls:
        assert kw["project_id"] == "demo"
        assert kw["session_id"] == "s1"


# -----------------------------------------------------------------------------
# pre_tool
# -----------------------------------------------------------------------------


def _stub_pretool_adapter(monkeypatch, *, playbooks=None, profiles=None, calls=None):
    class Stub:
        def search_both(self, **kwargs):
            if calls is not None:
                calls.append(kwargs)
            return (list(playbooks or []), list(profiles or []))

    monkeypatch.setattr("claude_smart.events.pre_tool.Adapter", lambda *a, **kw: Stub())
    monkeypatch.setattr(
        "claude_smart.events.pre_tool.ids.resolve_project_id",
        lambda *_a, **_kw: "demo",
    )


def test_pre_tool_emits_continue_without_session_id(session_dir, monkeypatch) -> None:
    from claude_smart.events import pre_tool

    buf = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buf)
    pre_tool.handle({"tool_name": "Edit", "tool_input": {"file_path": "a.py"}})
    assert json.loads(buf.getvalue().strip()) == {
        "continue": True,
        "suppressOutput": True,
    }


def test_pre_tool_emits_continue_for_unknown_tool(session_dir, monkeypatch) -> None:
    from claude_smart.events import pre_tool

    _stub_pretool_adapter(monkeypatch)
    buf = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buf)
    pre_tool.handle(
        {"session_id": "s1", "tool_name": "Read", "tool_input": {"file_path": "a.py"}}
    )
    assert json.loads(buf.getvalue().strip()) == {
        "continue": True,
        "suppressOutput": True,
    }


def test_pre_tool_injects_context_when_hits_present(session_dir, monkeypatch) -> None:
    from claude_smart.events import pre_tool

    calls: list[dict[str, Any]] = []
    _stub_pretool_adapter(
        monkeypatch,
        playbooks=[{"content": "run uv sync after edits", "trigger": "pyproject.toml"}],
        profiles=[{"content": "prefers anyio over asyncio"}],
        calls=calls,
    )
    buf = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buf)
    pre_tool.handle(
        {
            "session_id": "s1",
            "tool_name": "Edit",
            "tool_input": {"file_path": "src/x/pyproject.toml", "new_string": "dep"},
        }
    )
    payload = json.loads(buf.getvalue().strip())
    assert payload["hookSpecificOutput"]["hookEventName"] == "PreToolUse"
    markdown = payload["hookSpecificOutput"]["additionalContext"]
    assert "run uv sync after edits" in markdown
    assert "prefers anyio over asyncio" in markdown
    # Composed query must reach the adapter with both scoping ids.
    assert calls[0]["project_id"] == "demo"
    assert calls[0]["session_id"] == "s1"
    assert "pyproject.toml" in calls[0]["query"]


def test_pre_tool_emits_continue_when_search_empty(session_dir, monkeypatch) -> None:
    from claude_smart.events import pre_tool

    _stub_pretool_adapter(monkeypatch, playbooks=[], profiles=[])
    buf = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buf)
    pre_tool.handle(
        {
            "session_id": "s1",
            "tool_name": "Bash",
            "tool_input": {"command": "uv run pytest"},
        }
    )
    assert json.loads(buf.getvalue().strip()) == {
        "continue": True,
        "suppressOutput": True,
    }
