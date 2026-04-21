"""User-facing CLI for claude-smart.

Exposes four subcommands:

- ``install``: register the GitHub marketplace and install the plugin into
  Claude Code, then seed ``~/.reflexio/.env`` with the local-provider flags.
- ``playbook``: print the current project playbook (as markdown).
- ``sync``: force reflexio to run extraction on all unpublished interactions.
- ``correct "<note>"``: append a ``[correction]``-prefixed turn to the
  active session buffer so reflexio's extractor sees the signal on the
  next sync.
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
_DEFAULT_MARKETPLACE_SOURCE = "yilu/claude-smart"
_PLUGIN_SPEC = "claude-smart@yilu"


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

    sys.stdout.write(
        "\nclaude-smart installed. Next steps:\n"
        "  1. Start the reflexio backend (leave it running in another terminal):\n"
        "       uv run reflexio services start --only backend --no-reload\n"
        "  2. Restart Claude Code in your project.\n"
    )
    return 0


def cmd_playbook(args: argparse.Namespace) -> int:
    project_id = args.project or ids.resolve_project_id()
    adapter = Adapter()
    playbooks = adapter.fetch_project_playbooks(project_id)
    profiles: list = []
    if args.session:
        profiles = adapter.fetch_session_profiles(args.session)
    md = context_format.render(
        project_id=project_id, playbooks=playbooks, profiles=profiles
    )
    sys.stdout.write(md or f"_No playbook yet for project `{project_id}`._\n")
    return 0


def cmd_sync(args: argparse.Namespace) -> int:
    session_id = args.session or _latest_session_id()
    if not session_id:
        sys.stdout.write("No active claude-smart session buffer found.\n")
        return 0
    project_id = args.project or ids.resolve_project_id()
    status, count = publish.publish_unpublished(
        session_id=session_id, project_id=project_id, force_extraction=True
    )
    if status == "nothing":
        sys.stdout.write(f"Session `{session_id}`: nothing to sync.\n")
        return 0
    if status == "ok":
        sys.stdout.write(
            f"Synced {count} interactions to reflexio "
            f"(user_id={session_id}, agent_version={project_id}). "
            "Extraction running.\n"
        )
        return 0
    sys.stdout.write(
        "Failed to reach reflexio. Check that the server is running "
        "(`uv run reflexio services start`).\n"
    )
    return 1


def cmd_correct(args: argparse.Namespace) -> int:
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

    pb = sub.add_parser("playbook", help="Show the current project playbook")
    pb.add_argument("--project", help="Override project id")
    pb.add_argument("--session", help="Include session profile for this session_id")
    pb.set_defaults(func=cmd_playbook)

    sy = sub.add_parser("sync", help="Force reflexio extraction now")
    sy.add_argument("--project", help="Override project id")
    sy.add_argument("--session", help="Session id (defaults to latest)")
    sy.set_defaults(func=cmd_sync)

    co = sub.add_parser(
        "correct", help="Tag the current session with a correction note"
    )
    co.add_argument("note", nargs="?", default="", help="Correction description")
    co.add_argument("--session", help="Session id (defaults to latest)")
    co.set_defaults(func=cmd_correct)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
