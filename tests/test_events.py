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


def test_post_tool_records_tool_input(session_dir) -> None:
    post_tool.handle(
        {
            "session_id": "s1",
            "tool_name": "Bash",
            "tool_input": {"command": "ls -la"},
            "tool_response": {"ok": True},
        }
    )
    post_tool.handle(
        {
            "session_id": "s1",
            "tool_name": "Read",
            "tool_response": "plain",
        }
    )
    records = state.read_all("s1")
    assert records[0]["tool_input"] == {"command": "ls -la"}
    assert records[1]["tool_input"] == {}


def test_post_tool_redacts_secret_assignments(session_dir) -> None:
    """High-entropy KEY=VALUE secrets are masked; benign assignments survive."""
    post_tool.handle(
        {
            "session_id": "s1",
            "tool_name": "Bash",
            "tool_input": {
                "command": (
                    'AWS_SECRET_ACCESS_KEY="wJalrXUtnFEMI0abcdEXAMPLEkey123" '
                    "LOG_LEVEL=INFO curl -sf https://example.com"
                ),
            },
        }
    )
    records = state.read_all("s1")
    command = records[0]["tool_input"]["command"]
    assert "wJalrXUtnFEMI0abcdEXAMPLEkey123" not in command
    assert "<redacted:" in command
    # Benign lowercase-or-short assignments should pass through unchanged.
    assert "LOG_LEVEL=INFO" in command


def test_post_tool_truncates_oversized_string(session_dir) -> None:
    blob = "x" * 5000
    post_tool.handle(
        {
            "session_id": "s1",
            "tool_name": "Write",
            "tool_input": {"file_path": "/tmp/huge", "content": blob},
        }
    )
    stored = state.read_all("s1")[0]["tool_input"]["content"]
    assert stored.endswith("…(truncated)")
    assert len(stored) < len(blob)
    # file_path is short and must not be affected.
    assert state.read_all("s1")[0]["tool_input"]["file_path"] == "/tmp/huge"


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


def test_stop_concatenates_text_across_multi_entry_assistant_turn(
    session_dir, tmp_path, monkeypatch
) -> None:
    """A turn spans many transcript entries; all text blocks must be captured.

    Claude Code's JSONL writes each thinking/tool_use/text block as its own
    ``type: assistant`` entry. Tool results arrive as ``type: user`` entries
    holding ``tool_result`` blocks — they must not be treated as a turn
    boundary. Only the leading real user message bounds the collection.
    """
    transcript = _write_transcript(
        tmp_path,
        [
            {"type": "user", "message": {"content": "do the thing"}},
            {
                "type": "assistant",
                "message": {"content": [{"type": "thinking", "text": "hmm"}]},
            },
            {
                "type": "assistant",
                "message": {"content": [{"type": "text", "text": "Let me check."}]},
            },
            {
                "type": "assistant",
                "message": {"content": [{"type": "tool_use", "name": "Read"}]},
            },
            {
                "type": "user",
                "message": {"content": [{"type": "tool_result", "content": "..."}]},
            },
            {
                "type": "assistant",
                "message": {"content": [{"type": "text", "text": "Found it."}]},
            },
            {
                "type": "assistant",
                "message": {"content": [{"type": "tool_use", "name": "Edit"}]},
            },
            {
                "type": "user",
                "message": {"content": [{"type": "tool_result", "content": "ok"}]},
            },
            {
                "type": "assistant",
                "message": {"content": [{"type": "text", "text": "Done."}]},
            },
        ],
    )
    monkeypatch.setattr(
        "claude_smart.publish.publish_unpublished",
        lambda **_: ("nothing", 0),
    )
    stop.handle({"session_id": "s1", "transcript_path": str(transcript)})
    records = state.read_all("s1")
    assert records[-1]["role"] == "Assistant"
    assert records[-1]["content"] == "Let me check.\n\nFound it.\n\nDone."


def test_stop_does_not_cross_prior_turn_boundary(
    session_dir, tmp_path, monkeypatch
) -> None:
    """Backward walk must stop at the user message that opened THIS turn.

    Regression guard: earlier assistant text must NOT leak into the
    current Assistant record, or prior-turn content would get republished
    to reflexio every time the Stop hook fires.
    """
    transcript = _write_transcript(
        tmp_path,
        [
            {"type": "user", "message": {"content": "first question"}},
            {
                "type": "assistant",
                "message": {"content": [{"type": "text", "text": "First answer."}]},
            },
            {"type": "user", "message": {"content": "follow-up"}},
            {
                "type": "assistant",
                "message": {"content": [{"type": "text", "text": "Second answer."}]},
            },
        ],
    )
    monkeypatch.setattr(
        "claude_smart.publish.publish_unpublished",
        lambda **_: ("nothing", 0),
    )
    stop.handle({"session_id": "s1", "transcript_path": str(transcript)})
    records = state.read_all("s1")
    assert records[-1]["content"] == "Second answer."


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
        def apply_batch_defaults(self, **_kw):
            return True

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
        def apply_batch_defaults(self, **_kw):
            return True

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


def test_session_start_applies_claude_smart_batch_defaults(
    session_dir, monkeypatch
) -> None:
    """SessionStart must push claude-smart's 5/3 batch defaults to reflexio."""
    applied: list[dict[str, Any]] = []

    class Stub:
        def apply_batch_defaults(self, **kwargs):
            applied.append(kwargs)
            return True

        def fetch_both(self, **_kw):
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
    session_start.handle({"session_id": "s1", "source": "startup"})
    assert applied == [{"batch_size": 5, "batch_interval": 3}]


def test_session_start_fetches_both_on_every_source(session_dir, monkeypatch) -> None:
    """Used to skip profile fetch unless source ∈ {resume,clear,compact}; now always both."""
    calls: list[dict[str, Any]] = []

    class Stub:
        def apply_batch_defaults(self, **_kw):
            return True

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
