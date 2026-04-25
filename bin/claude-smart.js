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

const { execFileSync, execSync, spawn } = require("child_process");
const { appendFileSync, existsSync, mkdirSync, readFileSync } = require("fs");
const { homedir } = require("os");
const { dirname, join } = require("path");

const DEFAULT_MARKETPLACE_SOURCE = "ReflexioAI/claude-smart";
const PLUGIN_SPEC = "claude-smart@reflexioai";
const REFLEXIO_ENV_PATH = join(homedir(), ".reflexio", ".env");

function runClaude(args, { spinnerLabel } = {}) {
  const useSpinner = Boolean(spinnerLabel) && process.stdout.isTTY && !process.env.CI;
  return new Promise((resolve) => {
    const child = spawn("claude", args, {
      stdio: useSpinner ? ["inherit", "pipe", "pipe"] : "inherit",
    });

    if (useSpinner) {
      const frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"];
      let i = 0;
      let spinTimer = null;
      let rearmTimer = null;
      let exited = false;

      const draw = () => {
        process.stdout.write(`\r⠿ ${spinnerLabel}`.replace("⠿", frames[i = (i + 1) % frames.length]));
      };
      const clearLine = () => process.stdout.write("\r\x1b[2K");
      const startSpin = () => {
        if (spinTimer || exited) return;
        draw();
        spinTimer = setInterval(draw, 80);
      };
      const stopSpin = () => {
        if (!spinTimer) return;
        clearInterval(spinTimer);
        spinTimer = null;
        clearLine();
      };
      const armRearm = () => {
        if (rearmTimer) clearTimeout(rearmTimer);
        rearmTimer = setTimeout(() => {
          rearmTimer = null;
          startSpin();
        }, 200);
      };

      startSpin();

      const passthrough = (stream) => (chunk) => {
        stopSpin();
        stream.write(chunk);
        armRearm();
      };
      child.stdout.on("data", passthrough(process.stdout));
      child.stderr.on("data", passthrough(process.stderr));
      child.on("exit", () => {
        exited = true;
        if (rearmTimer) {
          clearTimeout(rearmTimer);
          rearmTimer = null;
        }
        stopSpin();
      });
    }

    child.on("exit", (code) => resolve(typeof code === "number" ? code : 1));
    child.on("error", () => resolve(1));
  });
}

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
      "Update:",
      "  npx claude-smart update                        Update to the latest version",
      "",
      "Uninstall:",
      "  npx claude-smart uninstall                     Remove the plugin from Claude Code",
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

async function runUpdate() {
  if (!hasClaudeCli()) {
    process.stderr.write(
      "error: 'claude' CLI not found on PATH. " +
        "Install Claude Code first: https://claude.com/claude-code\n",
    );
    process.exit(1);
  }

  const code = await runClaude(["plugin", "update", PLUGIN_SPEC], {
    spinnerLabel: "Checking for claude-smart updates…",
  });
  if (code !== 0) {
    process.stderr.write(`error: \`claude plugin update ${PLUGIN_SPEC}\` failed (exit ${code})\n`);
    process.exit(code);
  }

  process.stdout.write("\nclaude-smart updated. Restart Claude Code to apply.\n");
}

async function runUninstall() {
  if (!hasClaudeCli()) {
    process.stderr.write(
      "error: 'claude' CLI not found on PATH. " +
        "Install Claude Code first: https://claude.com/claude-code\n",
    );
    process.exit(1);
  }

  const code = await runClaude(["plugin", "uninstall", PLUGIN_SPEC], {
    spinnerLabel: "Uninstalling claude-smart…",
  });
  if (code !== 0) {
    process.stderr.write(
      `error: \`claude plugin uninstall ${PLUGIN_SPEC}\` failed (exit ${code})\n`,
    );
    process.exit(code);
  }

  process.stdout.write(
    [
      "",
      "claude-smart uninstalled. Restart Claude Code to apply.",
      "Local data in ~/.reflexio/ and ~/.claude-smart/ was left in place — remove manually if desired.",
      "",
    ].join("\n"),
  );
}

async function runInstall(args) {
  if (!hasClaudeCli()) {
    process.stderr.write(
      "error: 'claude' CLI not found on PATH. " +
        "Install Claude Code first: https://claude.com/claude-code\n",
    );
    process.exit(1);
  }

  const source = parseSource(args);
  const steps = [
    { args: ["plugin", "marketplace", "add", source], label: "Adding marketplace…" },
    { args: ["plugin", "install", PLUGIN_SPEC], label: "Installing claude-smart…" },
  ];

  for (const step of steps) {
    const code = await runClaude(step.args, { spinnerLabel: step.label });
    if (code !== 0) {
      process.stderr.write(
        `error: \`claude ${step.args.join(" ")}\` failed (exit ${code})\n`,
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
      "claude-smart installed. Restart Claude Code in your project.",
      "The reflexio backend and dashboard auto-start on session start.",
      "Opt out with CLAUDE_SMART_BACKEND_AUTOSTART=0 or CLAUDE_SMART_DASHBOARD_AUTOSTART=0.",
      "",
    ].join("\n"),
  );
}

async function main() {
  const args = process.argv.slice(2);
  const cmd = args[0] || "install";

  if (cmd === "help" || cmd === "--help" || cmd === "-h") {
    printHelp();
    return;
  }

  if (cmd === "install") {
    await runInstall(args.slice(1));
    return;
  }

  if (cmd === "update") {
    await runUpdate();
    return;
  }

  if (cmd === "uninstall") {
    await runUninstall();
    return;
  }

  process.stderr.write(
    `claude-smart: unknown command '${cmd}'. Try 'npx claude-smart --help'.\n`,
  );
  process.exit(1);
}

main().catch((err) => {
  process.stderr.write(`claude-smart: ${err && err.message ? err.message : err}\n`);
  process.exit(1);
});
