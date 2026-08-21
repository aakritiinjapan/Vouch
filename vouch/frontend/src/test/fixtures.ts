/** Builders for test data that mirror the backend schema shapes. */

import type {
  Counterfactual,
  DemoHints,
  Guardian,
  HealEvent,
  Product,
  Proposal,
} from "../types";

export function makeProduct(over: Partial<Product> = {}): Product {
  return {
    id: 1,
    sku: "GPU-5080",
    name: "MSI RTX 5080 Gaming Trio",
    my_price: 1279.99,
    cost: 1000,
    floor_margin: 0.1,
    floor_price: 1100,
    margin_pct: 0.22,
    competitor_url: "https://www.newegg.com/msi-rtx-5080",
    collector_id: "gd_collector_abc",
    last_confirmed_price: 1299.99,
    last_confirmed_at: "2026-08-22T10:00:00Z",
    last_confirmed_label: "confirmed 2m ago",
    source_confirmed: true,
    held_proposal_id: null,
    updated_at: "2026-08-22T10:00:00Z",
    ...over,
  };
}

export function makeGuardian(over: Partial<Guardian> = {}): Guardian {
  return {
    heal_event_id: 10,
    collector_id: "gd_collector_abc",
    verdict: "FAIL",
    confidence: 40,
    check_code: "COLUMN_SWAP",
    brief: "'price' matches the distribution of 'shipping'.",
    evidence: { looks_like: "shipping", field: "price" },
    attempt: 2,
    attempts_total: 2,
    prompt: "'price' was reading SHIPPING. Re-extract the item's own current sale price.",
    ...over,
  };
}

export function makeCounterfactual(over: Partial<Counterfactual> = {}): Counterfactual {
  return {
    competitor_price: 19.99,
    current_price: 1279.99,
    floor_price: 1100,
    applied_price: 1100,
    applied_reason: "clamped to floor",
    naive_price: 19.98,
    margin_pct_now: 0.22,
    margin_pct_applied: 0.09,
    margin_pct_naive: -0.98,
    profit_per_unit_now: 279.99,
    profit_per_unit_applied: 100,
    profit_per_unit_naive: -980,
    profit_delta_vs_now: -179.99,
    harm: "margin",
    harm_summary: "Acting on this would have cut margin from 22% to 9%.",
    source: "newegg.com",
    ...over,
  };
}

export function makeHeld(over: Partial<Proposal> = {}): Proposal {
  return {
    id: 101,
    status: "held",
    confidence: 40,
    current_price: 1279.99,
    proposed_price: 1100,
    delta: -179.99,
    delta_pct: -0.14,
    reason: "Source could not be verified.",
    created_at: "2026-08-22T10:00:00Z",
    created_label: "2m ago",
    decided_at: null,
    floor_price: 1100,
    margin_pct_now: 0.22,
    margin_pct_after: 0.09,
    is_safe: false,
    safe_reason: null,
    product: { id: 1, sku: "GPU-5080", name: "MSI RTX 5080 Gaming Trio" },
    source: {
      url: "https://www.newegg.com/msi-rtx-5080",
      confirmed: false,
      observed_price: 19.99,
      last_confirmed_at: "2026-08-22T09:00:00Z",
      last_confirmed_label: "last good 1h ago",
    },
    guardian: makeGuardian(),
    counterfactual: makeCounterfactual(),
    ...over,
  };
}

export function makePending(over: Partial<Proposal> = {}): Proposal {
  return {
    id: 201,
    status: "pending",
    confidence: 100,
    current_price: 549,
    proposed_price: 541,
    delta: -8,
    delta_pct: -0.014,
    reason: "Competitor moved.",
    created_at: "2026-08-22T10:00:00Z",
    created_label: "2m ago",
    decided_at: null,
    floor_price: 480,
    margin_pct_now: 0.2,
    margin_pct_after: 0.19,
    is_safe: true,
    safe_reason: "within safe band",
    product: { id: 2, sku: "GPU-4070", name: "NVIDIA RTX 4070" },
    source: {
      url: "https://www.newegg.com/rtx-4070",
      confirmed: true,
      observed_price: 541,
      last_confirmed_at: "2026-08-22T10:00:00Z",
      last_confirmed_label: "confirmed 2m ago",
    },
    guardian: null,
    counterfactual: null,
    ...over,
  };
}

export function makeHealEvent(over: Partial<HealEvent> = {}): HealEvent {
  return {
    id: 10,
    cycle_id: "cyc_1",
    collector_id: "gd_collector_abc",
    attempt: 2,
    verdict: "FAIL",
    proposed_confidence: 40,
    primary_check_code: "COLUMN_SWAP",
    risk_brief: "mixed up two columns",
    prompt: "Re-extract the item's own current sale price.",
    trigger_reason: "NULL_SPIKE",
    status: "rejected",
    created_at: "2026-08-22T10:00:00Z",
    created_label: "2m ago",
    product: { id: 1, sku: "GPU-5080", name: "MSI RTX 5080 Gaming Trio" },
    entries: [
      { kind: "run", text: "1 competitor price empty" },
      { kind: "heal", text: "scraper auto-fixed itself" },
      { kind: "verdict", text: "guardian checked it" },
    ],
    ...over,
  };
}

export function makeHints(over: Partial<DemoHints> = {}): DemoHints {
  return {
    mock_mode: true,
    dataset: "gpu",
    dataset_note: "8 GPUs from Newegg",
    hints: [
      { key: "healed_swapped", label: "Simulate: shipping-price swap", detail: "read shipping as price", stage: "heal" },
    ],
    ...over,
  };
}
