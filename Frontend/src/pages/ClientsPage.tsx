import type { ColumnDef } from "@tanstack/react-table";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { apiRequest, fetchList } from "../api/client";
import { EntityTable } from "../components/EntityTable";
import { PageHeader } from "../components/PageHeader";
import { Badge, statusTone } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { MotionSection, pageMotion } from "../components/ui/motion";
import { Select } from "../components/ui/select";
import { TableSkeleton } from "../components/ui/skeleton";
import { Textarea } from "../components/ui/textarea";
import { useAuth } from "../lib/auth";
import { useToast } from "../lib/toast";
import { useCrud } from "../hooks/useCrud";
import type { Client } from "../api/types";

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
  const [editing, setEditing] = useState<Client | null>(null);
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
            />
          )}
        </div>
      </div>
    </MotionSection>
  );
}
