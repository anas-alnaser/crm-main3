import { useQuery } from "@tanstack/react-query";
import { Download, ScrollText } from "lucide-react";
import { useState } from "react";

import { PageHeader } from "../components/PageHeader";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { EmptyState } from "../components/ui/empty-state";
import { Input } from "../components/ui/input";
import { Select } from "../components/ui/select";
import { Skeleton } from "../components/ui/skeleton";
import { apiRequest, fetchList, type Paginated } from "../api/client";
import type { AuditEvent, User } from "../api/types";

const CATEGORIES = ["auth", "shift", "policy", "crm", "lead", "document", "user", "branding", "ai", "security", "telemetry"];

export function AuditLogPage() {
  const [category, setCategory] = useState("");
  const [userId, setUserId] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [expanded, setExpanded] = useState<number | null>(null);

  const usersQuery = useQuery({ queryKey: ["users"], queryFn: () => fetchList<User>("/users/") });
  const query = useQuery({
    queryKey: ["audit", category, userId, search, page],
    queryFn: () => {
      const params = new URLSearchParams({ page: String(page) });
      if (category) params.set("category", category);
      if (userId) params.set("user", userId);
      if (search) params.set("search", search);
      return apiRequest<Paginated<AuditEvent>>(`/audit-events/?${params.toString()}`);
    },
  });

  const exportCsv = () => {
    const params = new URLSearchParams();
    if (category) params.set("category", category);
    if (userId) params.set("user", userId);
    if (search) params.set("search", search);
    apiRequest<Blob>(`/audit-events/export/?${params.toString()}`)
      .catch(() => {})
      .finally(() => window.open(`/api/audit-events/export/?${params.toString()}`, "_blank"));
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Audit Log"
        subtitle="Server-authoritative record of meaningful actions. No keystrokes or secrets are stored."
        actions={<Button variant="outline" onClick={exportCsv}><Download className="h-4 w-4" /> Export CSV</Button>}
      />

      <div className="flex flex-wrap items-center gap-2">
        <Select className="max-w-[180px]" value={category} onChange={(e) => { setCategory(e.target.value); setPage(1); }} aria-label="Category">
          <option value="">All categories</option>
          {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
        </Select>
        <Select className="max-w-[180px]" value={userId} onChange={(e) => { setUserId(e.target.value); setPage(1); }} aria-label="User">
          <option value="">All users</option>
          {usersQuery.data?.map((u) => <option key={u.id} value={u.id}>{u.username}</option>)}
        </Select>
        <Input className="max-w-[240px]" placeholder="Search summary…" value={search} onChange={(e) => { setSearch(e.target.value); setPage(1); }} aria-label="Search" />
      </div>

      {query.isLoading ? (
        <Skeleton className="h-96 w-full" />
      ) : query.isError ? (
        <div className="surface-card p-6 text-sm text-muted-foreground">Could not load the audit log.</div>
      ) : query.data && query.data.results.length > 0 ? (
        <>
          <div className="surface-card divide-y divide-border">
            {query.data.results.map((event) => (
              <div key={event.id} className="p-4">
                <button className="flex w-full items-start justify-between gap-4 text-left" onClick={() => setExpanded(expanded === event.id ? null : event.id)}>
                  <div className="min-w-0">
                    <p className="text-sm font-medium">{event.summary || event.action}</p>
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      {new Date(event.created_at).toLocaleString()} · {event.user_username ?? "system"} · {event.action}
                    </p>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    {event.source === "client" && <Badge tone="neutral">ui</Badge>}
                    <Badge tone="info">{event.category_display}</Badge>
                  </div>
                </button>
                {expanded === event.id && (
                  <div className="mt-3 grid gap-3 rounded-md border border-border bg-muted/30 p-3 text-xs sm:grid-cols-2">
                    <Meta label="Entity" value={`${event.entity_type}${event.entity_id ? ` #${event.entity_id}` : ""}`} />
                    <Meta label="IP" value={event.ip_address ?? "—"} />
                    {Object.keys(event.old_values).length > 0 && <Meta label="Old" value={JSON.stringify(event.old_values)} />}
                    {Object.keys(event.new_values).length > 0 && <Meta label="New" value={JSON.stringify(event.new_values)} />}
                    {Object.keys(event.metadata).length > 0 && <Meta label="Metadata" value={JSON.stringify(event.metadata)} />}
                  </div>
                )}
              </div>
            ))}
          </div>
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">{query.data.count} events</span>
            <div className="flex gap-2">
              <Button size="sm" variant="outline" disabled={!query.data.previous} onClick={() => setPage((p) => Math.max(1, p - 1))}>Previous</Button>
              <span className="grid place-items-center px-2 text-muted-foreground">Page {query.data.page} / {query.data.total_pages}</span>
              <Button size="sm" variant="outline" disabled={!query.data.next} onClick={() => setPage((p) => p + 1)}>Next</Button>
            </div>
          </div>
        </>
      ) : (
        <EmptyState icon={ScrollText} title="No audit events" message="No events match the current filters." />
      )}
    </div>
  );
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <p className="font-semibold uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="mt-0.5 break-words font-mono">{value}</p>
    </div>
  );
}
