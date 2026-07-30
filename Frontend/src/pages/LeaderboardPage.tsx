import { useQuery } from "@tanstack/react-query";
import { Medal, Trophy } from "lucide-react";
import { useMemo, useState } from "react";

import { apiRequest } from "../api/client";
import type { LeaderboardResponse, LeaderboardRow } from "../api/types";
import { PageHeader } from "../components/PageHeader";
import { Badge } from "../components/ui/badge";
import { EmptyState } from "../components/ui/empty-state";
import { MotionSection, pageMotion } from "../components/ui/motion";
import { Select } from "../components/ui/select";
import { TableSkeleton } from "../components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../components/ui/table";

const formatCurrency = (value?: string | number | null, currency = "JOD") =>
  value === undefined || value === null
    ? ""
    : new Intl.NumberFormat("en-US", { style: "currency", currency, maximumFractionDigits: 0 }).format(Number(value));
const maskedMoney = "JOD *****";

const medalTone = (rank: number) => {
  if (rank === 1) return "text-primary";
  if (rank === 2) return "text-muted-foreground";
  if (rank === 3) return "text-amber-500";
  return "text-muted-foreground";
};

export function LeaderboardPage() {
  const [period, setPeriod] = useState<"this_month" | "all_time">("this_month");
  const { data, isError, isLoading } = useQuery({
    queryKey: ["leaderboard", period],
    queryFn: () => apiRequest<LeaderboardResponse>(`/leaderboard/?period=${period}`),
  });

  const sortedAdminRows = useMemo(() => data?.results ?? [], [data]);
  const isAdminView = data?.scope === "company";

  return (
    <MotionSection className="page-shell" {...pageMotion}>
      <PageHeader
        title="Leaderboard"
        subtitle={isAdminView ? "Full performance table for every sales rep." : "Climb the board — close more to rank up."}
        actions={
          <Select className="w-[160px]" value={period} onChange={(event) => setPeriod(event.target.value as "this_month" | "all_time")}>
            <option value="this_month">This month</option>
            <option value="all_time">All time</option>
          </Select>
        }
      />

      {isLoading ? (
        <TableSkeleton />
      ) : isError || !data ? (
        <div className="surface-card p-6 text-sm text-muted-foreground">Could not load leaderboard. Check the backend terminal and try again.</div>
      ) : !data.results.length ? (
        <EmptyState icon={Trophy} title="No sales reps yet" message="Create sales users and add deals to start ranking the team." />
      ) : isAdminView ? (
        <AdminLeaderboard rows={sortedAdminRows} />
      ) : (
        <SalesLeaderboard rows={data.results} />
      )}
    </MotionSection>
  );
}

function RankCell({ rank }: { rank: number }) {
  return (
    <div className="flex items-center gap-2">
      {rank <= 3 ? <Medal className={`h-4 w-4 ${medalTone(rank)}`} /> : <span className="h-4 w-4" />}
      <span className="metric-number">#{rank}</span>
    </div>
  );
}

function RepCell({ row }: { row: LeaderboardRow }) {
  return (
    <div className="flex items-center gap-3">
      <span className="grid h-9 w-9 place-items-center rounded-full bg-primary/10 text-xs font-semibold text-primary">{row.rep_initials}</span>
      <div>
        <p className="font-medium">{row.rep_name}</p>
        {row.is_current_user && <Badge className="mt-1" tone="accent">you</Badge>}
      </div>
    </div>
  );
}

function SalesLeaderboard({ rows }: { rows: LeaderboardRow[] }) {
  return (
    <div className="surface-card overflow-hidden">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Rank</TableHead>
            <TableHead>Rep</TableHead>
            <TableHead>Your potential</TableHead>
            <TableHead>Your earned</TableHead>
            <TableHead>Your counts</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row) => (
            <TableRow key={row.rep_id ?? row.rank} className={row.is_current_user ? "bg-primary/5" : ""}>
              <TableCell><RankCell rank={row.rank} /></TableCell>
              <TableCell><RepCell row={row} /></TableCell>
              <TableCell className="metric-number text-primary">{row.is_current_user ? formatCurrency(row.potential_commission) : <span className="text-muted-foreground">{maskedMoney}</span>}</TableCell>
              <TableCell className="metric-number">{row.is_current_user ? formatCurrency(row.earned_commission) : <span className="text-muted-foreground">{maskedMoney}</span>}</TableCell>
              <TableCell>
                {row.is_current_user ? (
                  <span className="text-sm text-muted-foreground">{row.open_count ?? 0} open · {row.won_count ?? 0} won</span>
                ) : (
                  <span className="text-muted-foreground">***</span>
                )}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

function AdminLeaderboard({ rows }: { rows: LeaderboardRow[] }) {
  return (
    <div className="surface-card overflow-hidden">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Rank</TableHead>
            <TableHead>Rep</TableHead>
            <TableHead>Potential commission</TableHead>
            <TableHead>Earned commission</TableHead>
            <TableHead>Won value</TableHead>
            <TableHead>Counts</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row) => (
            <TableRow key={row.rep_id ?? row.rank}>
              <TableCell><RankCell rank={row.rank} /></TableCell>
              <TableCell><RepCell row={row} /></TableCell>
              <TableCell className="metric-number text-primary">{formatCurrency(row.potential_commission)}</TableCell>
              <TableCell className="metric-number">{formatCurrency(row.earned_commission)}</TableCell>
              <TableCell className="metric-number">{formatCurrency(row.won_value)}</TableCell>
              <TableCell className="text-sm text-muted-foreground">{row.open_count ?? 0} open · {row.won_count ?? 0} won</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
