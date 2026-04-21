"""Tests for project-id resolution."""

from __future__ import annotations

import subprocess

from claude_smart import ids


def test_resolve_uses_git_toplevel_basename(tmp_path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subdir = tmp_path / "packages" / "core"
    subdir.mkdir(parents=True)
    assert ids.resolve_project_id(subdir) == tmp_path.name


def test_resolve_falls_back_to_cwd_basename_outside_git(tmp_path) -> None:
    # tmp_path from pytest is not inside a git repo.
    assert ids.resolve_project_id(tmp_path) == tmp_path.name


def test_resolve_handles_missing_git_binary(tmp_path, monkeypatch) -> None:
    def _boom(*_a, **_kw):
        raise FileNotFoundError("git missing")

    monkeypatch.setattr(subprocess, "run", _boom)
    assert ids.resolve_project_id(tmp_path) == tmp_path.name
