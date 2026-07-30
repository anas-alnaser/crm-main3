import { useQuery } from "@tanstack/react-query";
import { Activity as ActivityIcon, ArrowRight, CalendarClock, CircleDollarSign, Gauge, Trophy, Wallet } from "lucide-react";
import { Link } from "react-router-dom";

import { apiRequest, fetchList } from "../api/client";
import type { Activity, CommissionSummary, DashboardStats, Deal, Meeting } from "../api/types";
import { PageHeader } from "../components/PageHeader";
import { EmptyState } from "../components/ui/empty-state";
import { MotionDiv, MotionSection, pageMotion } from "../components/ui/motion";
import { Skeleton } from "../components/ui/skeleton";
import { useAuth } from "../lib/auth";

const formatCurrency = (value: string | number | null, currency = "JOD") =>
  new Intl.NumberFormat("en-US", { style: "currency", currency, maximumFractionDigits: 0 }).format(Number(value ?? 0));
const formatMeetingDate = (meeting: Meeting) =>
  `${new Date(meeting.start_datetime).toLocaleDateString()} · ${new Date(meeting.start_datetime).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}`;

export function OverviewPage() {
  const { user } = useAuth();
  const { data: stats, isLoading: statsLoading, isError: statsError } = useQuery({
    queryKey: ["dashboard-stats"],
    queryFn: () => apiRequest<DashboardStats>("/dashboard/stats/"),
  });
  const { data: deals = [] } = useQuery({
    queryKey: ["deals", user?.role === "sales" ? "mine" : "all"],
    queryFn: () => fetchList<Deal>(user?.role === "sales" ? "/deals/?mine=true" : "/deals/"),
  });
  const { data: activities = [] } = useQuery({
    queryKey: ["activities"],
    queryFn: () => fetchList<Activity>("/activities/"),
  });
  const { data: commission, isLoading: commissionLoading } = useQuery({
    queryKey: ["commission"],
    queryFn: () => apiRequest<CommissionSummary>("/commission/"),
  });
  const { data: upcomingMeetings = [] } = useQuery({
    queryKey: ["meetings", "upcoming"],
    queryFn: () => fetchList<Meeting>("/meetings/upcoming/"),
  });

  const closingSoon = deals
    .filter((deal) => deal.status === "open" && deal.expected_close_date)
    .sort((a, b) => String(a.expected_close_date).localeCompare(String(b.expected_close_date)))
    .slice(0, 5);
  const recentActivity = [...activities]
    .sort((a, b) => String(b.created_at).localeCompare(String(a.created_at)))
    .slice(0, 5);

  return (
    <MotionSection className="page-shell" {...pageMotion}>
      <PageHeader title="Dashboard" subtitle="Pipeline health, closing work, and recent client touches at a glance." />

      {statsLoading ? (
        <div className="grid gap-4 md:grid-cols-4">
          {[0, 1, 2, 3].map((item) => <Skeleton key={item} className="h-32" />)}
        </div>
      ) : statsError || !stats ? (
        <div className="surface-card p-6 text-sm text-muted-foreground">Could not load dashboard stats. Check the backend terminal and try refreshing.</div>
      ) : (
        <>
          <div className="grid gap-4 md:grid-cols-4">
            <StatCard icon={CircleDollarSign} label={stats.scope === "personal" ? "My open deals" : "Open deals"} value={stats.total_open_deals} context={stats.scope === "personal" ? "Your active opportunities" : "Active opportunities in play"} />
            <StatCard icon={Wallet} label={stats.scope === "personal" ? "My pipeline value" : "Pipeline value"} value={formatCurrency(stats.total_pipeline_value)} context={stats.scope === "personal" ? "Your open revenue potential" : "Open revenue potential"} />
            <StatCard icon={Trophy} label={stats.scope === "personal" ? "My deals won this month" : "Won this month"} value={stats.deals_won_this_month} context={stats.scope === "personal" ? "Your closed wins this month" : "Closed wins this month"} />
            <StatCard icon={Gauge} label={stats.scope === "personal" ? "My win rate" : "Win rate"} value={`${stats.win_rate}%`} context={stats.scope === "personal" ? "Your conversion across closed deals" : "Conversion across closed deals"} />
          </div>

          <div className="surface-card p-6">
            <div className="mb-4 flex items-center justify-between">
              <div>
                <h2 className="text-lg font-semibold">{stats.scope === "personal" ? "My value by stage" : "Value by stage"}</h2>
                <p className="text-sm text-muted-foreground">{stats.scope === "personal" ? "How your revenue is distributed across the board." : "How revenue is distributed across the board."}</p>
              </div>
              <Link className="inline-flex items-center gap-1 text-sm font-medium text-primary hover:text-primary-hover" to="/">Open pipeline <ArrowRight className="h-4 w-4" /></Link>
            </div>
            <div className="space-y-3">
              {stats.value_by_stage.map((stage, index) => (
                <MotionDiv key={stage.stage_id} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.18, delay: index * 0.03 }}>
                  <div className="mb-1 flex justify-between text-sm">
                    <span>{stage.stage_name}</span>
                    <span className="tabular-nums text-muted-foreground">{formatCurrency(stage.value)} · {stage.count}</span>
                  </div>
                  <div className="h-2 rounded-full bg-muted">
                    <div
                      className="h-2 rounded-full bg-primary"
                      style={{
                        width: `${Math.min(100, Math.max(8, (Number(stage.value) / Math.max(1, Number(stats.total_pipeline_value || stage.value))) * 100))}%`,
                      }}
                    />
                  </div>
                </MotionDiv>
              ))}
              {!stats.value_by_stage.length && <p className="text-sm text-muted-foreground">No stage values yet.</p>}
            </div>
          </div>

          {stats.scope === "personal" && (
            commissionLoading || !commission ? (
              <Skeleton className="h-40" />
            ) : (
              <CommissionPanel commission={commission} />
            )
          )}
        </>
      )}

      <div className="grid gap-6 lg:grid-cols-3">
        <Panel title="Upcoming meetings" action={<Link className="text-sm font-medium text-primary hover:text-primary-hover" to="/schedule">Open schedule</Link>}>
          {upcomingMeetings.slice(0, 5).map((meeting) => (
            <div key={meeting.id} className="rounded-md border border-border bg-background p-4 text-sm transition hover:border-primary/40">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="font-medium">{meeting.title}</p>
                  <p className="text-muted-foreground">{meeting.company_name || meeting.deal_title || "Standalone meeting"}</p>
                </div>
                <span className="rounded-full border border-primary/30 bg-primary/10 px-2 py-1 text-xs font-medium text-primary">{meeting.status}</span>
              </div>
              <p className="mt-2 text-xs text-muted-foreground">{formatMeetingDate(meeting)}{meeting.location ? ` · ${meeting.location}` : ""}</p>
            </div>
          ))}
          {!upcomingMeetings.length && <EmptyState icon={CalendarClock} title="No meetings this week" message="Upcoming meetings will appear here once scheduled." />}
        </Panel>

        <Panel title="Deals closing soon" action={<Link className="text-sm font-medium text-primary hover:text-primary-hover" to="/deals">View all</Link>}>
          {closingSoon.map((deal) => (
            <div key={deal.id} className="rounded-md border border-border bg-background p-4 text-sm transition hover:border-primary/40">
              <div className="flex justify-between gap-3">
                <p className="font-medium">{deal.title}</p>
                <p className="metric-number text-primary">{formatCurrency(deal.value, deal.currency)}</p>
              </div>
              <p className="text-muted-foreground">{deal.company_name} · {deal.expected_close_date}</p>
            </div>
          ))}
          {!closingSoon.length && <EmptyAction text="No closing dates yet." action="Add Deal" to="/deals" />}
        </Panel>

        <Panel title="Recent activity">
          {recentActivity.map((activity) => (
            <div key={activity.id} className="rounded-md border border-border bg-background p-4 text-sm transition hover:border-primary/40">
              <p className="font-medium capitalize">{activity.type}</p>
              <p className="text-muted-foreground">{activity.content}</p>
            </div>
          ))}
          {!recentActivity.length && <EmptyState icon={ActivityIcon} title="No activity yet" message="Calls, notes, emails, and meetings will appear here once logged." />}
        </Panel>
      </div>
    </MotionSection>
  );
}

