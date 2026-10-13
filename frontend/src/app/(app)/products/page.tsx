import type { Metadata } from "next";

import { ProductsStock } from "@/components/products-stock";

export const metadata: Metadata = {
  title: "Products · Inventory Manager",
};

export default function ProductsPage() {
  return <ProductsStock />;
}
