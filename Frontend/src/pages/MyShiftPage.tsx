import { useMutation } from "@tanstack/react-query";
import { AlarmClock, Clock, LogIn, LogOut, Timer, TriangleAlert } from "lucide-react";
import { useState } from "react";

import { PageHeader } from "../components/PageHeader";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Skeleton } from "../components/ui/skeleton";
import { apiRequest } from "../api/client";
import type { ShiftEndPreview } from "../api/types";
import { useAuth } from "../lib/auth";
import { usePresence } from "../lib/presence";
import { useToast } from "../lib/toast";

const REASON_LABEL: Record<string, string> = {
  too_early: "Your shift window has not opened yet.",
  too_late: "Your shift window has closed for today.",
  disallowed_day: "Today is not a working day for your policy.",
  not_required: "Shift tracking is not required for your account.",
  active: "You are currently on shift.",
  ok: "You can start your shift now.",
};

export function MyShiftPage() {
  const { user } = useAuth();
  const { status, refresh, isLoading } = usePresence();
  const { showToast } = useToast();
  const [preview, setPreview] = useState<ShiftEndPreview | null>(null);

  const startMutation = useMutation({
    mutationFn: () => apiRequest("/workforce/shift/start/", { method: "POST", body: "{}" }),
    onSuccess: async () => {
      showToast("Shift started.", "success");
      await refresh();
    },
    onError: (error: Error) => showToast(parseError(error) ?? "Could not start shift.", "error"),
  });

  const previewMutation = useMutation({
    mutationFn: () => apiRequest<ShiftEndPreview>("/workforce/shift/end/preview/"),
    onSuccess: (data) => setPreview(data),
    onError: (error: Error) => showToast(parseError(error) ?? "Could not load shift summary.", "error"),
  });

  const endMutation = useMutation({
    mutationFn: () => apiRequest("/workforce/shift/end/", { method: "POST", body: "{}" }),
    onSuccess: async () => {
      setPreview(null);
      showToast("Shift ended. You remain logged in.", "success");
      await refresh();
    },
    onError: (error: Error) => showToast(parseError(error) ?? "Could not end shift.", "error"),
  });

  if (isLoading && !status) {
    return (
      <div className="space-y-6">
        <PageHeader title="My Shift" subtitle="Track your working sessions." />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  if (!status?.shift_tracking_required) {
    return (
      <div className="space-y-6">
        <PageHeader title="My Shift" subtitle="Track your working sessions." />
        <div className="surface-card p-6 text-sm text-muted-foreground">
          Shift tracking is not required for your account. You can use the CRM normally.
        </div>
      </div>
    );
  }

  const onShift = status.on_shift;
  const totals = status.totals;

  return (
    <div className="space-y-6">
      <PageHeader
        title="My Shift"
        subtitle={`Local time ${new Date(status.local_time).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })} · ${status.policy?.timezone ?? "Asia/Amman"}`}
        actions={
          onShift ? (
            <Button variant="danger" onClick={() => previewMutation.mutate()} disabled={previewMutation.isPending}>
              <LogOut className="h-4 w-4" /> End Shift
            </Button>
          ) : (
            <Button onClick={() => startMutation.mutate()} disabled={!status.can_start || startMutation.isPending}>
              <LogIn className="h-4 w-4" /> Start Shift
            </Button>
          )
        }
      />

      <div className="surface-card p-6">
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <span className={`grid h-11 w-11 place-items-center rounded-full ${onShift ? "bg-emerald-500/15 text-emerald-500" : "bg-muted text-muted-foreground"}`}>
              <Clock className="h-5 w-5" />
            </span>
            <div>
              <p className="text-lg font-semibold">{onShift ? "On shift" : "Off shift"}</p>
              <p className="text-sm text-muted-foreground">{REASON_LABEL[status.reason] ?? ""}</p>
            </div>
          </div>
          <Badge tone={onShift ? "success" : "neutral"}>{onShift ? "Active" : "Inactive"}</Badge>
        </div>

        {status.window && (
          <p className="mt-4 text-sm text-muted-foreground">
            Allowed working window: <span className="font-medium text-foreground">{status.window.start_time}</span> – <span className="font-medium text-foreground">{status.window.end_time}</span>
            {!status.window.is_working_day && " (not a working day today)"}
          </p>
        )}
      </div>

      {status.last_auto_closure && (
        <div className="surface-card flex items-start gap-3 border-amber-500/30 bg-amber-500/5 p-4">
          <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0 text-amber-500" />
          <div className="text-sm">
            <p className="font-medium text-foreground">Your last session was closed automatically.</p>
            <p className="text-muted-foreground">
              {status.last_auto_closure.reason_display} at {new Date(status.last_auto_closure.ended_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}. You are still logged in and can start a new shift within the working window.
            </p>
          </div>
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard icon={Timer} label="Credited today" value={totals.credited_display} />
        <StatCard icon={AlarmClock} label="Daily target" value={totals.target_display} />
        <StatCard icon={Clock} label="Remaining" value={totals.remaining_display} />
        <StatCard icon={Timer} label="Overtime" value={totals.overtime_display} tone={totals.overtime_seconds > 0 ? "success" : "neutral"} />
      </div>

      {onShift && status.session && (
        <div className="surface-card p-6">
          <p className="text-sm text-muted-foreground">Current session</p>
          <p className="mt-1 text-2xl font-semibold tabular-nums">{status.session.current_session_display}</p>
          <p className="mt-1 text-xs text-muted-foreground">
            Started at {new Date(status.session.started_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}. Sessions today: {totals.session_count}.
          </p>
        </div>
      )}

      {preview && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4" role="dialog" aria-modal="true">
          <div className="surface-card w-full max-w-md p-6">
            <h2 className="text-lg font-semibold">End work session</h2>
            <p className="mt-2 text-sm text-muted-foreground">{preview.message}</p>
            <dl className="mt-4 space-y-1 text-sm">
              <Row label="This session" value={preview.current_session_display} />
              <Row label="Credited today" value={preview.credited_display_today} />
              <Row label="Overtime" value={preview.overtime_display} />
            </dl>
            <div className="mt-6 flex justify-end gap-2">
              <Button variant="outline" onClick={() => setPreview(null)}>Cancel</Button>
              <Button variant="danger" onClick={() => endMutation.mutate()} disabled={endMutation.isPending}>
                Confirm end shift
              </Button>
            </div>
          </div>
        </div>
      )}
      <p className="text-xs text-muted-foreground">Signed in as {user?.first_name || user?.username}. Ending a shift keeps you logged in.</p>
    </div>
  );
}

function StatCard({ icon: Icon, label, value, tone = "neutral" }: { icon: typeof Clock; label: string; value: string; tone?: "neutral" | "success" }) {
  return (
    <div className="surface-card p-4">
      <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
        <Icon className="h-4 w-4" /> {label}
      </div>
      <p className={`mt-2 text-2xl font-semibold tabular-nums ${tone === "success" ? "text-emerald-500" : ""}`}>{value}</p>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="font-medium tabular-nums">{value}</dd>
    </div>
  );
}

function parseError(error: Error): string | null {
  try {
    const parsed = JSON.parse(error.message);
    return parsed.detail ?? null;
  } catch {
    return null;
  }
}
