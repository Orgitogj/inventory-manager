import type { Session } from "@/lib/api/client";

export const CSRF_TOKEN = "test-csrf-token";

export const SESSION: Session = {
  user: {
    id: "7f0c1f4e-58a1-4f0e-9d53-2f1f6f3f9a10",
    email: "ana@example.com",
    full_name: "Ana Example",
    role: "admin",
  },
  csrf_token: CSRF_TOKEN,
};
