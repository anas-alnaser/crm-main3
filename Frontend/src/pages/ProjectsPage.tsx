import type { ColumnDef } from "@tanstack/react-table";
import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { EntityTable } from "../components/EntityTable";
import { PageHeader } from "../components/PageHeader";
import { Badge, statusTone } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { MotionSection, pageMotion } from "../components/ui/motion";
import { Select } from "../components/ui/select";
import { TableSkeleton } from "../components/ui/skeleton";
import { Textarea } from "../components/ui/textarea";
import { useCrud } from "../hooks/useCrud";
import type { Client, Project } from "../api/types";

const emptyToNull = (value: unknown) => (value === "" ? null : value);

const schema = z.object({
  title: z.string().min(1, "Title is required"),
  client: z.coerce.number().min(1, "Client is required"),
  type: z.enum(["branding", "web", "dev", "other"]),
  status: z.enum(["lead", "proposal", "in_progress", "delivered", "paid"]),
  budget: z.preprocess(emptyToNull, z.coerce.number().nonnegative().nullable()),
  start_date: z.preprocess(emptyToNull, z.string().nullable()),
  deadline: z.preprocess(emptyToNull, z.string().nullable()),
  notes: z.string().optional(),
});

type FormValues = z.infer<typeof schema>;

const defaultValues = {
  title: "",
  client: 0,
  type: "branding",
  status: "lead",
  budget: null,
  start_date: null,
  deadline: null,
  notes: "",
} satisfies FormValues;

const columns: ColumnDef<Project>[] = [
  { accessorKey: "title", header: "Title" },
  { accessorKey: "client_name", header: "Client" },
  { accessorKey: "type", header: "Type", cell: ({ row }) => <Badge>{row.original.type}</Badge> },
  { accessorKey: "status", header: "Status", cell: ({ row }) => <Badge tone={statusTone(row.original.status)}>{row.original.status.replace("_", " ")}</Badge> },
  { accessorKey: "deadline", header: "Deadline" },
];

export function ProjectsPage() {
  const [editing, setEditing] = useState<Project | null>(null);
  const { data = [], isLoading, createMutation, updateMutation, deleteMutation } = useCrud<Project>("projects");
  const { data: clients = [] } = useCrud<Client>("clients");
  const form = useForm<FormValues>({ resolver: zodResolver(schema), defaultValues });

  const submit = form.handleSubmit(async (values) => {
    const payload = { ...values, budget: values.budget === null ? null : String(values.budget) };
    if (editing) await updateMutation.mutateAsync({ id: editing.id, data: payload });
    else await createMutation.mutateAsync(payload);
    setEditing(null);
    form.reset(defaultValues);
  });

  const edit = (project: Project) => {
    setEditing(project);
    form.reset({ ...project, budget: project.budget ? Number(project.budget) : null });
  };

  return (
    <MotionSection className="page-shell" {...pageMotion}>
      <PageHeader title="Projects" subtitle="Track delivery work from proposal through payment." />
      <div className="grid gap-6 xl:grid-cols-[400px_1fr]">
        <form onSubmit={submit} className="form-panel">
          <h3 className="mb-1 text-lg font-semibold">{editing ? "Edit project" : "Create project"}</h3>
          <p className="mb-5 text-sm text-muted-foreground">Plan budgets, deadlines, and delivery status.</p>
          <div className="space-y-4">
            <label className="field-label">Title<Input className="mt-2" placeholder="Brand refresh sprint" {...form.register("title")} />{form.formState.errors.title && <p className="field-hint text-primary">{form.formState.errors.title.message}</p>}</label>
            <label className="field-label">
              Client
              <Select className="mt-2" {...form.register("client")}>
                <option value={0}>Select client</option>
                {clients.map((client) => <option key={client.id} value={client.id}>{client.name}</option>)}
              </Select>
            </label>
            <label className="field-label">
              Type
              <Select className="mt-2" {...form.register("type")}>
                <option value="branding">Branding</option><option value="web">Web</option><option value="dev">Dev</option><option value="other">Other</option>
              </Select>
            </label>
            <label className="field-label">
              Status
              <Select className="mt-2" {...form.register("status")}>
                <option value="lead">Lead</option><option value="proposal">Proposal</option><option value="in_progress">In progress</option><option value="delivered">Delivered</option><option value="paid">Paid</option>
              </Select>
            </label>
            <label className="field-label">Budget<Input className="mt-2 tabular-nums" placeholder="0.00" type="number" step="0.01" {...form.register("budget")} /></label>
            <label className="field-label">Start date<Input className="mt-2" type="date" {...form.register("start_date")} /></label>
            <label className="field-label">Deadline<Input className="mt-2" type="date" {...form.register("deadline")} /></label>
            <label className="field-label">Notes<Textarea className="mt-2" placeholder="Scope, constraints, delivery details..." {...form.register("notes")} /></label>
            <div className="flex gap-2">
              <Button disabled={form.formState.isSubmitting}>{editing ? "Save" : "Create"}</Button>
              {editing && <Button type="button" variant="outline" onClick={() => { setEditing(null); form.reset(defaultValues); }}>Cancel</Button>}
            </div>
          </div>
        </form>
        <div className="min-w-0">{isLoading ? <TableSkeleton /> : <EntityTable columns={columns} data={data} onEdit={edit} onDelete={deleteMutation.mutate} />}</div>
      </div>
    </MotionSection>
  );
}
