"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { MessageSquare, AlertTriangle } from "lucide-react";
import { PageHeader } from "@/components/common/page-header";
import { EmptyState } from "@/components/common/empty-state";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { formatRelative, truncateId } from "@/lib/format";
import type { SessionSummary } from "@/lib/types";

export default function InteractionsPage() {
  const [sessions, setSessions] = useState<SessionSummary[] | null>(null);
  const [filter, setFilter] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/sessions", { cache: "no-store" })
      .then((r) => r.json())
      .then((data) => {
        if (!cancelled) setSessions(data.sessions ?? []);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const filtered = (sessions ?? []).filter((s) =>
    s.session_id.toLowerCase().includes(filter.toLowerCase()),
  );

  return (
    <div className="flex-1 overflow-auto">
      <PageHeader
        title="Interactions"
        description="Sessions buffered locally under ~/.claude-smart/sessions/."
        actions={
          <Input
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Filter by session id"
            className="h-8 w-56 text-xs font-mono"
          />
        }
      />

      <div className="p-6">
        {error && (
          <div className="rounded-lg border border-destructive/30 bg-destructive/5 text-destructive px-4 py-3 text-sm mb-4">
            {error}
          </div>
        )}

        {sessions === null ? (
          <div className="text-sm text-muted-foreground">Loading…</div>
        ) : filtered.length === 0 ? (
          <EmptyState
            icon={MessageSquare}
            title="No sessions found"
            description="Start Claude Code with claude-smart enabled — JSONL buffers will appear in ~/.claude-smart/sessions/."
          />
        ) : (
          <div className="rounded-xl border border-border overflow-hidden bg-card">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wide text-muted-foreground border-b border-border">
                  <th className="font-medium px-4 py-2.5">Session</th>
                  <th className="font-medium px-4 py-2.5 text-right">Turns</th>
                  <th className="font-medium px-4 py-2.5 text-right">Published</th>
                  <th className="font-medium px-4 py-2.5">Flags</th>
                  <th className="font-medium px-4 py-2.5 text-right">
                    Last activity
                  </th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((s) => (
                  <tr
                    key={s.session_id}
                    className="border-b border-border last:border-0 hover:bg-accent/30 transition-colors"
                  >
                    <td className="px-4 py-2.5">
                      <Link
                        href={`/interactions/${s.session_id}`}
                        className="font-mono text-xs hover:underline"
                      >
                        {truncateId(s.session_id, 12, 6)}
                      </Link>
                    </td>
                    <td className="px-4 py-2.5 text-right tabular-nums text-muted-foreground">
                      {s.turn_count}
                    </td>
                    <td className="px-4 py-2.5 text-right tabular-nums text-muted-foreground">
                      {s.published_up_to}
                    </td>
                    <td className="px-4 py-2.5">
                      {s.has_correction && (
                        <Badge variant="destructive" className="h-5 gap-1">
                          <AlertTriangle className="h-3 w-3" />
                          correction
                        </Badge>
                      )}
                    </td>
                    <td className="px-4 py-2.5 text-right text-xs text-muted-foreground">
                      {formatRelative(s.last_activity)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
