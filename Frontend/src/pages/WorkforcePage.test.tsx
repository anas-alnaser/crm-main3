import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi, type Mock } from "vitest";

import { WorkforcePage } from "./WorkforcePage";
import { apiRequest, fetchList } from "../api/client";

vi.mock("../api/client", () => ({ apiRequest: vi.fn(), fetchList: vi.fn() }));

const mockedApi = apiRequest as unknown as Mock;
const mockedList = fetchList as unknown as Mock;

function dashboard() {
  return {
    employee: { id: 2, username: "rep", name: "Rep" },
    period: { start: "2026-07-01", end: "2026-07-31" },
    work: { credited_display: "12h", expected_display: "60h", overtime_display: "0m", target_completion_percent: 20, session_count: 6, inactivity_closures: 3, window_closures: 1, days_worked: 4, expected_workdays: 22, observations: ["Rep had 3 inactivity closures during this period."] },
    leads: { assigned: 10, contacted: 6, contact_attempts: 15, interested: 2, not_interested: 1, converted: 3, conversion_rate: 30, overdue_follow_ups: 1 },
    crm: { companies_created: 1, tasks_created: 2, activities_logged: 4, meetings_created: 1, deals_created: 2, deals_moved: 5, deals_won: 1 },
    salary: { configured: true, basic_salary: "150.00", currency: "JOD", overtime_allowed: true, note: "Informational only. No payroll deduction formula is applied." },
    daily: [{ date: "2026-07-31", expected_display: "3h", credited_display: "2h", session_count: 2, inactivity_closures: 1, leads_contacted: 3, leads_converted: 1, deals_won: 0 }],
  };
}

function setup() {
  mockedList.mockResolvedValue([{ id: 2, username: "rep", first_name: "Rep", role: "sales" }]);
  mockedApi.mockResolvedValue(dashboard());
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <WorkforcePage />
    </QueryClientProvider>,
  );
}

describe("WorkforcePage", () => {
  afterEach(() => vi.restoreAllMocks());

  it("prompts to select an employee first", async () => {
    setup();
    expect(await screen.findByText(/choose an employee with a work policy/i)).toBeInTheDocument();
  });

  it("loads metrics after selecting an employee", async () => {
    setup();
    const user = userEvent.setup();
    await waitFor(() => expect(screen.getByRole("option", { name: "Rep" })).toBeInTheDocument());
    await user.selectOptions(screen.getByLabelText(/select employee/i), "2");
    await waitFor(() => expect(screen.getByText("12h")).toBeInTheDocument());
    // Inactivity observation surfaced.
    expect(screen.getByText(/3 inactivity closures/i)).toBeInTheDocument();
    // Lead + CRM metrics present.
    expect(screen.getByText("Conversion rate")).toBeInTheDocument();
    expect(screen.getByText("Deals moved")).toBeInTheDocument();
  });
});
