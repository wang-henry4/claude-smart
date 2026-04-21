"""claude-smart retrieval adapter for the benchmark.

Reuses ``claude_smart.reflexio_adapter.Adapter`` to query the reflexio
backend for the playbooks and profiles extracted during a scenario run.
Publish is non-blocking (matches production), so the adapter exposes a
``wait_for_extraction`` poll that waits until at least one profile or
playbook materializes for the scenario.
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path
from typing import Any

_LOGGER = logging.getLogger(__name__)

_THIS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _THIS_DIR.parents[2]  # benchmarks/memory_comparison/adapters -> repo root
_SRC_DIR = _REPO_ROOT / "src"

if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from claude_smart.reflexio_adapter import Adapter  # noqa: E402


def wait_for_extraction(
    *, project_dir: Path, session_id: str, timeout_s: float = 60.0
) -> bool:
    """Poll reflexio until extraction produces at least one record.

    Reflexio's ``publish_interaction`` is fire-and-forget in production
    (the reflexio hook in claude-smart passes ``wait_for_response=False``
    so user turns aren't blocked on LLM extraction). For a benchmark we
    still need to know when the data is queryable.

    Args:
        project_dir (Path): Scenario project / reflexio agent_version.
        session_id (str): Reflexio user_id and session_id.
        timeout_s (float): Max wait budget before giving up.

    Returns:
        bool: True once any profile or playbook has materialized, False on
            timeout. Callers still run their scored query either way.
    """
    deadline = time.monotonic() + timeout_s
    adapter = Adapter()
    while time.monotonic() < deadline:
        playbooks, profiles = adapter.fetch_both(
            project_id=str(project_dir),
            session_id=session_id,
            playbook_top_k=1,
            profile_top_k=1,
        )
        if playbooks or profiles:
            return True
        time.sleep(1.0)
    _LOGGER.warning(
        "claude-smart extraction did not materialize for session=%s within %ss",
        session_id,
        timeout_s,
    )
    return False


def _render(items: list[Any], label: str) -> list[str]:
    """Flatten playbook/profile records into plain strings for scoring.

    Args:
        items (list[Any]): Records returned by ``Adapter.search_*``.
        label (str): Short tag (``playbook`` or ``profile``) prepended to each
            line so the judge can tell them apart.

    Returns:
        list[str]: One string per item, non-empty fields joined.
    """
    out: list[str] = []
    for item in items:
        content = _get(item, "content") or _get(item, "text") or ""
        trigger = _get(item, "trigger") or ""
        rationale = _get(item, "rationale") or ""
        parts = [p for p in (content, trigger, rationale) if p]
        if parts:
            out.append(f"[{label}] " + " | ".join(parts))
    return out


def _get(obj: Any, field: str) -> str:
    """Read a field from a dict or dataclass-like record, empty string if absent."""
    if obj is None:
        return ""
    if isinstance(obj, dict):
        value = obj.get(field)
    else:
        value = getattr(obj, field, None)
    return str(value) if value else ""


def retrieve(
    *,
    project_dir: Path,
    session_id: str,
    probe_query: str,
    top_k: int = 5,
) -> list[str]:
    """Search playbooks and profiles via reflexio, return flat text list.

    Both legs of the fan-out tolerate failure (the adapter returns ``[]`` on
    backend error), so this function never raises.

    Args:
        project_dir (Path): Scenario scratch dir = project_id.
        session_id (str): Claude session id = reflexio user_id.
        probe_query (str): Retrieval query from the scenario.
        top_k (int): Results per side (playbooks, profiles).

    Returns:
        list[str]: Rendered memory lines, playbooks first then profiles.
    """
    adapter = Adapter()
    playbooks, profiles = adapter.search_both(
        project_id=str(project_dir),
        session_id=session_id,
        query=probe_query,
        top_k=top_k,
    )
    return _render(playbooks, "playbook") + _render(profiles, "profile")
