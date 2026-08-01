import type { ColumnDef } from "@tanstack/react-table";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Trash2 } from "lucide-react";

import { apiErrorMessage, apiRequest, fetchList } from "../api/client";
import { EntityTable } from "../components/EntityTable";
import { PageHeader } from "../components/PageHeader";
import { PermanentDeleteDialog, type PermanentDeleteConfirm } from "../components/PermanentDeleteDialog";
import { Badge, statusTone } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { MotionSection, pageMotion } from "../components/ui/motion";
import { Select } from "../components/ui/select";
import { TableSkeleton } from "../components/ui/skeleton";
import { Textarea } from "../components/ui/textarea";
import { useAuth } from "../lib/auth";
import { isSuperAdmin } from "../lib/superadmin";
import { useToast } from "../lib/toast";
import { useCrud } from "../hooks/useCrud";
import type { Client, CompanyDeleteImpact } from "../api/types";

const schema = z.object({
  name: z.string().min(1, "Business name is required"),
  contact_person: z.string().optional(),
  email: z.string().email().or(z.literal("")),
  phone: z.string().optional(),
  country: z.string().optional(),
  status: z.enum(["active", "inactive"]),
  notes: z.string().optional(),
});

type FormValues = z.infer<typeof schema>;

const defaultValues: FormValues = {
  name: "",
  contact_person: "",
  email: "",
  phone: "",
  country: "",
  status: "active",
  notes: "",
};

const columns: ColumnDef<Client>[] = [
  { accessorKey: "name", header: "Business" },
  { accessorKey: "contact_person", header: "Contact" },
  { accessorKey: "created_by_username", header: "Owner", cell: ({ row }) => row.original.created_by_username || "—" },
  {
    accessorKey: "status",
    header: "Status",
    cell: ({ row }) => <Badge tone={statusTone(row.original.status)}>{row.original.status}</Badge>,
  },
];

export function ClientsPage() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const isAdmin = user?.role === "admin";
  const superadmin = isSuperAdmin(user);
  const [editing, setEditing] = useState<Client | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Client | null>(null);
  const [showArchived, setShowArchived] = useState(false);
  const { data = [], isLoading, createMutation, updateMutation } = useCrud<Client>("clients");
  const archivedQuery = useQuery({
    queryKey: ["clients", "archived"],
    queryFn: () => fetchList<Client>("/clients/?archived=true"),
    enabled: showArchived,
  });
  const form = useForm<FormValues>({ resolver: zodResolver(schema), defaultValues });

  const archiveMutation = useMutation({
    mutationFn: (id: number) => apiRequest<Client>(`/clients/${id}/archive/`, { method: "PATCH" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["clients"] });
      showToast("Company archived. Its deals and projects are preserved.", "success");
    },
    onError: () => showToast("Could not archive company.", "error"),
  });

  const restoreMutation = useMutation({
    mutationFn: (id: number) => apiRequest<Client>(`/clients/${id}/restore/`, { method: "PATCH" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["clients"] });
      showToast("Company restored.", "success");
    },
    onError: () => showToast("Could not restore company.", "error"),
  });

  const submit = form.handleSubmit(async (values) => {
    if (editing) {
      await updateMutation.mutateAsync({ id: editing.id, data: values });
    } else {
      await createMutation.mutateAsync(values);
    }
    setEditing(null);
    form.reset(defaultValues);
  });

  const edit = (client: Client) => {
    setEditing(client);
    form.reset(client);
  };

  const canModify = (client: Client) => isAdmin || client.created_by === user?.id;
  const rows = showArchived ? archivedQuery.data ?? [] : data;
  const loading = showArchived ? archivedQuery.isLoading : isLoading;

  // Archive/Restore stay the default for everyone; only a superadmin sees the
  // irreversible Permanent delete action.
  const permanentDeleteAction = superadmin
    ? (client: Client) => (
        <Button
          variant="danger"
          className="h-8 px-3"
          onClick={() => setDeleteTarget(client)}
          aria-label={`Delete permanently ${client.name}`}
        >
          <Trash2 className="h-3.5 w-3.5" /> Delete permanently
        </Button>
      )
    : undefined;

  return (
    <MotionSection className="page-shell" {...pageMotion}>
      <PageHeader
        title="Companies"
        subtitle="Manage agency relationships, decision makers, and contact details."
        actions={
          <Button type="button" variant="outline" onClick={() => setShowArchived((value) => !value)}>
            {showArchived ? "Show active" : "Show archived"}
          </Button>
        }
      />
      <div className="grid gap-6 xl:grid-cols-[400px_1fr]">
        <form onSubmit={submit} className="form-panel">
          <h3 className="mb-1 text-lg font-semibold">{editing ? "Edit company" : "Create company"}</h3>
          <p className="mb-5 text-sm text-muted-foreground">Keep the essential business profile tidy and searchable.</p>
          <div className="space-y-4">
            <label className="field-label">Business<Input className="mt-2" placeholder="Acme Studio" {...form.register("name")} />{form.formState.errors.name && <p className="field-hint text-primary">{form.formState.errors.name.message}</p>}</label>
            <label className="field-label">Contact person<Input className="mt-2" placeholder="Main contact" {...form.register("contact_person")} /></label>
            <label className="field-label">Email<Input className="mt-2" placeholder="hello@example.com" {...form.register("email")} />{form.formState.errors.email && <p className="field-hint text-primary">{form.formState.errors.email.message}</p>}</label>
            <label className="field-label">Phone<Input className="mt-2" placeholder="+962..." {...form.register("phone")} /></label>
            <label className="field-label">Country<Input className="mt-2" placeholder="Jordan" {...form.register("country")} /></label>
            <label className="field-label">
              Status
              <Select className="mt-2" {...form.register("status")}>
                <option value="active">Active</option>
                <option value="inactive">Inactive</option>
              </Select>
            </label>
            <label className="field-label">Notes<Textarea className="mt-2" placeholder="Relationship notes, preferences, next steps..." {...form.register("notes")} /></label>
            <div className="flex gap-2">
              <Button disabled={form.formState.isSubmitting}>{editing ? "Save" : "Create"}</Button>
              {editing && <Button type="button" variant="outline" onClick={() => { setEditing(null); form.reset(defaultValues); }}>Cancel</Button>}
            </div>
          </div>
        </form>
        <div className="min-w-0">
          {loading ? (
            <TableSkeleton />
          ) : showArchived ? (
            <EntityTable
              columns={columns}
              data={rows}
              onEdit={edit}
              onDelete={isAdmin ? (id) => restoreMutation.mutate(id) : undefined}
              canModify={canModify}
              canDelete={() => isAdmin}
              destructiveLabel="Restore"
              confirmText="Restore this company to the active list?"
              extraActions={permanentDeleteAction}
            />
          ) : (
            <EntityTable
              columns={columns}
              data={rows}
              onEdit={edit}
              onDelete={isAdmin ? (id) => archiveMutation.mutate(id) : undefined}
              canModify={canModify}
              canDelete={() => isAdmin}
              destructiveLabel="Archive"
              confirmText="Archive this company? Its deals and projects are preserved and it is hidden from active lists."
              extraActions={permanentDeleteAction}
            />
          )}
        </div>
      </div>

      {deleteTarget && (
        <CompanyPermanentDeleteFlow
          company={deleteTarget}
          onClose={() => setDeleteTarget(null)}
          onDeleted={() => {
            setDeleteTarget(null);
            queryClient.invalidateQueries({ queryKey: ["clients"] });
            showToast("Company permanently deleted.", "success");
          }}
          showToast={showToast}
        />
      )}
    </MotionSection>
  );
}

