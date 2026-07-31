import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi, type Mock } from "vitest";

import { BrandProfilesPage } from "./BrandProfilesPage";
import { ToastProvider } from "../lib/toast";
import { apiRequest, fetchList, sendTelemetry } from "../api/client";

vi.mock("../api/client", () => ({ apiRequest: vi.fn(), fetchList: vi.fn(), patchEntity: vi.fn(), sendTelemetry: vi.fn() }));

const mockedApi = apiRequest as unknown as Mock;
const mockedList = fetchList as unknown as Mock;

const brands = [
  { id: 1, key: "fuel_dezign", legal_entity: 1, legal_name: "Fuel Dezign", display_name: "Fuel Dezign", logo_url: null, accent_color: "", secondary_color: "", website: "", public_email: "", service_category: "", document_prefix: "FUEL", default_signatory: null, is_active: true },
  { id: 2, key: "morph_studio", legal_entity: 2, legal_name: "Morph", display_name: "Morph Studio", logo_url: null, accent_color: "", secondary_color: "", website: "", public_email: "", service_category: "", document_prefix: "MORPH-STUDIO", default_signatory: null, is_active: true },
];

function setup() {
  mockedList.mockImplementation((path: string) => {
    if (path.startsWith("/brands")) return Promise.resolve(brands);
    if (path.startsWith("/legal-entities")) return Promise.resolve([{ id: 1, key: "fuel", legal_name: "Fuel Dezign", registration_number: "", tax_number: "", address: "", phone: "", email: "", website: "", bank_details: "", owner_name: "", owner_title: "", legal_terms: "", is_active: true }]);
    return Promise.resolve([]);
  });
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <BrandProfilesPage />
      </ToastProvider>
    </QueryClientProvider>,
  );
}

describe("BrandProfilesPage", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lists the presentation brands", async () => {
    setup();
    // Each brand name appears in its card and in the issuing-brand selector.
    expect((await screen.findAllByText("Morph Studio")).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Fuel Dezign").length).toBeGreaterThanOrEqual(1);
  });

  it("warns about incomplete legal details", async () => {
    setup();
    expect(await screen.findByText(/complete the legal details/i)).toBeInTheDocument();
  });

  it("generates a document via the brand selector and stores a snapshot", async () => {
    mockedApi.mockResolvedValue({ id: 5, document_number: "FUEL-INV-2026-0001", document_type_display: "Invoice", brand_name: "Fuel Dezign", amount: "250", currency: "JOD", created_at: "2026-07-31T00:00:00Z", snapshot: { legal_name: "Fuel Dezign" } });
    setup();
    const user = userEvent.setup();
    // Wait for the async-loaded brand options to render inside the selector.
    await waitFor(() => expect(screen.getByRole("option", { name: "Morph Studio" })).toBeInTheDocument());
    await user.selectOptions(screen.getByLabelText(/issuing brand/i), "1");
    await user.click(screen.getByRole("button", { name: /generate/i }));
    await waitFor(() => expect(mockedApi).toHaveBeenCalledWith("/documents/generate/", expect.objectContaining({ method: "POST" })));
    expect(sendTelemetry).toHaveBeenCalled();
  });
});
