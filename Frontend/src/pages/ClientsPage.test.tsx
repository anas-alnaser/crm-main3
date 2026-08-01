import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi, type Mock } from "vitest";

import { ClientsPage } from "./ClientsPage";
import { ToastProvider } from "../lib/toast";
import { apiRequest, listEntities } from "../api/client";
import { useAuth } from "../lib/auth";
import type { Client } from "../api/types";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return {
    listEntities: vi.fn(),
    fetchList: vi.fn().mockResolvedValue([]),
    apiRequest: vi.fn(),
    createEntity: vi.fn(),
    updateEntity: vi.fn(),
    deleteEntity: vi.fn(),
    apiErrorMessage: actual.apiErrorMessage,
  };
});
vi.mock("../lib/auth", () => ({ useAuth: vi.fn() }));

const mockedListEntities = listEntities as unknown as Mock;
const mockedRequest = apiRequest as unknown as Mock;
const mockedAuth = useAuth as unknown as Mock;

const SUPERADMIN = { id: 1, username: "owner", role: "admin", is_staff: true, is_superuser: true, is_active: true };
const NORMAL_ADMIN = { ...SUPERADMIN, is_superuser: false };

const company: Client = {
  id: 5, name: "Acme", contact_person: "", email: "", phone: "", country: "", status: "active",
  notes: "", created_by: 1, is_archived: false, archived_at: null, created_at: "2026-07-31T00:00:00Z",
};

function setup(user: object) {
  mockedAuth.mockReturnValue({ user });
  mockedListEntities.mockResolvedValue([company]);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <ClientsPage />
      </ToastProvider>
    </QueryClientProvider>,
  );
}

const impact = {
  client_id: 5, name: "Acme", is_archived: false,
  impact: { deals: 2, projects: 1, tasks: 0, activities: 0, meetings: 0, documents: 0, converted_leads: 0 },
  cascade_delete_count: 3, dependencies_exist: true, confirmation_phrase: "DELETE COMPANY",
};

describe("ClientsPage permanent delete", () => {
  afterEach(() => vi.restoreAllMocks());

  it("keeps Archive available", async () => {
    setup(NORMAL_ADMIN);
    expect(await screen.findByRole("button", { name: /archive/i })).toBeInTheDocument();
  });

  it("shows Permanent delete only to a superadmin", async () => {
    setup(NORMAL_ADMIN);
    await screen.findByRole("button", { name: /archive/i });
    expect(screen.queryByRole("button", { name: /delete permanently/i })).not.toBeInTheDocument();
  });

  it("renders dependency impact and requires cascade confirmation", async () => {
    mockedRequest.mockResolvedValue(impact);
    setup(SUPERADMIN);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /delete permanently acme/i }));

    await waitFor(() => expect(mockedRequest).toHaveBeenCalledWith("/clients/5/delete-impact/"));
    expect(await screen.findByText(/deals:/i)).toBeInTheDocument();

    const submit = screen.getByRole("button", { name: /permanently delete company/i });
    await user.type(screen.getByLabelText(/current password/i), "pw12345678");
    await user.type(screen.getByLabelText(/type delete company/i), "DELETE COMPANY");
    // Dependencies exist -> cascade checkbox required.
    expect(submit).toBeDisabled();
    await user.click(screen.getByLabelText(/deals and projects will also be permanently deleted/i));
    expect(submit).toBeEnabled();
  });
});