function CompanyPermanentDeleteFlow({
  company,
  onClose,
  onDeleted,
  showToast,
}: {
  company: Client;
  onClose: () => void;
  onDeleted: () => void;
  showToast: (m: string, t?: "success" | "error" | "info") => void;
}) {
  const [error, setError] = useState<string | null>(null);

  const impactQuery = useQuery({
    queryKey: ["client-delete-impact", company.id],
    queryFn: () => apiRequest<CompanyDeleteImpact>(`/clients/${company.id}/delete-impact/`),
  });

  const deleteMutation = useMutation({
    mutationFn: ({ password, cascadeConfirmed }: PermanentDeleteConfirm) =>
      apiRequest(`/clients/${company.id}/permanent-delete/`, {
        method: "POST",
        body: JSON.stringify({
          current_password: password,
          confirmation: "DELETE COMPANY",
          client_id: company.id,
          cascade_confirmed: cascadeConfirmed,
        }),
      }),
    onSuccess: () => onDeleted(),
    onError: (err) => {
      setError(apiErrorMessage(err, "Could not delete company."));
      showToast(apiErrorMessage(err, "Could not delete company."), "error");
    },
  });

  const impact = impactQuery.data;

  return (
    <PermanentDeleteDialog
      open
      title="Delete company permanently"
      phrase="DELETE COMPANY"
      allowed={Boolean(impact)}
      loadingImpact={impactQuery.isLoading}
      cascadeLabel={
        impact?.dependencies_exist
          ? "I understand its deals and projects will also be permanently deleted."
          : undefined
      }
      submitLabel="Permanently delete company"
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
          <p className="font-medium">{impact.name}</p>
          <p className="mt-1 text-muted-foreground">Related records:</p>
          <ul className="mt-1 grid grid-cols-2 gap-x-4">
            <li>Deals: {impact.impact.deals} <span className="text-xs text-red-500">(deleted)</span></li>
            <li>Projects: {impact.impact.projects} <span className="text-xs text-red-500">(deleted)</span></li>
            <li>Tasks: {impact.impact.tasks}</li>
            <li>Activities: {impact.impact.activities}</li>
            <li>Meetings: {impact.impact.meetings}</li>
            <li>Documents: {impact.impact.documents}</li>
            <li>Converted leads: {impact.impact.converted_leads}</li>
          </ul>
        </div>
      ) : impactQuery.isError ? (
        <p className="text-red-500">{apiErrorMessage(impactQuery.error, "Could not load company impact.")}</p>
      ) : null}
    </PermanentDeleteDialog>
  );
}
