import type { ColumnDef } from "@tanstack/react-table";
import { zodResolver } from "@hookform/resolvers/zod";
import { CalendarDays, ChevronLeft, ChevronRight } from "lucide-react";
import { useMemo, useState } from "react";
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
import type { Client, Deal, Project, Task } from "../api/types";

const emptyToNull = (value: unknown) => (value === "" || value === 0 ? null : value);

const schema = z.object({
  title: z.string().min(1, "Title is required"),
  description: z.string().optional(),
  project: z.preprocess(emptyToNull, z.coerce.number().nullable()),
  client: z.preprocess(emptyToNull, z.coerce.number().nullable()),
  deal: z.preprocess(emptyToNull, z.coerce.number().nullable()),
  due_date: z.preprocess((value) => (value === "" ? null : value), z.string().nullable()),
  status: z.enum(["todo", "doing", "done"]),
});

type FormValues = z.infer<typeof schema>;

const defaultValues = {
  title: "",
  description: "",
  project: null,
  client: null,
  deal: null,
  due_date: null,
  status: "todo",
} satisfies FormValues;

const columns: ColumnDef<Task>[] = [
  { accessorKey: "title", header: "Title" },
  { accessorKey: "client_name", header: "Client" },
  { accessorKey: "deal_title", header: "Deal" },
  { accessorKey: "due_date", header: "Due" },
  { accessorKey: "status", header: "Status", cell: ({ row }) => <Badge tone={statusTone(row.original.status)}>{row.original.status}</Badge> },
];

const weekdayLabels = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

const toDateKey = (date: Date) => {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
};

const formatMonth = (date: Date) => new Intl.DateTimeFormat("en-US", { month: "long", year: "numeric" }).format(date);

function TaskCalendar({
  month,
  onMonthChange,
  onSelectDate,
  selectedDate,
  tasks,
}: {
  month: Date;
  onMonthChange: (date: Date) => void;
  onSelectDate: (date: string | null) => void;
  selectedDate: string | null;
  tasks: Task[];
}) {
  const calendarDays = useMemo(() => {
    const firstDay = new Date(month.getFullYear(), month.getMonth(), 1);
    const lastDay = new Date(month.getFullYear(), month.getMonth() + 1, 0);
    const days: Array<Date | null> = Array.from({ length: firstDay.getDay() }, () => null);
    for (let day = 1; day <= lastDay.getDate(); day += 1) {
      days.push(new Date(month.getFullYear(), month.getMonth(), day));
    }
    return days;
  }, [month]);

  const tasksByDate = useMemo(() => {
    return tasks.reduce<Record<string, Task[]>>((acc, task) => {
      if (!task.due_date) return acc;
      acc[task.due_date] = [...(acc[task.due_date] ?? []), task];
      return acc;
    }, {});
  }, [tasks]);

  const selectedTasks = selectedDate ? tasksByDate[selectedDate] ?? [] : [];

  return (
    <section className="surface-card p-5">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <span className="grid h-9 w-9 place-items-center rounded-md bg-primary/10 text-primary">
              <CalendarDays className="h-4 w-4" />
            </span>
            <div>
              <h3 className="font-semibold">Task calendar</h3>
              <p className="text-sm text-muted-foreground">Plan meetings and follow-ups by due date.</p>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button aria-label="Previous month" size="icon" type="button" variant="outline" onClick={() => onMonthChange(new Date(month.getFullYear(), month.getMonth() - 1, 1))}>
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <div className="w-36 text-center text-sm font-semibold">{formatMonth(month)}</div>
          <Button aria-label="Next month" size="icon" type="button" variant="outline" onClick={() => onMonthChange(new Date(month.getFullYear(), month.getMonth() + 1, 1))}>
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-7 gap-2 text-center text-xs font-semibold uppercase tracking-[0.08em] text-muted-foreground">
        {weekdayLabels.map((day) => <div key={day}>{day}</div>)}
      </div>
      <div className="mt-2 grid grid-cols-7 gap-2">
        {calendarDays.map((day, index) => {
          if (!day) return <div key={`blank-${index}`} className="min-h-20 rounded-md border border-transparent" />;
          const dateKey = toDateKey(day);
          const dayTasks = tasksByDate[dateKey] ?? [];
          const isSelected = selectedDate === dateKey;
          const isToday = dateKey === toDateKey(new Date());

          return (
            <button
              key={dateKey}
              className={`min-h-20 rounded-md border p-2 text-left transition hover:border-primary/50 hover:bg-primary/5 ${
                isSelected ? "border-primary bg-primary/10" : "border-border bg-background"
              }`}
              type="button"
              onClick={() => onSelectDate(isSelected ? null : dateKey)}
            >
              <div className="flex items-center justify-between gap-2">
                <span className={`text-sm font-semibold tabular-nums ${isToday ? "text-primary" : "text-foreground"}`}>{day.getDate()}</span>
                {dayTasks.length > 0 && <span className="rounded-full bg-primary px-1.5 py-0.5 text-[10px] font-semibold text-primary-foreground">{dayTasks.length}</span>}
              </div>
              <div className="mt-2 space-y-1">
                {dayTasks.slice(0, 2).map((task) => (
                  <div key={task.id} className="truncate rounded-sm bg-muted px-1.5 py-1 text-[11px] text-muted-foreground">
                    {task.title}
                  </div>
                ))}
              </div>
            </button>
          );
        })}
      </div>

      {selectedDate && (
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-md border border-border bg-background px-3 py-2 text-sm">
          <span className="text-muted-foreground">
            {selectedTasks.length} task{selectedTasks.length === 1 ? "" : "s"} on <span className="font-medium text-foreground">{selectedDate}</span>
          </span>
          <Button size="sm" type="button" variant="ghost" onClick={() => onSelectDate(null)}>Clear date</Button>
        </div>
      )}
    </section>
  );
}

