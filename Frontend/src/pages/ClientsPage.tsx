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
  {
    accessorKey: "status",
    header: "Status",
    cell: ({ row }) => <Badge tone={statusTone(row.original.status)}>{row.original.status}</Badge>,
  },
];

export function ClientsPage() {
  const [editing, setEditing] = useState<Client | null>(null);
  const { data = [], isLoading, createMutation, updateMutation, deleteMutation } = useCrud<Client>("clients");
  const form = useForm<FormValues>({ resolver: zodResolver(schema), defaultValues });

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

  return (
    <MotionSection className="page-shell" {...pageMotion}>
      <PageHeader title="Companies" subtitle="Manage agency relationships, decision makers, and contact details." />
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
        <div className="min-w-0">{isLoading ? <TableSkeleton /> : <EntityTable columns={columns} data={data} onEdit={edit} onDelete={deleteMutation.mutate} />}</div>
      </div>
    </MotionSection>
  );
}
