import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi, type Mock } from "vitest";

import { UsersPage } from "./UsersPage";
import { ToastProvider } from "../lib/toast";
import { fetchList } from "../api/client";
import { useAuth } from "../lib/auth";
import type { User } from "../api/types";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return {
    fetchList: vi.fn(),
    apiRequest: vi.fn(),
    createEntity: vi.fn(),
    patchEntity: vi.fn(),
    apiErrorMessage: actual.apiErrorMessage,
  };
});
vi.mock("../lib/auth", () => ({ useAuth: vi.fn() }));

const mockedList = fetchList as unknown as Mock;
const mockedAuth = useAuth as unknown as Mock;

const SELF: User = { id: 1, username: "owner", email: "", first_name: "", last_name: "", is_staff: true, is_superuser: true, is_active: true, role: "admin" };
const OTHER: User = { id: 2, username: "rep", email: "", first_name: "", last_name: "", is_staff: false, is_superuser: false, is_active: true, role: "sales" };
const NORMAL_ADMIN: User = { ...SELF, is_superuser: false };

function setup(currentUser: User, users: User[]) {
  mockedAuth.mockReturnValue({ user: currentUser });
  mockedList.mockResolvedValue(users);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <UsersPage />
      </ToastProvider>
    </QueryClientProvider>,
  );
}

describe("UsersPage permanent delete", () => {
  afterEach(() => vi.restoreAllMocks());

  it("keeps Deactivate available", async () => {
    setup(SELF, [SELF, OTHER]);
    expect((await screen.findAllByRole("button", { name: /deactivate/i })).length).toBeGreaterThan(0);
  });

  it("shows Delete permanently only to a superadmin, and never on their own row", async () => {
    setup(SELF, [SELF, OTHER]);
    // Present for the other user, absent for self.
    expect(await screen.findByRole("button", { name: /delete permanently rep/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /delete permanently owner/i })).not.toBeInTheDocument();
  });

  it("hides Delete permanently from a normal admin", async () => {
    setup(NORMAL_ADMIN, [NORMAL_ADMIN, OTHER]);
    await screen.findAllByRole("button", { name: /deactivate/i });
    expect(screen.queryByRole("button", { name: /delete permanently/i })).not.toBeInTheDocument();
  });
});
