"""Tests for the per-session JSONL buffer."""

from __future__ import annotations

import json
import multiprocessing as mp
import os

from claude_smart import state


def test_append_and_read_roundtrip(session_dir) -> None:
    state.append("s1", {"role": "User", "content": "hi"})
    state.append("s1", {"role": "Assistant", "content": "hello"})
    assert state.read_all("s1") == [
        {"role": "User", "content": "hi"},
        {"role": "Assistant", "content": "hello"},
    ]


def test_read_all_skips_malformed_lines(session_dir) -> None:
    path = state.session_path("s1")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        '{"role":"User","content":"ok"}\nnot-json\n{"role":"Assistant","content":"ok"}\n'
    )
    records = state.read_all("s1")
    assert len(records) == 2
    assert records[0]["role"] == "User"
    assert records[1]["role"] == "Assistant"


def test_unpublished_slice_respects_watermark() -> None:
    records = [
        {"role": "User", "content": "u1"},
        {"role": "Assistant", "content": "a1"},
        {"published_up_to": 2},
        {"role": "User", "content": "u2"},
        {"role": "Assistant", "content": "a2"},
    ]
    watermark, turns = state.unpublished_slice(records)
    assert watermark == 2
    assert [t["content"] for t in turns] == ["u2", "a2"]


def test_unpublished_slice_attaches_tools_to_next_assistant() -> None:
    records = [
        {"role": "User", "content": "u1"},
        {
            "role": "Assistant_tool",
            "tool_name": "Bash",
            "tool_input": {"command": "ls"},
            "status": "success",
        },
        {
            "role": "Assistant_tool",
            "tool_name": "Read",
            "tool_input": {"file_path": "/tmp/x"},
            "status": "error",
        },
        {"role": "Assistant", "content": "a1"},
    ]
    _, turns = state.unpublished_slice(records)
    assert turns[-1]["role"] == "Assistant"
    assert turns[-1]["tools_used"] == [
        {
            "tool_name": "Bash",
            "status": "success",
            "tool_data": {"input": {"command": "ls"}},
        },
        {
            "tool_name": "Read",
            "status": "error",
            "tool_data": {"input": {"file_path": "/tmp/x"}},
        },
    ]


def test_unpublished_slice_omits_tool_data_when_input_missing() -> None:
    """Legacy records without ``tool_input`` still publish, without a tool_data key."""
    records = [
        {"role": "User", "content": "u1"},
        {"role": "Assistant_tool", "tool_name": "Bash", "status": "success"},
        {"role": "Assistant", "content": "a1"},
    ]
    _, turns = state.unpublished_slice(records)
    assert turns[-1]["tools_used"] == [
        {"tool_name": "Bash", "status": "success"},
    ]


def test_unpublished_slice_silent_assistant_placeholder_pins_tools() -> None:
    """Option A: an empty-content Assistant record still owns its tool runs."""
    records = [
        {"role": "User", "content": "u1"},
        {
            "role": "Assistant_tool",
            "tool_name": "Bash",
            "tool_input": {"command": "ls"},
            "status": "success",
        },
        {"role": "Assistant", "content": ""},  # Stop-hook placeholder
        {"role": "User", "content": "u2"},
        {
            "role": "Assistant_tool",
            "tool_name": "Edit",
            "tool_input": {"file_path": "/a"},
            "status": "success",
        },
        {"role": "Assistant", "content": "done"},
    ]
    _, turns = state.unpublished_slice(records)
    assert turns[0] == {"role": "User", "content": "u1"}
    assert turns[1]["role"] == "Assistant"
    assert turns[1]["content"] == ""
    assert turns[1]["tools_used"] == [
        {
            "tool_name": "Bash",
            "status": "success",
            "tool_data": {"input": {"command": "ls"}},
        },
    ]
    assert turns[2] == {"role": "User", "content": "u2"}
    assert turns[3]["tools_used"] == [
        {
            "tool_name": "Edit",
            "status": "success",
            "tool_data": {"input": {"file_path": "/a"}},
        },
    ]


def _append_worker(state_dir: str, session_id: str, payload: str) -> None:
    # Child processes inherit env after fork, so CLAUDE_SMART_STATE_DIR is
    # already set. Belt-and-suspenders: reassert it.
    os.environ["CLAUDE_SMART_STATE_DIR"] = state_dir
    from claude_smart import state as s  # fresh import in child

    s.append(session_id, {"role": "User", "content": payload})


def test_append_concurrent_writes_do_not_corrupt_jsonl(session_dir) -> None:
    """Under flock, concurrent appends of large payloads must stay line-atomic."""
    big = "x" * 128 * 1024  # 128 KB — above any stdio buffer
    ctx = mp.get_context("fork")
    procs = [
        ctx.Process(target=_append_worker, args=(str(session_dir), "s1", big))
        for _ in range(8)
    ]
    for p in procs:
        p.start()
    for p in procs:
        p.join(timeout=30)
        assert p.exitcode == 0

    path = state.session_path("s1")
    raw_lines = path.read_text().splitlines()
    assert len(raw_lines) == 8
    for line in raw_lines:
        record = json.loads(line)  # must parse — no interleaving
        assert record == {"role": "User", "content": big}
