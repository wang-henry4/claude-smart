# claude-smart

Self-improving [Claude Code](https://claude.com/claude-code) plugin — turns your corrections into durable rules that Claude Code follows in future sessions, via [reflexio](https://github.com/ReflexioAI/reflexio).

This directory is the published Python package (`claude-smart` on PyPI) and the Claude Code plugin payload shipped through the marketplace. For the project overview, install instructions, benchmarks, and feature walkthrough, see the [top-level README](https://github.com/ReflexioAI/claude-smart#readme).

## Install

```bash
npx claude-smart install   # or: uvx claude-smart install
```

Then restart Claude Code.

## Uninstall

```bash
npx claude-smart uninstall   # or: uvx claude-smart uninstall
```

Or run the equivalent command directly via the Claude Code CLI:

```bash
claude plugin uninstall claude-smart@reflexioai
```

Local data under `~/.reflexio/` and `~/.claude-smart/` is left in place — remove manually if desired.

## License

Apache 2.0 — see [LICENSE](LICENSE).
