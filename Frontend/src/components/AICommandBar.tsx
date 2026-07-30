import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Brain, CheckCircle2, Sparkles, X } from "lucide-react";
import { useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { apiRequest, createEntity } from "../api/client";
import type { AICommandDraft, AICommandResponse, Client, Deal, Meeting, Stage } from "../api/types";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { drawerMotion, MotionDiv } from "./ui/motion";
import { Select } from "./ui/select";
import { Textarea } from "./ui/textarea";
import { useToast } from "../lib/toast";
import { cn } from "../lib/utils";

const moveDraftSchema = z.object({
  deal: z.coerce.number().min(1, "Choose a deal"),
  stage: z.coerce.number().min(1, "Choose a stage"),
});

const meetingDraftSchema = z
  .object({
    title: z.string().min(1, "Title is required"),
    company: z.coerce.number().min(1, "Choose a company"),
    date: z.string().min(1, "Date is required"),
    start_time: z.string().min(1, "Start time is required"),
    end_time: z.string().optional(),
    location: z.string().optional(),
    description: z.string().optional(),
  })
  .refine((values) => !values.end_time || new Date(`${values.date}T${values.end_time}`) > new Date(`${values.date}T${values.start_time}`), {
    message: "End time must be after start time.",
    path: ["end_time"],
  });

type MoveDraftValues = z.infer<typeof moveDraftSchema>;
type MeetingDraftValues = z.infer<typeof meetingDraftSchema>;

const draftText = (draft?: AICommandDraft) => {
  if (!draft) return "";
  return draft.missing?.length ? `Needs confirmation: ${draft.missing.join(", ")}` : "Review before acting.";
};

export function AICommandBar() {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const [command, setCommand] = useState("");
  const [draft, setDraft] = useState<AICommandDraft | null>(null);

  const commandMutation = useMutation({
    mutationFn: (text: string) =>
      apiRequest<AICommandResponse>("/ai/command/", {
        method: "POST",
        body: JSON.stringify({ text }),
      }),
    onSuccess: (response) => {
      if (response.acted) {
        showToast(response.summary || "AI command completed.", "success");
        setCommand("");
        refreshAffectedViews(response.intent);
      } else if (response.draft) {
        setDraft(response.draft);
        showToast("Review the AI draft before acting.", "info");
      }
    },
    onError: (error) => {
      showToast(error instanceof Error ? error.message : "AI command failed.", "error");
    },
  });

  const refreshAffectedViews = (intent?: string) => {
    if (!intent || intent === "move_deal") {
      queryClient.invalidateQueries({ queryKey: ["deals"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard-stats"] });
    }
    if (!intent || intent === "create_meeting") {
      queryClient.invalidateQueries({ queryKey: ["meetings"] });
    }
  };

  return (
    <section className="border-b border-border bg-background/88 px-4 py-3 backdrop-blur lg:px-8">
      <div className="mx-auto flex max-w-[1440px] flex-col gap-3 rounded-lg border border-border bg-card p-3 text-card-foreground shadow-sm md:flex-row md:items-center">
        <div className="flex items-center gap-3">
          <span className="grid h-10 w-10 place-items-center rounded-md bg-primary/10 text-primary">
            <Sparkles className="h-5 w-5" />
          </span>
          <div className="hidden min-w-[180px] md:block">
            <p className="text-sm font-semibold">AI command</p>
            <p className="text-xs text-muted-foreground">Admin actions only</p>
          </div>
        </div>
        <form
          className="flex min-w-0 flex-1 flex-col gap-2 sm:flex-row"
          onSubmit={(event) => {
            event.preventDefault();
            if (command.trim()) commandMutation.mutate(command.trim());
          }}
        >
          <Input
            aria-label="AI command"
            className="min-w-0"
            placeholder={'Try: "Move the Zeidan deal to Negotiation" or "Meeting with Acme next Sunday 2pm about the proposal"'}
            value={command}
            onChange={(event) => setCommand(event.target.value)}
          />
          <Button className="shrink-0" disabled={commandMutation.isPending || !command.trim()} type="submit">
            <Brain className="h-4 w-4" />
            {commandMutation.isPending ? "Thinking..." : "Run"}
          </Button>
        </form>
      </div>
      {draft && <AICommandConfirmDrawer draft={draft} onClose={() => setDraft(null)} onDone={(intent) => { setDraft(null); setCommand(""); refreshAffectedViews(intent); }} />}
    </section>
  );
}

function AICommandConfirmDrawer({
  draft,
  onClose,
  onDone,
}: {
  draft: AICommandDraft;
  onClose: () => void;
  onDone: (intent: string) => void;
}) {
  const intent = draft.intent;
  const intentLabel = intent === "move_deal" ? "Move deal" : intent === "create_meeting" ? "Create meeting" : "Unknown action";

  return (
    <div className="fixed inset-0 z-[80] grid place-items-center bg-black/65 p-4">
      <MotionDiv className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-lg border border-border bg-card p-5 text-card-foreground shadow-soft" {...drawerMotion}>
        <div className="mb-5 flex items-start justify-between gap-4">
          <div>
            <Badge tone="warning">Confirmation required</Badge>
            <h2 className="mt-3 text-xl font-semibold">Review AI command</h2>
            <p className="mt-1 text-sm text-muted-foreground">{draftText(draft)}</p>
          </div>
          <Button aria-label="Close AI confirmation" size="icon" type="button" variant="ghost" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>

        <div className="mb-5 rounded-lg border border-border bg-background p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-sm font-semibold">{intentLabel}</p>
              <p className="mt-1 text-xs text-muted-foreground">Confidence {Math.round(Number(draft.confidence || 0) * 100)}%</p>
            </div>
            {draft.missing?.length > 0 && <Badge tone="warning">{draft.missing.length} field{draft.missing.length === 1 ? "" : "s"} need review</Badge>}
          </div>
          <div className="mt-3 grid gap-2 text-xs text-muted-foreground sm:grid-cols-2">
            {Object.entries(draft.fields || {}).map(([key, value]) => (
              <div key={key} className="rounded-md border border-border bg-card px-3 py-2">
                <span className="font-medium text-foreground">{key.replace(/_/g, " ")}</span>
                <span className="ml-2">{String(value || "empty")}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-lg border border-border bg-background p-4">
          {intent === "move_deal" ? (
            <MoveDealConfirm draft={draft} onDone={onDone} />
          ) : intent === "create_meeting" ? (
            <CreateMeetingConfirm draft={draft} onDone={onDone} />
          ) : (
            <div className="text-sm text-muted-foreground">
              I could not identify a supported action. Try a clearer meeting or move-deal command.
            </div>
          )}
        </div>
        <Button className="mt-4" type="button" variant="outline" onClick={onClose}>Cancel</Button>
      </MotionDiv>
    </div>
  );
}

function MoveDealConfirm({ draft, onDone }: { draft: AICommandDraft; onDone: (intent: string) => void }) {
  const { showToast } = useToast();
  const queryClient = useQueryClient();
  const { data: deals = [], isLoading: dealsLoading } = useQuery({ queryKey: ["deals"], queryFn: () => apiRequest<Deal[]>("/deals/") });
  const { data: stages = [], isLoading: stagesLoading } = useQuery({ queryKey: ["stages"], queryFn: () => apiRequest<Stage[]>("/stages/?ordering=order") });
  const fields = draft.fields || {};
  const missing = new Set(draft.missing || []);
  const guessedDeal = useMemo(() => findDeal(deals, String(fields.deal_identifier || "")), [deals, fields.deal_identifier]);
  const guessedStage = useMemo(() => findStage(stages, String(fields.target_stage || ""), guessedDeal), [stages, fields.target_stage, guessedDeal]);
  const form = useForm<MoveDraftValues>({
    resolver: zodResolver(moveDraftSchema),
    values: {
      deal: guessedDeal?.id ?? 0,
      stage: guessedStage?.id ?? 0,
    },
  });
  const stageOptions = stages;

  const moveMutation = useMutation({
    mutationFn: (values: MoveDraftValues) =>
      apiRequest<Deal>(`/deals/${values.deal}/move/`, {
        method: "PATCH",
        body: JSON.stringify({ stage: values.stage }),
      }),
    onSuccess: (deal) => {
      queryClient.invalidateQueries({ queryKey: ["deals"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard-stats"] });
      showToast(`Moved ${deal.title} to ${deal.stage_name}.`, "success");
      onDone("move_deal");
    },
    onError: () => showToast("Could not move deal.", "error"),
  });

  return (
    <form className="space-y-4" onSubmit={form.handleSubmit((values) => moveMutation.mutate(values))}>
      {dealsLoading || stagesLoading ? (
        <div className="rounded-md border border-border bg-card p-3 text-sm text-muted-foreground">Loading deals and stages...</div>
      ) : null}
      <label className="field-label">
        <span className={cn(missing.has("deal_identifier") || missing.has("deal_identifier_ambiguous") ? "text-primary" : "")}>Deal</span>
        <Select className={cn("mt-2", (missing.has("deal_identifier") || missing.has("deal_identifier_ambiguous")) && "border-primary bg-primary/5")} {...form.register("deal")}>
          <option value={0}>Choose deal</option>
          {deals.map((deal) => <option key={deal.id} value={deal.id}>{deal.title} · {deal.company_name}</option>)}
        </Select>
      </label>
      <label className="field-label">
        <span className={cn(missing.has("target_stage") || missing.has("target_stage_ambiguous") ? "text-primary" : "")}>Stage</span>
        <Select className={cn("mt-2", (missing.has("target_stage") || missing.has("target_stage_ambiguous")) && "border-primary bg-primary/5")} {...form.register("stage")}>
          <option value={0}>Choose stage</option>
          {stageOptions.map((stage) => <option key={stage.id} value={stage.id}>{stage.name}</option>)}
        </Select>
      </label>
      <Button disabled={moveMutation.isPending} type="submit">
        <CheckCircle2 className="h-4 w-4" />
        Confirm move
      </Button>
    </form>
  );
}

function CreateMeetingConfirm({ draft, onDone }: { draft: AICommandDraft; onDone: (intent: string) => void }) {
  const { showToast } = useToast();
  const queryClient = useQueryClient();
  const { data: clients = [], isLoading: clientsLoading } = useQuery({ queryKey: ["clients"], queryFn: () => apiRequest<Client[]>("/clients/") });
  const fields = draft.fields || {};
  const missing = new Set(draft.missing || []);
  const guessedClient = useMemo(() => findClient(clients, String(fields.company_name || "")), [clients, fields.company_name]);
  const form = useForm<MeetingDraftValues>({
    resolver: zodResolver(meetingDraftSchema),
    values: {
      title: String(fields.title || ""),
      company: guessedClient?.id ?? 0,
      date: String(fields.date || ""),
      start_time: String(fields.start_time || ""),
      end_time: String(fields.end_time || ""),
      location: String(fields.location || ""),
      description: String(fields.notes || ""),
    },
  });

  const createMeeting = useMutation({
    mutationFn: (values: MeetingDraftValues) =>
      createEntity<Meeting>("meetings", {
        title: values.title,
        company: values.company,
        deal: null,
        start_datetime: new Date(`${values.date}T${values.start_time}`).toISOString(),
        end_datetime: new Date(`${values.date}T${values.end_time || addOneHour(values.start_time)}`).toISOString(),
        location: values.location ?? "",
        description: values.description ?? "",
        status: "scheduled",
      }),
    onSuccess: (meeting) => {
      queryClient.invalidateQueries({ queryKey: ["meetings"] });
      showToast(`Scheduled ${meeting.title}.`, "success");
      onDone("create_meeting");
    },
    onError: () => showToast("Could not schedule meeting.", "error"),
  });

  return (
    <form className="space-y-4" onSubmit={form.handleSubmit((values) => createMeeting.mutate(values))}>
      {clientsLoading ? (
        <div className="rounded-md border border-border bg-card p-3 text-sm text-muted-foreground">Loading companies...</div>
      ) : null}
      <label className="field-label">
        <span className={cn(missing.has("title") ? "text-primary" : "")}>Title</span>
        <Input className={cn("mt-2", missing.has("title") && "border-primary bg-primary/5")} {...form.register("title")} />
      </label>
      <label className="field-label">
        <span className={cn(missing.has("company_name") || missing.has("company_name_ambiguous") ? "text-primary" : "")}>Company</span>
        <Select className={cn("mt-2", (missing.has("company_name") || missing.has("company_name_ambiguous")) && "border-primary bg-primary/5")} {...form.register("company")}>
          <option value={0}>Choose company</option>
          {clients.map((client) => <option key={client.id} value={client.id}>{client.name}</option>)}
        </Select>
      </label>
      <div className="grid gap-3 md:grid-cols-3">
        <label className="field-label">
          <span className={cn(missing.has("date") || missing.has("date_or_time") ? "text-primary" : "")}>Date</span>
          <Input className={cn("mt-2", (missing.has("date") || missing.has("date_or_time")) && "border-primary bg-primary/5")} type="date" {...form.register("date")} />
        </label>
        <label className="field-label">
          <span className={cn(missing.has("start_time") || missing.has("date_or_time") ? "text-primary" : "")}>Start</span>
          <Input className={cn("mt-2", (missing.has("start_time") || missing.has("date_or_time")) && "border-primary bg-primary/5")} type="time" {...form.register("start_time")} />
        </label>
        <label className="field-label">
          <span className={cn(missing.has("end_time") ? "text-primary" : "")}>End</span>
          <Input className={cn("mt-2", missing.has("end_time") && "border-primary bg-primary/5")} type="time" {...form.register("end_time")} />
        </label>
      </div>
      <label className="field-label">Location<Input className="mt-2" placeholder="Zoom, office, address..." {...form.register("location")} /></label>
      <label className="field-label">Notes<Textarea className="mt-2" {...form.register("description")} /></label>
      <Button disabled={createMeeting.isPending} type="submit">
        <CheckCircle2 className="h-4 w-4" />
        Confirm meeting
      </Button>
    </form>
  );
}

function findDeal(deals: Deal[], identifier: string) {
  const needle = identifier.toLowerCase();
  return deals.find((deal) => deal.title.toLowerCase() === needle) ?? deals.find((deal) => deal.title.toLowerCase().includes(needle) || (deal.company_name || "").toLowerCase().includes(needle));
}

function findStage(stages: Stage[], identifier: string, deal?: Deal) {
  const scopedStages = deal ? stages.filter((stage) => stage.pipeline === deal.pipeline) : stages;
  const needle = identifier.toLowerCase();
  return scopedStages.find((stage) => stage.name.toLowerCase() === needle)
    ?? scopedStages.find((stage) => stage.name.toLowerCase().includes(needle))
    ?? stages.find((stage) => stage.name.toLowerCase() === needle)
    ?? stages.find((stage) => stage.name.toLowerCase().includes(needle));
}

function findClient(clients: Client[], identifier: string) {
  const needle = identifier.toLowerCase();
  return clients.find((client) => client.name.toLowerCase() === needle) ?? clients.find((client) => client.name.toLowerCase().includes(needle));
}

function addOneHour(time: string) {
  const [hours, minutes] = time.split(":").map(Number);
  return `${String((hours + 1) % 24).padStart(2, "0")}:${String(minutes || 0).padStart(2, "0")}`;
}
