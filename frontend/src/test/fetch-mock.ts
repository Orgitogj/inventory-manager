import { vi } from "vitest";

export type Handler = (request: Request) => Response | Promise<Response>;

export const BASE_URL = "http://localhost";

export function jsonResponse(
  body: unknown,
  status = 200,
  headers: Record<string, string> = {},
): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...headers },
  });
}

export function errorResponse(
  status: number,
  code: string,
  message: string,
  headers: Record<string, string> = {},
  details?: { field: string; message: string }[],
): Response {
  const error =
    details === undefined ? { code, message } : { code, message, details };

  return jsonResponse({ error }, status, headers);
}

export function createFetchMock(handlers: Record<string, Handler>) {
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const request = input instanceof Request ? input : new Request(input, init);
    const handler =
      handlers[`${request.method} ${new URL(request.url).pathname}`];

    if (handler === undefined) {
      return errorResponse(404, "not_found", "Not Found");
    }

    return handler(request);
  });
}

export type FetchMock = ReturnType<typeof createFetchMock>;

export function requestsTo(fetchMock: FetchMock, path: string): Request[] {
  return fetchMock.mock.calls
    .map(([input]) => input)
    .filter((input): input is Request => input instanceof Request)
    .filter((request) => new URL(request.url).pathname === path);
}
