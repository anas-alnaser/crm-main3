import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { apiRequest } from "../api/client";
import type { CommissionSummary, Pipeline, Stage } from "../api/types";
import { PageHeader } from "../components/PageHeader";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { MotionSection, pageMotion } from "../components/ui/motion";
import { Skeleton } from "../components/ui/skeleton";
import { useToast } from "../lib/toast";

export function SettingsPage() {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const [commissionRate, setCommissionRate] = useState("");
  const { data: pipelines = [] } = useQuery({
    queryKey: ["pipelines"],
    queryFn: () => apiRequest<Pipeline[]>("/pipelines/"),
  });
  const { data: stages = [], isLoading } = useQuery({
    queryKey: ["stages"],
    queryFn: () => apiRequest<Stage[]>("/stages/?ordering=order"),
  });
  const { data: commission } = useQuery({
    queryKey: ["commission"],
    queryFn: () => apiRequest<CommissionSummary>("/commission/"),
  });
  const updateCommission = useMutation({
    mutationFn: () =>
      apiRequest<CommissionSummary>("/commission/", {
        method: "PATCH",
        body: JSON.stringify({ commission_rate_percent: commissionRate }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["commission"] });
      showToast("Commission rate updated.", "success");
    },
    onError: () => showToast("Could not update commission rate.", "error"),
  });

  useEffect(() => {
    if (commission) {
      setCommissionRate(String(commission.commission_rate_percent));
    }
  }, [commission]);

  return (
    <MotionSection className="page-shell" {...pageMotion}>
      <PageHeader title="Settings" subtitle="Review pipeline setup and admin-only CRM configuration." />

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="surface-card p-5 lg:col-span-2">
          <h2 className="text-lg font-semibold">Commission rate</h2>
          <p className="mt-1 text-sm text-muted-foreground">Flat percentage used for earned and potential commission calculations.</p>
          <div className="mt-4 flex max-w-md flex-wrap items-end gap-3">
            <label className="field-label flex-1">
              Rate percent
              <Input
                className="mt-2 tabular-nums"
                max={100}
                min={0}
                step="0.01"
                type="number"
                value={commissionRate}
                onChange={(event) => setCommissionRate(event.target.value)}
              />
            </label>
            <Button disabled={updateCommission.isPending} type="button" onClick={() => updateCommission.mutate()}>
              Save rate
            </Button>
          </div>
        </section>

        <section className="surface-card p-5">
          <h2 className="text-lg font-semibold">Pipelines</h2>
          <p className="mt-1 text-sm text-muted-foreground">Sales workflows available in this workspace.</p>
          <div className="mt-4 space-y-2 text-sm">
            {isLoading && <Skeleton className="h-20" />}
            {pipelines.map((pipeline) => (
              <div key={pipeline.id} className="flex items-center justify-between rounded-md border border-border bg-background px-3 py-3">
                <span>{pipeline.name}</span>
                {pipeline.is_default && <Badge tone="accent">default</Badge>}
              </div>
            ))}
          </div>
        </section>

        <section className="surface-card p-5">
          <h2 className="text-lg font-semibold">Stages</h2>
          <p className="mt-1 text-sm text-muted-foreground">The column order used by the pipeline board.</p>
          <div className="mt-4 space-y-2 text-sm">
            {isLoading && <Skeleton className="h-20" />}
            {stages.map((stage) => (
              <div key={stage.id} className="flex items-center justify-between rounded-md border border-border bg-background px-3 py-3">
                <span>{stage.name}</span>
                <span className="text-xs tabular-nums text-muted-foreground">order {stage.order}</span>
              </div>
            ))}
          </div>
        </section>
      </div>
    </MotionSection>
  );
}
