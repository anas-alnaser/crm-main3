import { useState, type ReactNode } from "react";
import { AlertTriangle } from "lucide-react";

import { Button } from "./ui/button";
import { Input } from "./ui/input";

export type PermanentDeleteConfirm = { password: string; cascadeConfirmed: boolean };

type Props = {
  open: boolean;
  title: string;
  /** The exact confirmation phrase the user must type (e.g. "DELETE LEAD"). */
  phrase: string;
  /** Whether the backend impact check allows deletion. */
  allowed: boolean;
  /** Safe reason shown when deletion is blocked. */
  blockedReason?: string | null;
  /** Rendered impact summary (counts, status, etc.). */
  children?: ReactNode;
  /** When set, an extra "I confirm this is …" checkbox is required. */
  idConfirmLabel?: string;
  /** When set, a cascade-confirmation checkbox is required to proceed. */
  cascadeLabel?: string;
  submitLabel?: string;
  loadingImpact?: boolean;
  error?: string | null;
  submitting?: boolean;
  onCancel: () => void;
  onConfirm: (data: PermanentDeleteConfirm) => void;
};

export function PermanentDeleteDialog({
  open,
  title,
  phrase,
  allowed,
  blockedReason,
  children,
  idConfirmLabel,
  cascadeLabel,
  submitLabel = "Permanently delete",
  loadingImpact = false,
  error,
  submitting = false,
  onCancel,
  onConfirm,
}: Props) {
  const [password, setPassword] = useState("");
  const [typed, setTyped] = useState("");
  const [idConfirmed, setIdConfirmed] = useState(false);
  const [cascadeConfirmed, setCascadeConfirmed] = useState(false);

  if (!open) return null;

  const ready =
    allowed &&
    !loadingImpact &&
    password.length > 0 &&
    typed === phrase &&
    (!idConfirmLabel || idConfirmed) &&
    (!cascadeLabel || cascadeConfirmed) &&
    !submitting;

  const submit = () => {
    if (!ready) return;
    onConfirm({ password, cascadeConfirmed });
    // Never keep the password around after a submit attempt.
    setPassword("");
  };

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/60 p-4" role="dialog" aria-modal="true">
      <div className="w-full max-w-lg rounded-lg border border-red-500/40 bg-card p-5 text-card-foreground shadow-soft">
        <div className="flex items-start gap-3">
          <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-red-500" />
          <div>
            <h2 className="text-lg font-semibold text-red-500">{title}</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              This action is permanent and cannot be undone.
            </p>
          </div>
        </div>

        <div className="mt-4 space-y-3 text-sm">
          {loadingImpact ? (
            <p className="text-muted-foreground">Checking impact…</p>
          ) : (
            children
          )}

          {!allowed && blockedReason ? (
            <div className="rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-amber-600 dark:text-amber-400">
              {blockedReason}
            </div>
          ) : null}

          {allowed && !loadingImpact ? (
            <>
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
                Type <span className="font-mono font-semibold text-red-500">{phrase}</span> to confirm
                <Input
                  className="mt-1"
                  value={typed}
                  onChange={(e) => setTyped(e.target.value)}
                  aria-label={`Type ${phrase} to confirm`}
                />
              </label>

              {idConfirmLabel ? (
                <label className="flex items-start gap-2 text-muted-foreground">
                  <input
                    type="checkbox"
                    className="mt-0.5"
                    checked={idConfirmed}
                    onChange={(e) => setIdConfirmed(e.target.checked)}
                    aria-label={idConfirmLabel}
                  />
                  <span>{idConfirmLabel}</span>
                </label>
              ) : null}

              {cascadeLabel ? (
                <label className="flex items-start gap-2 text-muted-foreground">
                  <input
                    type="checkbox"
                    className="mt-0.5"
                    checked={cascadeConfirmed}
                    onChange={(e) => setCascadeConfirmed(e.target.checked)}
                    aria-label={cascadeLabel}
                  />
                  <span>{cascadeLabel}</span>
                </label>
              ) : null}
            </>
          ) : null}

          {error ? <p className="text-sm text-red-500">{error}</p> : null}
        </div>

        <div className="mt-5 flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={onCancel} disabled={submitting}>
            Cancel
          </Button>
          <Button type="button" variant="danger" onClick={submit} disabled={!ready}>
            {submitting ? "Deleting…" : submitLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}
