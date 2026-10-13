"use client";

import { useState, type FormEvent } from "react";

import { ApiError, errorMessage } from "@/lib/api/errors";
import { useAuth } from "@/lib/auth/auth-context";

type FieldName = "email" | "password";

type FormError = {
  message: string | null;
  wait: string | null;
  fields: Partial<Record<FieldName, string>>;
};

const NO_ERROR: FormError = { message: null, wait: null, fields: {} };
const FIELD_NAMES: readonly FieldName[] = ["email", "password"];

const INPUT_CLASS =
  "mt-1 block w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm placeholder:text-slate-400 focus:border-indigo-600 focus:outline-none focus:ring-2 focus:ring-indigo-600/40 aria-[invalid=true]:border-red-600";

export function formatWait(seconds: number): string {
  if (seconds < 60) {
    return `${seconds} ${seconds === 1 ? "second" : "seconds"}`;
  }

  const minutes = Math.ceil(seconds / 60);
  return `${minutes} ${minutes === 1 ? "minute" : "minutes"}`;
}

function toFormError(error: unknown): FormError {
  if (!(error instanceof ApiError)) {
    return { ...NO_ERROR, message: errorMessage(error) };
  }

  const fields: FormError["fields"] = {};

  for (const detail of error.details ?? []) {
    const name = FIELD_NAMES.find((field) => field === detail.field);

    if (name !== undefined) {
      fields[name] = detail.message;
    }
  }

  const hasFieldErrors = Object.keys(fields).length > 0;

  return {
    message: hasFieldErrors ? null : error.message,
    wait:
      error.status === 429 && error.retryAfterSeconds !== null
        ? formatWait(error.retryAfterSeconds)
        : null,
    fields,
  };
}

export function LoginForm() {
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<FormError>(NO_ERROR);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(NO_ERROR);

    try {
      await login(email, password);
    } catch (caught) {
      setError(toFormError(caught));
      setSubmitting(false);
    }
  }

  return (
    <form
      method="post"
      onSubmit={handleSubmit}
      noValidate
      className="space-y-5"
    >
      {error.message !== null && (
        <div
          role="alert"
          className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800"
        >
          <p>{error.message}</p>
          {error.wait !== null && <p>Try again in {error.wait}.</p>}
        </div>
      )}

      <div>
        <label htmlFor="email" className="block text-sm font-medium">
          Email
        </label>
        <input
          id="email"
          name="email"
          type="email"
          autoComplete="username"
          required
          maxLength={320}
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          aria-invalid={error.fields.email !== undefined}
          aria-describedby={error.fields.email ? "email-error" : undefined}
          className={INPUT_CLASS}
        />
        {error.fields.email && (
          <p id="email-error" className="mt-1 text-sm text-red-700">
            {error.fields.email}
          </p>
        )}
      </div>

      <div>
        <label htmlFor="password" className="block text-sm font-medium">
          Password
        </label>
        <input
          id="password"
          name="password"
          type="password"
          autoComplete="current-password"
          required
          maxLength={128}
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          aria-invalid={error.fields.password !== undefined}
          aria-describedby={
            error.fields.password ? "password-error" : undefined
          }
          className={INPUT_CLASS}
        />
        {error.fields.password && (
          <p id="password-error" className="mt-1 text-sm text-red-700">
            {error.fields.password}
          </p>
        )}
      </div>

      <button
        type="submit"
        disabled={submitting}
        className="w-full rounded-md bg-indigo-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-indigo-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {submitting ? "Logging in…" : "Log in"}
      </button>
    </form>
  );
}
