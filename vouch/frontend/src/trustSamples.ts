/**
 * Deterministic sample rows for the Trust API demo.
 *
 * These are the real fixture runs of the Newegg GPU collector (backend
 * tests/fixtures/sample_runs.json): one last-known-good baseline and three candidate heals. They are
 * sent verbatim to the live POST /verify so the demo is deterministic AND genuinely round-trips the
 * real guardian, not a mock. `column-swap` reads SHIPPING as the price (distributions catch it);
 * `crossed-out` reads the crossed-out ORIGINAL price (only the ordering invariant catches it);
 * `clean` is a correct self-heal that must PASS.
 */

export type Row = Record<string, unknown>;

export type ScenarioKey = "column-swap" | "clean" | "crossed-out";

export interface Scenario {
  key: ScenarioKey;
  label: string;
  blurb: string;
  candidate: Row[];
}

// Last-known-good reference the candidate is judged against.
export const BASELINE: Row[] = [
  { name: "MSI RTX 5080 Gaming Trio", price: 1299.99, shipping: 19.99, rating: 4.6, in_stock: true, original_price: 1499.99 },
  { name: "ASUS TUF RTX 5080 OC", price: 1249.0, shipping: 15.0, rating: 4.5, in_stock: true, original_price: 1449.0 },
  { name: "Gigabyte RTX 5080 Aorus", price: 1399.99, shipping: 24.99, rating: 4.7, in_stock: false, original_price: 1599.99 },
  { name: "ASUS ROG Astral RTX 5090", price: 1999.0, shipping: 29.99, rating: 4.8, in_stock: true, original_price: 2199.0 },
  { name: "MSI RTX 5090 Suprim Liquid", price: 2099.99, shipping: 0.0, rating: 4.4, in_stock: true, original_price: 2299.99 },
  { name: "Gigabyte RTX 5070 Ti Eagle", price: 749.99, shipping: 14.99, rating: 4.3, in_stock: true, original_price: 869.99 },
  { name: "ASUS Prime RTX 5070", price: 599.0, shipping: 12.99, rating: 4.2, in_stock: true, original_price: 699.0 },
  { name: "MSI RTX 5070 Ventus 3X", price: 629.99, shipping: 18.5, rating: 4.1, in_stock: false, original_price: 729.99 },
];

const HEALED_GOOD: Row[] = [
  { name: "MSI RTX 5080 Gaming Trio", price: 1289.99, shipping: 19.99, rating: 4.6, in_stock: true, original_price: 1499.99 },
  { name: "ASUS TUF RTX 5080 OC", price: 1259.0, shipping: 15.0, rating: 4.5, in_stock: true, original_price: 1449.0 },
  { name: "Gigabyte RTX 5080 Aorus", price: 1379.99, shipping: 24.99, rating: 4.7, in_stock: true, original_price: 1599.99 },
  { name: "ASUS ROG Astral RTX 5090", price: 1979.0, shipping: 29.99, rating: 4.8, in_stock: true, original_price: 2199.0 },
  { name: "MSI RTX 5090 Suprim Liquid", price: 2149.99, shipping: 0.0, rating: 4.4, in_stock: true, original_price: 2299.99 },
  { name: "Gigabyte RTX 5070 Ti Eagle", price: 739.99, shipping: 14.99, rating: 4.3, in_stock: true, original_price: 869.99 },
  { name: "ASUS Prime RTX 5070", price: 609.0, shipping: 12.99, rating: 4.2, in_stock: true, original_price: 699.0 },
  { name: "MSI RTX 5070 Ventus 3X", price: 639.99, shipping: 18.5, rating: 4.1, in_stock: true, original_price: 729.99 },
];

const HEALED_SWAPPED: Row[] = [
  { name: "MSI RTX 5080 Gaming Trio", price: 19.99, shipping: 1299.99, rating: 4.6, in_stock: true, original_price: 1499.99 },
  { name: "ASUS TUF RTX 5080 OC", price: 15.0, shipping: 1249.0, rating: 4.5, in_stock: true, original_price: 1449.0 },
  { name: "Gigabyte RTX 5080 Aorus", price: 24.99, shipping: 1399.99, rating: 4.7, in_stock: false, original_price: 1599.99 },
  { name: "ASUS ROG Astral RTX 5090", price: 29.99, shipping: 1999.0, rating: 4.8, in_stock: true, original_price: 2199.0 },
  { name: "MSI RTX 5090 Suprim Liquid", price: 0.0, shipping: 2099.99, rating: 4.4, in_stock: true, original_price: 2299.99 },
  { name: "Gigabyte RTX 5070 Ti Eagle", price: 14.99, shipping: 749.99, rating: 4.3, in_stock: true, original_price: 869.99 },
  { name: "ASUS Prime RTX 5070", price: 12.99, shipping: 599.0, rating: 4.2, in_stock: true, original_price: 699.0 },
  { name: "MSI RTX 5070 Ventus 3X", price: 18.5, shipping: 629.99, rating: 4.1, in_stock: false, original_price: 729.99 },
];

const HEALED_SWAPPED_ORIGINAL: Row[] = [
  { name: "MSI RTX 5080 Gaming Trio", price: 1499.99, shipping: 19.99, rating: 4.6, in_stock: true, original_price: 1299.99 },
  { name: "ASUS TUF RTX 5080 OC", price: 1449.0, shipping: 15.0, rating: 4.5, in_stock: true, original_price: 1249.0 },
  { name: "Gigabyte RTX 5080 Aorus", price: 1599.99, shipping: 24.99, rating: 4.7, in_stock: false, original_price: 1399.99 },
  { name: "ASUS ROG Astral RTX 5090", price: 2199.0, shipping: 29.99, rating: 4.8, in_stock: true, original_price: 1999.0 },
  { name: "MSI RTX 5090 Suprim Liquid", price: 2299.99, shipping: 0.0, rating: 4.4, in_stock: true, original_price: 2099.99 },
  { name: "Gigabyte RTX 5070 Ti Eagle", price: 869.99, shipping: 14.99, rating: 4.3, in_stock: true, original_price: 749.99 },
  { name: "ASUS Prime RTX 5070", price: 699.0, shipping: 12.99, rating: 4.2, in_stock: true, original_price: 599.0 },
  { name: "MSI RTX 5070 Ventus 3X", price: 729.99, shipping: 18.5, rating: 4.1, in_stock: false, original_price: 629.99 },
];

export const SCENARIOS: Scenario[] = [
  {
    key: "column-swap",
    label: "Column swap",
    blurb: "The heal read the SHIPPING column as the price (~100× off — distributions catch it).",
    candidate: HEALED_SWAPPED,
  },
  {
    key: "clean",
    label: "Clean heal",
    blurb: "A correct self-heal — same meaning, small drift. Must PASS.",
    candidate: HEALED_GOOD,
  },
  {
    key: "crossed-out",
    label: "Crossed-out (was) price",
    blurb: "The heal read the crossed-out ORIGINAL price (~14% off — only the ordering invariant sees it).",
    candidate: HEALED_SWAPPED_ORIGINAL,
  },
];

export function scenarioByKey(key: string | null | undefined): Scenario {
  return SCENARIOS.find((s) => s.key === key) ?? SCENARIOS[0];
}
