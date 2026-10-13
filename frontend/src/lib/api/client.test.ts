import { describe, expect, test, vi } from "vitest";

import {
  BASE_URL,
  createFetchMock,
  errorResponse,
  jsonResponse,
  requestsTo,
  type FetchMock,
} from "@/test/fetch-mock";
import { CSRF_TOKEN, SESSION } from "@/test/fixtures";

import { createApiClient, CSRF_HEADER, needsCsrfToken } from "./client";
import { ApiError, UNKNOWN_ERROR_CODE, UNKNOWN_ERROR_MESSAGE } from "./errors";

const PRODUCT_ID = "0b7d2c1e-3f4a-4b5c-8d6e-7f8091a2b3c4";
const ORDER_ID = "1c8e3d2f-4a5b-4c6d-9e7f-8091a2b3c4d5";
const PRODUCT_PATH = `/api/v1/products/${PRODUCT_ID}`;
const ORDER_ITEMS_PATH = `/api/v1/orders/${ORDER_ID}/items`;

function setup(
  fetchMock: FetchMock,
  getCsrfToken: () => string | null = () => CSRF_TOKEN,
) {
  const onUnauthorized = vi.fn();
  const client = createApiClient({
    baseUrl: BASE_URL,
    fetch: fetchMock,
    getCsrfToken,
    onUnauthorized,
  });

  return { client, onUnauthorized };
}

async function caught(promise: Promise<unknown>): Promise<unknown> {
  try {
    await promise;
  } catch (error) {
    return error;
  }

  throw new Error("Expected the request to fail.");
}

describe("CSRF header", () => {
  test.each(["POST", "PATCH", "PUT", "DELETE", "delete"])(
    "%s needs a token",
    (method) => {
      expect(needsCsrfToken(method)).toBe(true);
    },
  );

  test.each(["GET", "HEAD", "OPTIONS", "get"])(
    "%s does not need a token",
    (method) => {
      expect(needsCsrfToken(method)).toBe(false);
    },
  );

  test("is sent on POST, PATCH and PUT requests", async () => {
    const fetchMock = createFetchMock({
      "POST /api/v1/auth/logout": () => new Response(null, { status: 204 }),
      [`PATCH ${PRODUCT_PATH}`]: () => jsonResponse({}),
      [`PUT ${ORDER_ITEMS_PATH}`]: () => jsonResponse({}),
    });
    const { client } = setup(fetchMock);

    await client.POST("/api/v1/auth/logout");
    await client.PATCH("/api/v1/products/{product_id}", {
      params: { path: { product_id: PRODUCT_ID } },
      body: { name: "Laptop" },
    });
    await client.PUT("/api/v1/orders/{order_id}/items", {
      params: { path: { order_id: ORDER_ID } },
      body: { items: [] },
    });

    const sent = fetchMock.mock.calls.map(([input]) => input as Request);

    expect(sent.map((request) => request.method)).toEqual([
      "POST",
      "PATCH",
      "PUT",
    ]);
    expect(sent.map((request) => request.headers.get(CSRF_HEADER))).toEqual([
      CSRF_TOKEN,
      CSRF_TOKEN,
      CSRF_TOKEN,
    ]);
  });

  test("is not sent on GET requests", async () => {
    const fetchMock = createFetchMock({
      "GET /api/v1/auth/me": () => jsonResponse(SESSION),
    });
    const { client } = setup(fetchMock);

    const { data } = await client.GET("/api/v1/auth/me");

    expect(data).toEqual(SESSION);
    expect(
      requestsTo(fetchMock, "/api/v1/auth/me")[0].headers.has(CSRF_HEADER),
    ).toBe(false);
  });

  test("is left out while there is no token", async () => {
    const fetchMock = createFetchMock({
      "POST /api/v1/auth/login": () => jsonResponse(SESSION),
    });
    const { client } = setup(fetchMock, () => null);

    await client.POST("/api/v1/auth/login", {
      body: { email: "ana@example.com", password: "example-password" },
    });

    expect(
      requestsTo(fetchMock, "/api/v1/auth/login")[0].headers.has(CSRF_HEADER),
    ).toBe(false);
  });
});