function CommissionPanel({ commission }: { commission: CommissionSummary }) {
  const potential = formatCurrency(commission.potential_commission);
  return (
    <section className="surface-card p-6">
      <div className="mb-5 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold">Commission</h2>
          <p className="text-sm text-muted-foreground">
            Flat {Number(commission.commission_rate_percent).toFixed(2).replace(".00", "")}% commission on your own deals.
          </p>
        </div>
        <span className="rounded-full border border-primary/30 bg-primary/10 px-3 py-1 text-xs font-medium text-primary">
          {Number(commission.commission_rate_percent).toFixed(2).replace(".00", "")}% rate
        </span>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <div className="rounded-lg border border-border bg-background p-4">
          <p className="text-sm text-muted-foreground">Earned commission</p>
          <p className="metric-number mt-2 text-3xl text-foreground">{formatCurrency(commission.earned_commission)}</p>
          <p className="mt-2 text-xs text-muted-foreground">From deals you've already closed as won.</p>
        </div>
        <div className="rounded-lg border border-border bg-background p-4">
          <p className="text-sm text-muted-foreground">Potential commission</p>
          <p className="metric-number mt-2 text-3xl text-primary">{potential}</p>
          <p className="mt-2 text-xs text-muted-foreground">Close your open pipeline to earn up to {potential}.</p>
        </div>
      </div>
    </section>
  );
}

function StatCard({ context, icon: Icon, label, value }: { context: string; icon: typeof CircleDollarSign; label: string; value: string | number }) {
  return (
    <MotionDiv className="surface-card p-5" whileHover={{ y: -2 }} transition={{ duration: 0.16 }}>
      <div className="flex items-center justify-between gap-4">
        <p className="text-sm text-muted-foreground">{label}</p>
        <span className="grid h-9 w-9 place-items-center rounded-md bg-primary/10 text-primary"><Icon className="h-4 w-4" /></span>
      </div>
      <p className="metric-number mt-4 text-3xl">{value}</p>
      <p className="mt-2 text-xs text-muted-foreground">{context}</p>
    </MotionDiv>
  );
}

function Panel({ title, action, children }: { title: string; action?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="surface-card p-5">
      <div className="mb-4 flex items-center justify-between gap-4">
        <h2 className="font-semibold">{title}</h2>
        {action}
      </div>
      <div className="space-y-3">{children}</div>
    </section>
  );
}

function EmptyAction({ text, action, to }: { text: string; action: string; to: string }) {
  return (
    <div className="rounded-lg border border-dashed border-border p-5 text-center">
      <p className="mb-3 text-sm text-muted-foreground">{text}</p>
      <Link className="inline-flex h-10 items-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-primary-hover" to={to}>
        {action}
      </Link>
    </div>
  );
}
