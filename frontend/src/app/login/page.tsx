import type { Metadata } from "next";

import { LoginScreen } from "@/components/login-screen";

export const metadata: Metadata = {
  title: "Log in · Inventory Manager",
};

export default function LoginPage() {
  return <LoginScreen />;
}
