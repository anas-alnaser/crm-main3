import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { createEntity, deleteEntity, listEntities, updateEntity } from "../api/client";
import { useToast } from "../lib/toast";

export function useCrud<T extends { id: number }>(resource: string) {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const queryKey = [resource];

  const query = useQuery({
    queryKey,
    queryFn: () => listEntities<T>(resource),
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey });

  return {
    ...query,
    createMutation: useMutation({
      mutationFn: (data: unknown) => createEntity<T>(resource, data),
      onSuccess: () => {
        invalidate();
        showToast(`${resource.slice(0, -1) || resource} created.`, "success");
      },
      onError: () => showToast(`Could not create ${resource.slice(0, -1) || resource}.`, "error"),
    }),
    updateMutation: useMutation({
      mutationFn: ({ id, data }: { id: number; data: unknown }) => updateEntity<T>(resource, id, data),
      onSuccess: () => {
        invalidate();
        showToast(`${resource.slice(0, -1) || resource} updated.`, "success");
      },
      onError: () => showToast(`Could not update ${resource.slice(0, -1) || resource}.`, "error"),
    }),
    deleteMutation: useMutation({
      mutationFn: (id: number) => deleteEntity(resource, id),
      onSuccess: () => {
        invalidate();
        showToast(`${resource.slice(0, -1) || resource} deleted.`, "success");
      },
      onError: () => showToast(`Could not delete ${resource.slice(0, -1) || resource}.`, "error"),
    }),
  };
}
