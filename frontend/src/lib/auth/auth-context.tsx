"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import {
  createApiClient,
  type ApiClient,
  type Session,
  type User,
} from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";

export const SESSION_QUERY_KEY = ["auth", "session"] as const;
export const LOGIN_ROUTE = "/login";
export const HOME_ROUTE = "/products";

export type AuthStatus =
  "loading" | "authenticated" | "unauthenticated" | "error";

type AuthContextValue = {
  api: ApiClient;
  status: AuthStatus;
  user: User | null;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  retry: () => void;
};

type AuthProviderProps = {
  children: ReactNode;
  baseUrl?: string;
  fetch?: typeof globalThis.fetch;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children, baseUrl, fetch }: AuthProviderProps) {
  const queryClient = useQueryClient();
  const router = useRouter();

  const clearSession = useCallback(() => {
    queryClient.setQueryData<Session | null>(SESSION_QUERY_KEY, null);
    queryClient.removeQueries({
      predicate: (query) => query.queryKey[0] !== SESSION_QUERY_KEY[0],
    });
  }, [queryClient]);

  const [api] = useState(() =>
    createApiClient({
      baseUrl,
      fetch,
      getCsrfToken: () =>
        queryClient.getQueryData<Session | null>(SESSION_QUERY_KEY)
          ?.csrf_token ?? null,
      onUnauthorized: () => {
        clearSession();
        router.replace(LOGIN_ROUTE);
      },
    }),
  );

  const sessionQuery = useQuery({
    queryKey: SESSION_QUERY_KEY,
    queryFn: async (): Promise<Session | null> => {
      try {
        const { data } = await api.GET("/api/v1/auth/me");
        return data ?? null;
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) {
          return null;
        }

        throw error;
      }
    },
    staleTime: Infinity,
    gcTime: Infinity,
    retry: false,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  });

  const login = useCallback(
    async (email: string, password: string) => {
      const { data } = await api.POST("/api/v1/auth/login", {
        body: { email, password },
      });

      queryClient.setQueryData<Session | null>(SESSION_QUERY_KEY, data ?? null);
      router.replace(HOME_ROUTE);
    },
    [api, queryClient, router],
  );

  const logout = useCallback(async () => {
    await api.POST("/api/v1/auth/logout");
    clearSession();
    router.replace(LOGIN_ROUTE);
  }, [api, clearSession, router]);

  const { data, isPending, isError, refetch } = sessionQuery;

  const value = useMemo<AuthContextValue>(() => {
    const status: AuthStatus = isPending
      ? "loading"
      : isError
        ? "error"
        : data
          ? "authenticated"
          : "unauthenticated";

    return {
      api,
      status,
      user: data?.user ?? null,
      login,
      logout,
      retry: () => void refetch(),
    };
  }, [api, data, isPending, isError, login, logout, refetch]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);

  if (value === null) {
    throw new Error("useAuth must be used inside AuthProvider.");
  }

  return value;
}

export function useApi(): ApiClient {
  return useAuth().api;
}
