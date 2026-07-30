import { DndContext, useDraggable, useDroppable, type DragEndEvent } from "@dnd-kit/core";
import { zodResolver } from "@hookform/resolvers/zod";
import { CalendarClock, CalendarDays, Clock3, Plus, X, Kanban } from "lucide-react";
import { useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { apiRequest, createEntity, fetchList, patchEntity, updateEntity } from "../api/client";
import type { Activity, Client, Deal, Meeting, Stage, Task, User } from "../api/types";
import { PageHeader } from "../components/PageHeader";
import { Badge, statusTone } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { EmptyState } from "../components/ui/empty-state";
import { Input } from "../components/ui/input";
import { drawerMotion, MotionDiv, MotionSection, pageMotion } from "../components/ui/motion";
import { Select } from "../components/ui/select";
import { BoardSkeleton } from "../components/ui/skeleton";
import { Textarea } from "../components/ui/textarea";
import { useAuth } from "../lib/auth";
import { cn } from "../lib/utils";
import { useToast } from "../lib/toast";

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

const activitySchema = z.object({
  type: z.enum(["call", "meeting", "email", "note"]),
  content: z.string().min(1, "Activity content is required"),
});

type DealFormValues = z.infer<typeof dealSchema>;
type ActivityFormValues = z.infer<typeof activitySchema>;

const formatCurrency = (value: string | null, currency = "JOD") => {
  const numericValue = Number(value ?? 0);
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(Number.isFinite(numericValue) ? numericValue : 0);
};

const formatDealValue = (value: string | null, currency = "JOD") => (value === null ? `${currency} *****` : formatCurrency(value, currency));
const formatMeetingTime = (meeting: Meeting) =>
  `${new Date(meeting.start_datetime).toLocaleDateString()} · ${new Date(meeting.start_datetime).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}`;

const initialsFor = (name?: string) =>
  (name || "?")
    .split(" ")
    .map((part) => part[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();

const ageInDays = (date: string) => {
  const days = Math.max(0, Math.floor((Date.now() - new Date(date).getTime()) / 86_400_000));
  if (days === 0) return "new";
  return `${days}d old`;
};

function DraggableDealCard({ canManage, deal, onOpen }: { canManage: boolean; deal: Deal; onOpen: (deal: Deal) => void }) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: String(deal.id),
    data: { deal },
    disabled: !canManage,
  });

  return (
    <button
      ref={setNodeRef}
      type="button"
      className={cn(
        "w-full rounded-lg border border-border bg-background p-4 text-left text-sm shadow-sm transition hover:-translate-y-0.5 hover:border-primary/50 hover:shadow-soft",
        isDragging && "scale-[1.02] border-primary opacity-90 shadow-soft",
        !canManage && "cursor-pointer opacity-80",
      )}
      style={transform ? { transform: `translate3d(${transform.x}px, ${transform.y}px, 0)` } : undefined}
      onClick={() => onOpen(deal)}
      {...(canManage ? listeners : {})}
      {...attributes}
    >
      <div className="mb-2 flex items-start justify-between gap-3">
        <h3 className="font-semibold leading-snug text-foreground">{deal.title}</h3>
        <Badge tone={statusTone(deal.status)}>{deal.status}</Badge>
      </div>
      <p className="text-muted-foreground">{deal.company_name}</p>
      <p className="metric-number mt-3 text-xl text-primary">{formatDealValue(deal.value, deal.currency)}</p>
      {deal.commission && (
        <p className="mt-1 text-xs font-medium text-muted-foreground">
          Commission {formatCurrency(deal.commission, deal.currency)}
        </p>
      )}
      <div className="mt-4 flex items-center justify-between gap-2 text-xs text-muted-foreground">
        <span className="flex items-center gap-2">
          <span className="grid h-7 w-7 place-items-center rounded-full bg-muted text-[10px] font-semibold text-foreground">{initialsFor(deal.owner_username)}</span>
          {deal.owner_username}
        </span>
        <span className="inline-flex items-center gap-1">
          <CalendarDays className="h-3 w-3" />
          {deal.expected_close_date || "No date"}
        </span>
      </div>
      <div className="mt-3 flex items-center gap-1 text-xs text-muted-foreground">
        <Clock3 className="h-3 w-3" />
        {ageInDays(deal.created_at)}
      </div>
    </button>
  );
}

