import type { User } from "../api/types";

/**
 * The single frontend definition of a *superadmin*, mirroring the backend's
 * `accounts.permissions.is_super_admin`. Used only to decide whether to *render*
 * irreversible destructive controls — the server re-enforces every such action,
 * so this is never a security boundary on its own.
 */
export function isSuperAdmin(user: User | null | undefined): boolean {
  return Boolean(
    user &&
      user.is_active &&
      user.is_staff &&
      user.is_superuser &&
      user.role === "admin",
  );
}
