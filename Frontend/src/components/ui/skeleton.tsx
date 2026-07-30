import { cn } from "../../lib/utils";

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-md bg-muted", className)} />;
}

export function TableSkeleton({ rows = 6 }: { rows?: number }) {
  return (
    <div className="surface-card overflow-hidden p-4">
      <Skeleton className="mb-4 h-10 w-56" />
      <div className="space-y-3">
        {Array.from({ length: rows }).map((_, index) => (
          <Skeleton key={index} className="h-14 w-full" />
        ))}
      </div>
    </div>
  );
}

export function BoardSkeleton() {
  return (
    <div className="flex gap-4 overflow-hidden">
      {Array.from({ length: 4 }).map((_, column) => (
        <div key={column} className="surface-card h-[540px] w-[320px] shrink-0 p-4">
          <Skeleton className="mb-5 h-8 w-36" />
          <div className="space-y-3">
            {Array.from({ length: 4 }).map((_, card) => (
              <Skeleton key={card} className="h-32 w-full" />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
