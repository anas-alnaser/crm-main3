import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarClock, ChevronLeft, ChevronRight, Clock3, MapPin, Plus, Trash2, UserRound, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { useSearchParams } from "react-router-dom";
import { z } from "zod";

import { apiRequest, createEntity, deleteEntity, fetchList, patchEntity, updateEntity } from "../api/client";
import type { Client, Deal, Meeting, User } from "../api/types";
import { PageHeader } from "../components/PageHeader";
import { Badge, statusTone } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { EmptyState } from "../components/ui/empty-state";
import { Input } from "../components/ui/input";
import { drawerMotion, MotionDiv, MotionSection, pageMotion } from "../components/ui/motion";
import { Select } from "../components/ui/select";
import { Skeleton } from "../components/ui/skeleton";
import { Textarea } from "../components/ui/textarea";
import { useAuth } from "../lib/auth";
import { useToast } from "../lib/toast";
import { cn } from "../lib/utils";

const emptyToNull = (value: unknown) => (value === "" ? null : value);

const meetingSchema = z
  .object({
    title: z.string().min(1, "Title is required"),
    date: z.string().min(1, "Date is required"),
    start_time: z.string().min(1, "Start time is required"),
    end_time: z.string().min(1, "End time is required"),
    location: z.string().optional(),
    deal: z.preprocess(emptyToNull, z.coerce.number().nullable()),
    company: z.preprocess(emptyToNull, z.coerce.number().nullable()),
    owner: z.coerce.number().optional(),
    status: z.enum(["scheduled", "completed", "cancelled"]),
    description: z.string().optional(),
  })
  .refine((values) => new Date(`${values.date}T${values.end_time}`) > new Date(`${values.date}T${values.start_time}`), {
    message: "End time must be after start time.",
    path: ["end_time"],
  });

type MeetingFormValues = z.infer<typeof meetingSchema>;
type ScheduleView = "week" | "agenda";
type ScheduleScope = "mine" | "all";

const dayFormatter = new Intl.DateTimeFormat("en-US", { weekday: "short", month: "short", day: "numeric" });
const timeFormatter = new Intl.DateTimeFormat("en-US", { hour: "numeric", minute: "2-digit" });

function startOfWeek(date: Date) {
  const next = new Date(date);
  const day = (next.getDay() + 1) % 7;
  next.setHours(0, 0, 0, 0);
  next.setDate(next.getDate() - day);
  return next;
}

function addDays(date: Date, days: number) {
  const next = new Date(date);
  next.setDate(next.getDate() + days);
  return next;
}

function toDateInputValue(date: Date) {
  return date.toISOString().slice(0, 10);
}

function toTimeInputValue(date: Date) {
  return date.toTimeString().slice(0, 5);
}

function formatMeetingTime(meeting: Meeting) {
  return `${timeFormatter.format(new Date(meeting.start_datetime))} - ${timeFormatter.format(new Date(meeting.end_datetime))}`;
}

function isSameDay(first: Date, second: Date) {
  return first.getFullYear() === second.getFullYear() && first.getMonth() === second.getMonth() && first.getDate() === second.getDate();
}

