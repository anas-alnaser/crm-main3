import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi, type Mock } from "vitest";

import { SettingsDangerZone } from "./SettingsDangerZone";
import { ToastProvider } from "../lib/toast";
import { apiRequest } from "../api/client";
import { useAuth } from "../lib/auth";

const navigateSpy = vi.fn();

vi.mock("react-router-dom", () => ({ useNavigate: () => navigateSpy }));
vi.mock("../lib/auth", () => ({ useAuth: vi.fn() }));
vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return { apiRequest: vi.fn(), apiErrorMessage: actual.apiErrorMessage };
});

const mockedRequest = apiRequest as unknown as Mock;
const mockedAuth = useAuth as unknown as Mock;

const SUPERADMIN = { id: 1, username: "owner", email: "o@e.com", role: "admin", is_staff: true, is_superuser: true, is_active: true };
const NORMAL_ADMIN = { ...SUPERADMIN, id: 2, is_superuser: false };
const SALES = { ...SUPERADMIN, id: 3, role: "sales", is_staff: false, is_superuser: false };

const previewData = {
  preserved_user: { id: 1, username: "owner", email: "o@e.com" },
  counts: { leads: 3, companies: 1, other_users: 2 },
  other_users_to_delete: 2,
  total_rows: 6,
  preserved_config: { legal_entities: ["Fuel", "Morph"], brands: ["Fuel Dezign", "Morph Studio", "Morph Solutions"] },
  preview_token: "tok123",
  preview_expires_at: new Date(Date.now() + 600000).toISOString(),
  confirmation_phrase: "DELETE ALL CRM DATA",
};

function setup(user: object, refreshUser = vi.fn().mockResolvedValue(undefined)) {
  mockedAuth.mockReturnValue({ user, refreshUser });
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const clearSpy = vi.spyOn(queryClient, "clear");
  const utils = render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <SettingsDangerZone />
      </ToastProvider>
    </QueryClientProvider>,
  );
  return { ...utils, clearSpy, refreshUser };
}

describe("SettingsDangerZone", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("is hidden for sales users", () => {
    setup(SALES);
    expect(screen.queryByRole("heading", { name: /danger zone/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /preview full reset/i })).not.toBeInTheDocument();
  });

  it("is hidden for normal admins", () => {
    setup(NORMAL_ADMIN);
    expect(screen.queryByRole("heading", { name: /danger zone/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /preview full reset/i })).not.toBeInTheDocument();
  });

  it("is shown for a superadmin", () => {
    setup(SUPERADMIN);
    expect(screen.getByRole("heading", { name: /danger zone/i })).toBeInTheDocument();
  });

  it("renders preview counts and disables reset until all requirements are met", async () => {
    mockedRequest.mockResolvedValue(previewData);
    setup(SUPERADMIN);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /preview full reset/i }));

    await waitFor(() => expect(mockedRequest).toHaveBeenCalledWith("/admin/data-reset/preview/"));
    expect(await screen.findByText(/total rows to delete:/i)).toBeInTheDocument();
    expect(screen.getByText(/other users to delete:/i)).toBeInTheDocument();

    const reset = screen.getByRole("button", { name: /permanently reset crm/i });
    expect(reset).toBeDisabled();

    await user.type(screen.getByLabelText(/current password/i), "ownerpw123");
    expect(reset).toBeDisabled();
    await user.type(screen.getByLabelText(/type delete all crm data/i), "DELETE ALL CRM DATA");
    expect(reset).toBeDisabled(); // checkbox still required
    await user.click(screen.getByLabelText(/i understand that this permanently deletes/i));
    expect(reset).toBeEnabled();
  });

  it("sends the correct execute body and, on success, clears caches, refetches user, and navigates", async () => {
    mockedRequest.mockImplementation((path: string) => {
      if (path.endsWith("/preview/")) return Promise.resolve(previewData);
      return Promise.resolve({ detail: "CRM data reset completed. Your account was preserved." });
    });
    const { clearSpy, refreshUser } = setup(SUPERADMIN);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /preview full reset/i }));
    await screen.findByText(/total rows to delete:/i);
    await user.type(screen.getByLabelText(/current password/i), "ownerpw123");
    await user.type(screen.getByLabelText(/type delete all crm data/i), "DELETE ALL CRM DATA");
    await user.click(screen.getByLabelText(/i understand that this permanently deletes/i));
    await user.click(screen.getByRole("button", { name: /permanently reset crm/i }));

    await waitFor(() =>
      expect(mockedRequest).toHaveBeenCalledWith(
        "/admin/data-reset/execute/",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({
            current_password: "ownerpw123",
            confirmation: "DELETE ALL CRM DATA",
            preserved_user_id: 1,
            preview_token: "tok123",
          }),
        }),
      ),
    );
    await waitFor(() => expect(clearSpy).toHaveBeenCalled());
    expect(refreshUser).toHaveBeenCalled();
    await waitFor(() => expect(navigateSpy).toHaveBeenCalledWith("/"));
  });

  it("displays a safe backend error on failure and clears the password", async () => {
    mockedRequest.mockImplementation((path: string) => {
      if (path.endsWith("/preview/")) return Promise.resolve(previewData);
      return Promise.reject(new Error(JSON.stringify({ detail: "Incorrect password.", code: "incorrect_password" })));
    });
    setup(SUPERADMIN);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /preview full reset/i }));
    await screen.findByText(/total rows to delete:/i);
    const pw = screen.getByLabelText(/current password/i) as HTMLInputElement;
    await user.type(pw, "ownerpw123");
    await user.type(screen.getByLabelText(/type delete all crm data/i), "DELETE ALL CRM DATA");
    await user.click(screen.getByLabelText(/i understand that this permanently deletes/i));
    await user.click(screen.getByRole("button", { name: /permanently reset crm/i }));

    expect((await screen.findAllByText("Incorrect password.")).length).toBeGreaterThan(0);
    expect(navigateSpy).not.toHaveBeenCalled();
    // Password is cleared after a failed attempt (never retained).
    await waitFor(() => expect(pw.value).toBe(""));
  });
});
