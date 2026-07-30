import { useMutation, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { AlertTriangle, Ban, Brain, CheckCircle2, HelpCircle, RotateCcw, ShieldAlert, Sparkles, X } from "lucide-react";
import { useState } from "react";

import { apiRequest } from "../api/client";
import type { AICommandResponse, AICommandUndoResponse } from "../api/types";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { drawerMotion, MotionDiv } from "./ui/motion";
import { useToast } from "../lib/toast";

// Central mapping from AI intent to the TanStack Query keys it affects.
// invalidateQueries does prefix matching, so ["deals"] refreshes ["deals", ...].
const INTENT_QUERY_KEYS: Record<string, string[][]> = {
  create_company: [["clients"], ["workspace-search"]],
  edit_company_details: [["clients"], ["workspace-search"]],
  create_deal: [["deals"], ["dashboard-stats"], ["commission"], ["leaderboard"], ["workspace-search"]],
  move_deal: [["deals"], ["dashboard-stats"], ["commission"], ["leaderboard"], ["workspace-search"]],
  update_deal_value: [["deals"], ["dashboard-stats"], ["commission"], ["leaderboard"], ["workspace-search"]],
  update_deal_close_date: [["deals"], ["workspace-search"]],
  reassign_deal_owner: [["deals"], ["leaderboard"], ["commission"], ["workspace-search"]],
  create_task: [["tasks"], ["workspace-search"]],
  update_task: [["tasks"], ["workspace-search"]],
  schedule_followup: [["tasks"], ["workspace-search"]],
  create_meeting: [["meetings"], ["workspace-search"]],
  edit_meeting: [["meetings"], ["workspace-search"]],
  log_activity: [["activities"], ["workspace-search"]],
  add_note: [["activities"], ["workspace-search"]],
};

const ALL_KEYS: string[][] = [
  ["deals"], ["clients"], ["tasks"], ["activities"], ["meetings"],
  ["dashboard-stats"], ["commission"], ["leaderboard"], ["workspace-search"],
];

function invalidateForIntent(queryClient: QueryClient, intent?: string | null) {
  const keys = (intent && INTENT_QUERY_KEYS[intent]) || ALL_KEYS;
  keys.forEach((queryKey) => queryClient.invalidateQueries({ queryKey }));
}

function parseApiError(error: unknown): { detail: string; code?: string } {
  const fallback = { detail: error instanceof Error ? error.message : "Something went wrong." };
  if (!(error instanceof Error)) return fallback;
  try {
    const parsed = JSON.parse(error.message) as { detail?: string; code?: string; error?: string };
    return { detail: parsed.detail || parsed.error || error.message, code: parsed.code };
  } catch {
    return fallback;
  }
}

type UndoInfo = { actionId: number; summary: string; intent?: string | null };

export function AICommandBar() {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const [command, setCommand] = useState("");
  const [panel, setPanel] = useState<AICommandResponse | null>(null);
  const [undoInfo, setUndoInfo] = useState<UndoInfo | null>(null);

  const applyActed = (response: AICommandResponse) => {
    invalidateForIntent(queryClient, response.intent);
    showToast(response.summary || "AI command completed.", "success");
    setCommand("");
    setPanel(null);
    if (response.undoable && response.action_id) {
      setUndoInfo({ actionId: response.action_id, summary: response.summary || "Action completed.", intent: response.intent });
    } else {
      setUndoInfo(null);
    }
  };

  const commandMutation = useMutation({
    mutationFn: (text: string) =>
      apiRequest<AICommandResponse>("/ai/command/", { method: "POST", body: JSON.stringify({ text }) }),
    onSuccess: (response) => {
      if (response.acted) {
        applyActed(response);
      } else if (response.requires_confirmation) {
        setPanel(response);
      } else if (response.blocked) {
        setPanel(response);
        showToast(response.refusal || response.summary || "That command is blocked.", "error");
      } else if (response.requires_disambiguation || response.needs_review) {
        setPanel(response);
      } else {
        setPanel(response);
      }
    },
    onError: (error) => {
      const { detail, code } = parseApiError(error);
      if (code === "ai_unconfigured") {
        showToast("AI is not configured. Set ANTHROPIC_API_KEY on the backend.", "error");
      } else if (code === "ai_unavailable") {
        showToast("The AI command service is disabled.", "error");
      } else if (code === "provider_error") {
        showToast("The AI provider could not interpret that. Try rephrasing.", "error");
      } else {
        showToast(detail, "error");
      }
    },
  });

  const confirmMutation = useMutation({
    mutationFn: (confirmationId: string) =>
      apiRequest<AICommandResponse>("/ai/command/confirm/", { method: "POST", body: JSON.stringify({ confirmation_id: confirmationId }) }),
    onSuccess: (response) => applyActed(response),
    onError: (error) => {
      const { detail, code } = parseApiError(error);
      const messages: Record<string, string> = {
        expired: "This confirmation expired. Re-issue the command.",
        already_used: "This action was already confirmed.",
        cancelled: "This confirmation was cancelled.",
        cannot_apply: "The record changed and the action can no longer be applied.",
      };
      showToast(code ? messages[code] || detail : detail, "error");
      setPanel(null);
    },
  });

  const cancelMutation = useMutation({
    mutationFn: (confirmationId: string) =>
      apiRequest<{ cancelled: boolean }>("/ai/command/cancel/", { method: "POST", body: JSON.stringify({ confirmation_id: confirmationId }) }),
    onSettled: () => {
      showToast("Cancelled.", "info");
      setPanel(null);
    },
  });

  const undoMutation = useMutation({
    mutationFn: (actionId: number) =>
      apiRequest<AICommandUndoResponse>("/ai/command/undo/", { method: "POST", body: JSON.stringify({ action_id: actionId }) }),
    onSuccess: (response, actionId) => {
      const intent = undoInfo?.actionId === actionId ? undoInfo?.intent : null;
      invalidateForIntent(queryClient, intent);
      showToast(response.summary || "Action undone.", "success");
      setUndoInfo(null);
    },
    onError: (error) => {
      const { detail } = parseApiError(error);
      showToast(detail, "error");
      setUndoInfo(null);
    },
  });

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
            placeholder={'Try: "Move the Zeidan deal to Negotiation" or "Set the Acme deal value to 5000"'}
            value={command}
            onChange={(event) => setCommand(event.target.value)}
          />
          <Button className="shrink-0" disabled={commandMutation.isPending || !command.trim()} type="submit">
            <Brain className="h-4 w-4" />
            {commandMutation.isPending ? "Thinking..." : "Run"}
          </Button>
        </form>
      </div>

      {undoInfo && (
        <div className="mx-auto mt-2 flex max-w-[1440px] items-center justify-between gap-3 rounded-lg border border-primary/30 bg-primary/5 px-4 py-2 text-sm">
          <span className="flex items-center gap-2 text-foreground">
            <CheckCircle2 className="h-4 w-4 text-primary" />
            {undoInfo.summary}
          </span>
          <div className="flex items-center gap-2">
            <Button className="h-8 px-3" disabled={undoMutation.isPending} type="button" variant="outline" onClick={() => undoMutation.mutate(undoInfo.actionId)}>
              <RotateCcw className="h-3.5 w-3.5" />
              {undoMutation.isPending ? "Undoing..." : "Undo"}
            </Button>
            <Button aria-label="Dismiss" className="h-8 px-2" size="icon" type="button" variant="ghost" onClick={() => setUndoInfo(null)}>
              <X className="h-4 w-4" />
            </Button>
          </div>
        </div>
      )}

      {panel && (
        <AICommandPanel
          response={panel}
          isConfirming={confirmMutation.isPending}
          onConfirm={() => panel.confirmation_id && confirmMutation.mutate(panel.confirmation_id)}
          onCancel={() => {
            if (panel.confirmation_id) cancelMutation.mutate(panel.confirmation_id);
            else setPanel(null);
          }}
          onClose={() => setPanel(null)}
        />
      )}
    </section>
  );
}