export function SchedulePage() {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const { user } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const isAdmin = user?.role === "admin";
  const [view, setView] = useState<ScheduleView>("week");
  const [scope, setScope] = useState<ScheduleScope>("mine");
  const [weekStart, setWeekStart] = useState(() => startOfWeek(new Date()));
  const [editingMeeting, setEditingMeeting] = useState<Meeting | null | "new">(null);
  const [selectedMeeting, setSelectedMeeting] = useState<Meeting | null>(null);
  const prefillDealId = searchParams.get("deal") ? Number(searchParams.get("deal")) : null;

  const weekDays = useMemo(() => Array.from({ length: 7 }, (_item, index) => addDays(weekStart, index)), [weekStart]);
  const rangeStart = weekDays[0];
  const rangeEnd = addDays(weekDays[6], 1);
  const activeScope = isAdmin ? scope : "mine";

  const meetingsQuery = useQuery({
    queryKey: ["meetings", activeScope, rangeStart.toISOString(), rangeEnd.toISOString()],
    queryFn: () =>
      fetchList<Meeting>(
        `/meetings/?scope=${activeScope}&from=${encodeURIComponent(rangeStart.toISOString())}&to=${encodeURIComponent(rangeEnd.toISOString())}&ordering=start_datetime`,
      ),
  });
  const { data: clients = [] } = useQuery({
    queryKey: ["clients"],
    queryFn: () => fetchList<Client>("/clients/"),
  });
  const { data: deals = [] } = useQuery({
    queryKey: ["deals", isAdmin ? "all" : "visible"],
    queryFn: () => fetchList<Deal>("/deals/"),
  });
  const { data: users = [] } = useQuery({
    queryKey: ["users"],
    queryFn: () => fetchList<User>("/users/"),
    enabled: isAdmin,
  });

  const meetings = meetingsQuery.data ?? [];
  const ownerOptions = isAdmin ? users : user ? [user] : [];

  useEffect(() => {
    if (prefillDealId) setEditingMeeting("new");
  }, [prefillDealId]);

  const invalidateMeetings = () => {
    queryClient.invalidateQueries({ queryKey: ["meetings"] });
  };

  const createMeeting = useMutation({
    mutationFn: (values: MeetingFormValues) => createEntity<Meeting>("meetings", toMeetingPayload(values, deals, user)),
    onSuccess: () => {
      invalidateMeetings();
      setEditingMeeting(null);
      if (prefillDealId) setSearchParams({});
      showToast("Meeting scheduled.", "success");
    },
    onError: () => showToast("Could not schedule meeting.", "error"),
  });

  const updateMeeting = useMutation({
    mutationFn: ({ id, values }: { id: number; values: MeetingFormValues }) => updateEntity<Meeting>("meetings", id, toMeetingPayload(values, deals, user)),
    onSuccess: (meeting) => {
      invalidateMeetings();
      setEditingMeeting(null);
      setSelectedMeeting(meeting);
      showToast("Meeting updated.", "success");
    },
    onError: () => showToast("Could not update meeting.", "error"),
  });

  const patchMeeting = useMutation({
    mutationFn: ({ id, status }: { id: number; status: Meeting["status"] }) => patchEntity<Meeting>("meetings", id, { status }),
    onSuccess: (meeting) => {
      invalidateMeetings();
      setSelectedMeeting(meeting);
      showToast("Meeting status updated.", "success");
    },
    onError: () => showToast("Could not update meeting status.", "error"),
  });

  const deleteMeeting = useMutation({
    mutationFn: (id: number) => deleteEntity("meetings", id),
    onSuccess: () => {
      invalidateMeetings();
      setSelectedMeeting(null);
      showToast("Meeting deleted.", "success");
    },
    onError: () => showToast("Could not delete meeting.", "error"),
  });

  return (
    <MotionSection className="page-shell" {...pageMotion}>
      <PageHeader
        title="Schedule"
        subtitle={isAdmin ? "Read the team's meetings and plan the week ahead." : "Keep your calls, meetings, and follow-ups in one clear calendar."}
        actions={
          <>
            {isAdmin && (
              <Select className="w-[148px]" value={scope} onChange={(event) => setScope(event.target.value as ScheduleScope)}>
                <option value="mine">My meetings</option>
                <option value="all">Whole team</option>
              </Select>
            )}
            <Select className="w-[124px]" value={view} onChange={(event) => setView(event.target.value as ScheduleView)}>
              <option value="week">Week</option>
              <option value="agenda">Agenda</option>
            </Select>
            <Button onClick={() => setEditingMeeting("new")}>
              <Plus className="h-4 w-4" />
              Add Meeting
            </Button>
          </>
        }
      />

      <div className="surface-card p-4">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-sm font-semibold">
              {dayFormatter.format(rangeStart)} - {dayFormatter.format(weekDays[6])}
            </p>
            <p className="text-xs text-muted-foreground">{isAdmin && activeScope === "all" ? "Whole team schedule" : "Your meeting schedule"}</p>
          </div>
          <div className="flex items-center gap-2">
            <Button aria-label="Previous week" size="icon" type="button" variant="outline" onClick={() => setWeekStart(addDays(weekStart, -7))}>
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <Button type="button" variant="outline" onClick={() => setWeekStart(startOfWeek(new Date()))}>
              This week
            </Button>
            <Button aria-label="Next week" size="icon" type="button" variant="outline" onClick={() => setWeekStart(addDays(weekStart, 7))}>
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>

        {meetingsQuery.isLoading ? (
          <div className="grid gap-3 md:grid-cols-7">
            {weekDays.map((day) => <Skeleton key={day.toISOString()} className="h-56" />)}
          </div>
        ) : meetingsQuery.isError ? (
          <div className="rounded-lg border border-border bg-background p-6 text-sm text-muted-foreground">Could not load meetings. Check the backend terminal and try again.</div>
        ) : meetings.length === 0 ? (
          <EmptyState icon={CalendarClock} title="No meetings scheduled" message="Add your first meeting to keep calls, demos, and follow-ups organized." actionLabel="Add Meeting" onAction={() => setEditingMeeting("new")} />
        ) : view === "week" ? (
          <WeekView days={weekDays} meetings={meetings} showOwner={isAdmin && activeScope === "all"} onSelect={setSelectedMeeting} />
        ) : (
          <AgendaView meetings={meetings} showOwner={isAdmin && activeScope === "all"} onSelect={setSelectedMeeting} />
        )}
      </div>

      {selectedMeeting && (
        <MeetingDetailDrawer
          meeting={selectedMeeting}
          showOwner={isAdmin && activeScope === "all"}
          onClose={() => setSelectedMeeting(null)}
          onDelete={() => {
            if (window.confirm("Delete this meeting?")) deleteMeeting.mutate(selectedMeeting.id);
          }}
          onEdit={() => setEditingMeeting(selectedMeeting)}
          onStatusChange={(status) => patchMeeting.mutate({ id: selectedMeeting.id, status })}
        />
      )}

      {editingMeeting && (
        <MeetingFormDrawer
          clients={clients}
          deals={deals}
          meeting={editingMeeting === "new" ? null : editingMeeting}
          ownerOptions={ownerOptions}
          prefillDealId={editingMeeting === "new" ? prefillDealId : null}
          onClose={() => {
            setEditingMeeting(null);
            if (prefillDealId) setSearchParams({});
          }}
          onSubmit={(values) =>
            editingMeeting === "new"
              ? createMeeting.mutateAsync(values)
              : updateMeeting.mutateAsync({ id: editingMeeting.id, values })
          }
        />
      )}
    </MotionSection>
  );
}

