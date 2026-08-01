import {
  flexRender,
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
} from "@tanstack/react-table";
import { zodResolver } from "@hookform/resolvers/zod";
import { Plus } from "lucide-react";
import { useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";

import { Trash2 } from "lucide-react";

import { apiErrorMessage, apiRequest, createEntity, fetchList, patchEntity } from "../api/client";
import type { User, UserDeleteImpact } from "../api/types";
import { PageHeader } from "../components/PageHeader";
import { PermanentDeleteDialog, type PermanentDeleteConfirm } from "../components/PermanentDeleteDialog";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { MotionDiv, MotionSection, pageMotion } from "../components/ui/motion";
import { Select } from "../components/ui/select";
import { TableSkeleton } from "../components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../components/ui/table";
import { useAuth } from "../lib/auth";
import { isSuperAdmin } from "../lib/superadmin";
import { useToast } from "../lib/toast";

const userSchema = z.object({
  username: z.string().min(1, "Username is required"),
  email: z.string().email("Use a valid email").optional().or(z.literal("")),
  first_name: z.string().optional(),
  last_name: z.string().optional(),
  temp_password: z.string().min(8, "Use at least 8 characters"),
  role: z.enum(["admin", "sales"], { message: "Choose a role" }),
});

type UserFormValues = z.infer<typeof userSchema>;

function readDetail(message: string): string {
  try {
    return (JSON.parse(message) as { detail?: string }).detail || "Could not deactivate user.";
  } catch {
    return "Could not deactivate user.";
  }
}

function RoleBadge({ role }: { role: User["role"] }) {
  return <Badge tone={role === "admin" ? "accent" : "neutral"}>{role}</Badge>;
}

export function UsersPage() {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const { user: currentUser } = useAuth();
  const superadmin = isSuperAdmin(currentUser);
  const [isCreating, setIsCreating] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<User | null>(null);

  const { data: users = [], isLoading, isError } = useQuery({
    queryKey: ["users"],
    queryFn: () => fetchList<User>("/users/"),
  });

  const form = useForm<UserFormValues>({
    resolver: zodResolver(userSchema),
    defaultValues: {
      username: "",
      email: "",
      first_name: "",
      last_name: "",
      temp_password: "",
      role: undefined,
    },
  });

  const createUser = useMutation({
    mutationFn: (values: UserFormValues) => createEntity<User>("users", values),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] });
      form.reset({ username: "", email: "", first_name: "", last_name: "", temp_password: "", role: undefined });
      setIsCreating(false);
      showToast("User created.", "success");
    },
    onError: () => showToast("Could not create user. Check the required role and password.", "error"),
  });

  const updateRole = useMutation({
    mutationFn: ({ id, role }: { id: number; role: User["role"] }) => patchEntity<User>("users", id, { role }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] });
      showToast("Role updated.", "success");
    },
    onError: () => showToast("Could not update role.", "error"),
  });

  const deactivateUser = useMutation({
    mutationFn: (id: number) => apiRequest<User>(`/users/${id}/deactivate/`, { method: "PATCH" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] });
      showToast("User deactivated.", "success");
    },
    onError: (error) => showToast(error instanceof Error ? readDetail(error.message) : "Could not deactivate user.", "error"),
  });

  const reactivateUser = useMutation({
    mutationFn: (id: number) => apiRequest<User>(`/users/${id}/reactivate/`, { method: "PATCH" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] });
      showToast("User reactivated.", "success");
    },
    onError: () => showToast("Could not reactivate user.", "error"),
  });

  const columns = useMemo<ColumnDef<User>[]>(
    () => [
      {
        accessorKey: "username",
        header: "Username",
        cell: ({ row }) => (
          <div>
            <p className="font-medium">{row.original.username}</p>
            <p className="text-xs text-muted-foreground">{row.original.email || "No email"}</p>
          </div>
        ),
      },
      {
        accessorKey: "role",
        header: "Role",
        cell: ({ row }) => <RoleBadge role={row.original.role} />,
      },
      {
        accessorKey: "is_active",
        header: "Status",
        cell: ({ row }) => (
          <span className="rounded-sm bg-muted px-2 py-1 text-xs text-muted-foreground">
            {row.original.is_active ? "active" : "inactive"}
          </span>
        ),
      },
      {
        id: "changeRole",
        header: "Change role",
        cell: ({ row }) => (
          <Select
            className="h-9"
            value={row.original.role}
            onChange={(event) => updateRole.mutate({ id: row.original.id, role: event.target.value as User["role"] })}
          >
            <option value="admin">admin</option>
            <option value="sales">sales</option>
          </Select>
        ),
      },
      {
        id: "actions",
        header: "",
        cell: ({ row }) => {
          const isSelf = row.original.id === currentUser?.id;
          return (
            <div className="flex justify-end gap-2">
              {row.original.is_active ? (
                <Button className="h-8 px-3" type="button" variant="outline" onClick={() => deactivateUser.mutate(row.original.id)}>
                  Deactivate
                </Button>
              ) : (
                <Button className="h-8 px-3" type="button" onClick={() => reactivateUser.mutate(row.original.id)}>
                  Reactivate
                </Button>
              )}
              {/* Permanent delete: superadmin only, and never on your own row. */}
              {superadmin && !isSelf && (
                <Button
                  className="h-8 px-3"
                  type="button"
                  variant="danger"
                  onClick={() => setDeleteTarget(row.original)}
                  aria-label={`Delete permanently ${row.original.username}`}
                >
                  <Trash2 className="h-3.5 w-3.5" /> Delete permanently
                </Button>
              )}
            </div>
          );
        },
      },
    ],
    [currentUser?.id, superadmin, deactivateUser, reactivateUser, updateRole],
  );

  const table = useReactTable({
    data: users,
    columns,
    getCoreRowModel: getCoreRowModel(),
  });

  return (
    <MotionSection className="page-shell" {...pageMotion}>
      <PageHeader
        title="Users"
        subtitle="Create agency users, assign roles, and keep access tidy."
        actions={<Button type="button" onClick={() => setIsCreating(true)}><Plus className="h-4 w-4" />New User</Button>}
      />

      {isLoading ? (
        <TableSkeleton />
      ) : isError ? (
        <div className="surface-card p-6 text-sm text-muted-foreground">
          Could not load users. Only admins can access this page.
        </div>
      ) : (
        <div className="surface-card overflow-hidden">
          <Table>
            <TableHeader>
              {table.getHeaderGroups().map((headerGroup) => (
                <TableRow key={headerGroup.id}>
                  {headerGroup.headers.map((header) => (
                    <TableHead key={header.id}>{flexRender(header.column.columnDef.header, header.getContext())}</TableHead>
                  ))}
                </TableRow>
              ))}
            </TableHeader>
            <TableBody>
              {table.getRowModel().rows.map((row) => (
                <TableRow key={row.id}>
                  {row.getVisibleCells().map((cell) => (
                    <TableCell key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      {isCreating && (
        <div className="fixed inset-0 z-40 grid place-items-center bg-black/60 p-4">
          <MotionDiv className="w-full max-w-xl rounded-lg border border-border bg-card p-5 text-card-foreground shadow-soft" initial={{ opacity: 0, y: 12, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} transition={{ duration: 0.18 }}>
            <h2 className="mb-5 text-lg font-semibold">Create user</h2>
            <form className="space-y-4" onSubmit={form.handleSubmit((values) => createUser.mutateAsync(values))}>
              <label className="field-label">
                Username
                <Input className="mt-2" placeholder="sales-team" {...form.register("username")} />
                {form.formState.errors.username && <p className="field-hint text-primary">{form.formState.errors.username.message}</p>}
              </label>
              <label className="field-label">
                Role
                <Select className="mt-2" {...form.register("role")}>
                  <option value="">Choose role</option>
                  <option value="admin">admin</option>
                  <option value="sales">sales</option>
                </Select>
                {form.formState.errors.role && <p className="field-hint text-primary">{form.formState.errors.role.message}</p>}
              </label>
              <label className="field-label">
                Temporary password
                <Input className="mt-2" type="password" {...form.register("temp_password")} />
                {form.formState.errors.temp_password && <p className="field-hint text-primary">{form.formState.errors.temp_password.message}</p>}
              </label>
              <label className="field-label">
                Email
                <Input className="mt-2" type="email" {...form.register("email")} />
              </label>
              <div className="grid gap-3 md:grid-cols-2">
                <label className="field-label">
                  First name
                  <Input className="mt-2" {...form.register("first_name")} />
                </label>
                <label className="field-label">
                  Last name
                  <Input className="mt-2" {...form.register("last_name")} />
                </label>
              </div>
              <div className="flex gap-2">
                <Button disabled={form.formState.isSubmitting}>Create</Button>
                <Button type="button" variant="outline" onClick={() => setIsCreating(false)}>
                  Cancel
                </Button>
              </div>
            </form>
          </MotionDiv>
        </div>
      )}

      {deleteTarget && (
        <UserPermanentDeleteFlow
          target={deleteTarget}
          onClose={() => setDeleteTarget(null)}
          onDeleted={() => {
            setDeleteTarget(null);
            queryClient.invalidateQueries({ queryKey: ["users"] });
            showToast("User permanently deleted.", "success");
          }}
          showToast={showToast}
        />
      )}
    </MotionSection>
  );
}

function UserPermanentDeleteFlow({
  target,
  onClose,
  onDeleted,
  showToast,
}: {
  target: User;
  onClose: () => void;
  onDeleted: () => void;
  showToast: (m: string, t?: "success" | "error" | "info") => void;
}) {
  const [error, setError] = useState<string | null>(null);

  const impactQuery = useQuery({
    queryKey: ["user-delete-impact", target.id],
    queryFn: () => apiRequest<UserDeleteImpact>(`/users/${target.id}/delete-impact/`),
  });

  const deleteMutation = useMutation({
    mutationFn: ({ password }: PermanentDeleteConfirm) =>
      apiRequest(`/users/${target.id}/permanent-delete/`, {
        method: "POST",
        body: JSON.stringify({ current_password: password, confirmation: "DELETE USER", user_id: target.id }),
      }),
    onSuccess: () => onDeleted(),
    onError: (err) => {
      setError(apiErrorMessage(err, "Could not delete user."));
      showToast(apiErrorMessage(err, "Could not delete user."), "error");
    },
  });

  const impact = impactQuery.data;

  return (
    <PermanentDeleteDialog
      open
      title="Delete user permanently"
      phrase="DELETE USER"
      allowed={impact ? impact.deletion_allowed : false}
      blockedReason={impact?.blocked_reason}
      loadingImpact={impactQuery.isLoading}
      submitLabel="Permanently delete user"
      error={error}
      submitting={deleteMutation.isPending}
      onCancel={onClose}
      onConfirm={(data) => {
        setError(null);
        deleteMutation.mutate(data);
      }}
    >
      {impact ? (
        <div className="rounded-md border border-border bg-muted/40 p-3">
          <p className="font-medium">{impact.username}</p>
          <p className="text-muted-foreground">Role: {impact.role}</p>
          <p className="mt-1 text-muted-foreground">Owned records:</p>
          <ul className="mt-1 grid grid-cols-2 gap-x-4">
            <li>Deals: {String(impact.impact.owned_deals ?? 0)}</li>
            <li>Meetings: {String(impact.impact.owned_meetings ?? 0)}</li>
            <li>Work sessions: {String(impact.impact.work_sessions ?? 0)}</li>
            <li>Created leads: {String(impact.impact.created_leads ?? 0)}</li>
          </ul>
        </div>
      ) : impactQuery.isError ? (
        <p className="text-red-500">{apiErrorMessage(impactQuery.error, "Could not load user impact.")}</p>
      ) : null}
    </PermanentDeleteDialog>
  );
}
