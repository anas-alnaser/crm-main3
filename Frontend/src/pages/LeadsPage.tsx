import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { PhoneCall, Trash2, Upload, UserCheck } from "lucide-react";
import { useRef, useState } from "react";

import { PageHeader } from "../components/PageHeader";
import { PermanentDeleteDialog, type PermanentDeleteConfirm } from "../components/PermanentDeleteDialog";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { EmptyState } from "../components/ui/empty-state";
import { Input } from "../components/ui/input";
import { Select } from "../components/ui/select";
import { Skeleton } from "../components/ui/skeleton";
import { apiErrorMessage, apiRequest, fetchList, sendTelemetry, uploadForm } from "../api/client";
import type { Lead, LeadContactAttempt, LeadDeleteImpact, User } from "../api/types";
import { useAuth } from "../lib/auth";
import { isSuperAdmin } from "../lib/superadmin";
import { useToast } from "../lib/toast";

const STATUS_TONE: Record<string, "neutral" | "success" | "warning" | "danger" | "info"> = {
  new: "info",
  contacted: "info",
  no_answer: "warning",
  follow_up: "warning",
  interested: "success",
  not_interested: "danger",
  converted: "success",
};

const OUTCOMES = ["reached", "no_answer", "busy", "wrong_number", "callback_requested", "interested", "not_interested", "other"];
const SETTABLE_STATUSES = ["contacted", "no_answer", "follow_up", "interested", "not_interested"];

