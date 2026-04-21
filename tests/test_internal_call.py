"""Tests for the reflexio self-feedback guard.

``is_internal_invocation`` is the gate that stops the Stop hook from
publishing reflexio's own extractor prompts back into reflexio. A silent
regression here causes the backend to train on its own internals, so
each detection path has an explicit test.
"""

from __future__ import annotations

import pytest

from claude_smart import internal_call
from claude_smart.internal_call import is_internal_invocation


def test_returns_true_when_env_marker_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDE_SMART_INTERNAL", "1")
    assert is_internal_invocation({}) is True


def test_env_marker_wins_over_cwd(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDE_SMART_INTERNAL", "1")
    assert is_internal_invocation({"cwd": "/tmp"}) is True


def test_returns_true_when_cwd_inside_reflexio(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.delenv("CLAUDE_SMART_INTERNAL", raising=False)
    fake_reflexio = tmp_path / "reflexio"
    (fake_reflexio / "server").mkdir(parents=True)
    monkeypatch.setattr(internal_call, "_REFLEXIO_DIR", fake_reflexio)
    assert is_internal_invocation({"cwd": str(fake_reflexio / "server")}) is True


def test_returns_false_for_external_cwd(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.delenv("CLAUDE_SMART_INTERNAL", raising=False)
    fake_reflexio = tmp_path / "reflexio"
    fake_reflexio.mkdir()
    monkeypatch.setattr(internal_call, "_REFLEXIO_DIR", fake_reflexio)
    assert is_internal_invocation({"cwd": str(tmp_path)}) is False


def test_returns_false_when_cwd_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CLAUDE_SMART_INTERNAL", raising=False)
    assert is_internal_invocation({}) is False


def test_returns_false_when_cwd_empty_string(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CLAUDE_SMART_INTERNAL", raising=False)
    assert is_internal_invocation({"cwd": ""}) is False


@pytest.mark.parametrize("bad_cwd", [None, 123, ["/tmp"], {"path": "/tmp"}])
def test_returns_false_when_cwd_wrong_type(
    monkeypatch: pytest.MonkeyPatch, bad_cwd: object
) -> None:
    monkeypatch.delenv("CLAUDE_SMART_INTERNAL", raising=False)
    assert is_internal_invocation({"cwd": bad_cwd}) is False


def test_env_marker_other_values_do_not_trigger(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CLAUDE_SMART_INTERNAL", "0")
    assert is_internal_invocation({}) is False
    monkeypatch.setenv("CLAUDE_SMART_INTERNAL", "true")
    assert is_internal_invocation({}) is False