function StageColumn({
  canManageDeal,
  stage,
  deals,
  onOpenDeal,
  showRevenueTotal,
}: {
  canManageDeal: (deal: Deal) => boolean;
  stage: Stage;
  deals: Deal[];
  onOpenDeal: (deal: Deal) => void;
  showRevenueTotal: boolean;
}) {
  const { setNodeRef, isOver } = useDroppable({ id: String(stage.id), data: { stage } });
  const total = deals.reduce((sum, deal) => sum + Number(deal.value ?? 0), 0);

  return (
    <section
      ref={setNodeRef}
      className={cn(
        "flex min-h-[560px] w-[330px] shrink-0 flex-col rounded-lg border border-border bg-card text-card-foreground shadow-soft transition",
        isOver && "border-primary bg-primary/5 shadow-soft",
        stage.is_won && "border-primary/60",
        stage.is_lost && "opacity-80",
      )}
    >
      <header className="border-b border-border p-4">
        <div className="mb-3 h-1.5 rounded-full bg-primary/80" />
        <div className="flex items-center justify-between gap-3">
          <h2 className="font-semibold">{stage.name}</h2>
          <Badge>{deals.length} deals</Badge>
        </div>
        <p className="metric-number mt-2 text-sm text-muted-foreground">{showRevenueTotal ? formatCurrency(String(total), "JOD") : `${deals.length} deal${deals.length === 1 ? "" : "s"}`}</p>
      </header>
      <div className="flex flex-1 flex-col gap-3 p-3">
        {deals.map((deal) => (
          <DraggableDealCard key={deal.id} canManage={canManageDeal(deal)} deal={deal} onOpen={onOpenDeal} />
        ))}
        {!deals.length && <EmptyState icon={Kanban} title="No deals" message="Drop a deal here or create one to fill this stage." />}
      </div>
    </section>
  );
}

