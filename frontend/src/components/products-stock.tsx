"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { errorMessage } from "@/lib/api/errors";
import { useApi } from "@/lib/auth/auth-context";
import { useDebouncedValue } from "@/lib/use-debounced-value";

export const PAGE_SIZE = 20;
export const SEARCH_DELAY_MS = 300;

const BUTTON_CLASS =
  "rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 shadow-sm hover:bg-slate-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600 disabled:cursor-not-allowed disabled:opacity-50";

export function ProductsStock() {
  const api = useApi();
  const [searchInput, setSearchInput] = useState("");
  const [offset, setOffset] = useState(0);
  const search = useDebouncedValue(searchInput.trim(), SEARCH_DELAY_MS);

  const { data, error, isPending, isError, isFetching, refetch } = useQuery({
    queryKey: ["inventory", "stock", { search, limit: PAGE_SIZE, offset }],
    queryFn: async ({ signal }) => {
      const { data } = await api.GET("/api/v1/inventory/stock", {
        params: {
          query: {
            search: search === "" ? undefined : search,
            limit: PAGE_SIZE,
            offset,
          },
        },
        signal,
      });

      if (data === undefined) {
        throw new Error("Empty stock response.");
      }

      return data;
    },
    placeholderData: keepPreviousData,
  });

  function handleSearchChange(value: string) {
    setSearchInput(value);
    setOffset(0);
  }

  const total = data?.total ?? 0;
  const rows = data?.stock ?? [];
  const firstRow = total === 0 ? 0 : (data?.offset ?? 0) + 1;
  const lastRow = (data?.offset ?? 0) + rows.length;
  const hasPrevious = offset > 0;
  const hasNext = offset + PAGE_SIZE < total;

  return (
    <section aria-labelledby="products-heading" className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <h1 id="products-heading" className="text-xl font-semibold">
          Products
        </h1>
        <div className="w-full sm:w-72">
          <label htmlFor="product-search" className="sr-only">
            Search products
          </label>
          <input
            id="product-search"
            type="search"
            placeholder="Search by name or SKU"
            maxLength={200}
            value={searchInput}
            onChange={(event) => handleSearchChange(event.target.value)}
            className="block w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm placeholder:text-slate-400 focus:border-indigo-600 focus:outline-none focus:ring-2 focus:ring-indigo-600/40"
          />
        </div>
      </div>

      {isPending ? (
        <p role="status" className="py-10 text-center text-sm text-slate-600">
          Loading products…
        </p>
      ) : isError ? (
        <div
          role="alert"
          className="space-y-3 rounded-md border border-red-200 bg-red-50 px-4 py-6 text-center text-sm text-red-800"
        >
          <p>{errorMessage(error)}</p>
          <button
            type="button"
            onClick={() => void refetch()}
            className={BUTTON_CLASS}
          >
            Try again
          </button>
        </div>
      ) : rows.length === 0 ? (
        <p className="rounded-md border border-dashed border-slate-300 bg-white py-10 text-center text-sm text-slate-600">
          {search === ""
            ? "No products yet."
            : `No products match “${search}”.`}
        </p>
      ) : (
        <div
          className="overflow-x-auto rounded-lg border border-slate-200 bg-white shadow-sm"
          aria-busy={isFetching}
        >
          <table className="min-w-full divide-y divide-slate-200 text-sm">
            <caption className="sr-only">Products with current stock</caption>
            <thead className="bg-slate-50 text-left text-xs font-semibold tracking-wide text-slate-600 uppercase">
              <tr>
                <th scope="col" className="px-4 py-3">
                  SKU
                </th>
                <th scope="col" className="px-4 py-3">
                  Name
                </th>
                <th scope="col" className="px-4 py-3 text-right">
                  Quantity
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {rows.map(({ product, quantity }) => {
                const outOfStock = quantity === 0;

                return (
                  <tr
                    key={product.id}
                    data-out-of-stock={outOfStock}
                    className={outOfStock ? "bg-red-50/60" : undefined}
                  >
                    <td className="px-4 py-3 font-mono text-xs whitespace-nowrap text-slate-700">
                      {product.sku}
                    </td>
                    <th scope="row" className="px-4 py-3 text-left font-medium">
                      {product.name}
                    </th>
                    <td className="px-4 py-3 text-right whitespace-nowrap tabular-nums">
                      {outOfStock && (
                        <span className="mr-2 rounded-full bg-red-100 px-2 py-0.5 text-xs font-semibold text-red-800">
                          Out of stock
                        </span>
                      )}
                      <span className={outOfStock ? "text-red-800" : undefined}>
                        {quantity}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {!isPending && !isError && (
        <nav
          aria-label="Pagination"
          className="flex flex-wrap items-center justify-between gap-3 text-sm text-slate-600"
        >
          <p aria-live="polite">
            {total === 0
              ? "0 products"
              : `Showing ${firstRow}–${lastRow} of ${total}`}
          </p>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
              disabled={!hasPrevious}
              className={BUTTON_CLASS}
            >
              Previous
            </button>
            <button
              type="button"
              onClick={() => setOffset(offset + PAGE_SIZE)}
              disabled={!hasNext}
              className={BUTTON_CLASS}
            >
              Next
            </button>
          </div>
        </nav>
      )}
    </section>
  );
}