function toMeetingPayload(values: MeetingFormValues, deals: Deal[], user?: User | null) {
  const selectedDeal = values.deal ? deals.find((deal) => deal.id === values.deal) : undefined;
  return {
    title: values.title,
    description: values.description ?? "",
    start_datetime: new Date(`${values.date}T${values.start_time}`).toISOString(),
    end_datetime: new Date(`${values.date}T${values.end_time}`).toISOString(),
    location: values.location ?? "",
    deal: values.deal,
    company: values.company ?? selectedDeal?.company ?? null,
    owner: values.owner ?? user?.id,
    status: values.status,
  };
}

function WeekView({ days, meetings, onSelect, showOwner }: { days: Date[]; meetings: Meeting[]; onSelect: (meeting: Meeting) => void; showOwner: boolean }) {
  return (
    <div className="grid gap-3 md:grid-cols-7">
      {days.map((day) => {
        const dayMeetings = meetings.filter((meeting) => isSameDay(new Date(meeting.start_datetime), day));
        return (
          <section key={day.toISOString()} className={cn("min-h-64 rounded-lg border border-border bg-background p-3", isSameDay(day, new Date()) && "border-primary/50 bg-primary/5")}>
            <div className="mb-3">
              <p className="text-sm font-semibold">{dayFormatter.format(day)}</p>
              <p className="text-xs text-muted-foreground">{dayMeetings.length} meeting{dayMeetings.length === 1 ? "" : "s"}</p>
            </div>
            <div className="space-y-2">
              {dayMeetings.map((meeting) => (
                <MeetingCard key={meeting.id} meeting={meeting} showOwner={showOwner} onClick={() => onSelect(meeting)} />
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
}

function AgendaView({ meetings, onSelect, showOwner }: { meetings: Meeting[]; onSelect: (meeting: Meeting) => void; showOwner: boolean }) {
  return (
    <div className="space-y-3">
      {meetings.map((meeting) => (
        <MeetingCard key={meeting.id} meeting={meeting} showOwner={showOwner} wide onClick={() => onSelect(meeting)} />
      ))}
    </div>
  );
}

function MeetingCard({ meeting, onClick, showOwner, wide }: { meeting: Meeting; onClick: () => void; showOwner: boolean; wide?: boolean }) {
  return (
    <button className={cn("w-full rounded-lg border border-border bg-card p-3 text-left text-sm shadow-sm transition hover:-translate-y-0.5 hover:border-primary/50 hover:shadow-soft", wide && "flex items-start justify-between gap-4")} type="button" onClick={onClick}>
      <div className="min-w-0">
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <Badge tone={statusTone(meeting.status)}>{meeting.status}</Badge>
          {showOwner && <Badge>{meeting.owner_name || meeting.owner_username}</Badge>}
        </div>
        <p className="font-semibold leading-snug">{meeting.title}</p>
        <p className="mt-1 text-xs text-muted-foreground">{meeting.company_name || meeting.deal_title || "Standalone meeting"}</p>
      </div>
      <div className={cn("mt-3 space-y-1 text-xs text-muted-foreground", wide && "mt-0 shrink-0 text-right")}>
        <span className="flex items-center gap-1">
          <Clock3 className="h-3 w-3" />
          {formatMeetingTime(meeting)}
        </span>
        {meeting.location && (
          <span className="flex items-center gap-1">
            <MapPin className="h-3 w-3" />
            {meeting.location}
          </span>
        )}
      </div>
    </button>
  );
}

function MeetingDetailDrawer({
  meeting,
  onClose,
  onDelete,
  onEdit,
  onStatusChange,
  showOwner,
}: {
  meeting: Meeting;
  onClose: () => void;
  onDelete: () => void;
  onEdit: () => void;
  onStatusChange: (status: Meeting["status"]) => void;
  showOwner: boolean;
}) {
  return (
    <MotionDiv className="fixed inset-y-0 right-0 z-40 w-full max-w-lg overflow-y-auto border-l border-border bg-card p-5 text-card-foreground shadow-soft" {...drawerMotion}>
      <div className="mb-5 flex items-start justify-between gap-4">
        <div>
          <Badge tone={statusTone(meeting.status)}>{meeting.status}</Badge>
          <h2 className="mt-3 text-xl font-semibold">{meeting.title}</h2>
          <p className="mt-1 text-sm text-muted-foreground">{meeting.company_name || meeting.deal_title || "Standalone meeting"}</p>
        </div>
        <Button aria-label="Close meeting details" size="icon" type="button" variant="ghost" onClick={onClose}>
          <X className="h-4 w-4" />
        </Button>
      </div>

      <div className="space-y-3 rounded-lg border border-border bg-background p-4 text-sm">
        <p className="flex items-center gap-2 text-muted-foreground"><Clock3 className="h-4 w-4 text-primary" />{dayFormatter.format(new Date(meeting.start_datetime))}, {formatMeetingTime(meeting)}</p>
        {meeting.location && <p className="flex items-center gap-2 text-muted-foreground"><MapPin className="h-4 w-4 text-primary" />{meeting.location}</p>}
        {showOwner && <p className="flex items-center gap-2 text-muted-foreground"><UserRound className="h-4 w-4 text-primary" />{meeting.owner_name || meeting.owner_username}</p>}
      </div>

      {meeting.description && (
        <div className="mt-5 rounded-lg border border-border bg-background p-4">
          <h3 className="text-sm font-semibold">Notes</h3>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">{meeting.description}</p>
        </div>
      )}

      <div className="mt-6 flex flex-wrap gap-2">
        <Button type="button" onClick={onEdit}>Edit</Button>
        {meeting.status !== "completed" && <Button type="button" variant="outline" onClick={() => onStatusChange("completed")}>Mark completed</Button>}
        {meeting.status !== "cancelled" && <Button type="button" variant="outline" onClick={() => onStatusChange("cancelled")}>Cancel meeting</Button>}
        <Button type="button" variant="danger" onClick={onDelete}>
          <Trash2 className="h-4 w-4" />
          Delete
        </Button>
      </div>
    </MotionDiv>
  );
}

function MeetingFormDrawer({
  clients,
  deals,
  meeting,
  onClose,
  onSubmit,
  ownerOptions,
  prefillDealId,
}: {
  clients: Client[];
  deals: Deal[];
  meeting: Meeting | null;
  onClose: () => void;
  onSubmit: (values: MeetingFormValues) => Promise<unknown>;
  ownerOptions: User[];
  prefillDealId?: number | null;
}) {
  const start = meeting ? new Date(meeting.start_datetime) : new Date(Date.now() + 60 * 60 * 1000);
  const end = meeting ? new Date(meeting.end_datetime) : new Date(start.getTime() + 60 * 60 * 1000);
  const prefillDeal = prefillDealId ? deals.find((deal) => deal.id === prefillDealId) : undefined;
  const form = useForm<MeetingFormValues>({
    resolver: zodResolver(meetingSchema),
    defaultValues: {
      title: meeting?.title ?? "",
      date: toDateInputValue(start),
      start_time: toTimeInputValue(start),
      end_time: toTimeInputValue(end),
      location: meeting?.location ?? "",
      deal: meeting?.deal ?? prefillDeal?.id ?? null,
      company: meeting?.company ?? prefillDeal?.company ?? null,
      owner: meeting?.owner ?? ownerOptions[0]?.id,
      status: meeting?.status ?? "scheduled",
      description: meeting?.description ?? "",
    },
  });

  const selectedDealId = form.watch("deal");
  const selectedDeal = selectedDealId ? deals.find((deal) => deal.id === Number(selectedDealId)) : undefined;

  useEffect(() => {
    if (!meeting && prefillDeal) {
      form.setValue("deal", prefillDeal.id);
      form.setValue("company", prefillDeal.company);
    }
  }, [form, meeting, prefillDeal]);

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/50">
      <MotionDiv className="h-full w-full max-w-xl overflow-y-auto border-l border-border bg-card p-5 text-card-foreground shadow-soft" {...drawerMotion}>
        <div className="mb-5 flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold">{meeting ? "Edit meeting" : "Schedule meeting"}</h2>
            <p className="text-sm text-muted-foreground">Plan the date, owner, and client context.</p>
          </div>
          <Button aria-label="Close meeting form" size="icon" type="button" variant="ghost" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>

        <form className="space-y-4" onSubmit={form.handleSubmit(onSubmit)}>
          <label className="field-label">Title<Input className="mt-2" placeholder="Discovery call" {...form.register("title")} /></label>
          {form.formState.errors.title && <p className="text-xs text-red-500">{form.formState.errors.title.message}</p>}

          <div className="grid gap-3 md:grid-cols-3">
            <label className="field-label">Date<Input className="mt-2" type="date" {...form.register("date")} /></label>
            <label className="field-label">Start<Input className="mt-2" type="time" {...form.register("start_time")} /></label>
            <label className="field-label">End<Input className="mt-2" type="time" {...form.register("end_time")} /></label>
          </div>
          {form.formState.errors.end_time && <p className="text-xs text-red-500">{form.formState.errors.end_time.message}</p>}

          <label className="field-label">Location<Input className="mt-2" placeholder="Zoom, office, or address" {...form.register("location")} /></label>

          <label className="field-label">
            Deal
            <Select className="mt-2" {...form.register("deal")}>
              <option value="">No deal</option>
              {deals.map((deal) => <option key={deal.id} value={deal.id}>{deal.title}</option>)}
            </Select>
          </label>

          <label className="field-label">
            Company
            <Select className="mt-2" {...form.register("company")}>
              <option value="">No company</option>
              {clients.map((client) => <option key={client.id} value={client.id}>{client.name}</option>)}
            </Select>
          </label>
          {selectedDeal && <p className="text-xs text-muted-foreground">Selected deal is linked to {selectedDeal.company_name}. If company is blank, it will be filled automatically.</p>}

          {ownerOptions.length > 1 && (
            <label className="field-label">
              Owner
              <Select className="mt-2" {...form.register("owner")}>
                {ownerOptions.map((owner) => <option key={owner.id} value={owner.id}>{owner.first_name || owner.username}</option>)}
              </Select>
            </label>
          )}

          <label className="field-label">
            Status
            <Select className="mt-2" {...form.register("status")}>
              <option value="scheduled">Scheduled</option>
              <option value="completed">Completed</option>
              <option value="cancelled">Cancelled</option>
            </Select>
          </label>

          <label className="field-label">Notes<Textarea className="mt-2" placeholder="Agenda, prep notes, or next steps..." {...form.register("description")} /></label>

          <div className="flex gap-2 pt-2">
            <Button disabled={form.formState.isSubmitting}>{meeting ? "Save meeting" : "Schedule meeting"}</Button>
            <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
          </div>
        </form>
      </MotionDiv>
    </div>
  );
}