export function LeadsPage() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const superadmin = isSuperAdmin(user);
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const [statusFilter, setStatusFilter] = useState("");
  const [selected, setSelected] = useState<Lead | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Lead | null>(null);

  const leadsQuery = useQuery({
    queryKey: ["leads", statusFilter],
    queryFn: () => fetchList<Lead>(`/leads/${statusFilter ? `?status=${statusFilter}` : ""}`),
  });

  const openLead = (lead: Lead) => {
    setSelected(lead);
    sendTelemetry("lead.opened", { entity_type: "Lead", entity_id: String(lead.id) });
  };

  const refresh = () => queryClient.invalidateQueries({ queryKey: ["leads"] });

  return (
    <div className="space-y-6">
      <PageHeader
        title="Leads"
        subtitle={isAdmin ? "Upload, assign, and track lead outcomes." : "Your assigned leads."}
        actions={isAdmin ? <LeadUpload onDone={refresh} /> : undefined}
      />

      <div className="flex flex-wrap items-center gap-2">
        <Select className="max-w-[220px]" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} aria-label="Filter by status">
          <option value="">All statuses</option>
          {["new", "contacted", "no_answer", "follow_up", "interested", "not_interested", "converted"].map((s) => (
            <option key={s} value={s}>{s.replace("_", " ")}</option>
          ))}
        </Select>
      </div>

      {leadsQuery.isLoading ? (
        <Skeleton className="h-64 w-full" />
      ) : leadsQuery.isError ? (
        <div className="surface-card p-6 text-sm text-muted-foreground">Could not load leads.</div>
      ) : leadsQuery.data && leadsQuery.data.length > 0 ? (
        <div className="surface-card overflow-hidden">
          <table className="w-full text-sm">
            <thead className="border-b border-border bg-muted/40 text-left text-xs uppercase tracking-wide text-muted-foreground">
              <tr>
                <th className="px-4 py-3">Name</th>
                <th className="px-4 py-3">Phone</th>
                <th className="px-4 py-3">Status</th>
                {isAdmin && <th className="px-4 py-3">Assigned</th>}
                <th className="px-4 py-3">Follow-up</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {leadsQuery.data.map((lead) => (
                <tr
                  key={lead.id}
                  className={`border-b border-border/60 last:border-0 ${lead.status === "not_interested" ? "bg-red-500/5" : ""}`}
                >
                  <td className={`px-4 py-3 font-medium ${lead.status === "not_interested" ? "text-red-500" : ""}`}>{lead.name}</td>
                  <td className="px-4 py-3 tabular-nums text-muted-foreground">{lead.normalized_phone || lead.original_phone}</td>
                  <td className="px-4 py-3"><Badge tone={STATUS_TONE[lead.status]}>{lead.status_display}</Badge></td>
                  {isAdmin && <td className="px-4 py-3 text-muted-foreground">{lead.assigned_to_name ?? "—"}</td>}
                  <td className="px-4 py-3 text-muted-foreground">{lead.follow_up_at ? new Date(lead.follow_up_at).toLocaleString() : "—"}</td>
                  <td className="px-4 py-3 text-right">
                    <div className="flex justify-end gap-2">
                      <Button size="sm" variant="outline" onClick={() => openLead(lead)}>Open</Button>
                      {superadmin && (
                        <Button
                          size="sm"
                          variant="danger"
                          onClick={() => setDeleteTarget(lead)}
                          aria-label={`Delete permanently ${lead.name}`}
                        >
                          <Trash2 className="h-3.5 w-3.5" /> Delete permanently
                        </Button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <EmptyState icon={PhoneCall} title="No leads" message={isAdmin ? "Upload an .xlsx file to import leads." : "You have no assigned leads yet."} />
      )}

      {selected && <LeadDrawer lead={selected} isAdmin={isAdmin} onClose={() => setSelected(null)} onChanged={() => { refresh(); }} showToast={showToast} />}

      {deleteTarget && (
        <LeadPermanentDeleteFlow
          lead={deleteTarget}
          onClose={() => setDeleteTarget(null)}
          onDeleted={() => {
            setDeleteTarget(null);
            setSelected(null);
            refresh();
            showToast("Lead permanently deleted.", "success");
          }}
          showToast={showToast}
        />
      )}
    </div>
  );
}

function LeadPermanentDeleteFlow({
  lead,
  onClose,
  onDeleted,
  showToast,
}: {
  lead: Lead;
  onClose: () => void;
  onDeleted: () => void;
  showToast: (m: string, t?: "success" | "error" | "info") => void;
}) {
  const [error, setError] = useState<string | null>(null);

  const impactQuery = useQuery({
    queryKey: ["lead-delete-impact", lead.id],
    queryFn: () => apiRequest<LeadDeleteImpact>(`/leads/${lead.id}/delete-impact/`),
  });

  const deleteMutation = useMutation({
    mutationFn: ({ password }: PermanentDeleteConfirm) =>
      apiRequest<{ deleted_lead_id: number }>(`/leads/${lead.id}/permanent-delete/`, {
        method: "POST",
        body: JSON.stringify({ current_password: password, confirmation: "DELETE LEAD", lead_id: lead.id }),
      }),
    onSuccess: () => onDeleted(),
    onError: (err) => {
      // Clear the password state (handled inside the dialog) and show the real
      // backend error without claiming success.
      setError(apiErrorMessage(err, "Could not delete lead."));
      showToast(apiErrorMessage(err, "Could not delete lead."), "error");
    },
  });

  const impact = impactQuery.data;
  const allowed = impact ? impact.deletion_allowed : false;

  return (
    <PermanentDeleteDialog
      open
      title="Delete lead permanently"
      phrase="DELETE LEAD"
      allowed={allowed}
      blockedReason={impact?.blocked_reason}
      loadingImpact={impactQuery.isLoading}
      idConfirmLabel={impact ? `I confirm this is lead #${impact.lead_id}.` : undefined}
      submitLabel="Permanently delete lead"
      error={error}
      submitting={deleteMutation.isPending}
      onCancel={onClose}
      onConfirm={(data) => {
        setError(null);
        deleteMutation.mutate(data);
      }}
    >
      {impact ? (
        <div className="rounded-md border border-border bg-muted/40 p-3">
          <p><span className="text-muted-foreground">Lead ID:</span> {impact.lead_id}</p>
          <p><span className="text-muted-foreground">Name:</span> {impact.name}</p>
          <p><span className="text-muted-foreground">Status:</span> {impact.status_display}</p>
          <p><span className="text-muted-foreground">Converted:</span> {impact.is_converted ? "Yes" : "No"}</p>
          <p><span className="text-muted-foreground">Contact attempts:</span> {impact.contact_attempt_count}</p>
        </div>
      ) : impactQuery.isError ? (
        <p className="text-red-500">{apiErrorMessage(impactQuery.error, "Could not load lead impact.")}</p>
      ) : null}
    </PermanentDeleteDialog>
  );
}

function LeadUpload({ onDone }: { onDone: () => void }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const { showToast } = useToast();
  const usersQuery = useQuery({ queryKey: ["users"], queryFn: () => fetchList<User>("/users/") });
  const [assignee, setAssignee] = useState("");

  const uploadMutation = useMutation({
    mutationFn: (file: File) => {
      const form = new FormData();
      form.append("file", file);
      if (assignee) form.append("assigned_to", assignee);
      return uploadForm<{ imported_count: number; duplicate_count: number }>("/lead-imports/upload/", form);
    },
    onSuccess: (data) => {
      showToast(`Imported ${data.imported_count} leads (${data.duplicate_count} duplicates skipped).`, "success");
      onDone();
    },
    onError: () => showToast("Import failed. Check the file format.", "error"),
  });

  return (
    <div className="flex items-center gap-2">
      <Select className="max-w-[180px]" value={assignee} onChange={(e) => setAssignee(e.target.value)} aria-label="Assign imported leads to">
        <option value="">Unassigned</option>
        {usersQuery.data?.filter((u) => u.role === "sales").map((u) => (
          <option key={u.id} value={u.id}>{u.first_name || u.username}</option>
        ))}
      </Select>
      <input
        ref={inputRef}
        type="file"
        accept=".xlsx"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) uploadMutation.mutate(file);
          e.target.value = "";
        }}
      />
      <Button onClick={() => inputRef.current?.click()} disabled={uploadMutation.isPending}>
        <Upload className="h-4 w-4" /> Upload .xlsx
      </Button>
    </div>
  );
}

