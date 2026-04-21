#!/usr/bin/env node
/**
 * npx claude-smart install — thin wrapper around the native Claude Code
 * plugin CLI. Registers the GitHub marketplace, installs the plugin, and
 * seeds ~/.reflexio/.env with the two local-provider flags so reflexio
 * can route generation through the local `claude` CLI with no API key.
 *
 * Keep this file dependency-free — it runs via `npx` with no install step.
 */
"use strict";

const { execFileSync, execSync } = require("child_process");
const { appendFileSync, existsSync, mkdirSync, readFileSync } = require("fs");
const { homedir } = require("os");
const { dirname, join } = require("path");

const DEFAULT_MARKETPLACE_SOURCE = "yilu/claude-smart";
const PLUGIN_SPEC = "claude-smart@yilu";
const REFLEXIO_ENV_PATH = join(homedir(), ".reflexio", ".env");

function hasClaudeCli() {
  const probe = process.platform === "win32" ? "where claude" : "command -v claude";
  try {
    execSync(probe, { stdio: "ignore" });
    return true;
  } catch {
    return false;
  }
}

function seedReflexioEnv() {
  mkdirSync(dirname(REFLEXIO_ENV_PATH), { recursive: true });
  const existing = existsSync(REFLEXIO_ENV_PATH)
    ? readFileSync(REFLEXIO_ENV_PATH, "utf8")
    : "";
  const flags = ["CLAUDE_SMART_USE_LOCAL_CLI", "CLAUDE_SMART_USE_LOCAL_EMBEDDING"];
  const missing = flags.filter((f) => !new RegExp(`^${f}=`, "m").test(existing));
  if (missing.length === 0) return [];
  const prefix = existing && !existing.endsWith("\n") ? "\n" : "";
  const body = missing.map((f) => `${f}=1`).join("\n") + "\n";
  appendFileSync(REFLEXIO_ENV_PATH, prefix + body);
  return missing;
}

function printHelp() {
  process.stdout.write(
    [
      "claude-smart — install helper for the Claude Code plugin",
      "",
      "Usage:",
      "  npx claude-smart install                       Install the plugin into Claude Code",
      "  npx claude-smart install --source <owner/repo> Override the marketplace source",
      "  npx claude-smart --help                        Show this help",
      "",
      "What it does:",
      "  1. claude plugin marketplace add <source>",
      `  2. claude plugin install ${PLUGIN_SPEC}`,
      "  3. Appends CLAUDE_SMART_USE_LOCAL_CLI=1 and CLAUDE_SMART_USE_LOCAL_EMBEDDING=1",
      "     to ~/.reflexio/.env (idempotent).",
      "",
    ].join("\n"),
  );
}

function parseSource(args) {
  const idx = args.indexOf("--source");
  if (idx === -1) return DEFAULT_MARKETPLACE_SOURCE;
  const value = args[idx + 1];
  if (!value) {
    process.stderr.write("error: --source requires a value (e.g. owner/repo)\n");
    process.exit(1);
  }
  return value;
}

function runInstall(args) {
  if (!hasClaudeCli()) {
    process.stderr.write(
      "error: 'claude' CLI not found on PATH. " +
        "Install Claude Code first: https://claude.com/claude-code\n",
    );
    process.exit(1);
  }

  const source = parseSource(args);
  const steps = [
    ["plugin", "marketplace", "add", source],
    ["plugin", "install", PLUGIN_SPEC],
  ];

  for (const stepArgs of steps) {
    try {
      execFileSync("claude", stepArgs, { stdio: "inherit" });
    } catch (err) {
      const code = typeof err.status === "number" ? err.status : 1;
      process.stderr.write(
        `error: \`claude ${stepArgs.join(" ")}\` failed (exit ${code})\n`,
      );
      process.exit(code);
    }
  }

  const added = seedReflexioEnv();
  if (added.length > 0) {
    process.stdout.write(
      `Seeded ${REFLEXIO_ENV_PATH} with ${added.join(", ")}.\n`,
    );
  }

  process.stdout.write(
    [
      "",
      "claude-smart installed. Next steps:",
      "  1. Start the reflexio backend (leave it running in another terminal):",
      "       uv run reflexio services start --only backend --no-reload",
      "  2. Restart Claude Code in your project.",
      "",
    ].join("\n"),
  );
}

function main() {
  const args = process.argv.slice(2);
  const cmd = args[0] || "install";

  if (cmd === "help" || cmd === "--help" || cmd === "-h") {
    printHelp();
    return;
  }

  if (cmd === "install") {
    runInstall(args.slice(1));
    return;
  }

  process.stderr.write(
    `claude-smart: unknown command '${cmd}'. Try 'npx claude-smart --help'.\n`,
  );
  process.exit(1);
}

main();
