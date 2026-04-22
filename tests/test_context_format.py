"""Tests for the context-markdown renderer and citation registry."""

from __future__ import annotations

from claude_smart import context_format, cs_cite


def test_render_with_registry_empty_returns_empty_tuple() -> None:
    md, registry = context_format.render_with_registry(
        project_id="demo", playbooks=[], profiles=[]
    )
    assert md == ""
    assert registry == []


def test_render_with_registry_empty_content_items_ignored() -> None:
    """Items whose ``content`` is blank contribute neither bullet nor registry entry."""
    md, registry = context_format.render_with_registry(
        project_id="demo",
        playbooks=[{"content": ""}, {"content": "   "}],
        profiles=[{"content": None}],
    )
    assert md == ""
    assert registry == []


def test_render_with_registry_ids_match_between_markdown_and_registry() -> None:
    pbs = [{"content": "use pathlib"}]
    prs = [{"content": "prefers anyio"}]
    md, registry = context_format.render_with_registry(
        project_id="demo", playbooks=pbs, profiles=prs
    )
    pb_id = cs_cite.short_id("playbook", "use pathlib")
    pr_id = cs_cite.short_id("profile", "prefers anyio")
    assert f"[cs:{pb_id}]" in md
    assert f"[cs:{pr_id}]" in md
    assert {e["id"] for e in registry} == {pb_id, pr_id}
    kinds = {e["id"]: e["kind"] for e in registry}
    assert kinds[pb_id] == "playbook"
    assert kinds[pr_id] == "profile"


def test_render_with_registry_emits_citation_instruction() -> None:
    md, _ = context_format.render_with_registry(
        project_id="demo",
        playbooks=[{"content": "x"}],
        profiles=[],
    )
    assert cs_cite.CITATION_INSTRUCTION in md


def test_render_with_registry_playbook_trigger_and_rationale_emitted() -> None:
    pbs = [
        {
            "content": "use pathlib",
            "trigger": "writing a script",
            "rationale": "os.path is error-prone",
        }
    ]
    md, _ = context_format.render_with_registry(
        project_id="demo", playbooks=pbs, profiles=[]
    )
    assert "_(when: writing a script)_" in md
    assert "*why:* os.path is error-prone" in md


def test_render_inline_with_registry_uses_inline_headers() -> None:
    md, registry = context_format.render_inline_with_registry(
        project_id="demo",
        playbooks=[{"content": "use pathlib"}],
        profiles=[{"content": "prefers anyio"}],
    )
    assert "### Relevant playbook rules" in md
    assert "### Relevant project preferences" in md
    assert len(registry) == 2


def test_title_from_content_short_content_kept_intact() -> None:
    assert context_format._title_from_content("short content") == "short content"


def test_title_from_content_truncates_with_ellipsis() -> None:
    long = "a" * 200
    out = context_format._title_from_content(long, limit=10)
    assert out.endswith("…")
    assert len(out) == 10


def test_title_from_content_splits_on_sentence_boundary() -> None:
    text = "First sentence. Second sentence."
    assert context_format._title_from_content(text) == "First sentence"
