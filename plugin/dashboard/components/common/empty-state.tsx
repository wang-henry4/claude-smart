import { cn } from "@/lib/utils";
import type { LucideIcon } from "lucide-react";

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  className,
}: {
  icon?: LucideIcon;
  title: string;
  description?: string;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center text-center py-12 px-6 border border-dashed border-border rounded-xl bg-muted/20",
        className,
      )}
    >
      {Icon && (
        <Icon className="h-8 w-8 text-muted-foreground/60 mb-3" strokeWidth={1.5} />
      )}
      <div className="text-sm font-medium text-foreground">{title}</div>
      {description && (
        <p className="text-sm text-muted-foreground mt-1 max-w-md">{description}</p>
      )}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
