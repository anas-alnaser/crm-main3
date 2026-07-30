import type { ColumnDef } from "@tanstack/react-table";
import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { EntityTable } from "../components/EntityTable";
import { PageHeader } from "../components/PageHeader";
import { Badge, statusTone } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { MotionSection, pageMotion } from "../components/ui/motion";
import { Select } from "../components/ui/select";
import { TableSkeleton } from "../components/ui/skeleton";
import { Textarea } from "../components/ui/textarea";
import { useAuth } from "../lib/auth";
import { useCrud } from "../hooks/useCrud";
import type { Activity, Client, Deal, Project } from "../api/types";

const emptyToNull = (value: unknown) => (value === "" || value === 0 ? null : value);

const schema = z.object({
  type: z.enum(["call", "meeting", "email", "note"]),
  content: z.string().min(1, "Content is required"),
  project: z.preprocess(emptyToNull, z.coerce.number().nullable()),
  client: z.preprocess(emptyToNull, z.coerce.number().nullable()),
  deal: z.preprocess(emptyToNull, z.coerce.number().nullable()),
});

type FormValues = z.infer<typeof schema>;

const defaultValues = {
  type: "note",
  content: "",
  project: null,
  client: null,
  deal: null,
} satisfies FormValues;

const columns: ColumnDef<Activity>[] = [
  { accessorKey: "type", header: "Type", cell: ({ row }) => <Badge tone={statusTone(row.original.type)}>{row.original.type}</Badge> },
  { accessorKey: "client_name", header: "Client" },
  { accessorKey: "deal_title", header: "Deal" },
  { accessorKey: "content", header: "Content" },
];

export function ActivitiesPage() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const canModify = (activity: Activity) => isAdmin || activity.created_by === user?.id;
  const [editing, setEditing] = useState<Activity | null>(null);
  const { data = [], isLoading, createMutation, updateMutation, deleteMutation } = useCrud<Activity>("activities");
  const { data: clients = [] } = useCrud<Client>("clients");
  const { data: projects = [] } = useCrud<Project>("projects");
  const { data: deals = [] } = useCrud<Deal>("deals");
  const form = useForm<FormValues>({ resolver: zodResolver(schema), defaultValues });

  const submit = form.handleSubmit(async (values) => {
    if (editing) await updateMutation.mutateAsync({ id: editing.id, data: values });
    else await createMutation.mutateAsync(values);
    setEditing(null);
    form.reset(defaultValues);
  });

  const edit = (activity: Activity) => {
    setEditing(activity);
    form.reset(activity);
  };

  return (
    <MotionSection className="page-shell" {...pageMotion}>
      <PageHeader title="Activities" subtitle="Log every call, meeting, email, and note connected to client work." />
      <div className="grid gap-6 xl:grid-cols-[400px_1fr]">
        <form onSubmit={submit} className="form-panel">
          <h3 className="mb-1 text-lg font-semibold">{editing ? "Edit activity" : "Create activity"}</h3>
          <p className="mb-5 text-sm text-muted-foreground">Capture useful context while it is still fresh.</p>
          <div className="space-y-4">
            <label className="field-label">
              Type
              <Select className="mt-2" {...form.register("type")}>
                <option value="call">Call</option><option value="meeting">Meeting</option><option value="email">Email</option><option value="note">Note</option>
              </Select>
            </label>
            <label className="field-label">
              Client
              <Select className="mt-2" {...form.register("client")}>
                <option value="">No client</option>
                {clients.map((client) => <option key={client.id} value={client.id}>{client.name}</option>)}
              </Select>
            </label>
            <label className="field-label">
              Deal
              <Select className="mt-2" {...form.register("deal")}>
                <option value="">No deal</option>
                {deals.map((deal) => <option key={deal.id} value={deal.id}>{deal.title}</option>)}
              </Select>
            </label>
            <label className="field-label">
              Project
              <Select className="mt-2" {...form.register("project")}>
                <option value="">No project</option>
                {projects.map((project) => <option key={project.id} value={project.id}>{project.title}</option>)}
              </Select>
            </label>
            <label className="field-label">Content<Textarea className="mt-2" placeholder="What happened? What is the next move?" {...form.register("content")} />{form.formState.errors.content && <p className="field-hint text-primary">{form.formState.errors.content.message}</p>}</label>
            <div className="flex gap-2">
              <Button disabled={form.formState.isSubmitting}>{editing ? "Save" : "Create"}</Button>
              {editing && <Button type="button" variant="outline" onClick={() => { setEditing(null); form.reset(defaultValues); }}>Cancel</Button>}
            </div>
          </div>
        </form>
        <div className="min-w-0">{isLoading ? <TableSkeleton /> : <EntityTable columns={columns} data={data} onEdit={edit} onDelete={deleteMutation.mutate} canModify={canModify} />}</div>
      </div>
    </MotionSection>
  );
}