describe("error handling", () => {
  test("turns the backend error shape into an ApiError", async () => {
    const details = [{ field: "name", message: "Field required" }];
    const fetchMock = createFetchMock({
      "POST /api/v1/products": () =>
        errorResponse(422, "validation_error", "Invalid input.", {}, details),
    });
    const { client, onUnauthorized } = setup(fetchMock);

    const error = await caught(
      client.POST("/api/v1/products", {
        body: { sku: "LAP-1", name: "", unit_price: "10.00" } as never,
      }),
    );

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      status: 422,
      code: "validation_error",
      message: "Invalid input.",
      details,
      retryAfterSeconds: null,
    });
    expect(onUnauthorized).not.toHaveBeenCalled();
  });

  test("leaves details undefined when the backend sends none", async () => {
    const fetchMock = createFetchMock({
      [`GET ${PRODUCT_PATH}`]: () =>
        errorResponse(404, "not_found", "Product not found."),
    });
    const { client } = setup(fetchMock);

    const error = await caught(
      client.GET("/api/v1/products/{product_id}", {
        params: { path: { product_id: PRODUCT_ID } },
      }),
    );

    expect(error).toMatchObject({
      status: 404,
      code: "not_found",
      message: "Product not found.",
      details: undefined,
    });
  });

  test("reads Retry-After as seconds", async () => {
    const fetchMock = createFetchMock({
      "POST /api/v1/auth/login": () =>
        errorResponse(429, "too_many_attempts", "Too many attempts.", {
          "Retry-After": "840",
        }),
    });
    const { client } = setup(fetchMock);

    const error = await caught(
      client.POST("/api/v1/auth/login", {
        body: { email: "ana@example.com", password: "example-password" },
      }),
    );

    expect(error).toMatchObject({ status: 429, retryAfterSeconds: 840 });
  });

  test("falls back to a generic error for a non-JSON body", async () => {
    const fetchMock = createFetchMock({
      "GET /api/v1/inventory/stock": () =>
        new Response("Internal Server Error", { status: 500 }),
    });
    const { client } = setup(fetchMock);

    const error = await caught(client.GET("/api/v1/inventory/stock"));

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      status: 500,
      code: UNKNOWN_ERROR_CODE,
      message: UNKNOWN_ERROR_MESSAGE,
    });
  });
});

describe("unauthorized responses", () => {
  test("a 401 calls the logout handler and still rejects", async () => {
    const fetchMock = createFetchMock({
      "GET /api/v1/inventory/stock": () =>
        errorResponse(401, "unauthenticated", "Login required."),
    });
    const { client, onUnauthorized } = setup(fetchMock);

    const error = await caught(client.GET("/api/v1/inventory/stock"));

    expect(error).toMatchObject({ status: 401, code: "unauthenticated" });
    expect(onUnauthorized).toHaveBeenCalledTimes(1);
  });

  test("a 401 from login does not call the logout handler", async () => {
    const fetchMock = createFetchMock({
      "POST /api/v1/auth/login": () =>
        errorResponse(401, "invalid_credentials", "Invalid email or password."),
    });
    const { client, onUnauthorized } = setup(fetchMock);

    const error = await caught(
      client.POST("/api/v1/auth/login", {
        body: { email: "ana@example.com", password: "example-password" },
      }),
    );

    expect(error).toMatchObject({ status: 401, code: "invalid_credentials" });
    expect(onUnauthorized).not.toHaveBeenCalled();
  });

  test("a 403 does not call the logout handler", async () => {
    const fetchMock = createFetchMock({
      "GET /api/v1/users": () =>
        errorResponse(403, "forbidden", "You do not have permission."),
    });
    const { client, onUnauthorized } = setup(fetchMock);

    await caught(client.GET("/api/v1/users"));

    expect(onUnauthorized).not.toHaveBeenCalled();
  });
});
