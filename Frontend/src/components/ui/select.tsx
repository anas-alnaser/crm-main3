import * as React from "react";

import { cn } from "../../lib/utils";

export const Select = React.forwardRef<HTMLSelectElement, React.SelectHTMLAttributes<HTMLSelectElement>>(
  ({ className, ...props }, ref) => {
    return (
      <select
        ref={ref}
        {...props}
        className={cn(
          "focus-ring h-10 w-full rounded-md border border-input bg-card px-3 text-sm text-foreground shadow-sm outline-none transition hover:border-border focus:border-primary disabled:cursor-not-allowed disabled:opacity-50",
          className,
        )}
      />
    );
  },
);

Select.displayName = "Select";
