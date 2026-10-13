"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { LoginForm } from "@/components/login-form";
import { HOME_ROUTE, useAuth } from "@/lib/auth/auth-context";

export function LoginScreen() {
  const { status } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (status === "authenticated") {
      router.replace(HOME_ROUTE);
    }
  }, [status, router]);

  return (
    <main className="flex min-h-screen items-center justify-center px-4 py-12">
      <div className="w-full max-w-sm rounded-lg border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
        <h1 className="text-xl font-semibold">Inventory Manager</h1>
        <p className="mt-1 mb-6 text-sm text-slate-600">
          Log in to manage stock and orders.
        </p>
        <LoginForm />
      </div>
    </main>
  );
}
