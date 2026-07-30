import type { LucideIcon } from "lucide-react";

import { Button } from "./button";

export function EmptyState({
  actionLabel,
  icon: Icon,
  message,
  onAction,
  title,
}: {
  actionLabel?: string;
  icon: LucideIcon;
  message: string;
  onAction?: () => void;
  title: string;
}) {
  return (
    <div className="rounded-lg border border-dashed border-border bg-card px-6 py-10 text-center">
      <div className="mx-auto grid h-12 w-12 place-items-center rounded-full bg-primary/10 text-primary">
        <Icon className="h-5 w-5" />
      </div>
      <h3 className="mt-4 text-sm font-semibold">{title}</h3>
      <p className="mx-auto mt-2 max-w-sm text-sm leading-6 text-muted-foreground">{message}</p>
      {actionLabel && onAction && (
        <Button className="mt-5" type="button" onClick={onAction}>
          {actionLabel}
        </Button>
      )}
    </div>
  );
}
