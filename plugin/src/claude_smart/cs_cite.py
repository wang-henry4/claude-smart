"""Support helpers for the ``cs-cite`` citation channel.

Context injected at SessionStart / PreToolUse tags each playbook and
profile bullet with a short stable id (``[cs:ab12]``). The injected
instruction asks Claude to end impactful replies with a call like::

    cs-cite ab12,cd34

via the Bash tool. The Stop hook later scans the session transcript for
those tool calls and resolves the ids against a per-session registry
persisted at ``~/.claude-smart/sessions/<session_id>.injected.jsonl``.

This module holds:

- ``short_id``: stable 4-hex-char id per (kind, content) pair.
- ``CITATION_CMD_RE``: regex matching a valid ``cs-cite`` command line.
- ``ensure_installed``: idempotent copy of ``plugin/bin/cs-cite`` to
  ``~/.claude-smart/bin/cs-cite`` with the executable bit set.
- ``CITATION_INSTRUCTION``: the trailer text appended to injected
  context so Claude knows when and how to call the tool.
"""

from __future__ import annotations

import hashlib
import logging
import re
import shutil
import stat as stat_
from pathlib import Path

_LOGGER = logging.getLogger(__name__)

_THIS_DIR = Path(__file__).resolve().parent
_PLUGIN_ROOT = _THIS_DIR.parents[1]  # plugin/src/claude_smart/ -> plugin/
_SOURCE_SCRIPT = _PLUGIN_ROOT / "bin" / "cs-cite"
_INSTALL_DIR = Path.home() / ".claude-smart" / "bin"
INSTALL_PATH = _INSTALL_DIR / "cs-cite"

# Match a bare `cs-cite <ids>` invocation. Ids are 4-hex-char tokens,
# optionally `cs:`-prefixed (since playbook items render as `[cs:ab12]`
# and the model often copies the tag verbatim). The `(?i:cs:)` inline
# flag makes only the prefix case-insensitive so `CS:AB12` is accepted
# — matching the `re.IGNORECASE` used by the standalone `cs-cite`
# script. Tokens may be comma- and/or whitespace-separated. Chained
# commands (&&, |, ;) and extra trailing tokens remain rejected by the
# anchored `\s*$` terminator so accidental mentions don't register as
# citations.
_ID_TOKEN = r"(?i:cs:)?[A-Fa-f0-9]{4}"
_ID_SEP = r"[,\s]+"
CITATION_CMD_RE = re.compile(
    rf"^\s*(?:[^\s]*/)?cs-cite\s+({_ID_TOKEN}(?:{_ID_SEP}{_ID_TOKEN})*)\s*$"
)
_CLEAN_ID_RE = re.compile(r"^(?i:cs:)?([A-Fa-f0-9]{4})$")
_SPLIT_RE = re.compile(_ID_SEP)

CITATION_INSTRUCTION = (
    "_If any item above materially shaped this response, end your reply "
    "with `cs-cite ab12,cd34` via the Bash tool — pass the 4-hex ids "
    "from the `[cs:xxxx]` tags (e.g. for `[cs:ab12]` and `[cs:cd34]` run "
    "`cs-cite ab12,cd34`; the `cs:` prefix is stripped automatically if "
    "you include it). Ids only, no prose, one Bash call. Omit if none "
    "applied._"
)


def short_id(kind: str, content: str) -> str:
    """Return a stable 4-hex-char id for a playbook or profile item.

    The id is a prefix of ``sha1(f"{kind}:{content}")`` so the same item
    injected across hooks or sessions receives the same tag. Four hex
    chars yield 65,536 possible values, which gives a negligible
    collision probability within the small registries (<= 25 items) that
    a single session produces.

    Args:
        kind: ``"playbook"`` or ``"profile"`` — namespaces the hash so
            two items with identical content but different kinds don't
            collapse to the same id.
        content: The rendered bullet content used for stability.

    Returns:
        str: 4-character lowercase hex id.
    """
    digest = hashlib.sha1(f"{kind}:{content}".encode("utf-8")).hexdigest()
    return digest[:4]


def parse_citation_command(command: str) -> list[str]:
    """Extract citation ids from a ``cs-cite`` Bash command string.

    Returns an empty list when the command does not match the expected
    shape (chained commands, extra arguments, or anything other than a
    bare ``cs-cite <ids>`` invocation are rejected to avoid false
    positives from accidental mentions).

    Args:
        command: The raw ``input.command`` value from a Bash tool_use
            block.

    Returns:
        list[str]: Lowercase 4-hex-char ids, in the order Claude cited
            them. Empty when the command does not match.
    """
    match = CITATION_CMD_RE.match(command or "")
    if not match:
        return []
    ids: list[str] = []
    for tok in _SPLIT_RE.split(match.group(1).strip()):
        if clean := _CLEAN_ID_RE.match(tok):
            ids.append(clean.group(1).lower())
    return ids


def ensure_installed() -> Path:
    """Idempotently install ``cs-cite`` into ``~/.claude-smart/bin/``.

    Called from SessionStart and PreToolUse so the script is always on
    disk before Claude could be asked to invoke it. Never raises —
    filesystem errors are logged at DEBUG and the caller proceeds with
    injection regardless (the citation feature degrades to silent if
    the script is unreachable).

    Returns:
        Path: Target path, whether or not install succeeded.
    """
    try:
        _INSTALL_DIR.mkdir(parents=True, exist_ok=True)
        if _SOURCE_SCRIPT.is_file():
            shutil.copy2(_SOURCE_SCRIPT, INSTALL_PATH)
            mode = INSTALL_PATH.stat().st_mode
            INSTALL_PATH.chmod(mode | stat_.S_IXUSR | stat_.S_IXGRP | stat_.S_IXOTH)
    except OSError as exc:
        _LOGGER.debug("cs-cite install failed: %s", exc)
    return INSTALL_PATH