export function TasksPage() {
  const [editing, setEditing] = useState<Task | null>(null);
  const [calendarMonth, setCalendarMonth] = useState(() => new Date());
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const { data = [], isLoading, createMutation, updateMutation, deleteMutation } = useCrud<Task>("tasks");
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

  const edit = (task: Task) => {
    setEditing(task);
    form.reset(task);
  };

  const visibleTasks = selectedDate ? data.filter((task) => task.due_date === selectedDate) : data;

  return (
    <MotionSection className="page-shell" {...pageMotion}>
      <PageHeader title="Tasks" subtitle="Coordinate day-to-day work across companies, deals, and projects." />
      <div className="grid gap-6 xl:grid-cols-[400px_1fr]">
        <form onSubmit={submit} className="form-panel">
          <h3 className="mb-1 text-lg font-semibold">{editing ? "Edit task" : "Create task"}</h3>
          <p className="mb-5 text-sm text-muted-foreground">Add work items with clear ownership context.</p>
          <div className="space-y-4">
            <label className="field-label">Title<Input className="mt-2" placeholder="Follow up on proposal" {...form.register("title")} />{form.formState.errors.title && <p className="field-hint text-primary">{form.formState.errors.title.message}</p>}</label>
            <label className="field-label">Description<Textarea className="mt-2" placeholder="What needs to happen?" {...form.register("description")} /></label>
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
            <label className="field-label">Due date<Input className="mt-2" type="date" {...form.register("due_date")} /></label>
            <label className="field-label">
              Status
              <Select className="mt-2" {...form.register("status")}>
                <option value="todo">Todo</option><option value="doing">Doing</option><option value="done">Done</option>
              </Select>
            </label>
            <div className="flex gap-2">
              <Button disabled={form.formState.isSubmitting}>{editing ? "Save" : "Create"}</Button>
              {editing && <Button type="button" variant="outline" onClick={() => { setEditing(null); form.reset(defaultValues); }}>Cancel</Button>}
            </div>
          </div>
        </form>
        <div className="min-w-0 space-y-6">
          <TaskCalendar
            month={calendarMonth}
            onMonthChange={setCalendarMonth}
            onSelectDate={setSelectedDate}
            selectedDate={selectedDate}
            tasks={data}
          />
          {isLoading ? <TableSkeleton /> : <EntityTable columns={columns} data={visibleTasks} onEdit={edit} onDelete={deleteMutation.mutate} />}
        </div>
      </div>
    </MotionSection>
  );
}
