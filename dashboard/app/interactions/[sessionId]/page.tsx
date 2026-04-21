"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, Wrench, AlertTriangle, ChevronRight } from "lucide-react";
import { PageHeader } from "@/components/common/page-header";
import { EmptyState } from "@/components/common/empty-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { formatTimestamp } from "@/lib/format";
import type { SessionDetail } from "@/lib/types";

export default function InteractionDetailPage({
  params,
}: {
  params: Promise<{ sessionId: string }>;
}) {
  const { sessionId } = use(params);
  const [detail, setDetail] = useState<SessionDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch(`/api/sessions/${encodeURIComponent(sessionId)}`, { cache: "no-store" })
      .then(async (r) => {
        if (!r.ok) throw new Error(`failed: ${r.status}`);
        return r.json();
      })
      .then((data) => {
        if (!cancelled) setDetail(data);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  return (
    <div className="flex-1 overflow-auto">
      <PageHeader
        title="Session transcript"
        description={sessionId}
        actions={
          <Link href="/interactions">
            <Button variant="outline" size="sm">
              <ArrowLeft className="h-3.5 w-3.5" />
              Back
            </Button>
          </Link>
        }
      />

      <div className="p-6 max-w-3xl mx-auto">
        {error && (
          <EmptyState
            icon={AlertTriangle}
            title="Unable to load session"
            description={error}
          />
        )}

        {!error && detail && detail.turns.length === 0 && (
          <EmptyState
            icon={AlertTriangle}
            title="Empty session"
            description="No turns recorded in this buffer yet."
          />
        )}

        {detail && detail.turns.length > 0 && (
          <div className="space-y-4">
            {detail.turns.map((turn, idx) => {
              const isUser = turn.role === "User";
              const flagged =
                turn.user_action && turn.user_action !== "NONE";
              return (
                <article
                  key={idx}
                  className={cn(
                    "rounded-xl border px-4 py-3 bg-card",
                    flagged
                      ? "border-destructive/30 bg-destructive/5"
                      : "border-border",
                  )}
                >
                  <header className="flex items-center justify-between gap-2 mb-2">
                    <div className="flex items-center gap-2">
                      <Badge
                        variant={isUser ? "secondary" : "outline"}
                        className="h-5 font-mono text-[10px]"
                      >
                        {turn.role}
                      </Badge>
                      {flagged && (
                        <Badge variant="destructive" className="h-5">
                          {turn.user_action}
                        </Badge>
                      )}
                      {turn.tools_used && turn.tools_used.length > 0 && (
                        <div className="flex items-center gap-1 flex-wrap">
                          {turn.tools_used.map((t, ti) => {
                            const input = t.tool_data?.input;
                            const hasInput =
                              input && Object.keys(input).length > 0;
                            if (!hasInput) {
                              return (
                                <span key={ti}>
                                  <Badge
                                    variant="outline"
                                    className="h-5 gap-1 text-[10px]"
                                  >
                                    <Wrench className="h-3 w-3" />
                                    {t.tool_name}
                                  </Badge>
                                </span>
                              );
                            }
                            return (
                              <details key={ti} className="group">
                                <summary className="cursor-pointer list-none">
                                  <Badge
                                    variant="outline"
                                    className="h-5 gap-1 text-[10px]"
                                  >
                                    <Wrench className="h-3 w-3" />
                                    {t.tool_name}
                                    <ChevronRight className="h-3 w-3 transition-transform group-open:rotate-90" />
                                  </Badge>
                                </summary>
                                <pre className="mt-1 whitespace-pre-wrap break-words rounded-md border border-border bg-muted/40 px-2 py-1 text-[10px] font-mono text-muted-foreground">
                                  {JSON.stringify(input, null, 2)}
                                </pre>
                              </details>
                            );
                          })}
                        </div>
                      )}
                    </div>
                    <span className="text-[11px] text-muted-foreground font-mono">
                      {formatTimestamp(turn.ts)}
                    </span>
                  </header>
                  <pre className="whitespace-pre-wrap break-words text-sm font-sans leading-relaxed">
                    {turn.content}
                  </pre>
                  {turn.user_action_description && (
                    <p className="text-xs text-muted-foreground mt-2 italic">
                      {turn.user_action_description}
                    </p>
                  )}
                </article>
              );
            })}
            <div className="text-xs text-muted-foreground text-center">
              Published up to turn {detail.published_up_to}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
