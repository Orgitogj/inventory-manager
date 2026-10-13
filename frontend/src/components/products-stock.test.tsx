import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test } from "vitest";

import type { StockList } from "@/lib/api/client";
import {
  createFetchMock,
  errorResponse,
  jsonResponse,
  requestsTo,
  type Handler,
} from "@/test/fetch-mock";
import { SESSION } from "@/test/fixtures";
import { renderWithProviders } from "@/test/render";
import { routerMock } from "@/test/router";

import { PAGE_SIZE, ProductsStock } from "./products-stock";

const STOCK_PATH = "/api/v1/inventory/stock";

const LAPTOP = {
  product: {
    id: "0b7d2c1e-3f4a-4b5c-8d6e-7f8091a2b3c4",
    sku: "LAP-001",
    name: "Laptop",
  },
  quantity: 5,
};
const MOUSE = {
  product: {
    id: "1c8e3d2f-4a5b-4c6d-9e7f-8091a2b3c4d5",
    sku: "MOU-001",
    name: "Mouse",
  },
  quantity: 0,
};

function stockList(
  stock: StockList["stock"],
  total = stock.length,
  offset = 0,
): StockList {
  return { stock, total, limit: PAGE_SIZE, offset };
}

function renderProducts(stockHandler: Handler) {
  const fetchMock = createFetchMock({
    "GET /api/v1/auth/me": () => jsonResponse(SESSION),
    [`GET ${STOCK_PATH}`]: stockHandler,
  });

  renderWithProviders(<ProductsStock />, fetchMock);

  return fetchMock;
}

function queryOf(request: Request): URLSearchParams {
  return new URL(request.url).searchParams;
}

describe("ProductsStock", () => {
  test("renders a row for each product", async () => {
    const fetchMock = renderProducts(() =>
      jsonResponse(stockList([LAPTOP, MOUSE])),
    );

    expect(screen.getByRole("status")).toHaveTextContent("Loading products…");

    const laptop = await screen.findByRole("row", { name: /Laptop/ });

    expect(within(laptop).getByText("LAP-001")).toBeInTheDocument();
    expect(within(laptop).getByText("5")).toBeInTheDocument();
    expect(screen.getAllByRole("row")).toHaveLength(3);
    expect(screen.getByText("Showing 1–2 of 2")).toBeInTheDocument();

    const query = queryOf(requestsTo(fetchMock, STOCK_PATH)[0]);

    expect(query.get("limit")).toBe(String(PAGE_SIZE));
    expect(query.get("offset")).toBe("0");
    expect(query.has("search")).toBe(false);
  });

  test("marks products with zero stock", async () => {
    renderProducts(() => jsonResponse(stockList([LAPTOP, MOUSE])));

    const mouse = await screen.findByRole("row", { name: /Mouse/ });
    const laptop = screen.getByRole("row", { name: /Laptop/ });

    expect(within(mouse).getByText("Out of stock")).toBeInTheDocument();
    expect(mouse).toHaveAttribute("data-out-of-stock", "true");
    expect(within(laptop).queryByText("Out of stock")).not.toBeInTheDocument();
    expect(laptop).toHaveAttribute("data-out-of-stock", "false");
  });

  test("search updates the query after a short delay", async () => {
    const user = userEvent.setup();
    const fetchMock = renderProducts((request) =>
      jsonResponse(
        stockList(
          queryOf(request).get("search") === "lap" ? [LAPTOP] : [LAPTOP, MOUSE],
        ),
      ),
    );

    await screen.findByRole("row", { name: /Mouse/ });
    await user.type(screen.getByRole("searchbox"), "lap");

    await waitFor(() =>
      expect(
        screen.queryByRole("row", { name: /Mouse/ }),
      ).not.toBeInTheDocument(),
    );

    const searches = requestsTo(fetchMock, STOCK_PATH).map((request) =>
      queryOf(request).get("search"),
    );

    expect(searches).toEqual([null, "lap"]);
    expect(screen.getByRole("row", { name: /Laptop/ })).toBeInTheDocument();
  });

  test("pagination moves through the pages using the total", async () => {
    const user = userEvent.setup();
    const fetchMock = renderProducts((request) => {
      const offset = Number(queryOf(request).get("offset"));

      return jsonResponse(
        stockList(offset === 0 ? [LAPTOP] : [MOUSE], 21, offset),
      );
    });

    await screen.findByRole("row", { name: /Laptop/ });

    expect(screen.getByText("Showing 1–1 of 21")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "Next" }));
    await screen.findByRole("row", { name: /Mouse/ });

    expect(screen.getByText("Showing 21–21 of 21")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Previous" })).toBeEnabled();
    expect(
      requestsTo(fetchMock, STOCK_PATH).map((request) =>
        queryOf(request).get("offset"),
      ),
    ).toEqual(["0", String(PAGE_SIZE)]);
  });

  test("shows an empty state", async () => {
    renderProducts(() => jsonResponse(stockList([])));

    expect(await screen.findByText("No products yet.")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(screen.getByText("0 products")).toBeInTheDocument();
  });

  test("shows the error and retries on demand", async () => {
    const user = userEvent.setup();
    let failing = true;

    renderProducts(() =>
      failing
        ? errorResponse(
            503,
            "service_unavailable",
            "The service is temporarily unavailable.",
          )
        : jsonResponse(stockList([LAPTOP])),
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The service is temporarily unavailable.",
    );

    failing = false;
    await user.click(screen.getByRole("button", { name: "Try again" }));

    expect(
      await screen.findByRole("row", { name: /Laptop/ }),
    ).toBeInTheDocument();
  });

  test("an expired session sends the user to login", async () => {
    renderProducts(() =>
      errorResponse(401, "unauthenticated", "Login required."),
    );

    await waitFor(() =>
      expect(routerMock.replace).toHaveBeenCalledWith("/login"),
    );
  });
});
