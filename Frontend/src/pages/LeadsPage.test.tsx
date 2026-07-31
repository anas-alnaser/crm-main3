import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi, type Mock } from "vitest";

import { LeadsPage } from "./LeadsPage";
import { ToastProvider } from "../lib/toast";
import { fetchList, sendTelemetry } from "../api/client";
import { useAuth } from "../lib/auth";
import type { Lead } from "../api/types";

vi.mock("../api/client", () => ({
  fetchList: vi.fn(),
  apiRequest: vi.fn(),
  uploadForm: vi.fn(),
  sendTelemetry: vi.fn(),
}));
vi.mock("../lib/auth", () => ({ useAuth: vi.fn() }));

const mockedList = fetchList as unknown as Mock;
const mockedAuth = useAuth as unknown as Mock;

function makeLead(overrides: Partial<Lead>): Lead {
  return {
    id: 1, batch: null, name: "Alice", original_phone: "0790000001", normalized_phone: "+962790000001", source: "",
    notes: "", assigned_to: 2, assigned_to_name: "Rep", status: "new", status_display: "New", is_terminal: false,
    follow_up_at: null, first_viewed_at: null, converted_client: null, converted_deal: null, converted_at: null,
    reopened_reason: "", contact_attempt_count: 0, created_at: "2026-07-31T00:00:00Z", ...overrides,
  };
}

function setup(role: "admin" | "sales", leads: Lead[]) {
  mockedAuth.mockReturnValue({ user: { username: "u", role } });
  mockedList.mockResolvedValue(leads);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <LeadsPage />
      </ToastProvider>
    </QueryClientProvider>,
  );
}

describe("LeadsPage", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows the upload control for admins only", async () => {
    setup("admin", []);
    await waitFor(() => expect(screen.getByRole("button", { name: /upload .xlsx/i })).toBeInTheDocument());
  });

  it("hides the upload control from sales", async () => {
    setup("sales", []);
    await waitFor(() => expect(screen.getByText(/your assigned leads/i)).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: /upload .xlsx/i })).not.toBeInTheDocument();
  });

  it("renders not-interested leads in red", async () => {
    setup("sales", [makeLead({ status: "not_interested", status_display: "Not interested" })]);
    const nameCell = await screen.findByText("Alice");
    expect(nameCell.className).toContain("text-red-500");
  });

  it("sends telemetry when opening a lead", async () => {
    setup("sales", [makeLead({})]);
    const openButton = await screen.findByRole("button", { name: /open/i });
    openButton.click();
    await waitFor(() => expect(sendTelemetry).toHaveBeenCalledWith("lead.opened", expect.objectContaining({ entity_id: "1" })));
  });
});
