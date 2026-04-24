"""Render reflexio profiles + playbooks as markdown for SessionStart injection."""

from __future__ import annotations

from typing import Any, Iterable

from claude_smart import cs_cite


def _first_nonempty(*values: Any) -> str:
    """Return the first truthy string value, or an empty string."""
    for v in values:
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def render(
    *,
    project_id: str,
    playbooks: Iterable[Any],
    profiles: Iterable[Any],
) -> str:
    """Render playbooks + profiles as the markdown injected at SessionStart.

    Empty sections are omitted. When both sections are empty, returns "".

    Args:
        project_id: Displayed in the header so the user can tell which
            project's playbook is in effect.
        playbooks: Iterable of ``UserPlaybook`` objects (or dicts with the
            same fields).
        profiles: Iterable of ``UserProfile`` objects (or dicts).

    Returns:
        str: Markdown, or "" when there is nothing to show.
    """
    markdown, _ = render_with_registry(
        project_id=project_id, playbooks=playbooks, profiles=profiles
    )
    return markdown


def render_with_registry(
    *,
    project_id: str,
    playbooks: Iterable[Any],
    profiles: Iterable[Any],
) -> tuple[str, list[dict[str, Any]]]:
    """Variant of ``render`` that also returns the citation registry.

    Every playbook and profile bullet is tagged with a short
    ``[cs:ID]`` prefix. The registry maps those ids back to
    ``{id, kind, title, content}`` entries so ``events.stop`` can
    resolve citations into human-readable titles for the dashboard.

    Args:
        project_id (str): Displayed in the header so the user can tell
            which project's playbook is in effect.
        playbooks (Iterable[Any]): Iterable of ``UserPlaybook`` objects
            (or dicts with the same fields).
        profiles (Iterable[Any]): Iterable of ``UserProfile`` objects
            (or dicts).

    Returns:
        tuple[str, list[dict[str, Any]]]: ``(markdown, registry_entries)``.
            When both playbook and profile lists are empty the markdown
            is ``""`` and the registry is ``[]``.
    """
    playbook_lines, playbook_entries = _format_playbooks(playbooks)
    profile_lines, profile_entries = _format_profiles(profiles)
    if not playbook_lines and not profile_lines:
        return "", []

    sections: list[str] = [f"## claude-smart — project `{project_id}`"]
    if playbook_lines:
        sections.append("### Playbook")
        sections.extend(playbook_lines)
    if profile_lines:
        sections.append("### Project preferences")
        sections.extend(profile_lines)
    sections.append(cs_cite.CITATION_INSTRUCTION)
    return "\n".join(sections) + "\n", playbook_entries + profile_entries


def render_inline(
    *,
    project_id: str,
    playbooks: Iterable[Any],
    profiles: Iterable[Any],
) -> str:
    """Render playbooks + profiles for mid-session (PreToolUse) injection.

    Same bullet format as ``render`` but with no top-level project header —
    this block is injected just-in-time alongside an in-flight tool call, not
    at session start, so the caller already has project context.

    Args:
        project_id (str): Reserved for future use (e.g. multi-project
            diagnostics); currently unused in the output.
        playbooks (Iterable[Any]): Relevance-ranked playbook hits.
        profiles (Iterable[Any]): Relevance-ranked profile hits.

    Returns:
        str: Markdown with ``### Relevant playbook rules`` and/or
            ``### Relevant project preferences`` sub-sections, or ``""``
            when both inputs are empty.
    """
    markdown, _ = render_inline_with_registry(
        project_id=project_id, playbooks=playbooks, profiles=profiles
    )
    return markdown


def render_inline_with_registry(
    *,
    project_id: str,
    playbooks: Iterable[Any],
    profiles: Iterable[Any],
) -> tuple[str, list[dict[str, Any]]]:
    """Variant of ``render_inline`` that also returns the citation registry.

    Args:
        project_id (str): Reserved for future use; currently unused in
            the output.
        playbooks (Iterable[Any]): Relevance-ranked playbook hits.
        profiles (Iterable[Any]): Relevance-ranked profile hits.

    Returns:
        tuple[str, list[dict[str, Any]]]: ``(markdown, registry_entries)``.
            When both playbook and profile lists are empty the markdown
            is ``""`` and the registry is ``[]``.
    """
    del project_id  # kept for symmetry with ``render_with_registry``.
    playbook_lines, playbook_entries = _format_playbooks(playbooks)
    profile_lines, profile_entries = _format_profiles(profiles)
    if not playbook_lines and not profile_lines:
        return "", []
    sections: list[str] = []
    if playbook_lines:
        sections.append("### Relevant playbook rules")
        sections.extend(playbook_lines)
    if profile_lines:
        sections.append("### Relevant project preferences")
        sections.extend(profile_lines)
    sections.append(cs_cite.CITATION_INSTRUCTION)
    return "\n".join(sections) + "\n", playbook_entries + profile_entries


def _format_playbooks(
    playbooks: Iterable[Any],
) -> tuple[list[str], list[dict[str, Any]]]:
    lines: list[str] = []
    entries: list[dict[str, Any]] = []
    rank = 0
    for pb in playbooks:
        content = _first_nonempty(_field(pb, "content"))
        if not content:
            continue
        rank += 1
        trigger = _first_nonempty(_field(pb, "trigger"))
        rationale = _first_nonempty(_field(pb, "rationale"))
        real_id = _field(pb, "user_playbook_id")
        item_id = cs_cite.rank_id("playbook", rank, real_id)
        title = _title_from_content(content)
        bullet = f"- [cs:{item_id}] {content}"
        if trigger:
            bullet += f" _(when: {trigger})_"
        if rationale:
            bullet += f" — *why:* {rationale}"
        lines.append(bullet)
        entries.append(
            {
                "id": item_id,
                "kind": "playbook",
                "title": title,
                "content": content,
                "real_id": str(real_id) if real_id is not None else None,
            }
        )
    return lines, entries


def _format_profiles(
    profiles: Iterable[Any],
) -> tuple[list[str], list[dict[str, Any]]]:
    lines: list[str] = []
    entries: list[dict[str, Any]] = []
    rank = 0
    for p in profiles:
        content = _first_nonempty(_field(p, "content"))
        if not content:
            continue
        rank += 1
        real_id = _field(p, "profile_id")
        item_id = cs_cite.rank_id("profile", rank, real_id)
        title = _title_from_content(content)
        lines.append(f"- [cs:{item_id}] {content}")
        entries.append(
            {
                "id": item_id,
                "kind": "profile",
                "title": title,
                "content": content,
                "real_id": str(real_id) if real_id is not None else None,
            }
        )
    return lines, entries


def _title_from_content(content: str, limit: int = 80) -> str:
    """Derive a compact human-readable title from a bullet's content.

    Truncates at the first sentence boundary when one falls within the
    character limit; otherwise hard-trims with an ellipsis. Used only for
    dashboard display.
    """
    text = content.strip()
    if not text:
        return ""
    for terminator in (". ", "\n"):
        idx = text.find(terminator)
        if 0 < idx <= limit:
            return text[:idx].rstrip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _field(obj: Any, name: str) -> Any:
    """Read ``name`` from either an attribute or a dict key."""
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)
