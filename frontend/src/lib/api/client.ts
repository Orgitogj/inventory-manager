import createClient, { type Client, type Middleware } from "openapi-fetch";

import { toApiError } from "./errors";
import type { components, paths } from "./schema";

export type ApiClient = Client<paths>;
export type Session = components["schemas"]["SessionOut"];
export type User = components["schemas"]["UserOut"];
export type StockList = components["schemas"]["StockListOut"];

export type ApiClientOptions = {
  getCsrfToken: () => string | null;
  onUnauthorized: () => void;
  baseUrl?: string;
  fetch?: typeof globalThis.fetch;
};

export const CSRF_HEADER = "X-CSRF-Token";
export const LOGIN_PATH = "/api/v1/auth/login";

const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

export function needsCsrfToken(method: string): boolean {
  return !SAFE_METHODS.has(method.toUpperCase());
}

export function createApiClient(options: ApiClientOptions): ApiClient {
  const middleware: Middleware = {
    onRequest({ request }) {
      const token = options.getCsrfToken();

      if (token !== null && needsCsrfToken(request.method)) {
        request.headers.set(CSRF_HEADER, token);
      }

      return request;
    },
    async onResponse({ request, response }) {
      if (response.ok) {
        return response;
      }

      const error = await toApiError(response);
      const isLogin = new URL(request.url).pathname === LOGIN_PATH;

      if (error.status === 401 && !isLogin) {
        options.onUnauthorized();
      }

      throw error;
    },
  };

  const client = createClient<paths>({
    baseUrl: options.baseUrl ?? "",
    credentials: "same-origin",
    fetch: options.fetch,
  });
  client.use(middleware);

  return client;
}
