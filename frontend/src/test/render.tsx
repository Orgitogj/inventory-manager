import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";

import { AuthProvider } from "@/lib/auth/auth-context";

import { BASE_URL, type FetchMock } from "./fetch-mock";

export function renderWithProviders(ui: ReactElement, fetchMock: FetchMock) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider baseUrl={BASE_URL} fetch={fetchMock}>
        {ui}
      </AuthProvider>
    </QueryClientProvider>,
  );
}
