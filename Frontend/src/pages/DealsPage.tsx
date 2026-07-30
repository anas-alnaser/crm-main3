import {
  flexRender,
  getCoreRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type SortingState,
} from "@tanstack/react-table";
import { zodResolver } from "@hookform/resolvers/zod";
import { Plus } from "lucide-react";
import { useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";

import { apiRequest, createEntity, deleteEntity, fetchList, updateEntity } from "../api/client";
import type { Client, Deal, Stage, User } from "../api/types";
import { PageHeader } from "../components/PageHeader";
import { Badge, statusTone } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { MotionDiv, MotionSection, pageMotion } from "../components/ui/motion";
import { Select } from "../components/ui/select";
import { TableSkeleton } from "../components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../components/ui/table";
import { Textarea } from "../components/ui/textarea";
import { useAuth } from "../lib/auth";
import { useToast } from "../lib/toast";
import { useCrud } from "../hooks/useCrud";

const emptyToNull = (value: unknown) => (value === "" ? null : value);

const dealSchema = z.object({
  title: z.string().min(1, "Title is required"),
  company: z.coerce.number().min(1, "Company is required"),
  contact_person: z.string().optional(),
  value: z.preprocess(emptyToNull, z.coerce.number().nonnegative().nullable()),
  currency: z.string().min(3).max(3),
  pipeline: z.coerce.number().min(1),
  stage: z.coerce.number().min(1),
  owner: z.coerce.number().min(1, "Owner is required"),
  expected_close_date: z.preprocess(emptyToNull, z.string().nullable()),
  notes: z.string().optional(),
});

type DealFormValues = z.infer<typeof dealSchema>;

const formatCurrency = (value: string | number | null, currency = "JOD") =>
  new Intl.NumberFormat("en-US", { style: "currency", currency, maximumFractionDigits: 0 }).format(Number(value ?? 0));

const formatDealValue = (value: string | number | null, currency = "JOD") => (value === null ? `${currency} *****` : formatCurrency(value, currency));

function DealEditor({
  clients,
  deal,
  stages,
  users,
  onCancel,
  onSubmit,
}: {
  clients: Client[];
  deal: Deal | null;
  stages: Stage[];
  users: User[];
  onCancel: () => void;
  onSubmit: (values: DealFormValues) => Promise<unknown>;
}) {
  const { user } = useAuth();
  const firstStage = stages[0];
  const form = useForm<DealFormValues>({
    resolver: zodResolver(dealSchema),
    defaultValues: deal
      ? {
          title: deal.title,
          company: deal.company,
          contact_person: deal.contact_person,
          value: deal.value ? Number(deal.value) : null,
          currency: deal.currency,
          pipeline: deal.pipeline,
          stage: deal.stage,
          owner: deal.owner,
          expected_close_date: deal.expected_close_date,
          notes: deal.notes,
        }
      : {
          title: "",
          company: clients[0]?.id ?? 0,
          contact_person: "",
          value: null,
          currency: "JOD",
          pipeline: firstStage?.pipeline ?? 0,
          stage: firstStage?.id ?? 0,
          owner: user?.id ?? users[0]?.id ?? 0,
          expected_close_date: null,
          notes: "",
        },
  });
  const selectedStage = stages.find((stage) => stage.id === Number(form.watch("stage")));

  return (
    <form
      className="space-y-4"
      onSubmit={form.handleSubmit((values) => onSubmit({ ...values, pipeline: selectedStage?.pipeline ?? values.pipeline }))}
    >
      <label className="field-label">Title<Input className="mt-2" placeholder="Brand strategy retainer" {...form.register("title")} /></label>
      <label className="field-label">
        Company
        <Select className="mt-2" {...form.register("company")}>
          {clients.map((client) => <option key={client.id} value={client.id}>{client.name}</option>)}
        </Select>
      </label>
      <label className="field-label">Contact person<Input className="mt-2" placeholder="Primary buyer" {...form.register("contact_person")} /></label>
      <div className="grid gap-3 md:grid-cols-[1fr_96px]">
        <label className="field-label">Value<Input className="mt-2 tabular-nums" step="0.01" type="number" {...form.register("value")} /></label>
        <label className="field-label">Currency<Input className="mt-2 uppercase" maxLength={3} {...form.register("currency")} /></label>
      </div>
      <label className="field-label">
        Owner
        <Select className="mt-2" {...form.register("owner")}>
          {users.map((owner) => <option key={owner.id} value={owner.id}>{owner.first_name || owner.username}</option>)}
        </Select>
      </label>
      <label className="field-label">
        Stage
        <Select className="mt-2" {...form.register("stage")}>
          {stages.map((stage) => <option key={stage.id} value={stage.id}>{stage.name}</option>)}
        </Select>
      </label>
      <label className="field-label">Expected close<Input className="mt-2" type="date" {...form.register("expected_close_date")} /></label>
      <label className="field-label">Notes<Textarea className="mt-2" placeholder="Commercial notes, risks, next steps..." {...form.register("notes")} /></label>
      <div className="flex gap-2">
        <Button disabled={form.formState.isSubmitting}>{deal ? "Save" : "Create"}</Button>
        <Button type="button" variant="outline" onClick={onCancel}>Cancel</Button>
      </div>
    </form>
  );
}

export function DealsPage() {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const { user: currentUser } = useAuth();
  const isAdmin = currentUser?.role === "admin";
  const [sorting, setSorting] = useState<SortingState>([]);
  const [query, setQuery] = useState("");
  const [stageFilter, setStageFilter] = useState("all");
  const [ownerFilter, setOwnerFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [mineMode, setMineMode] = useState(currentUser?.role === "sales");
  const [editingDeal, setEditingDeal] = useState<Deal | null>(null);
  const [isCreating, setIsCreating] = useState(false);

  const { data: deals = [], isLoading, isError } = useQuery({
    queryKey: ["deals", mineMode],
    queryFn: () => fetchList<Deal>(mineMode ? "/deals/?mine=true" : "/deals/"),
  });
  const { data: clients = [] } = useCrud<Client>("clients");
  const { data: stages = [] } = useCrud<Stage>("stages");
  const { data: users = [] } = useQuery({
    queryKey: ["users"],
    queryFn: () => fetchList<User>("/users/"),
    enabled: isAdmin,
  });
  const ownerOptions = isAdmin ? users : currentUser ? [currentUser] : [];

  function canManageDeal(deal: Deal) {
    return isAdmin || deal.owner === currentUser?.id;
  }

  const filteredDeals = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return deals.filter((deal) => {
      const matchesSearch = !needle || [deal.title, deal.company_name, deal.owner_username, deal.contact_person]
        .filter(Boolean)
        .some((value) => value?.toLowerCase().includes(needle));
      const matchesStage = stageFilter === "all" || deal.stage === Number(stageFilter);
      const matchesOwner = ownerFilter === "all" || deal.owner === Number(ownerFilter);
      const matchesStatus = statusFilter === "all" || deal.status === statusFilter;
      return matchesSearch && matchesStage && matchesOwner && matchesStatus;
    });
  }, [deals, ownerFilter, query, stageFilter, statusFilter]);

  const columns = useMemo<ColumnDef<Deal>[]>(
    () => [
      { accessorKey: "title", header: "Deal" },
      { accessorKey: "company_name", header: "Company" },
      { accessorKey: "stage_name", header: "Stage", cell: ({ row }) => <Badge>{row.original.stage_name}</Badge> },
      { accessorKey: "owner_username", header: "Owner" },
      { accessorKey: "status", header: "Status", cell: ({ row }) => <Badge tone={statusTone(row.original.status)}>{row.original.status}</Badge> },
      {
        accessorKey: "value",
        header: "Value",
        cell: ({ row }) => <span className="metric-number text-primary">{formatDealValue(row.original.value, row.original.currency)}</span>,
      },
      { accessorKey: "expected_close_date", header: "Close date" },
      {
        id: "actions",
        header: "",
        cell: ({ row }) => {
          const canManage = canManageDeal(row.original);
          return (
            <div className="flex justify-end gap-2">
              <Button className="h-8 px-3" disabled={!canManage} variant="outline" onClick={() => setEditingDeal(row.original)}>Edit</Button>
              <Button className="h-8 px-3" disabled={!canManage} variant="danger" onClick={() => handleDelete(row.original.id)}>Delete</Button>
            </div>
          );
        },
      },
    ],
    [currentUser, isAdmin],
  );

  const table = useReactTable({
    data: filteredDeals,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
  });

  const createDeal = useMutation({
    mutationFn: (values: DealFormValues) => createEntity<Deal>("deals", { ...values, value: values.value === null ? null : String(values.value) }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["deals"] });
      setIsCreating(false);
      showToast("Deal created.", "success");
    },
    onError: () => showToast("Could not create deal.", "error"),
  });

  const updateDeal = useMutation({
    mutationFn: ({ id, values }: { id: number; values: DealFormValues }) => updateEntity<Deal>("deals", id, { ...values, value: values.value === null ? null : String(values.value) }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["deals"] });
      setEditingDeal(null);
      showToast("Deal updated.", "success");
    },
    onError: () => showToast("Could not update deal.", "error"),
  });

  const deleteDeal = useMutation({
    mutationFn: (id: number) => deleteEntity("deals", id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["deals"] });
      showToast("Deal deleted.", "success");
    },
    onError: () => showToast("Could not delete deal.", "error"),
  });

  function handleDelete(id: number) {
    if (window.confirm("Delete this deal?")) {
      deleteDeal.mutate(id);
    }
  }

  return (
    <MotionSection className="page-shell" {...pageMotion}>
      <PageHeader
        title="Deals"
        subtitle="Search, sort, filter, create, edit, and close sales opportunities."
        actions={<Button className="shrink-0" onClick={() => setIsCreating(true)}><Plus className="h-4 w-4" /> Add Deal</Button>}
      />

      <div className="surface-card grid gap-3 p-4 lg:grid-cols-[1fr_150px_180px_180px_160px]">
        <Input placeholder="Search deals..." value={query} onChange={(event) => setQuery(event.target.value)} />
        <Select
          value={mineMode ? "mine" : "all"}
          onChange={(event) => setMineMode(event.target.value === "mine")}
        >
          <option value="all">All deals</option>
          <option value="mine">My deals</option>
        </Select>
        <Select value={stageFilter} onChange={(event) => setStageFilter(event.target.value)}>
          <option value="all">All stages</option>
          {stages.map((stage) => <option key={stage.id} value={stage.id}>{stage.name}</option>)}
        </Select>
        <Select disabled={!isAdmin} value={ownerFilter} onChange={(event) => setOwnerFilter(event.target.value)}>
          <option value="all">All owners</option>
          {ownerOptions.map((owner) => <option key={owner.id} value={owner.id}>{owner.first_name || owner.username}</option>)}
        </Select>
        <Select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
          <option value="all">All statuses</option>
          <option value="open">Open</option>
          <option value="won">Won</option>
          <option value="lost">Lost</option>
        </Select>
      </div>

      {isLoading ? (
        <TableSkeleton />
      ) : isError ? (
        <div className="surface-card p-6 text-sm text-muted-foreground">Could not load deals. Check the backend terminal and browser Network tab.</div>
      ) : (
        <div className="surface-card overflow-hidden">
          <Table>
            <TableHeader>
              {table.getHeaderGroups().map((headerGroup) => (
                <TableRow key={headerGroup.id}>
                  {headerGroup.headers.map((header) => (
                    <TableHead key={header.id}>
                      <button className="font-semibold" type="button" onClick={header.column.getToggleSortingHandler()}>
                        {flexRender(header.column.columnDef.header, header.getContext())}
                        {header.column.getIsSorted() === "asc" ? " ↑" : header.column.getIsSorted() === "desc" ? " ↓" : ""}
                      </button>
                    </TableHead>
                  ))}
                </TableRow>
              ))}
            </TableHeader>
            <TableBody>
              {table.getRowModel().rows.map((row) => (
                <TableRow key={row.id}>
                  {row.getVisibleCells().map((cell) => <TableCell key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</TableCell>)}
                </TableRow>
              ))}
              {!filteredDeals.length && (
                <TableRow>
                  <TableCell className="h-32 text-center" colSpan={columns.length}>
                    <div className="space-y-3">
                      <p className="text-muted-foreground">No deals yet.</p>
                      <Button onClick={() => setIsCreating(true)}>Add your first deal</Button>
                    </div>
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
          <div className="flex items-center justify-between border-t border-border px-4 py-3 text-sm">
            <span className="text-muted-foreground">Page {table.getState().pagination.pageIndex + 1} of {table.getPageCount() || 1}</span>
            <div className="flex gap-2">
              <Button className="h-8 px-3" disabled={!table.getCanPreviousPage()} variant="outline" onClick={() => table.previousPage()}>Previous</Button>
              <Button className="h-8 px-3" disabled={!table.getCanNextPage()} variant="outline" onClick={() => table.nextPage()}>Next</Button>
            </div>
          </div>
        </div>
      )}

      {(isCreating || editingDeal) && (
        <div className="fixed inset-0 z-40 grid place-items-center bg-black/60 p-4">
          <MotionDiv className="max-h-[90vh] w-full max-w-xl overflow-y-auto rounded-lg border border-border bg-card p-5 text-card-foreground shadow-soft" initial={{ opacity: 0, y: 12, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} transition={{ duration: 0.18 }}>
            <h2 className="mb-5 text-lg font-semibold">{editingDeal ? "Edit deal" : "Create deal"}</h2>
            <DealEditor
              clients={clients}
              deal={editingDeal}
              stages={stages}
              users={ownerOptions}
              onCancel={() => { setIsCreating(false); setEditingDeal(null); }}
              onSubmit={(values) => editingDeal ? updateDeal.mutateAsync({ id: editingDeal.id, values }) : createDeal.mutateAsync(values)}
            />
          </MotionDiv>
        </div>
      )}
    </MotionSection>
  );
}
