"use client";

import { useEffect, useState } from "react";
import { Save, CheckCircle2 } from "lucide-react";
import { PageHeader } from "@/components/common/page-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Separator } from "@/components/ui/separator";
import { useSettings } from "@/hooks/use-settings";
import type { ClaudeSmartConfig } from "@/lib/types";

export default function ConfigurePage() {
  const { reflexioUrl, setReflexioUrl } = useSettings();
  const [config, setConfig] = useState<ClaudeSmartConfig | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    fetch("/api/config", { cache: "no-store" })
      .then((r) => r.json())
      .then((data) => setConfig(data))
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  const update = <K extends keyof ClaudeSmartConfig>(
    key: K,
    value: ClaudeSmartConfig[K],
  ) => {
    setConfig((prev) => (prev ? { ...prev, [key]: value } : prev));
    setSaved(false);
  };

  const save = async () => {
    if (!config) return;
    setSaving(true);
    setError(null);
    try {
      const res = await fetch("/api/config", {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(config),
      });
      if (!res.ok) throw new Error(`save failed: ${res.status}`);
      const updated: ClaudeSmartConfig = await res.json();
      setConfig(updated);
      setSaved(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex-1 overflow-auto">
      <PageHeader
        title="Configure"
        description="Dashboard settings and the claude-smart environment written to ~/.reflexio/.env."
        actions={
          <Button onClick={save} disabled={!config || saving} size="sm">
            <Save className="h-3.5 w-3.5" />
            {saving ? "Saving…" : "Save"}
          </Button>
        }
      />

      <div className="p-6 max-w-2xl mx-auto space-y-6">
        {error && (
          <div className="rounded-lg border border-destructive/30 bg-destructive/5 text-destructive px-4 py-3 text-sm">
            {error}
          </div>
        )}
        {saved && (
          <div className="rounded-lg border border-border bg-accent/40 px-4 py-2.5 text-sm flex items-center gap-2">
            <CheckCircle2 className="h-4 w-4 text-muted-foreground" />
            Saved to ~/.reflexio/.env
          </div>
        )}

        <section className="space-y-4">
          <div>
            <h2 className="text-sm font-semibold">Dashboard</h2>
            <p className="text-xs text-muted-foreground">
              Stored in browser localStorage — only affects this UI.
            </p>
          </div>
          <div className="space-y-2">
            <Label>Reflexio endpoint (dashboard)</Label>
            <Input
              value={reflexioUrl}
              onChange={(e) => setReflexioUrl(e.target.value)}
              className="font-mono text-xs"
              placeholder="http://localhost:8081"
            />
          </div>
        </section>

        <Separator />

        <section className="space-y-4">
          <div>
            <h2 className="text-sm font-semibold">claude-smart environment</h2>
            <p className="text-xs text-muted-foreground">
              Writes to <code className="font-mono">~/.reflexio/.env</code>. Unknown
              keys are preserved.
            </p>
          </div>

          {config === null && !error ? (
            <div className="text-sm text-muted-foreground">Loading…</div>
          ) : config ? (
            <div className="space-y-5">
              <div className="space-y-2">
                <Label>REFLEXIO_URL</Label>
                <Input
                  value={config.REFLEXIO_URL}
                  onChange={(e) => update("REFLEXIO_URL", e.target.value)}
                  className="font-mono text-xs"
                  placeholder="http://localhost:8081/"
                />
              </div>

              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0">
                  <Label htmlFor="use-local-cli">CLAUDE_SMART_USE_LOCAL_CLI</Label>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Route generation through the local <code>claude</code> CLI.
                  </p>
                </div>
                <Switch
                  id="use-local-cli"
                  checked={!!config.CLAUDE_SMART_USE_LOCAL_CLI}
                  onCheckedChange={(v) =>
                    update("CLAUDE_SMART_USE_LOCAL_CLI", v)
                  }
                />
              </div>

              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0">
                  <Label htmlFor="use-local-embed">
                    CLAUDE_SMART_USE_LOCAL_EMBEDDING
                  </Label>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Use in-process ONNX embedder (offline-friendly).
                  </p>
                </div>
                <Switch
                  id="use-local-embed"
                  checked={!!config.CLAUDE_SMART_USE_LOCAL_EMBEDDING}
                  onCheckedChange={(v) =>
                    update("CLAUDE_SMART_USE_LOCAL_EMBEDDING", v)
                  }
                />
              </div>

              <div className="space-y-2">
                <Label>CLAUDE_SMART_CLI_PATH</Label>
                <Input
                  value={String(config.CLAUDE_SMART_CLI_PATH ?? "")}
                  onChange={(e) => update("CLAUDE_SMART_CLI_PATH", e.target.value)}
                  className="font-mono text-xs"
                  placeholder="(empty — auto-detect via $PATH)"
                />
              </div>

              <div className="space-y-2">
                <Label>CLAUDE_SMART_CLI_TIMEOUT</Label>
                <Input
                  value={String(config.CLAUDE_SMART_CLI_TIMEOUT ?? "")}
                  onChange={(e) =>
                    update("CLAUDE_SMART_CLI_TIMEOUT", e.target.value)
                  }
                  className="font-mono text-xs"
                  placeholder="120"
                />
              </div>

              <div className="space-y-2">
                <Label>CLAUDE_SMART_STATE_DIR</Label>
                <Input
                  value={String(config.CLAUDE_SMART_STATE_DIR ?? "")}
                  onChange={(e) =>
                    update("CLAUDE_SMART_STATE_DIR", e.target.value)
                  }
                  className="font-mono text-xs"
                  placeholder="(empty — default ~/.claude-smart/sessions)"
                />
              </div>
            </div>
          ) : null}
        </section>
      </div>
    </div>
  );
}
