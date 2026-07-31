import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileText, Palette } from "lucide-react";
import { useState } from "react";

import { PageHeader } from "../components/PageHeader";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Select } from "../components/ui/select";
import { Skeleton } from "../components/ui/skeleton";
import { apiRequest, fetchList, patchEntity, sendTelemetry } from "../api/client";
import type { BrandProfile, GeneratedDocument, LegalEntity } from "../api/types";
import { useToast } from "../lib/toast";

const DOC_TYPES = [
  { value: "invoice", label: "Invoice" },
  { value: "contract", label: "Contract" },
  { value: "receipt", label: "Receipt" },
  { value: "quotation", label: "Quotation" },
  { value: "payment_acknowledgment", label: "Payment acknowledgment" },
];

export function BrandProfilesPage() {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const brandsQuery = useQuery({ queryKey: ["brands"], queryFn: () => fetchList<BrandProfile>("/brands/") });
  const legalQuery = useQuery({ queryKey: ["legal-entities"], queryFn: () => fetchList<LegalEntity>("/legal-entities/") });
  const documentsQuery = useQuery({ queryKey: ["documents"], queryFn: () => fetchList<GeneratedDocument>("/documents/") });

  return (
    <div className="space-y-6">
      <PageHeader title="Brand Profiles" subtitle="Fuel × Morph — Shared Business Workspace. Manage brands, legal profiles, and issue documents." />

      <section className="space-y-3">
        <h2 className="text-sm font-semibold text-muted-foreground">Presentation brands</h2>
        {brandsQuery.isLoading ? (
          <Skeleton className="h-40 w-full" />
        ) : (
          <div className="grid gap-4 md:grid-cols-3">
            {brandsQuery.data?.map((brand) => (
              <BrandCard key={brand.id} brand={brand} onChanged={() => queryClient.invalidateQueries({ queryKey: ["brands"] })} showToast={showToast} />
            ))}
          </div>
        )}
      </section>

      <section className="space-y-3">
        <h2 className="text-sm font-semibold text-muted-foreground">Legal profiles</h2>
        <div className="grid gap-4 md:grid-cols-2">
          {legalQuery.data?.map((entity) => (
            <div key={entity.id} className="surface-card p-4">
              <div className="flex items-center justify-between">
                <p className="font-medium">{entity.legal_name}</p>
                <Badge tone="neutral">{entity.key}</Badge>
              </div>
              {(!entity.registration_number || !entity.tax_number) && (
                <p className="mt-2 text-xs text-amber-500">Complete the legal details (registration, tax, bank, owner, terms) before issuing documents.</p>
              )}
            </div>
          ))}
        </div>
      </section>

      <GenerateDocument brands={brandsQuery.data ?? []} onDone={() => queryClient.invalidateQueries({ queryKey: ["documents"] })} showToast={showToast} />

      <section className="space-y-3">
        <h2 className="text-sm font-semibold text-muted-foreground">Recent documents</h2>
        <div className="surface-card overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="border-b border-border bg-muted/40 text-left text-xs uppercase tracking-wide text-muted-foreground">
              <tr>
                <th className="px-4 py-2">Number</th>
                <th className="px-4 py-2">Type</th>
                <th className="px-4 py-2">Brand</th>
                <th className="px-4 py-2">Amount</th>
                <th className="px-4 py-2">Date</th>
              </tr>
            </thead>
            <tbody>
              {documentsQuery.data?.map((doc) => (
                <tr key={doc.id} className="border-b border-border/60 last:border-0">
                  <td className="px-4 py-2 font-mono text-xs">{doc.document_number}</td>
                  <td className="px-4 py-2">{doc.document_type_display}</td>
                  <td className="px-4 py-2">{doc.brand_name}</td>
                  <td className="px-4 py-2 tabular-nums">{doc.amount ? `${doc.amount} ${doc.currency}` : "—"}</td>
                  <td className="px-4 py-2 text-muted-foreground">{new Date(doc.created_at).toLocaleDateString()}</td>
                </tr>
              ))}
              {documentsQuery.data?.length === 0 && (
                <tr><td colSpan={5} className="px-4 py-6 text-center text-muted-foreground">No documents generated yet.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

function BrandCard({ brand, onChanged, showToast }: { brand: BrandProfile; onChanged: () => void; showToast: (m: string, t?: "success" | "error" | "info") => void }) {
  const [accent, setAccent] = useState(brand.accent_color);
  const save = useMutation({
    mutationFn: () => patchEntity<BrandProfile>("brands", brand.id, { accent_color: accent }),
    onSuccess: () => { showToast("Brand updated.", "success"); onChanged(); },
    onError: () => showToast("Could not update brand.", "error"),
  });
  return (
    <div className="surface-card p-4">
      <div className="flex items-center gap-3">
        <span className="grid h-10 w-10 place-items-center rounded-md bg-primary/10 text-primary"><Palette className="h-5 w-5" /></span>
        <div>
          <p className="font-semibold">{brand.display_name}</p>
          <p className="text-xs text-muted-foreground">{brand.legal_name} · {brand.document_prefix}</p>
        </div>
      </div>
      <label className="mt-3 block text-xs font-medium text-muted-foreground">
        Accent color
        <Input className="mt-1" value={accent} placeholder="#3B82F6" onChange={(e) => setAccent(e.target.value)} />
      </label>
      <Button className="mt-3 w-full" size="sm" variant="outline" onClick={() => save.mutate()} disabled={save.isPending}>Save</Button>
    </div>
  );
}

function GenerateDocument({ brands, onDone, showToast }: { brands: BrandProfile[]; onDone: () => void; showToast: (m: string, t?: "success" | "error" | "info") => void }) {
  const [brand, setBrand] = useState("");
  const [type, setType] = useState("invoice");
  const [amount, setAmount] = useState("");

  const generate = useMutation({
    mutationFn: () => apiRequest<GeneratedDocument>("/documents/generate/", {
      method: "POST",
      body: JSON.stringify({ brand: Number(brand), document_type: type, amount: amount || undefined }),
    }),
    onSuccess: (doc) => {
      showToast(`Generated ${doc.document_number}.`, "success");
      sendTelemetry("pdf.opened", { entity_type: "GeneratedDocument", entity_id: String(doc.id) });
      onDone();
    },
    onError: () => showToast("Could not generate document.", "error"),
  });

  return (
    <section className="surface-card p-5">
      <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold"><FileText className="h-4 w-4" /> Issue a document</h2>
      <div className="grid gap-2 sm:grid-cols-4">
        <Select value={brand} onChange={(e) => setBrand(e.target.value)} aria-label="Issuing brand">
          <option value="">Select brand…</option>
          {brands.map((b) => <option key={b.id} value={b.id}>{b.display_name}</option>)}
        </Select>
        <Select value={type} onChange={(e) => setType(e.target.value)} aria-label="Document type">
          {DOC_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
        </Select>
        <Input type="number" placeholder="Amount (optional)" value={amount} onChange={(e) => setAmount(e.target.value)} aria-label="Amount" />
        <Button onClick={() => generate.mutate()} disabled={!brand || generate.isPending}>Generate</Button>
      </div>
      <p className="mt-2 text-xs text-muted-foreground">
        Each document permanently stores the exact brand and legal values used at generation time. Editing a brand later never changes past documents.
      </p>
    </section>
  );
}
