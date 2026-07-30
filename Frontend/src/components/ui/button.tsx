import * as React from "react";

import { cn } from "../../lib/utils";

type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "ghost" | "outline" | "danger";
  size?: "sm" | "md" | "icon";
};

export function Button({ className, size = "md", variant = "primary", ...props }: ButtonProps) {
  return (
    <button
      className={cn(
        "focus-ring inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium transition active:scale-[0.98] disabled:pointer-events-none disabled:opacity-45",
        size === "md" && "h-10 px-4",
        size === "sm" && "h-8 px-3 text-xs",
        size === "icon" && "h-10 w-10 px-0",
        variant === "primary" && "bg-primary text-primary-foreground shadow-sm shadow-primary/20 hover:bg-primary-hover",
        variant === "ghost" && "text-muted-foreground hover:bg-muted hover:text-foreground",
        variant === "outline" && "border border-border bg-card text-foreground hover:border-primary/40 hover:bg-muted/70",
        variant === "danger" && "bg-red-600 text-white shadow-sm shadow-red-950/20 hover:bg-red-700",
        className,
      )}
      {...props}
    />
  );
}
