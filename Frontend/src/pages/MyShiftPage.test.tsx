import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi, type Mock } from "vitest";

import { MyShiftPage } from "./MyShiftPage";
import { ToastProvider } from "../lib/toast";
import { apiRequest } from "../api/client";
import { useAuth } from "../lib/auth";
import { usePresence } from "../lib/presence";
import type { ShiftStatus } from "../api/types";

vi.mock("../api/client", () => ({ apiRequest: vi.fn() }));
vi.mock("../lib/auth", () => ({ useAuth: vi.fn() }));
vi.mock("../lib/presence", () => ({ usePresence: vi.fn() }));

const mockedApi = apiRequest as unknown as Mock;
const mockedAuth = useAuth as unknown as Mock;
const mockedPresence = usePresence as unknown as Mock;

function baseTotals() {
  return {
    date: "2026-07-31", credited_seconds: 3600, credited_display: "1h", target_seconds: 10800, target_display: "3h",
    remaining_seconds: 7200, remaining_display: "2h", overtime_seconds: 0, overtime_display: "0m", session_count: 1,
  };
}

function setup(status: Partial<ShiftStatus>, refresh = vi.fn()) {
  mockedAuth.mockReturnValue({ user: { username: "rep", first_name: "Rep", role: "sales" } });
  mockedPresence.mockReturnValue({
    status: { shift_tracking_required: true, on_shift: false, server_time: "2026-07-31T12:00:00Z", local_time: "2026-07-31T15:00:00Z", today: "2026-07-31", reason: "ok", can_start: true, totals: baseTotals(), ...status },
    refresh,
    isLoading: false,
  });
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <MyShiftPage />
      </ToastProvider>
    </QueryClientProvider>,
  );
}

describe("MyShiftPage", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows Start Shift when off shift and able to start", () => {
    setup({ on_shift: false, can_start: true });
    expect(screen.getByRole("button", { name: /start shift/i })).toBeEnabled();
    expect(screen.getByText(/off shift/i)).toBeInTheDocument();
  });

  it("disables Start Shift when outside the window", () => {
    setup({ on_shift: false, can_start: false, reason: "too_early" });
    expect(screen.getByRole("button", { name: /start shift/i })).toBeDisabled();
    expect(screen.getByText(/window has not opened/i)).toBeInTheDocument();
  });

  it("shows End Shift when on shift and loads a preview", async () => {
    mockedApi.mockResolvedValue({
      employee_name: "Rep", message: "Hi Rep, you have worked for 1h today. Are you sure?",
      current_session_seconds: 1800, current_session_display: "30m", credited_seconds_today: 3600,
      credited_display_today: "1h", target_display: "3h", remaining_display: "2h", overtime_display: "0m", session_count: 1,
    });
    setup({ on_shift: true, session: { id: 1, started_at: "2026-07-31T14:30:00Z", last_activity_at: "2026-07-31T15:00:00Z", work_date: "2026-07-31", current_session_seconds: 1800, current_session_display: "30m" } });
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /end shift/i }));
    await waitFor(() => expect(screen.getByText(/are you sure/i)).toBeInTheDocument());
    expect(screen.getByRole("button", { name: /confirm end shift/i })).toBeInTheDocument();
  });

  it("shows a message when shift tracking is not required", () => {
    setup({ shift_tracking_required: false });
    expect(screen.getByText(/not required/i)).toBeInTheDocument();
  });

  it("surfaces an automatic inactivity closure notice", () => {
    setup({ last_auto_closure: { reason: "inactivity", reason_display: "Closed by inactivity", ended_at: "2026-07-31T14:10:00Z" } });
    expect(screen.getByText(/closed automatically/i)).toBeInTheDocument();
  });
});
