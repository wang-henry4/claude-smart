"""Tests for the ``cs-cite`` support helpers and installer."""

from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from claude_smart import cs_cite


def test_parse_citation_command_accepts_bare_invocation() -> None:
    assert cs_cite.parse_citation_command("cs-cite ab12,cd34") == ["ab12", "cd34"]


def test_parse_citation_command_accepts_single_id() -> None:
    assert cs_cite.parse_citation_command("cs-cite ab12") == ["ab12"]


def test_parse_citation_command_accepts_absolute_path_prefix() -> None:
    """The regex documents an optional path prefix for bare TUI rendering."""
    cmd = "/Users/me/.claude-smart/bin/cs-cite ab12"
    assert cs_cite.parse_citation_command(cmd) == ["ab12"]


def test_parse_citation_command_rejects_chained_commands() -> None:
    assert cs_cite.parse_citation_command("cs-cite ab12 && echo ok") == []
    assert cs_cite.parse_citation_command("cs-cite ab12 | cat") == []
    assert cs_cite.parse_citation_command("cs-cite ab12; echo ok") == []


def test_parse_citation_command_rejects_non_hex_ids() -> None:
    assert cs_cite.parse_citation_command("cs-cite xxxx") == []
    assert cs_cite.parse_citation_command("cs-cite toolong") == []


def test_parse_citation_command_normalizes_uppercase() -> None:
    """Uppercase ids are accepted and normalized to lowercase."""
    assert cs_cite.parse_citation_command("cs-cite AB12") == ["ab12"]
    assert cs_cite.parse_citation_command("cs-cite AB12,CD34") == ["ab12", "cd34"]


def test_parse_citation_command_strips_cs_prefix() -> None:
    """The `cs:` prefix from `[cs:xxxx]` tags is stripped automatically."""
    assert cs_cite.parse_citation_command("cs-cite cs:ab12") == ["ab12"]
    assert cs_cite.parse_citation_command("cs-cite cs:ab12,cs:cd34") == [
        "ab12",
        "cd34",
    ]
    assert cs_cite.parse_citation_command("cs-cite cs:ab12,cd34") == ["ab12", "cd34"]


def test_parse_citation_command_accepts_uppercase_cs_prefix() -> None:
    """An uppercase `CS:` prefix is tolerated — the bin script accepts it too."""
    assert cs_cite.parse_citation_command("cs-cite CS:ab12") == ["ab12"]
    assert cs_cite.parse_citation_command("cs-cite CS:AB12,Cs:CD34") == [
        "ab12",
        "cd34",
    ]


def test_parse_citation_command_accepts_whitespace_separators() -> None:
    """Whitespace between ids is accepted alongside commas."""
    assert cs_cite.parse_citation_command("cs-cite ab12 cd34") == ["ab12", "cd34"]
    assert cs_cite.parse_citation_command("cs-cite ab12, cd34") == ["ab12", "cd34"]


def test_parse_citation_command_rejects_embedded_path_traversal() -> None:
    """A path prefix is allowed, but must not contain spaces or extra tokens."""
    assert cs_cite.parse_citation_command("/tmp/../evil cs-cite ab12") == []


def test_short_id_is_stable_and_namespaced() -> None:
    a = cs_cite.short_id("playbook", "use pathlib")
    b = cs_cite.short_id("playbook", "use pathlib")
    c = cs_cite.short_id("profile", "use pathlib")
    assert a == b
    assert a != c
    assert len(a) == 4
    assert all(ch in "0123456789abcdef" for ch in a)


def test_ensure_installed_is_idempotent_and_executable(tmp_path, monkeypatch) -> None:
    """Two calls produce an executable target; the second call is a no-op."""
    monkeypatch.setattr(cs_cite, "_INSTALL_DIR", tmp_path / "bin")
    monkeypatch.setattr(cs_cite, "INSTALL_PATH", tmp_path / "bin" / "cs-cite")
    cs_cite.ensure_installed()
    target = tmp_path / "bin" / "cs-cite"
    assert target.is_file()
    mode = target.stat().st_mode
    assert mode & stat.S_IXUSR
    first_mtime = target.stat().st_mtime_ns
    # Second call must not raise and must leave the bit set.
    cs_cite.ensure_installed()
    assert target.stat().st_mode & stat.S_IXUSR
    # copy2 preserves the source mtime, so the file's mtime should be stable
    # across repeated calls (guards against a re-download/re-build loop).
    assert target.stat().st_mtime_ns == first_mtime


def test_ensure_installed_tolerates_readonly_target_parent(
    tmp_path, monkeypatch
) -> None:
    """Install is best-effort: read-only parent dir must not raise."""
    if os.geteuid() == 0:
        pytest.skip("root bypasses the read-only bit")
    parent = tmp_path / "locked"
    parent.mkdir()
    parent.chmod(0o500)
    try:
        monkeypatch.setattr(cs_cite, "_INSTALL_DIR", parent / "bin")
        monkeypatch.setattr(cs_cite, "INSTALL_PATH", parent / "bin" / "cs-cite")
        # Must not raise.
        cs_cite.ensure_installed()
    finally:
        parent.chmod(0o700)


def _run_cs_cite(*argv: str) -> subprocess.CompletedProcess[str]:
    script = Path(__file__).resolve().parents[1] / "plugin" / "bin" / "cs-cite"
    return subprocess.run(
        [sys.executable, str(script), *argv],
        capture_output=True,
        text=True,
        check=False,
    )


def test_cs_cite_script_prints_singular_line() -> None:
    r = _run_cs_cite("ab12")
    assert r.returncode == 0
    assert r.stdout == "✨ used 1 claude-smart learning\n"


def test_cs_cite_script_prints_plural_line() -> None:
    r = _run_cs_cite("ab12,cd34,ef56")
    assert r.returncode == 0
    assert r.stdout == "✨ used 3 claude-smart learnings\n"


def test_cs_cite_script_rejects_no_args() -> None:
    r = _run_cs_cite()
    assert r.returncode == 1
    assert "4-hex-char" in r.stderr


def test_cs_cite_script_accepts_space_separated_argv() -> None:
    """Multiple argv tokens are joined; Stop-side regex tolerates the shape."""
    r = _run_cs_cite("ab12", "cd34")
    assert r.returncode == 0
    assert r.stdout == "✨ used 2 claude-smart learnings\n"


def test_cs_cite_script_strips_cs_prefix() -> None:
    """Ids copied verbatim from `[cs:xxxx]` tags are accepted."""
    r = _run_cs_cite("cs:ab12,cs:cd34,cs:ef56")
    assert r.returncode == 0
    assert r.stdout == "✨ used 3 claude-smart learnings\n"


def test_cs_cite_script_normalizes_uppercase() -> None:
    r = _run_cs_cite("AB12,CD34")
    assert r.returncode == 0
    assert r.stdout == "✨ used 2 claude-smart learnings\n"


def test_cs_cite_script_rejects_non_hex_ids() -> None:
    r = _run_cs_cite("xxxx")
    assert r.returncode == 1
    assert "4-hex-char" in r.stderr


def test_cs_cite_script_warns_on_mixed_valid_and_invalid() -> None:
    """Valid ids still succeed; invalid tokens are flagged on stderr."""
    r = _run_cs_cite("ab12,notahex,cd34")
    assert r.returncode == 0
    assert r.stdout == "✨ used 2 claude-smart learnings\n"
    assert "notahex" in r.stderr
