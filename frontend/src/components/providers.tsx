"use client";

import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { createContext, useContext, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { User } from "@/lib/types";

type AuthState = { user: User | null | undefined; loading: boolean; error: Error | null; refresh: () => void };
const AuthContext = createContext<AuthState>({ user: undefined, loading: true, error: null, refresh: () => {} });
function AuthProvider({ children }: { children: React.ReactNode }) {
  const query = useQuery({
    queryKey: ["me"],
    queryFn: async () => { try { return await api<User>("/auth/me"); } catch (error) { if (error instanceof ApiError && error.status === 401) return null; throw error; } },
    retry: false,
    staleTime: 30_000,
  });
  return <AuthContext.Provider value={{ user: query.data, loading: query.isPending, error: query.error, refresh: () => { void query.refetch(); } }}>{children}</AuthContext.Provider>;
}
export function useAuth() { return useContext(AuthContext); }
export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(() => new QueryClient({ defaultOptions: { queries: { retry: 1, staleTime: 20_000, refetchOnWindowFocus: false }, mutations: { retry: false } } }));
  return <QueryClientProvider client={queryClient}><AuthProvider>{children}</AuthProvider></QueryClientProvider>;
}
