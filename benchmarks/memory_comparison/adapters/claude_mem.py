"""claude-mem retrieval adapter for the benchmark.

Reads directly from ``~/.claude-mem/claude-mem.db``. Uses the FTS5 virtual
table ``observations_fts`` for ranked retrieval and falls back to a recency
scan when FTS returns nothing.
"""

from __future__ import annotations

import logging
import re
import sqlite3
import time
from pathlib import Path

_LOGGER = logging.getLogger(__name__)

CLAUDE_MEM_DB = Path.home() / ".claude-mem" / "claude-mem.db"

# Stopwords to strip from probes before building an FTS match query. Judge
# retrieval quality comes from content words, not function words.
_STOPWORDS = frozenset(
    "a an and are as at be by for from has have in is it of on or that "
    "the to was were will with what does do who when where why how".split()
)
_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9_]+")


def _fts_query(probe: str) -> str:
    """Turn a natural-language probe into an FTS5 OR-of-prefixes expression.

    Args:
        probe (str): Free-text probe query from the scenario.

    Returns:
        str: Space-OR-joined FTS5 expression (each term uses the ``*`` prefix
            operator for loose matching), or empty string if no content words.
    """
    terms = [
        t.lower()
        for t in _TOKEN.findall(probe)
        if t.lower() not in _STOPWORDS and len(t) > 2
    ]
    if not terms:
        return ""
    return " OR ".join(f"{t}*" for t in terms)


def wait_for_worker_drain(*, session_id: str, timeout_s: float = 90.0) -> bool:
    """Poll ``pending_messages`` until the scenario's queue is empty.

    claude-mem's background worker processes queued turn messages and
    generates observations asynchronously via an LLM extraction call. For a
    fair comparison we wait until the queue has drained before scoring.

    Args:
        session_id (str): ``content_session_id`` rows were inserted under.
        timeout_s (float): Max wait before giving up. Per-scenario extraction
            can take 30–60s because each pending_message issues one LLM call.

    Returns:
        bool: True if the queue drained, False on timeout. The harness still
            scores either way; False is logged in the result row.
    """
    deadline = time.monotonic() + timeout_s
    with sqlite3.connect(f"file:{CLAUDE_MEM_DB}?mode=ro", uri=True) as conn:
        while time.monotonic() < deadline:
            row = conn.execute(
                "SELECT COUNT(*) FROM pending_messages "
                "WHERE content_session_id = ? AND status IN ('pending', 'processing')",
                (session_id,),
            ).fetchone()
            if row[0] == 0:
                return True
            time.sleep(1.5)
    _LOGGER.warning(
        "claude-mem worker did not drain session=%s within %ss", session_id, timeout_s
    )
    return False


def _row_to_text(row: sqlite3.Row) -> str:
    """Concatenate the non-empty text fields of an observation for scoring."""
    parts = [
        row[k] for k in ("title", "subtitle", "narrative", "text", "facts") if row[k]
    ]
    return " | ".join(str(p) for p in parts)


def _project_key(project: str) -> str:
    """Normalize a project path into claude-mem's stored project key.

    claude-mem tags observations with the project basename (e.g.,
    ``pref-testfmk``), not the full cwd. Passing in either form works.

    Args:
        project (str): Full path or bare name.

    Returns:
        str: The basename claude-mem uses.
    """
    from pathlib import Path as _P

    return _P(project).name or project


def retrieve(*, project: str, probe_query: str, top_k: int = 5) -> list[str]:
    """Return up to ``top_k`` observation texts most relevant to the probe.

    Ranking strategy:
        1. FTS5 ``MATCH`` with OR-of-prefixes on content words, ordered by
           BM25.
        2. If FTS returns nothing (probe fully stopworded, or no rows match),
           fall back to the most recent observations for the project.

    Args:
        project (str): Project_id the scenario ran in.
        probe_query (str): Retrieval probe from the scenario.
        top_k (int): Max observations to return.

    Returns:
        list[str]: Each element prefixed with ``[obs]`` for judge clarity.
    """
    fts = _fts_query(probe_query)
    key = _project_key(project)
    with sqlite3.connect(f"file:{CLAUDE_MEM_DB}?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        rows: list[sqlite3.Row] = []
        if fts:
            rows = list(
                conn.execute(
                    """
                    SELECT o.title, o.subtitle, o.narrative, o.text, o.facts
                    FROM observations_fts f
                    JOIN observations o ON o.id = f.rowid
                    WHERE f.observations_fts MATCH ?
                      AND o.project = ?
                    ORDER BY bm25(observations_fts)
                    LIMIT ?
                    """,
                    (fts, key, top_k),
                )
            )
        if not rows:
            rows = list(
                conn.execute(
                    """
                    SELECT title, subtitle, narrative, text, facts
                    FROM observations
                    WHERE project = ?
                    ORDER BY created_at_epoch DESC
                    LIMIT ?
                    """,
                    (key, top_k),
                )
            )
    return [f"[obs] {_row_to_text(r)}" for r in rows if _row_to_text(r)]
