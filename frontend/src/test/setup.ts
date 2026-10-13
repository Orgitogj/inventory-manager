import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach, beforeEach, vi } from "vitest";

import { routerMock } from "./router";

vi.mock("next/navigation", async () => {
  const { routerMock: router } = await import("./router");

  return { useRouter: () => router };
});

beforeEach(() => {
  routerMock.replace.mockReset();
  routerMock.push.mockReset();
});

afterEach(() => {
  cleanup();
});
