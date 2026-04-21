/**
 * Server-side reader for claude-smart JSONL session buffers.
 * Mirrors the format documented in src/claude_smart/state.py:
 *   - {role: "User" | "Assistant" | "Assistant_tool", ...}
 *   - {published_up_to: N}  watermark
 */

import fs from "node:fs/promises";
import path from "node:path";
import os from "node:os";
import type {
  SessionDetail,
  SessionSummary,
  SessionTurn,
  ToolUsed,
  UserActionType,
} from "./types";

export function stateDir(): string {
  const override = process.env.CLAUDE_SMART_STATE_DIR;
  if (override) return override;
  return path.join(os.homedir(), ".claude-smart", "sessions");
}

type RawRecord = {
  role?: "User" | "Assistant" | "Assistant_tool";
  content?: string;
  ts?: number;
  tool_name?: string;
  tool_input?: Record<string, unknown>;
  status?: string;
  user_action?: UserActionType;
  user_action_description?: string;
  published_up_to?: number;
};

async function readJsonl(filePath: string): Promise<RawRecord[]> {
  const text = await fs.readFile(filePath, "utf-8");
  const out: RawRecord[] = [];
  for (const line of text.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    try {
      out.push(JSON.parse(trimmed));
    } catch {
      // skip malformed line, matches state.py behaviour
    }
  }
  return out;
}

function foldTurns(records: RawRecord[]): {
  turns: SessionTurn[];
  publishedUpTo: number;
  hasCorrection: boolean;
  lastTs: number | null;
} {
  let published = 0;
  let pendingTools: ToolUsed[] = [];
  const turns: SessionTurn[] = [];
  let hasCorrection = false;
  let lastTs: number | null = null;

  for (let idx = 0; idx < records.length; idx++) {
    const rec = records[idx];
    if (typeof rec.published_up_to === "number") {
      published = rec.published_up_to;
      pendingTools = [];
      continue;
    }
    const role = rec.role;
    if (role === "Assistant_tool") {
      const entry: ToolUsed = {
        tool_name: rec.tool_name ?? "",
        status: rec.status ?? "success",
      };
      if (rec.tool_input && Object.keys(rec.tool_input).length > 0) {
        entry.tool_data = { input: rec.tool_input };
      }
      pendingTools.push(entry);
      continue;
    }
    if (role !== "User" && role !== "Assistant") continue;

    if (rec.user_action && rec.user_action !== "NONE") hasCorrection = true;
    if (typeof rec.ts === "number") lastTs = rec.ts;

    const turn: SessionTurn = {
      role,
      content: rec.content ?? "",
      ts: rec.ts,
      user_action: rec.user_action,
      user_action_description: rec.user_action_description,
    };
    if (role === "Assistant" && pendingTools.length) {
      turn.tools_used = pendingTools;
      pendingTools = [];
    }
    turns.push(turn);
  }

  return { turns, publishedUpTo: published, hasCorrection, lastTs };
}

export async function listSessions(): Promise<SessionSummary[]> {
  const dir = stateDir();
  let entries: string[];
  try {
    entries = await fs.readdir(dir);
  } catch {
    return [];
  }

  const summaries: SessionSummary[] = [];
  for (const entry of entries) {
    if (!entry.endsWith(".jsonl")) continue;
    const fullPath = path.join(dir, entry);
    const records = await readJsonl(fullPath).catch(() => []);
    const { turns, publishedUpTo, hasCorrection, lastTs } = foldTurns(records);
    summaries.push({
      session_id: entry.replace(/\.jsonl$/, ""),
      turn_count: turns.length,
      has_correction: hasCorrection,
      last_activity: lastTs,
      published_up_to: publishedUpTo,
      source: "local",
    });
  }
  summaries.sort((a, b) => (b.last_activity ?? 0) - (a.last_activity ?? 0));
  return summaries;
}

export async function readSession(
  sessionId: string,
): Promise<SessionDetail | null> {
  const file = path.join(stateDir(), `${sessionId}.jsonl`);
  let records: RawRecord[];
  try {
    records = await readJsonl(file);
  } catch {
    return null;
  }
  const { turns, publishedUpTo } = foldTurns(records);
  return { session_id: sessionId, turns, published_up_to: publishedUpTo };
}