function fieldRows(response: AICommandResponse) {
  const preview = response.preview || {};
  const rows: Array<{ field: string; old: string; new: string }> = [];
  if (preview.field) {
    rows.push({ field: preview.field, old: preview.old ?? "", new: preview.new ?? "" });
  }
  if (preview.changes) {
    Object.entries(preview.changes).forEach(([field, change]) => rows.push({ field, old: change.old, new: change.new }));
  }
  return rows;
}

function AICommandPanel({
  response,
  isConfirming,
  onConfirm,
  onCancel,
  onClose,
}: {
  response: AICommandResponse;
  isConfirming: boolean;
  onConfirm: () => void;
  onCancel: () => void;
  onClose: () => void;
}) {
  const isConfirmation = Boolean(response.requires_confirmation);
  const isBlocked = Boolean(response.blocked);
  const isDisambiguation = Boolean(response.requires_disambiguation);
  const rows = fieldRows(response);

  const header = isConfirmation
    ? { tone: "warning" as const, icon: ShieldAlert, label: "Confirmation required", title: "Confirm this change" }
    : isBlocked
      ? { tone: "danger" as const, icon: Ban, label: "Blocked", title: "This action is not allowed" }
      : isDisambiguation
        ? { tone: "warning" as const, icon: HelpCircle, label: "Needs clarification", title: "Which record did you mean?" }
        : { tone: "warning" as const, icon: AlertTriangle, label: "Needs review", title: "More detail required" };

  return (
    <div className="fixed inset-0 z-[80] grid place-items-center bg-black/65 p-4" role="dialog" aria-modal="true">
      <MotionDiv className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-lg border border-border bg-card p-5 text-card-foreground shadow-soft" {...drawerMotion}>
        <div className="mb-5 flex items-start justify-between gap-4">
          <div>
            <Badge tone={header.tone}>
              <header.icon className="mr-1 h-3 w-3" />
              {header.label}
            </Badge>
            <h2 className="mt-3 text-xl font-semibold">{header.title}</h2>
            <p className="mt-1 text-sm text-muted-foreground">{response.summary || response.reason || response.refusal || "Review the details below."}</p>
          </div>
          <Button aria-label="Close" size="icon" type="button" variant="ghost" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>

        {isConfirmation && (
          <div className="mb-4 rounded-lg border border-amber-500/40 bg-amber-500/5 p-4 text-sm">
            <p className="flex items-center gap-2 font-medium text-foreground">
              <AlertTriangle className="h-4 w-4 text-amber-500" />
              This will modify stored data.
            </p>
            {response.preview?.record && <p className="mt-2 text-muted-foreground">Record: <span className="font-medium text-foreground">{response.preview.record}</span></p>}
            {response.confirmation_expires_at && (
              <p className="mt-1 text-xs text-muted-foreground">Confirmation expires at {new Date(response.confirmation_expires_at).toLocaleTimeString()}.</p>
            )}
          </div>
        )}

        {rows.length > 0 && (
          <div className="mb-4 overflow-hidden rounded-lg border border-border">
            <table className="w-full text-sm">
              <thead className="bg-muted/50 text-left text-xs uppercase tracking-wide text-muted-foreground">
                <tr>
                  <th className="px-3 py-2">Field</th>
                  <th className="px-3 py-2">Current</th>
                  <th className="px-3 py-2">Proposed</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.field} className="border-t border-border">
                    <td className="px-3 py-2 font-medium capitalize">{row.field.replace(/_/g, " ")}</td>
                    <td className="px-3 py-2 text-muted-foreground">{row.old || "empty"}</td>
                    <td className="px-3 py-2 text-primary">{row.new || "empty"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {response.missing && response.missing.length > 0 && (
          <div className="mb-4 rounded-lg border border-border bg-background p-4 text-sm">
            <p className="font-medium">Still needed</p>
            <ul className="mt-2 list-disc pl-5 text-muted-foreground">
              {response.missing.map((item) => (
                <li key={item}>{item.replace(/_/g, " ")}</li>
              ))}
            </ul>
          </div>
        )}

        {response.options && Object.keys(response.options).length > 0 && (
          <div className="mb-4 space-y-3">
            {Object.entries(response.options).map(([field, options]) => (
              <div key={field} className="rounded-lg border border-border bg-background p-4 text-sm">
                <p className="font-medium capitalize">{field.replace(/_/g, " ")} — possible matches</p>
                <ul className="mt-2 space-y-1 text-muted-foreground">
                  {options.map((option) => (
                    <li key={option.id}>• {option.label}</li>
                  ))}
                </ul>
                <p className="mt-2 text-xs text-muted-foreground">Re-issue the command with a more specific name to continue.</p>
              </div>
            ))}
          </div>
        )}

        <div className="mt-4 flex gap-2">
          {isConfirmation ? (
            <>
              <Button disabled={isConfirming} type="button" onClick={onConfirm}>
                <CheckCircle2 className="h-4 w-4" />
                {isConfirming ? "Applying..." : "Confirm"}
              </Button>
              <Button type="button" variant="outline" onClick={onCancel}>Cancel</Button>
            </>
          ) : (
            <Button type="button" variant="outline" onClick={onClose}>Close</Button>
          )}
        </div>
      </MotionDiv>
    </div>
  );
}
