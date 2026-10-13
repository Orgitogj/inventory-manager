"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { errorMessage } from "@/lib/api/errors";
import { LOGIN_ROUTE, useAuth } from "@/lib/auth/auth-context";

const ROLE_LABELS = {
  admin: "Admin",
  warehouse: "Warehouse",
  sales: "Sales",
} as const;

const BUTTON_CLASS =
  "rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 shadow-sm hover:bg-slate-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600 disabled:cursor-not-allowed disabled:opacity-60";

function CenteredMessage({ children }: { children: ReactNode }) {
  return (
    <main className="flex min-h-screen items-center justify-center px-4 text-sm text-slate-600">
      {children}
    </main>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const { status, user, logout, retry } = useAuth();
  const router = useRouter();
  const [loggingOut, setLoggingOut] = useState(false);
  const [logoutError, setLogoutError] = useState<string | null>(null);

  useEffect(() => {
    if (status === "unauthenticated") {
      router.replace(LOGIN_ROUTE);
    }
  }, [status, router]);

  async function handleLogout() {
    setLoggingOut(true);
    setLogoutError(null);

    try {
      await logout();
    } catch (error) {
      setLogoutError(errorMessage(error));
      setLoggingOut(false);
    }
  }

  if (status === "error") {
    return (
      <CenteredMessage>
        <div role="alert" className="space-y-3 text-center">
          <p>We could not reach the server.</p>
          <button type="button" onClick={retry} className={BUTTON_CLASS}>
            Try again
          </button>
        </div>
      </CenteredMessage>
    );
  }

  if (status !== "authenticated" || user === null) {
    return (
      <CenteredMessage>
        <p role="status">Loading…</p>
      </CenteredMessage>
    );
  }

  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-3 px-4 py-3">
          <span className="text-base font-semibold">Inventory Manager</span>
          <div className="flex items-center gap-3">
            <div className="text-right text-sm leading-tight">
              <p className="font-medium">{user.full_name}</p>
              <p className="text-slate-500">{ROLE_LABELS[user.role]}</p>
            </div>
            <button
              type="button"
              onClick={handleLogout}
              disabled={loggingOut}
              className={BUTTON_CLASS}
            >
              {loggingOut ? "Logging out…" : "Log out"}
            </button>
          </div>
        </div>
        {logoutError !== null && (
          <p
            role="alert"
            className="mx-auto max-w-5xl px-4 pb-3 text-sm text-red-700"
          >
            {logoutError}
          </p>
        )}
      </header>
      <main className="mx-auto max-w-5xl px-4 py-6">{children}</main>
    </div>
  );
}
