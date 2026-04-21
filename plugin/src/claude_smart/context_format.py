"""Render reflexio profiles + playbooks as markdown for SessionStart injection."""

from __future__ import annotations

from typing import Any, Iterable


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
    playbook_lines = _format_playbooks(playbooks)
    profile_lines = _format_profiles(profiles)
    if not playbook_lines and not profile_lines:
        return ""

    sections: list[str] = [f"## claude-smart — project `{project_id}`"]
    if playbook_lines:
        sections.append("### Project playbook")
        sections.extend(playbook_lines)
    if profile_lines:
        sections.append("### Session preferences")
        sections.extend(profile_lines)
    return "\n".join(sections) + "\n"


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
            ``### Relevant session preferences`` sub-sections, or ``""``
            when both inputs are empty.
    """
    del project_id  # kept in the signature for symmetry with ``render``.
    playbook_lines = _format_playbooks(playbooks)
    profile_lines = _format_profiles(profiles)
    if not playbook_lines and not profile_lines:
        return ""
    sections: list[str] = []
    if playbook_lines:
        sections.append("### Relevant playbook rules")
        sections.extend(playbook_lines)
    if profile_lines:
        sections.append("### Relevant session preferences")
        sections.extend(profile_lines)
    return "\n".join(sections) + "\n"


def _format_playbooks(playbooks: Iterable[Any]) -> list[str]:
    lines: list[str] = []
    for pb in playbooks:
        content = _first_nonempty(_field(pb, "content"))
        if not content:
            continue
        trigger = _first_nonempty(_field(pb, "trigger"))
        rationale = _first_nonempty(_field(pb, "rationale"))
        bullet = f"- {content}"
        if trigger:
            bullet += f" _(when: {trigger})_"
        if rationale:
            bullet += f" — *why:* {rationale}"
        lines.append(bullet)
    return lines


def _format_profiles(profiles: Iterable[Any]) -> list[str]:
    lines: list[str] = []
    for p in profiles:
        content = _first_nonempty(_field(p, "content"))
        if content:
            lines.append(f"- {content}")
    return lines


def _field(obj: Any, name: str) -> Any:
    """Read ``name`` from either an attribute or a dict key."""
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)
