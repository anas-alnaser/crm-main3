import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from "vitest";

import { AICommandBar } from "./AICommandBar";
import { ToastProvider } from "../lib/toast";
import { apiRequest } from "../api/client";

vi.mock("../api/client", () => ({ apiRequest: vi.fn() }));

const mockedApi = apiRequest as unknown as Mock;

function renderBar() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <AICommandBar />
      </ToastProvider>
    </QueryClientProvider>,
  );
}

async function runCommand(text: string) {
  renderBar();
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("AI command"), text);
  await user.click(screen.getByRole("button", { name: /run/i }));
  return user;
}

describe("AICommandBar", () => {
  beforeEach(() => mockedApi.mockReset());
  afterEach(() => vi.restoreAllMocks());

  it("shows a server confirmation panel and confirms via the confirm endpoint", async () => {
    mockedApi.mockImplementation((path: string) => {
      if (path === "/ai/command/") {
        return Promise.resolve({
          intent: "update_deal_value",
          tier: "confirm",
          acted: false,
          requires_confirmation: true,
          confirmation_id: "conf-1",
          preview: { record: "Acme", field: "value", old: "1000", new: "5000" },
          summary: "Deal value edits require confirmation.",
        });
      }
      if (path === "/ai/command/confirm/") {
        return Promise.resolve({ intent: "update_deal_value", acted: true, undoable: true, action_id: 7, summary: "Updated deal value to 5000." });
      }
      return Promise.resolve({});
    });

    const user = await runCommand("set the acme deal to 5000");

    expect(await screen.findByText("Confirmation required")).toBeInTheDocument();
    expect(screen.getByText("5000")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /^confirm$/i }));

    await waitFor(() => expect(mockedApi).toHaveBeenCalledWith("/ai/command/confirm/", expect.objectContaining({ method: "POST" })));
    const confirmBody = JSON.parse((mockedApi.mock.calls.find((c) => c[0] === "/ai/command/confirm/")![1] as { body: string }).body);
    expect(confirmBody).toEqual({ confirmation_id: "conf-1" });
    // Undo affordance appears after a successful action.
    expect(await screen.findByRole("button", { name: /undo/i })).toBeInTheDocument();
  });

  it("does not send the mutation from the browser (no direct entity write)", async () => {
    mockedApi.mockResolvedValue({
      intent: "update_deal_value",
      requires_confirmation: true,
      confirmation_id: "conf-2",
      preview: { record: "Acme", field: "value", old: "1", new: "2" },
      acted: false,
    });
    await runCommand("set value");
    await screen.findByText("Confirmation required");
    // Only the command endpoint was hit; no deal write happened client-side.
    const paths = mockedApi.mock.calls.map((c) => c[0]);
    expect(paths).toEqual(["/ai/command/"]);
  });

  it("surfaces blocked commands instead of going idle", async () => {
    mockedApi.mockResolvedValue({
      intent: "delete_deal",
      tier: "blocked",
      acted: false,
      blocked: true,
      refusal: "This action is blocked for safety.",
      summary: "This action is blocked for safety.",
    });
    await runCommand("delete the acme deal");
    expect(await screen.findByText("Blocked")).toBeInTheDocument();
  });

  it("runs undo for an immediately-executed action", async () => {
    mockedApi.mockImplementation((path: string) => {
      if (path === "/ai/command/") {
        return Promise.resolve({ intent: "create_company", acted: true, undoable: true, action_id: 42, summary: "Created company 'NewCo'." });
      }
      if (path === "/ai/command/undo/") {
        return Promise.resolve({ undone: true, action_id: 42, summary: "Deleted created record 'NewCo'." });
      }
      return Promise.resolve({});
    });
    const user = await runCommand("create company NewCo");
    const undoButton = await screen.findByRole("button", { name: /undo/i });
    await user.click(undoButton);
    await waitFor(() => expect(mockedApi).toHaveBeenCalledWith("/ai/command/undo/", expect.objectContaining({ method: "POST" })));
    const undoBody = JSON.parse((mockedApi.mock.calls.find((c) => c[0] === "/ai/command/undo/")![1] as { body: string }).body);
    expect(undoBody).toEqual({ action_id: 42 });
  });

  it("shows a config error when the provider key is missing", async () => {
    mockedApi.mockRejectedValue(new Error(JSON.stringify({ detail: "AI command service is not configured.", code: "ai_unconfigured" })));
    await runCommand("do something");
    expect(await screen.findByText(/not configured/i)).toBeInTheDocument();
  });
});
