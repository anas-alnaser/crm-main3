import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi, type Mock } from "vitest";

import { LeadsPage } from "./LeadsPage";
import { ToastProvider } from "../lib/toast";
import { apiRequest, fetchList, sendTelemetry } from "../api/client";
import { useAuth } from "../lib/auth";
import type { Lead } from "../api/types";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return {
    fetchList: vi.fn(),
    apiRequest: vi.fn(),
    uploadForm: vi.fn(),
    sendTelemetry: vi.fn(),
    // Keep the real error parser so error-surfacing behaviour is exercised.
    apiErrorMessage: actual.apiErrorMessage,
  };
});
vi.mock("../lib/auth", () => ({ useAuth: vi.fn() }));

const mockedList = fetchList as unknown as Mock;
const mockedRequest = apiRequest as unknown as Mock;
const mockedAuth = useAuth as unknown as Mock;

const SUPERADMIN = { id: 1, username: "owner", role: "admin", is_staff: true, is_superuser: true, is_active: true };
const NORMAL_ADMIN = { id: 2, username: "admin", role: "admin", is_staff: true, is_superuser: false, is_active: true };
const SALES = { id: 3, username: "rep", role: "sales", is_staff: false, is_superuser: false, is_active: true };

function makeLead(overrides: Partial<Lead>): Lead {
  return {
    id: 1, batch: null, name: "Alice", original_phone: "0790000001", normalized_phone: "+962790000001", source: "",
    notes: "", assigned_to: 2, assigned_to_name: "Rep", status: "new", status_display: "New", is_terminal: false,
    follow_up_at: null, first_viewed_at: null, converted_client: null, converted_deal: null, converted_at: null,
    reopened_reason: "", contact_attempt_count: 0, created_at: "2026-07-31T00:00:00Z", ...overrides,
  };
}

type TestUser = { id: number; username: string; role: string; is_staff: boolean; is_superuser: boolean; is_active: boolean };

function setup(userOrRole: "admin" | "sales" | TestUser, leads: Lead[]) {
  const user = typeof userOrRole === "string" ? (userOrRole === "admin" ? NORMAL_ADMIN : SALES) : userOrRole;
  mockedAuth.mockReturnValue({ user });
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

describe("LeadsPage permanent delete", () => {
  afterEach(() => vi.restoreAllMocks());

  const impact = (overrides = {}) => ({
    lead_id: 1, name: "Alice", status: "new", status_display: "New", is_converted: false,
    contact_attempt_count: 2, deletion_allowed: true, blocked_reason: null, confirmation_phrase: "DELETE LEAD",
    ...overrides,
  });

  it("hides Delete permanently from sales", async () => {
    setup("sales", [makeLead({})]);
    await screen.findByRole("button", { name: /open/i });
    expect(screen.queryByRole("button", { name: /delete permanently/i })).not.toBeInTheDocument();
  });

  it("hides Delete permanently from a normal admin", async () => {
    setup("admin", [makeLead({})]);
    await screen.findByRole("button", { name: /open/i });
    expect(screen.queryByRole("button", { name: /delete permanently/i })).not.toBeInTheDocument();
  });

  it("shows Delete permanently for a superadmin", async () => {
    setup(SUPERADMIN, [makeLead({})]);
    expect(await screen.findByRole("button", { name: /delete permanently/i })).toBeInTheDocument();
  });

  it("renders the delete impact and requires password + phrase + id confirmation", async () => {
    mockedRequest.mockResolvedValue(impact());
    setup(SUPERADMIN, [makeLead({})]);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /delete permanently alice/i }));

    // Impact fetched and rendered.
    await waitFor(() => expect(mockedRequest).toHaveBeenCalledWith("/leads/1/delete-impact/"));
    expect(await screen.findByText(/contact attempts:/i)).toBeInTheDocument();

    const submit = screen.getByRole("button", { name: /permanently delete lead/i });
    expect(submit).toBeDisabled();

    await user.type(screen.getByLabelText(/current password/i), "pw123456");
    await user.type(screen.getByLabelText(/type delete lead/i), "DELETE LEAD");
    expect(submit).toBeDisabled(); // id confirmation still required
    await user.click(screen.getByLabelText(/i confirm this is lead #1/i));
    expect(submit).toBeEnabled();
  });

  it("blocks deletion of a converted lead", async () => {
    mockedRequest.mockResolvedValue(
      impact({ is_converted: true, deletion_allowed: false, blocked_reason: "Converted leads cannot be permanently deleted because they are linked to business records." }),
    );
    setup(SUPERADMIN, [makeLead({ status: "converted", status_display: "Converted" })]);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /delete permanently alice/i }));
    expect(await screen.findByText(/converted leads cannot be permanently deleted/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/current password/i)).not.toBeInTheDocument();
  });

  it("sends the correct request body and surfaces backend errors", async () => {
    mockedRequest.mockImplementation((path: string) => {
      if (path.endsWith("/delete-impact/")) return Promise.resolve(impact());
      return Promise.reject(new Error(JSON.stringify({ detail: "Incorrect password.", code: "incorrect_password" })));
    });
    setup(SUPERADMIN, [makeLead({})]);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /delete permanently alice/i }));
    await screen.findByText(/contact attempts:/i);
    await user.type(screen.getByLabelText(/current password/i), "wrongpw123");
    await user.type(screen.getByLabelText(/type delete lead/i), "DELETE LEAD");
    await user.click(screen.getByLabelText(/i confirm this is lead #1/i));
    await user.click(screen.getByRole("button", { name: /permanently delete lead/i }));

    await waitFor(() =>
      expect(mockedRequest).toHaveBeenCalledWith(
        "/leads/1/permanent-delete/",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({ current_password: "wrongpw123", confirmation: "DELETE LEAD", lead_id: 1 }),
        }),
      ),
    );
    // Backend error is shown (dialog + toast); success is NOT claimed.
    expect((await screen.findAllByText("Incorrect password.")).length).toBeGreaterThan(0);
  });
});
