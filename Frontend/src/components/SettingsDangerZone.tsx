import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { apiErrorMessage, apiRequest } from "../api/client";
import type { ResetPreview } from "../api/types";
import { useAuth } from "../lib/auth";
import { isSuperAdmin } from "../lib/superadmin";
import { useToast } from "../lib/toast";
import { Button } from "./ui/button";
import { Input } from "./ui/input";

const PHRASE = "DELETE ALL CRM DATA";

/**
 * Settings → Danger Zone: permanently reset all CRM business data and every
 * other user, preserving only the current superadmin. Rendered only for a
 * superadmin; the server re-enforces every check regardless.
 */
export function SettingsDangerZone() {
  const { user, refreshUser } = useAuth();
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const navigate = useNavigate();

  const [preview, setPreview] = useState<ResetPreview | null>(null);
  const [password, setPassword] = useState("");
  const [typed, setTyped] = useState("");
  const [acknowledged, setAcknowledged] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const resetLocalState = () => {
    setPassword("");
    setTyped("");
    setAcknowledged(false);
  };

  const previewMutation = useMutation({
    mutationFn: () => apiRequest<ResetPreview>("/admin/data-reset/preview/"),
    onSuccess: (data) => {
      setPreview(data);
      setError(null);
    },
    onError: (err) => {
      setError(apiErrorMessage(err, "Could not load the reset preview."));
      showToast(apiErrorMessage(err, "Could not load the reset preview."), "error");
    },
  });

  const executeMutation = useMutation({
    mutationFn: () =>
      apiRequest<{ detail: string }>("/admin/data-reset/execute/", {
        method: "POST",
        body: JSON.stringify({
          current_password: password,
          confirmation: PHRASE,
          preserved_user_id: preview?.preserved_user.id,
          preview_token: preview?.preview_token,
        }),
      }),
    onSuccess: async () => {
      // Never keep the password around.
      resetLocalState();
      setPreview(null);
      // Clear all cached business data, keep the session, refetch the user.
      queryClient.clear();
      try {
        await refreshUser();
      } catch {
        /* keep the user logged in; /auth/me is best-effort here */
      }
      showToast("CRM data reset completed. Your account was preserved.", "success");
      navigate("/");
    },
    onError: (err) => {
      // Show the real backend error; do NOT claim success. Clear the password
      // but keep the user logged in unless auth genuinely failed.
      setPassword("");
      setError(apiErrorMessage(err, "Could not reset CRM data."));
      showToast(apiErrorMessage(err, "Could not reset CRM data."), "error");
    },
  });

  // Gate on the exact superadmin definition (after all hooks, to satisfy the
  // rules of hooks). Never a security boundary on its own — the server re-checks.
  if (!isSuperAdmin(user)) return null;

  const canExecute =
    Boolean(preview) &&
    password.length > 0 &&
    typed === PHRASE &&
    acknowledged &&
    Boolean(preview?.preview_token) &&
    !executeMutation.isPending;

  return (
    <section className="surface-card border-red-500/40 p-5 lg:col-span-2">
      <div className="flex items-start gap-3">
        <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-red-500" />
        <div>
          <h2 className="text-lg font-semibold text-red-500">Danger Zone</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Permanently delete all CRM business data and all other users while preserving your
            currently logged-in superadmin account. This cannot be undone.
          </p>
        </div>
      </div>

      {/* Step 1 — Preview */}
      <div className="mt-4">
        <Button
          type="button"
          variant="outline"
          onClick={() => previewMutation.mutate()}
          disabled={previewMutation.isPending}
        >
          {previewMutation.isPending ? "Loading preview…" : "Preview full reset"}
        </Button>
      </div>

      {preview && (
        <div className="mt-4 space-y-4">
          <div className="rounded-md border border-border bg-muted/40 p-3 text-sm">
            <p>
              <span className="text-muted-foreground">Preserved account:</span>{" "}
              <span className="font-medium">{preview.preserved_user.username}</span> ({preview.preserved_user.email})
            </p>
            <p><span className="text-muted-foreground">Other users to delete:</span> {preview.other_users_to_delete}</p>
            <p><span className="text-muted-foreground">Total rows to delete:</span> {preview.total_rows}</p>
            <p className="mt-1 text-muted-foreground">Records by type:</p>
            <ul className="mt-1 grid grid-cols-2 gap-x-4 sm:grid-cols-3">
              {Object.entries(preview.counts).map(([label, count]) => (
                <li key={label}>
                  {label.replace(/_/g, " ")}: <span className="tabular-nums">{count}</span>
                </li>
              ))}
            </ul>
            <p className="mt-2 text-muted-foreground">
              Preserved / reseeded: {preview.preserved_config.brands.join(", ") || "brand structure"}
            </p>
            <p className="mt-1 text-xs text-muted-foreground">
              Preview expires {new Date(preview.preview_expires_at).toLocaleTimeString()}
            </p>
          </div>

          {/* Step 2 — Confirmation */}
          <label className="field-label">
            Current password
            <Input
              className="mt-1"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              aria-label="Current password"
            />
          </label>

          <label className="field-label">
            Type <span className="font-mono font-semibold text-red-500">{PHRASE}</span> to confirm
            <Input
              className="mt-1"
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              aria-label={`Type ${PHRASE} to confirm`}
            />
          </label>

          <label className="flex items-start gap-2 text-sm text-muted-foreground">
            <input
              type="checkbox"
              className="mt-0.5"
              checked={acknowledged}
              onChange={(e) => setAcknowledged(e.target.checked)}
              aria-label="I understand that this permanently deletes CRM data and cannot be undone."
            />
            <span>I understand that this permanently deletes CRM data and cannot be undone.</span>
          </label>

          {error && <p className="text-sm text-red-500">{error}</p>}

          <Button
            type="button"
            variant="danger"
            onClick={() => {
              setError(null);
              executeMutation.mutate();
            }}
            disabled={!canExecute}
          >
            {executeMutation.isPending ? "Resetting…" : "Permanently reset CRM"}
          </Button>
        </div>
      )}
    </section>
  );
}
