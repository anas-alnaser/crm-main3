import type { ReactNode } from "react";

import { cn } from "../../lib/utils";

type BadgeTone = "accent" | "neutral" | "success" | "warning" | "danger" | "info";

const toneClass: Record<BadgeTone, string> = {
  accent: "border-primary/30 bg-primary/10 text-primary",
  neutral: "border-border bg-muted text-muted-foreground",
  success: "border-emerald-500/30 bg-emerald-500/10 text-emerald-500",
  warning: "border-amber-500/30 bg-amber-500/10 text-amber-500",
  danger: "border-red-500/30 bg-red-500/10 text-red-500",
  info: "border-sky-500/30 bg-sky-500/10 text-sky-500",
};

export function Badge({
  children,
  className,
  tone = "neutral",
}: {
  children: ReactNode;
  className?: string;
  tone?: BadgeTone;
}) {
  return (
    <span className={cn("inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-medium capitalize", toneClass[tone], className)}>
      {children}
    </span>
  );
}

export function statusTone(status?: string): BadgeTone {
  if (!status) return "neutral";
  if (["won", "paid", "done", "active", "delivered"].includes(status)) return "success";
  if (["lost", "inactive"].includes(status)) return "danger";
  if (["proposal", "doing", "in_progress"].includes(status)) return "warning";
  if (["open", "lead", "todo"].includes(status)) return "info";
  if (status === "admin") return "accent";
  return "neutral";
}
