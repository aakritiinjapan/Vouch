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

export type ScenarioKey = "column-swap" | "clean" | "crossed-out" | "jobs-swap";

export interface Scenario {
  key: ScenarioKey;
  label: string;
  blurb: string;
  candidate: Row[];
  /** Defaults to the price BASELINE. A non-price scenario brings its own reference. */
  baseline?: Row[];
  /** Caller-supplied invariant pairs — the "bring your own schema" knob. */
  orderings?: [string, string][];
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

// A NON-price schema, to prove the endpoint isn't pinned to e-commerce. A jobs feed whose heal
// swapped min/max salary; the ranges overlap, so distributions can't tell — only the caller's own
// `orderings` invariant (min_salary ≤ max_salary) catches it. All salaries in $k.
const JOBS_BASELINE: Row[] = [
  { role: "Backend Engineer", min_salary: 120, max_salary: 160 },
  { role: "Data Analyst", min_salary: 90, max_salary: 120 },
  { role: "Product Manager", min_salary: 130, max_salary: 170 },
  { role: "Designer", min_salary: 100, max_salary: 135 },
  { role: "Site Reliability Eng", min_salary: 140, max_salary: 180 },
  { role: "Recruiter", min_salary: 80, max_salary: 110 },
];

const JOBS_SWAPPED: Row[] = [
  { role: "Backend Engineer", min_salary: 160, max_salary: 120 },
  { role: "Data Analyst", min_salary: 120, max_salary: 90 },
  { role: "Product Manager", min_salary: 170, max_salary: 130 },
  { role: "Designer", min_salary: 135, max_salary: 100 },
  { role: "Site Reliability Eng", min_salary: 180, max_salary: 140 },
  { role: "Recruiter", min_salary: 110, max_salary: 80 },
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
  {
    key: "jobs-swap",
    label: "Jobs feed · your own schema",
    blurb: "No price columns at all — a jobs feed with min/max salary swapped. Your own `orderings` invariant catches it.",
    candidate: JOBS_SWAPPED,
    baseline: JOBS_BASELINE,
    orderings: [["min_salary", "max_salary"]],
  },
];

export function scenarioByKey(key: string | null | undefined): Scenario {
  return SCENARIOS.find((s) => s.key === key) ?? SCENARIOS[0];
}
