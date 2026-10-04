"use client";

// Сессия: JWT в localStorage + текущий пользователь из /auth/me.

import { useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useState } from "react";

import { api, getToken, setToken, setUnauthorizedHandler } from "./api/client";
import type { Role, TokenOut, User } from "./api/types";

interface AuthState {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<User>;
  logout: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function homePath(role: Role): string {
  if (role === "patient") return "/patient";
  if (role === "manager") return "/dashboard";
  return "/studies";
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const qc = useQueryClient();
  const router = useRouter();

  const logout = useCallback(() => {
    setToken(null);
    setUser(null);
    qc.clear();
    router.replace("/login");
  }, [qc, router]);

  useEffect(() => {
    setUnauthorizedHandler(logout);
    return () => setUnauthorizedHandler(null);
  }, [logout]);

  useEffect(() => {
    const restore = getToken()
      ? api<User>("/auth/me")
          .then(setUser)
          .catch(() => setToken(null))
      : Promise.resolve();
    restore.finally(() => setLoading(false));
  }, []);

  const login = useCallback(
    async (email: string, password: string) => {
      const res = await api<TokenOut>("/auth/login", {
        method: "POST",
        body: { email, password },
      });
      qc.clear();
      setToken(res.access_token);
      setUser(res.user);
      return res.user;
    },
    [qc],
  );

  return (
    <AuthContext.Provider value={{ user, loading, login, logout }}>{children}</AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth вне AuthProvider");
  return ctx;
}
