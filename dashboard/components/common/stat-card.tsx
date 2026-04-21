import { cn } from "@/lib/utils";
import type { LucideIcon } from "lucide-react";

export function StatCard({
  label,
  value,
  hint,
  icon: Icon,
  className,
}: {
  label: string;
  value: string | number;
  hint?: string;
  icon?: LucideIcon;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "rounded-xl border border-border bg-card px-5 py-4 flex items-start justify-between gap-4",
        className,
      )}
    >
      <div className="min-w-0">
        <div className="text-xs uppercase tracking-wide text-muted-foreground font-medium">
          {label}
        </div>
        <div className="mt-1.5 text-2xl font-semibold tracking-tight tabular-nums">
          {value}
        </div>
        {hint && (
          <div className="text-xs text-muted-foreground mt-1">{hint}</div>
        )}
      </div>
      {Icon && <Icon className="h-4 w-4 text-muted-foreground mt-0.5" />}
    </div>
  );
}
