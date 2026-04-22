"""User-facing CLI for claude-smart.

Exposes five subcommands:

- ``install``: register the GitHub marketplace and install the plugin into
  Claude Code, then seed ``~/.reflexio/.env`` with the local-provider flags.
- ``update``: update the plugin to the latest version via the native Claude
  Code plugin CLI.
- ``show``: print the current project playbook and session user profiles
  (as markdown).
- ``learn``: force reflexio to run extraction on all unpublished interactions.
- ``tag "<note>"``: append a ``[correction]``-prefixed turn to the active
  session buffer so reflexio's extractor sees the signal on the next
  ``learn`` pass.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

from claude_smart import context_format, ids, publish, state
from claude_smart.reflexio_adapter import Adapter

_REFLEXIO_ENV_PATH = Path.home() / ".reflexio" / ".env"
_DEFAULT_MARKETPLACE_SOURCE = "ReflexioAI/claude-smart"
_PLUGIN_SPEC = "claude-smart@reflexioai"
_REFLEXIO_UNREACHABLE_MSG = (
    "Failed to reach reflexio. Check ~/.claude-smart/backend.log "
    "or restart Claude Code.\n"
)


def _latest_session_id() -> str | None:
    """Most-recently-modified session JSONL in the state dir. None if none exist."""
    root = state.state_dir()
    if not root.is_dir():
        return None
    files = sorted(root.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return None
    return files[0].stem


def _seed_reflexio_env() -> list[str]:
    """Append the two local-provider flags to ``~/.reflexio/.env``, idempotently.

    Returns:
        list[str]: Flag names that were newly appended (empty if already present).
    """
    _REFLEXIO_ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    _REFLEXIO_ENV_PATH.touch(exist_ok=True)
    existing = _REFLEXIO_ENV_PATH.read_text()
    flags = ("CLAUDE_SMART_USE_LOCAL_CLI", "CLAUDE_SMART_USE_LOCAL_EMBEDDING")
    missing = [f for f in flags if f"{f}=" not in existing]
    if not missing:
        return []
    prefix = "" if not existing or existing.endswith("\n") else "\n"
    with _REFLEXIO_ENV_PATH.open("a") as fh:
        fh.write(prefix + "\n".join(f"{f}=1" for f in missing) + "\n")
    return missing


def cmd_install(args: argparse.Namespace) -> int:
    """Install claude-smart into Claude Code via the native plugin CLI.

    Runs ``claude plugin marketplace add`` followed by ``claude plugin install``,
    then appends the local-provider flags to ``~/.reflexio/.env`` so reflexio
    can route generation through the local Claude Code CLI.

    Args:
        args (argparse.Namespace): Parsed CLI args. Uses ``args.source`` as the
            marketplace ref (``owner/repo`` on GitHub, or a local directory).

    Returns:
        int: 0 on success, non-zero if the ``claude`` CLI is missing or fails.
    """
    if not shutil.which("claude"):
        sys.stderr.write(
            "error: 'claude' CLI not found on PATH. "
            "Install Claude Code first: https://claude.com/claude-code\n"
        )
        return 1

    for cmd in (
        ["claude", "plugin", "marketplace", "add", args.source],
        ["claude", "plugin", "install", _PLUGIN_SPEC],
    ):
        try:
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError as exc:
            sys.stderr.write(f"error: {' '.join(cmd)} failed (exit {exc.returncode})\n")
            return exc.returncode or 1

    added = _seed_reflexio_env()
    if added:
        sys.stdout.write(f"Seeded {_REFLEXIO_ENV_PATH} with {', '.join(added)}.\n")

    sys.stdout.write("\nclaude-smart installed. Restart Claude Code in your project.\n")
    return 0


def cmd_update(_args: argparse.Namespace) -> int:
    """Update claude-smart to the latest version via the native plugin CLI.

    Runs ``claude plugin update claude-smart@reflexioai``.

    Args:
        args (argparse.Namespace): Parsed CLI args (unused).

    Returns:
        int: 0 on success, non-zero if the ``claude`` CLI is missing or fails.
    """
    if not shutil.which("claude"):
        sys.stderr.write(
            "error: 'claude' CLI not found on PATH. "
            "Install Claude Code first: https://claude.com/claude-code\n"
        )
        return 1

    cmd = ["claude", "plugin", "update", _PLUGIN_SPEC]
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as exc:
        sys.stderr.write(f"error: {' '.join(cmd)} failed (exit {exc.returncode})\n")
        return exc.returncode or 1

    sys.stdout.write("\nclaude-smart updated. Restart Claude Code to apply.\n")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    """Print the current project playbook and session user profiles.

    The session profile fetch defaults to the most-recently-modified session
    buffer so ``/show`` surfaces both playbook rules and user profiles in one
    pass, without the caller having to know the session id.

    Args:
        args (argparse.Namespace): Parsed CLI args. Honors ``args.project``
            (override project id) and ``args.session`` (override session id;
            falls back to the latest session buffer).

    Returns:
        int: 0 on success.
    """
    project_id = args.project or ids.resolve_project_id()
    session_id = args.session or _latest_session_id()
    adapter = Adapter()
    playbooks = adapter.fetch_project_playbooks(project_id)
    profiles: list = adapter.fetch_session_profiles(session_id) if session_id else []
    md = context_format.render(
        project_id=project_id, playbooks=playbooks, profiles=profiles
    )
    sys.stdout.write(
        md or f"_No playbook or profiles yet for project `{project_id}`._\n"
    )
    return 0


def cmd_learn(args: argparse.Namespace) -> int:
    session_id = args.session or _latest_session_id()
    if not session_id:
        sys.stdout.write("No active claude-smart session buffer found.\n")
        return 0
    project_id = args.project or ids.resolve_project_id()
    status, count = publish.publish_unpublished(
        session_id=session_id,
        project_id=project_id,
        force_extraction=True,
        skip_aggregation=True,
    )
    if status == "nothing":
        sys.stdout.write(f"Session `{session_id}`: nothing to learn from.\n")
        return 0
    if status == "ok":
        sys.stdout.write(
            f"Published {count} interactions to reflexio "
            f"(user_id={session_id}, agent_version={project_id}). "
            "Extraction running.\n"
        )
        return 0
    sys.stdout.write(_REFLEXIO_UNREACHABLE_MSG)
    return 1


def cmd_tag(args: argparse.Namespace) -> int:
    session_id = args.session or _latest_session_id()
    if not session_id:
        sys.stdout.write("No active claude-smart session buffer found.\n")
        return 0
    note = args.note or "the previous answer was wrong"
    state.append(
        session_id,
        {
            "ts": int(time.time()),
            "role": "User",
            "content": f"[correction] {note}",
        },
    )
    sys.stdout.write(f"Tagged correction on session `{session_id}`.\n")
    return 0


def cmd_clear_all(args: argparse.Namespace) -> int:
    """Delete all interactions, profiles, and user playbooks from reflexio.

    Also removes local session JSONL buffers under ``state_dir()`` so
    claude-smart starts from a clean slate. Requires ``--yes`` to proceed.

    Args:
        args (argparse.Namespace): Parsed CLI args. Honors ``args.yes``
            (skip the confirmation prompt).

    Returns:
        int: 0 on success, 1 if reflexio is unreachable or the user aborts.
    """
    if not args.yes:
        sys.stdout.write(
            "This will permanently delete ALL interactions, profiles, and "
            "user playbooks from reflexio, plus local session buffers under "
            f"{state.state_dir()}.\nRe-run with --yes to confirm.\n"
        )
        return 1

    result = Adapter().delete_all()
    if result is None:
        sys.stdout.write(_REFLEXIO_UNREACHABLE_MSG)
        return 1
    counts, errors = result

    removed_buffers = 0
    root = state.state_dir()
    if root.is_dir():
        for buf in root.glob("*.jsonl"):
            try:
                buf.unlink()
                removed_buffers += 1
            except OSError as exc:
                sys.stderr.write(f"warning: could not remove {buf}: {exc}\n")

    sys.stdout.write(
        "Cleared reflexio: "
        f"{counts.get('interactions', 0)} interactions, "
        f"{counts.get('profiles', 0)} profiles, "
        f"{counts.get('user_playbooks', 0)} user playbooks. "
        f"Removed {removed_buffers} local session buffer(s).\n"
    )
    for entity, err in errors:
        sys.stderr.write(f"warning: delete {entity} failed: {err}\n")
    return 1 if errors else 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="claude-smart")
    sub = parser.add_subparsers(dest="command", required=True)

    inst = sub.add_parser("install", help="Install claude-smart into Claude Code")
    inst.add_argument(
        "--source",
        default=_DEFAULT_MARKETPLACE_SOURCE,
        help="Marketplace ref — GitHub owner/repo, or a local directory path",
    )
    inst.set_defaults(func=cmd_install)

    upd = sub.add_parser("update", help="Update claude-smart to the latest version")
    upd.set_defaults(func=cmd_update)

    sh = sub.add_parser(
        "show",
        help="Show the current project playbook and session user profiles",
    )
    sh.add_argument("--project", help="Override project id")
    sh.add_argument(
        "--session",
        help="Session id for profile lookup (defaults to latest session)",
    )
    sh.set_defaults(func=cmd_show)

    ln = sub.add_parser("learn", help="Force reflexio extraction now")
    ln.add_argument("--project", help="Override project id")
    ln.add_argument("--session", help="Session id (defaults to latest)")
    ln.set_defaults(func=cmd_learn)

    tg = sub.add_parser("tag", help="Tag the current session with a correction note")
    tg.add_argument("note", nargs="?", default="", help="Correction description")
    tg.add_argument("--session", help="Session id (defaults to latest)")
    tg.set_defaults(func=cmd_tag)

    ca = sub.add_parser(
        "clear-all",
        help="Delete all interactions, profiles, and user playbooks from reflexio",
    )
    ca.add_argument(
        "--yes",
        action="store_true",
        help="Confirm the destructive clear without prompting",
    )
    ca.set_defaults(func=cmd_clear_all)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
