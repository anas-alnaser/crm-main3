import { useQuery } from "@tanstack/react-query";
import { BarChart3 } from "lucide-react";
import { useState } from "react";

import { PageHeader } from "../components/PageHeader";
import { Badge } from "../components/ui/badge";
import { EmptyState } from "../components/ui/empty-state";
import { Select } from "../components/ui/select";
import { Skeleton } from "../components/ui/skeleton";
import { apiRequest, fetchList } from "../api/client";
import type { User, WorkforceDashboard } from "../api/types";

const PERIODS = [
  { value: "current_month", label: "Current month" },
  { value: "previous_month", label: "Previous month" },
  { value: "last_7_days", label: "Last 7 days" },
];

function n(record: Record<string, unknown>, key: string): string {
  const value = record?.[key];
  return value === null || value === undefined ? "—" : String(value);
}

export function WorkforcePage() {
  const [employee, setEmployee] = useState("");
  const [period, setPeriod] = useState("current_month");

  const employeesQuery = useQuery({ queryKey: ["workforce-employees"], queryFn: () => fetchList<User>("/workforce/employees/") });
  const dashboardQuery = useQuery({
    queryKey: ["workforce-dashboard", employee, period],
    queryFn: () => apiRequest<WorkforceDashboard>(`/workforce/dashboard/?employee=${employee}&period=${period}`),
    enabled: Boolean(employee),
  });

  return (
    <div className="space-y-6">
      <PageHeader title="Workforce" subtitle="Employee performance, attendance, and lead metrics." />

      <div className="flex flex-wrap items-center gap-2">
        <Select className="max-w-[240px]" value={employee} onChange={(e) => setEmployee(e.target.value)} aria-label="Select employee">
          <option value="">Select an employee…</option>
          {employeesQuery.data?.map((u) => <option key={u.id} value={u.id}>{u.first_name || u.username}</option>)}
        </Select>
        <Select className="max-w-[200px]" value={period} onChange={(e) => setPeriod(e.target.value)} aria-label="Select period">
          {PERIODS.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
        </Select>
      </div>

      {!employee ? (
        <EmptyState icon={BarChart3} title="Select an employee" message="Choose an employee with a work policy to view their performance." />
      ) : dashboardQuery.isLoading ? (
        <Skeleton className="h-96 w-full" />
      ) : dashboardQuery.isError ? (
        <div className="surface-card p-6 text-sm text-muted-foreground">Could not load the dashboard.</div>
      ) : dashboardQuery.data ? (
        <Dashboard data={dashboardQuery.data} />
      ) : null}
    </div>
  );
}

function Dashboard({ data }: { data: WorkforceDashboard }) {
  const work = data.work;
  const leads = data.leads;
  const crm = data.crm;
  const salary = data.salary;
  const observations = (work.observations as string[]) ?? [];

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Credited" value={n(work, "credited_display")} />
        <Stat label="Expected" value={n(work, "expected_display")} />
        <Stat label="Overtime" value={n(work, "overtime_display")} />
        <Stat label="Target completion" value={`${n(work, "target_completion_percent")}%`} />
        <Stat label="Sessions" value={n(work, "session_count")} />
        <Stat label="Inactivity closures" value={n(work, "inactivity_closures")} />
        <Stat label="9 PM closures" value={n(work, "window_closures")} />
        <Stat label="Days worked" value={`${n(work, "days_worked")} / ${n(work, "expected_workdays")}`} />
      </div>

      {observations.length > 0 && (
        <div className="surface-card space-y-1 p-4 text-sm">
          {observations.map((o, i) => <p key={i} className="text-muted-foreground">• {o}</p>)}
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Leads">
          <MetricRow label="Assigned" value={n(leads, "assigned")} />
          <MetricRow label="Contacted" value={n(leads, "contacted")} />
          <MetricRow label="Contact attempts" value={n(leads, "contact_attempts")} />
          <MetricRow label="Interested" value={n(leads, "interested")} />
          <MetricRow label="Not interested" value={n(leads, "not_interested")} />
          <MetricRow label="Converted" value={n(leads, "converted")} />
          <MetricRow label="Conversion rate" value={`${n(leads, "conversion_rate")}%`} />
          <MetricRow label="Overdue follow-ups" value={n(leads, "overdue_follow_ups")} />
        </Panel>
        <Panel title="CRM activity">
          <MetricRow label="Companies created" value={n(crm, "companies_created")} />
          <MetricRow label="Tasks created" value={n(crm, "tasks_created")} />
          <MetricRow label="Activities logged" value={n(crm, "activities_logged")} />
          <MetricRow label="Meetings created" value={n(crm, "meetings_created")} />
          <MetricRow label="Deals created" value={n(crm, "deals_created")} />
          <MetricRow label="Deals moved" value={n(crm, "deals_moved")} />
          <MetricRow label="Deals won" value={n(crm, "deals_won")} />
        </Panel>
      </div>

      <Panel title="Salary (informational only)">
        <MetricRow label="Basic salary" value={salary.configured ? `${n(salary, "basic_salary")} ${n(salary, "currency")}` : "Not configured"} />
        <MetricRow label="Overtime allowed" value={String(salary.overtime_allowed ?? "—")} />
        <p className="mt-2 text-xs text-muted-foreground">{n(salary, "note")}</p>
      </Panel>

      <div className="surface-card overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="border-b border-border bg-muted/40 text-left text-xs uppercase tracking-wide text-muted-foreground">
            <tr>
              <th className="px-3 py-2">Date</th>
              <th className="px-3 py-2">Expected</th>
              <th className="px-3 py-2">Credited</th>
              <th className="px-3 py-2">Sessions</th>
              <th className="px-3 py-2">Inactivity</th>
              <th className="px-3 py-2">Contacted</th>
              <th className="px-3 py-2">Converted</th>
              <th className="px-3 py-2">Deals won</th>
            </tr>
          </thead>
          <tbody>
            {data.daily.map((row, i) => (
              <tr key={i} className="border-b border-border/60 last:border-0">
                <td className="px-3 py-2">{n(row, "date")}</td>
                <td className="px-3 py-2 text-muted-foreground">{n(row, "expected_display")}</td>
                <td className="px-3 py-2 font-medium">{n(row, "credited_display")}</td>
                <td className="px-3 py-2">{n(row, "session_count")}</td>
                <td className="px-3 py-2">{Number(row.inactivity_closures) > 0 ? <Badge tone="warning">{n(row, "inactivity_closures")}</Badge> : "—"}</td>
                <td className="px-3 py-2">{n(row, "leads_contacted")}</td>
                <td className="px-3 py-2">{n(row, "leads_converted")}</td>
                <td className="px-3 py-2">{n(row, "deals_won")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="surface-card p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="mt-2 text-xl font-semibold tabular-nums">{value}</p>
    </div>
  );
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="surface-card p-5">
      <h3 className="mb-3 text-sm font-semibold">{title}</h3>
      <dl className="space-y-1.5 text-sm">{children}</dl>
    </div>
  );
}

function MetricRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="font-medium tabular-nums">{value}</dd>
    </div>
  );
}
