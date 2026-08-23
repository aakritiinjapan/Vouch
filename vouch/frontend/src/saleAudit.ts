/**
 * The sale-audit scenario, GENERATED from vouch/testbed by scripts (see repo history).
 *
 * These are the real parsed rows of the Voltmart storefront: `candidate` is its fake_sale
 * variant, `baseline` is the same products on the clean page, and `referencePrices` is what each
 * one actually charged before the sale. They are sent verbatim to POST /verify, so the verdict
 * the console renders is computed by the real guardian over the real rows - not narrated here.
 *
 * Trimmed to the six deepest overstatements so the table stays readable. The verdict is computed
 * over exactly these rows, so nothing is withheld from the check.
 */

export const SALE_CANDIDATE = [
  {
    "name": "Voltmart RTX 5090 Titan Liquid 32GB",
    "price": 1714.99,
    "rating": 4.9,
    "in_stock": false,
    "original_price": 3919.98,
    "shipping": 24.99
  },
  {
    "name": "Voltmart RTX 5090 Founders Edition 32GB GDDR7",
    "price": 1399.99,
    "rating": 4.8,
    "in_stock": true,
    "original_price": 3199.98,
    "shipping": 24.99
  },
  {
    "name": "Voltmart RTX 4090 Gaming OC 24GB",
    "price": 1259.99,
    "rating": 4.8,
    "in_stock": false,
    "original_price": 2879.98,
    "shipping": 21.99
  },
  {
    "name": "Voltmart RTX 5080 Suprim Liquid X 16GB",
    "price": 944.99,
    "rating": 4.7,
    "in_stock": true,
    "original_price": 2159.98,
    "shipping": 22.99
  },
  {
    "name": "Voltmart RTX 5080 Stormbringer 16GB GDDR7",
    "price": 804.99,
    "rating": 4.6,
    "in_stock": true,
    "original_price": 1839.98,
    "shipping": 19.99
  }
] as const;

export const SALE_BASELINE = [
  {
    "name": "Voltmart RTX 5090 Titan Liquid 32GB",
    "price": 2449.99,
    "rating": 4.9,
    "in_stock": false,
    "original_price": 2599.99,
    "shipping": 24.99
  },
  {
    "name": "Voltmart RTX 5090 Founders Edition 32GB GDDR7",
    "price": 1999.99,
    "rating": 4.8,
    "in_stock": true,
    "original_price": 2199.99,
    "shipping": 24.99
  },
  {
    "name": "Voltmart RTX 4090 Gaming OC 24GB",
    "price": 1799.99,
    "rating": 4.8,
    "in_stock": false,
    "original_price": 1949.99,
    "shipping": 21.99
  },
  {
    "name": "Voltmart RTX 5080 Suprim Liquid X 16GB",
    "price": 1349.99,
    "rating": 4.7,
    "in_stock": true,
    "original_price": 1449.99,
    "shipping": 22.99
  },
  {
    "name": "Voltmart RTX 5080 Stormbringer 16GB GDDR7",
    "price": 1149.99,
    "rating": 4.6,
    "in_stock": true,
    "original_price": 1279.99,
    "shipping": 19.99
  }
] as const;

export const SALE_REFERENCE_PRICES: Record<string, number> = {
  "Voltmart RTX 5090 Titan Liquid 32GB": 2449.99,
  "Voltmart RTX 5090 Founders Edition 32GB GDDR7": 1999.99,
  "Voltmart RTX 4090 Gaming OC 24GB": 1799.99,
  "Voltmart RTX 5080 Suprim Liquid X 16GB": 1349.99,
  "Voltmart RTX 5080 Stormbringer 16GB GDDR7": 1149.99
};
