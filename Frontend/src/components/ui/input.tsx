import * as React from "react";

import { cn } from "../../lib/utils";

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => {
    return (
      <input
        ref={ref}
        {...props}
        className={cn(
          "focus-ring h-10 w-full rounded-md border border-input bg-card px-3 text-sm text-foreground shadow-sm outline-none transition placeholder:text-muted-foreground/70 hover:border-border focus:border-primary disabled:cursor-not-allowed disabled:opacity-50",
          className,
        )}
      />
    );
  },
);

Input.displayName = "Input";
