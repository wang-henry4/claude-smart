"""Tests for ``claude_smart.cli.cmd_learn``.

The merged ``/learn`` command is the only path users have to mark a turn as
a correction, so the regressions worth pinning are: the correction row is
actually written, the default note kicks in for empty input, the no-active-
session case is a clean no-op, and reflexio being unreachable still leaves
the local correction on disk for the next drain.
"""

from __future__ import annotations

import argparse
from typing import Any

import pytest

from claude_smart import cli, state


def _make_args(**overrides: Any) -> argparse.Namespace:
    """Build a Namespace matching the ``learn`` subparser defaults."""
    defaults = {"note": "", "session": None, "project": "test-project"}
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


@pytest.fixture
def fake_publish(monkeypatch):
    """Stub ``cli.publish.publish_unpublished`` and capture its kwargs.

    Returns:
        tuple[list[dict], dict]: ``(calls, control)`` — ``calls`` records
            each invocation's kwargs in order; ``control`` is mutable so a
            test can flip the canned ``return_value`` before the call.
    """
    calls: list[dict[str, Any]] = []
    control: dict[str, Any] = {"return_value": ("ok", 3)}

    def fake(**kwargs):
        calls.append(kwargs)
        return control["return_value"]

    monkeypatch.setattr(cli.publish, "publish_unpublished", fake)
    return calls, control


def test_cmd_learn_records_correction_and_publishes(
    session_dir, fake_publish, capsys
) -> None:
    """Happy path: correction row appended, publish called, exit 0."""
    state.append("s1", {"role": "User", "content": "hi"})
    state.append("s1", {"role": "Assistant", "content": "wrong answer"})
    calls, _ = fake_publish

    rc = cli.cmd_learn(_make_args(note="please don't do that"))

    assert rc == 0
    records = state.read_all("s1")
    assert records[-1]["role"] == "User"
    assert records[-1]["content"] == "[correction] please don't do that"
    assert records[-1]["user_id"] == "test-project"
    assert calls == [
        {
            "session_id": "s1",
            "project_id": "test-project",
            "force_extraction": True,
            "skip_aggregation": True,
        }
    ]
    out = capsys.readouterr().out
    assert "Recorded correction on session `s1`" in out
    assert "forced extraction" in out


def test_cmd_learn_default_note_when_empty(session_dir, fake_publish) -> None:
    """Empty note → the literal default string is what extraction sees."""
    state.append("s1", {"role": "User", "content": "hi"})

    rc = cli.cmd_learn(_make_args(note=""))

    assert rc == 0
    last = state.read_all("s1")[-1]
    assert last["content"] == "[correction] the previous answer was wrong"


def test_cmd_learn_no_active_session_returns_zero(
    session_dir, fake_publish, capsys
) -> None:
    """Empty state dir → message + exit 0; no JSONL created, no publish call."""
    calls, _ = fake_publish

    rc = cli.cmd_learn(_make_args())

    assert rc == 0
    assert calls == []
    assert list(session_dir.glob("*.jsonl")) == []
    assert "No active claude-smart session buffer found" in capsys.readouterr().out


def test_cmd_learn_reflexio_unreachable_still_persists_correction(
    session_dir, fake_publish, capsys
) -> None:
    """Publish ``failed`` → correction row stays on disk, exit 1."""
    state.append("s1", {"role": "User", "content": "hi"})
    state.append("s1", {"role": "Assistant", "content": "wrong"})
    _, control = fake_publish
    control["return_value"] = ("failed", 2)

    rc = cli.cmd_learn(_make_args(note="bad answer"))

    assert rc == 1
    last = state.read_all("s1")[-1]
    assert last["content"] == "[correction] bad answer"
    assert "Failed to reach reflexio" in capsys.readouterr().out
