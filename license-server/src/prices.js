import prices from "../prices.json" with { type: "json" };

export const PRODUCTS = ["bt", "ff", "both"];
export const CHECK_PRODUCTS = ["bt", "ff"];

export function priceRow(product, catalog = prices) {
  return catalog.products?.[product] || null;
}

export function formatPrice(product, catalog = prices) {
  const row = priceRow(product, catalog);
  if (!row || typeof row.amount_cents !== "number") return "";
  const amount = (row.amount_cents / 100).toFixed(2);
  const currency = String(catalog.currency || "usd").toUpperCase();
  const interval = catalog.interval || "month";
  return `${amount} ${currency}/${interval}`;
}

export function pricePayload(product, catalog = prices) {
  const row = priceRow(product, catalog);
  if (!row) return null;
  return {
    label: row.label,
    amount_cents: row.amount_cents,
    currency: catalog.currency || "usd",
    interval: catalog.interval || "month",
    display: formatPrice(product, catalog),
  };
}

export { prices };
