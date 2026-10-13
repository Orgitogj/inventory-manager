import { vi } from "vitest";

export const routerMock = {
  replace: vi.fn<(href: string) => void>(),
  push: vi.fn<(href: string) => void>(),
};
