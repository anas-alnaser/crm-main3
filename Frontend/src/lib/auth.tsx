import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { apiRequest, login as loginRequest } from "../api/client";
import type { User } from "../api/types";

type AuthContextValue = {
  user: User | null;
  isLoading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  /** Re-fetch the current user from /auth/me/ (e.g. after a full CRM reset). */
  refreshUser: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem("accessToken");
    if (!token) {
      setIsLoading(false);
      return;
    }

    apiRequest<User>("/auth/me/")
      .then(setUser)
      .catch(() => {
        localStorage.removeItem("accessToken");
        localStorage.removeItem("refreshToken");
      })
      .finally(() => setIsLoading(false));
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      isLoading,
      login: async (username, password) => {
        const tokens = await loginRequest(username, password);
        localStorage.setItem("accessToken", tokens.access);
        localStorage.setItem("refreshToken", tokens.refresh);
        const currentUser = await apiRequest<User>("/auth/me/");
        setUser(currentUser);
      },
      logout: () => {
        localStorage.removeItem("accessToken");
        localStorage.removeItem("refreshToken");
        setUser(null);
      },
      refreshUser: async () => {
        const currentUser = await apiRequest<User>("/auth/me/");
        setUser(currentUser);
      },
    }),
    [isLoading, user],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return context;
}
