import { createContext, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { apiRequest } from "../api/client";
import type { ShiftStatus } from "../api/types";
import { useAuth } from "./auth";

/**
 * Presence detection for shift tracking.
 *
 * Listens for genuine interaction events and, at most once every ~30s while the
 * user has actually interacted, sends a heartbeat so the server can keep the
 * work session alive. It records NOTHING about the interaction — not the key,
 * not the text, not the coordinates — only that the browser was active.
 *
 * Multiple tabs coordinate through a BroadcastChannel so a single heartbeat is
 * sent per interval across all tabs (no double counting).
 */

const HEARTBEAT_INTERVAL_MS = 30_000;
const ACTIVITY_EVENTS = ["keydown", "mousedown", "pointerdown", "touchstart", "wheel"] as const;

type PresenceContextValue = {
  status: ShiftStatus | null;
  refresh: () => Promise<void>;
  isLoading: boolean;
};

const PresenceContext = createContext<PresenceContextValue | undefined>(undefined);

async function fetchStatus(): Promise<ShiftStatus> {
  return apiRequest<ShiftStatus>("/workforce/shift/status/");
}

async function sendHeartbeat(): Promise<void> {
  await apiRequest("/workforce/shift/heartbeat/", { method: "POST", body: "{}" });
}

export function PresenceProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const [status, setStatus] = useState<ShiftStatus | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const interactedRef = useRef(false);
  const channelRef = useRef<BroadcastChannel | null>(null);

  const refresh = useMemo(
    () => async () => {
      if (!user) return;
      setIsLoading(true);
      try {
        setStatus(await fetchStatus());
      } catch {
        /* leave last-known status; the shift page shows an error state */
      } finally {
        setIsLoading(false);
      }
    },
    [user],
  );

  // Track genuine interaction (content-free).
  useEffect(() => {
    if (!user) return;
    const markInteracted = () => {
      interactedRef.current = true;
    };
    ACTIVITY_EVENTS.forEach((event) => window.addEventListener(event, markInteracted, { passive: true }));
    return () => ACTIVITY_EVENTS.forEach((event) => window.removeEventListener(event, markInteracted));
  }, [user]);

  // Coordinate heartbeats across tabs.
  useEffect(() => {
    if (!user || typeof BroadcastChannel === "undefined") return;
    const channel = new BroadcastChannel("crm-presence");
    channelRef.current = channel;
    channel.onmessage = (event) => {
      if (event.data?.type === "shift-changed") {
        void refresh();
      }
    };
    return () => {
      channel.close();
      channelRef.current = null;
    };
  }, [user, refresh]);

  // Heartbeat loop.
  useEffect(() => {
    if (!user) {
      setStatus(null);
      return;
    }
    void refresh();
    let cancelled = false;
    // Only one tab (the visible one, or any tab when hidden) sends per tick;
    // interacted flag prevents heartbeats for a truly idle browser.
    const timer = window.setInterval(async () => {
      if (cancelled) return;
      if (!interactedRef.current) return;
      if (document.visibilityState === "hidden") return;
      interactedRef.current = false;
      try {
        await sendHeartbeat();
      } catch {
        /* offline / stale token: the interval will retry next tick */
      }
    }, HEARTBEAT_INTERVAL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [user, refresh]);

  const value = useMemo<PresenceContextValue>(
    () => ({
      status,
      isLoading,
      refresh: async () => {
        await refresh();
        channelRef.current?.postMessage({ type: "shift-changed" });
      },
    }),
    [status, isLoading, refresh],
  );

  return <PresenceContext.Provider value={value}>{children}</PresenceContext.Provider>;
}

export function usePresence() {
  const context = useContext(PresenceContext);
  if (!context) {
    throw new Error("usePresence must be used within PresenceProvider");
  }
  return context;
}