function LeadDrawer({
  lead,
  isAdmin,
  onClose,
  onChanged,
  showToast,
}: {
  lead: Lead;
  isAdmin: boolean;
  onClose: () => void;
  onChanged: () => void;
  showToast: (m: string, t?: "success" | "error" | "info") => void;
}) {
  const [method, setMethod] = useState("call");
  const [outcome, setOutcome] = useState("reached");
  const [resultingStatus, setResultingStatus] = useState("");
  const [followUp, setFollowUp] = useState("");
  const [notes, setNotes] = useState("");

  const attemptsQuery = useQuery({
    queryKey: ["lead-attempts", lead.id],
    queryFn: () => apiRequest<LeadContactAttempt[]>(`/leads/${lead.id}/attempts/`),
  });

  const contactMutation = useMutation({
    mutationFn: () =>
      apiRequest(`/leads/${lead.id}/contact/`, {
        method: "POST",
        body: JSON.stringify({ method, outcome, resulting_status: resultingStatus || undefined, follow_up_at: followUp || undefined, notes }),
      }),
    onSuccess: () => {
      showToast("Contact attempt saved.", "success");
      setNotes("");
      attemptsQuery.refetch();
      onChanged();
    },
    onError: (error: Error) => showToast(parseError(error) ?? "Could not save attempt.", "error"),
  });

  const convertMutation = useMutation({
    mutationFn: (reason: string) =>
      apiRequest(`/leads/${lead.id}/convert/`, { method: "POST", body: JSON.stringify({ create_deal: false, reason }) }),
    onSuccess: () => {
      showToast("Lead converted to a client.", "success");
      onChanged();
      onClose();
    },
    onError: (error: Error) => showToast(parseError(error) ?? "Could not convert lead.", "error"),
  });

  const reopenMutation = useMutation({
    mutationFn: (reason: string) => apiRequest(`/leads/${lead.id}/reopen/`, { method: "POST", body: JSON.stringify({ reason }) }),
    onSuccess: () => {
      showToast("Lead reopened.", "success");
      onChanged();
      onClose();
    },
    onError: (error: Error) => showToast(parseError(error) ?? "Could not reopen lead.", "error"),
  });

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/40" role="dialog" aria-modal="true" onClick={onClose}>
      <div className="h-full w-full max-w-md overflow-y-auto bg-card p-6 shadow-soft" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between">
          <div>
            <h2 className="text-lg font-semibold">{lead.name}</h2>
            <p className="text-sm text-muted-foreground">{lead.normalized_phone || lead.original_phone}</p>
          </div>
          <Badge tone={STATUS_TONE[lead.status]}>{lead.status_display}</Badge>
        </div>

        {lead.status === "converted" ? (
          <div className="mt-6 surface-card p-4 text-sm text-muted-foreground">
            This lead was converted{lead.converted_at ? ` on ${new Date(lead.converted_at).toLocaleDateString()}` : ""}.
            {isAdmin && (
              <Button className="mt-3 w-full" variant="outline" onClick={() => promptReopen(reopenMutation)}>Reopen (admin)</Button>
            )}
          </div>
        ) : lead.status === "not_interested" ? (
          <div className="mt-6 surface-card border-red-500/30 bg-red-500/5 p-4 text-sm text-red-500">
            Marked not interested. This is a terminal outcome.
            {isAdmin && (
              <Button className="mt-3 w-full" variant="outline" onClick={() => promptReopen(reopenMutation)}>Reopen with reason (admin)</Button>
            )}
          </div>
        ) : (
          <>
            <section className="mt-6 space-y-3">
              <h3 className="text-sm font-semibold">Log contact attempt</h3>
              <div className="grid grid-cols-2 gap-2">
                <Select value={method} onChange={(e) => setMethod(e.target.value)} aria-label="Method">
                  {["call", "whatsapp", "sms", "email", "other"].map((m) => <option key={m} value={m}>{m}</option>)}
                </Select>
                <Select value={outcome} onChange={(e) => setOutcome(e.target.value)} aria-label="Outcome">
                  {OUTCOMES.map((o) => <option key={o} value={o}>{o.replace("_", " ")}</option>)}
                </Select>
              </div>
              <Select value={resultingStatus} onChange={(e) => setResultingStatus(e.target.value)} aria-label="Set status">
                <option value="">Keep current status</option>
                {SETTABLE_STATUSES.map((s) => <option key={s} value={s}>{s.replace("_", " ")}</option>)}
              </Select>
              {resultingStatus === "follow_up" && (
                <Input type="datetime-local" value={followUp} onChange={(e) => setFollowUp(e.target.value)} aria-label="Follow-up date" />
              )}
              <Input placeholder="Notes (optional)" value={notes} onChange={(e) => setNotes(e.target.value)} aria-label="Notes" />
              <Button className="w-full" onClick={() => contactMutation.mutate()} disabled={contactMutation.isPending}>
                <PhoneCall className="h-4 w-4" /> Save attempt
              </Button>
            </section>

            <section className="mt-6">
              <Button
                className="w-full"
                variant="outline"
                onClick={() => convertMutation.mutate(lead.status === "no_answer" ? promptString("Reason for converting a no-answer lead:") ?? "" : "")}
                disabled={convertMutation.isPending}
              >
                <UserCheck className="h-4 w-4" /> Convert to client
              </Button>
            </section>
          </>
        )}

        <section className="mt-6">
          <h3 className="text-sm font-semibold">History ({lead.contact_attempt_count})</h3>
          <div className="mt-2 space-y-2">
            {attemptsQuery.data?.map((a) => (
              <div key={a.id} className="rounded-md border border-border p-2 text-xs">
                <p className="font-medium">{a.method} · {a.outcome}</p>
                {a.notes && <p className="text-muted-foreground">{a.notes}</p>}
                <p className="text-muted-foreground">{new Date(a.created_at).toLocaleString()}</p>
              </div>
            ))}
          </div>
        </section>

        <Button className="mt-6 w-full" variant="ghost" onClick={onClose}>Close</Button>
      </div>
    </div>
  );
}

function promptString(message: string): string | null {
  return typeof window !== "undefined" ? window.prompt(message) : null;
}

function promptReopen(mutation: { mutate: (reason: string) => void }) {
  const reason = promptString("Reason to reopen this lead (required):");
  if (reason && reason.trim()) mutation.mutate(reason.trim());
}

function parseError(error: Error): string | null {
  try {
    return JSON.parse(error.message).detail ?? null;
  } catch {
    return null;
  }
}