function DealForm({
  clients,
  stages,
  users,
  initialDeal,
  onSubmit,
  onCancel,
}: {
  clients: Client[];
  stages: Stage[];
  users: User[];
  initialDeal?: Deal;
  onSubmit: (values: DealFormValues) => Promise<unknown>;
  onCancel: () => void;
}) {
  const { user } = useAuth();
  const firstStage = stages[0];
  const form = useForm<DealFormValues>({
    resolver: zodResolver(dealSchema),
    defaultValues: initialDeal
      ? {
          title: initialDeal.title,
          company: initialDeal.company,
          contact_person: initialDeal.contact_person,
          value: initialDeal.value ? Number(initialDeal.value) : null,
          currency: initialDeal.currency,
          pipeline: initialDeal.pipeline,
          stage: initialDeal.stage,
          owner: initialDeal.owner,
          expected_close_date: initialDeal.expected_close_date,
          notes: initialDeal.notes,
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

  const selectedStageId = Number(form.watch("stage"));
  const selectedStage = stages.find((stage) => stage.id === selectedStageId);

  return (
    <form
      className="space-y-4"
      onSubmit={form.handleSubmit(async (values) => {
        await onSubmit({
          ...values,
          pipeline: selectedStage?.pipeline ?? values.pipeline,
        });
      })}
    >
      <label className="field-label">
        Deal title
        <Input className="mt-2" placeholder="Website redesign opportunity" {...form.register("title")} />
      </label>
      <label className="field-label">
        Company
        <Select className="mt-2" {...form.register("company")}>
          {clients.map((client) => (
            <option key={client.id} value={client.id}>
              {client.name}
            </option>
          ))}
        </Select>
      </label>
      <label className="field-label">
        Contact person
        <Input className="mt-2" placeholder="Decision maker" {...form.register("contact_person")} />
      </label>
      <div className="grid grid-cols-[1fr_96px] gap-3">
        <label className="field-label">
          Value
          <Input className="mt-2 tabular-nums" step="0.01" type="number" {...form.register("value")} />
        </label>
        <label className="field-label">
          Currency
          <Input className="mt-2 uppercase" maxLength={3} {...form.register("currency")} />
        </label>
      </div>
      <label className="field-label">
        Owner
        <Select className="mt-2" {...form.register("owner")}>
          {users.map((owner) => (
            <option key={owner.id} value={owner.id}>
              {owner.first_name || owner.username}
            </option>
          ))}
        </Select>
      </label>
      <label className="field-label">
        Stage
        <Select className="mt-2" {...form.register("stage")}>
          {stages.map((stage) => (
            <option key={stage.id} value={stage.id}>
              {stage.name}
            </option>
          ))}
        </Select>
      </label>
      <label className="field-label">
        Expected close
        <Input className="mt-2" type="date" {...form.register("expected_close_date")} />
      </label>
      <label className="field-label">
        Notes
        <Textarea className="mt-2" placeholder="Commercial context, risks, or next step..." {...form.register("notes")} />
      </label>
      <div className="flex gap-2">
        <Button disabled={form.formState.isSubmitting}>{initialDeal ? "Save deal" : "Add deal"}</Button>
        <Button type="button" variant="outline" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

export function PipelinePage() {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const { user: currentUser } = useAuth();
  const isAdmin = currentUser?.role === "admin";
  const [isAddOpen, setIsAddOpen] = useState(false);
  const [selectedDeal, setSelectedDeal] = useState<Deal | null>(null);
  const [mineMode, setMineMode] = useState(currentUser?.role === "sales");
  const dealsQueryKey = useMemo(() => ["deals", mineMode] as const, [mineMode]);

  const { data: stages = [], isLoading: stagesLoading } = useQuery({
    queryKey: ["stages"],
    queryFn: () => fetchList<Stage>("/stages/?ordering=order"),
  });
  const { data: deals = [], isLoading: dealsLoading } = useQuery({
    queryKey: dealsQueryKey,
    queryFn: () => fetchList<Deal>(mineMode ? "/deals/?mine=true" : "/deals/"),
  });
  const { data: clients = [] } = useQuery({
    queryKey: ["clients"],
    queryFn: () => fetchList<Client>("/clients/"),
  });
  const { data: users = [] } = useQuery({
    queryKey: ["users"],
    queryFn: () => fetchList<User>("/users/"),
    enabled: isAdmin,
  });
  const { data: tasks = [] } = useQuery({
    queryKey: ["tasks"],
    queryFn: () => fetchList<Task>("/tasks/"),
  });
  const { data: activities = [] } = useQuery({
    queryKey: ["activities"],
    queryFn: () => fetchList<Activity>("/activities/"),
  });
  const { data: selectedDealMeetings = [], isLoading: selectedDealMeetingsLoading } = useQuery({
    queryKey: ["meetings", "deal", selectedDeal?.id],
    queryFn: () => fetchList<Meeting>(`/meetings/?deal=${selectedDeal?.id}&ordering=start_datetime`),
    enabled: Boolean(selectedDeal),
  });

  const dealsByStage = useMemo(() => {
    return stages.reduce<Record<number, Deal[]>>((acc, stage) => {
      acc[stage.id] = deals.filter((deal) => deal.stage === stage.id);
      return acc;
    }, {});
  }, [deals, stages]);

  const ownerOptions = isAdmin ? users : currentUser ? [currentUser] : [];
  const showRevenueTotals = isAdmin || mineMode;

  function canManageDeal(deal: Deal) {
    return isAdmin || deal.owner === currentUser?.id;
  }

  const createDeal = useMutation({
    mutationFn: (values: DealFormValues) =>
      createEntity<Deal>("deals", {
        ...values,
        value: values.value === null ? null : String(values.value),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["deals"] });
      setIsAddOpen(false);
      showToast("Deal added.", "success");
    },
    onError: () => showToast("Could not add deal.", "error"),
  });

  const updateDeal = useMutation({
    mutationFn: ({ id, values }: { id: number; values: DealFormValues }) =>
      updateEntity<Deal>("deals", id, {
        ...values,
        value: values.value === null ? null : String(values.value),
      }),
    onSuccess: (deal) => {
      queryClient.invalidateQueries({ queryKey: ["deals"] });
      setSelectedDeal(deal);
      showToast("Deal updated.", "success");
    },
    onError: () => showToast("Could not update deal.", "error"),
  });

  const moveDeal = useMutation({
    mutationFn: ({ id, stage }: { id: number; stage: number }) => apiRequest<Deal>(`/deals/${id}/move/`, {
      method: "PATCH",
      body: JSON.stringify({ stage }),
    }),
    onMutate: async ({ id, stage }) => {
      await queryClient.cancelQueries({ queryKey: dealsQueryKey });
      const previousDeals = queryClient.getQueryData<Deal[]>(dealsQueryKey);
      queryClient.setQueryData<Deal[]>(dealsQueryKey, (current = []) =>
        current.map((deal) => (deal.id === id ? { ...deal, stage } : deal)),
      );
      return { previousDeals };
    },
    onError: (_error, _variables, context) => {
      if (context?.previousDeals) queryClient.setQueryData(dealsQueryKey, context.previousDeals);
      showToast("Could not move deal.", "error");
    },
    onSuccess: () => showToast("Deal moved.", "success"),
    onSettled: () => queryClient.invalidateQueries({ queryKey: dealsQueryKey }),
  });

  const createActivity = useMutation({
    mutationFn: (values: ActivityFormValues) =>
      createEntity<Activity>("activities", {
        ...values,
        client: selectedDeal?.company ?? null,
        deal: selectedDeal?.id ?? null,
        project: null,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["activities"] });
      showToast("Activity logged.", "success");
    },
    onError: () => showToast("Could not log activity.", "error"),
  });

  const activityForm = useForm<ActivityFormValues>({
    resolver: zodResolver(activitySchema),
    defaultValues: { type: "note", content: "" },
  });

  const onDragEnd = (event: DragEndEvent) => {
    const deal = event.active.data.current?.deal as Deal | undefined;
    const stage = event.over?.data.current?.stage as Stage | undefined;
    if (!deal || !stage || deal.stage === stage.id) return;
    if (!canManageDeal(deal)) {
      showToast("Sales users can only move their own deals.", "error");
      return;
    }
    moveDeal.mutate({ id: deal.id, stage: stage.id });
  };

  const selectedDealTasks = tasks.filter((task) => task.deal === selectedDeal?.id);
  const selectedDealActivities = activities.filter((activity) => activity.deal === selectedDeal?.id);

  return (
    <MotionSection className="page-shell min-w-0" {...pageMotion}>
      <PageHeader
        title="Pipeline"
        subtitle="Create deals, read the board quickly, and move opportunities through your sales stages."
        actions={
        <div className="flex items-center gap-2">
          <Select className="w-[168px] shrink-0" value={mineMode ? "mine" : "all"} onChange={(event) => setMineMode(event.target.value === "mine")}>
            <option value="all">All deals</option>
            <option value="mine">My deals</option>
          </Select>
          <Button className="shrink-0" onClick={() => setIsAddOpen(true)}>
            <Plus className="h-4 w-4" />
            Add Deal
          </Button>
        </div>
        }
      />

      {stagesLoading || dealsLoading ? (
        <BoardSkeleton />
      ) : (
        <DndContext onDragEnd={onDragEnd}>
          <div className="flex gap-4 overflow-x-auto pb-4">
            {stages.map((stage) => (
              <StageColumn
                key={stage.id}
                canManageDeal={canManageDeal}
                stage={stage}
                deals={dealsByStage[stage.id] ?? []}
                onOpenDeal={setSelectedDeal}
                showRevenueTotal={showRevenueTotals}
              />
            ))}
          </div>
        </DndContext>
      )}

      {isAddOpen && (
        <div className="fixed inset-0 z-40 grid place-items-center bg-black/60 p-4">
          <MotionDiv className="max-h-[90vh] w-full max-w-xl overflow-y-auto rounded-lg border border-border bg-card p-5 text-card-foreground shadow-soft" initial={{ opacity: 0, y: 12, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} transition={{ duration: 0.18 }}>
            <div className="mb-5 flex items-center justify-between">
              <h2 className="text-lg font-semibold">Add deal</h2>
              <Button aria-label="Close add deal modal" size="icon" type="button" variant="ghost" onClick={() => setIsAddOpen(false)}>
                <X className="h-4 w-4" />
              </Button>
            </div>
            <DealForm
              clients={clients}
              stages={stages}
              users={ownerOptions}
              onCancel={() => setIsAddOpen(false)}
              onSubmit={(values) => createDeal.mutateAsync(values)}
            />
          </MotionDiv>
        </div>
      )}

      {selectedDeal && (
        <MotionDiv className="fixed inset-y-0 right-0 z-40 w-full max-w-xl overflow-y-auto border-l border-border bg-card p-5 text-card-foreground shadow-soft" {...drawerMotion}>
          <div className="mb-5 flex items-center justify-between">
            <div>
              <h2 className="text-lg font-semibold">{selectedDeal.title}</h2>
              <p className="text-sm text-muted-foreground">{selectedDeal.company_name}</p>
              {selectedDeal.commission && (
                <p className="mt-2 text-sm font-medium text-primary">
                  Deal commission {formatCurrency(selectedDeal.commission, selectedDeal.currency)}
                </p>
              )}
            </div>
            <Button aria-label="Close deal drawer" size="icon" type="button" variant="ghost" onClick={() => setSelectedDeal(null)}>
              <X className="h-4 w-4" />
            </Button>
          </div>

          {canManageDeal(selectedDeal) ? (
            <DealForm
              clients={clients}
              initialDeal={selectedDeal}
              stages={stages}
              users={ownerOptions}
              onCancel={() => setSelectedDeal(null)}
              onSubmit={(values) => updateDeal.mutateAsync({ id: selectedDeal.id, values })}
            />
          ) : (
            <div className="rounded-md border border-border bg-muted p-4 text-sm text-muted-foreground">
              You can view this deal, but only the owner or an admin can edit it.
            </div>
          )}

          <div className="mt-8 border-t border-border pt-6">
            <div className="flex items-center justify-between gap-3">
              <h3 className="font-semibold">Meetings</h3>
              <Link
                className="inline-flex h-9 items-center gap-2 rounded-md bg-primary px-3 text-xs font-medium text-primary-foreground shadow-sm shadow-primary/20 transition hover:bg-primary-hover"
                to={`/schedule?deal=${selectedDeal.id}`}
              >
                <CalendarClock className="h-4 w-4" />
                Schedule
              </Link>
            </div>
            <div className="mt-3 space-y-2">
              {selectedDealMeetingsLoading ? (
                <div className="rounded-md border border-border p-3 text-sm text-muted-foreground">Loading meetings...</div>
              ) : selectedDealMeetings.length ? (
                selectedDealMeetings.map((meeting) => (
                  <div key={meeting.id} className="rounded-md border border-border p-3 text-sm">
                    <div className="flex items-center justify-between gap-3">
                      <p className="font-medium">{meeting.title}</p>
                      <Badge tone={statusTone(meeting.status)}>{meeting.status}</Badge>
                    </div>
                    <p className="mt-1 text-muted-foreground">{formatMeetingTime(meeting)}{meeting.location ? ` · ${meeting.location}` : ""}</p>
                  </div>
                ))
              ) : (
                <p className="text-sm text-muted-foreground">No meetings linked to this deal.</p>
              )}
            </div>
          </div>

          <div className="mt-8 border-t border-border pt-6">
            <h3 className="font-semibold">Tasks</h3>
            <div className="mt-3 space-y-2">
              {selectedDealTasks.map((task) => (
                <div key={task.id} className="rounded-md border border-border p-3 text-sm">
                  <p className="font-medium">{task.title}</p>
                  <p className="text-muted-foreground">{task.status}</p>
                </div>
              ))}
              {!selectedDealTasks.length && <p className="text-sm text-muted-foreground">No tasks linked to this deal.</p>}
            </div>
          </div>

          <div className="mt-8 border-t border-border pt-6">
            <h3 className="font-semibold">Activities</h3>
            <form
              className="mt-3 space-y-3"
              onSubmit={activityForm.handleSubmit(async (values) => {
                await createActivity.mutateAsync(values);
                activityForm.reset({ type: "note", content: "" });
              })}
            >
              <Select {...activityForm.register("type")}>
                <option value="note">Note</option>
                <option value="call">Call</option>
                <option value="meeting">Meeting</option>
                <option value="email">Email</option>
              </Select>
              <Textarea placeholder="Log activity..." {...activityForm.register("content")} />
              <Button disabled={activityForm.formState.isSubmitting}>Log activity</Button>
            </form>
            <div className="mt-4 space-y-2">
              {selectedDealActivities.map((activity) => (
                <div key={activity.id} className="rounded-md border border-border p-3 text-sm">
                  <p className="font-medium capitalize">{activity.type}</p>
                  <p className="text-muted-foreground">{activity.content}</p>
                </div>
              ))}
              {!selectedDealActivities.length && <p className="text-sm text-muted-foreground">No activity yet.</p>}
            </div>
          </div>
        </MotionDiv>
      )}
    </MotionSection>
  );
}
