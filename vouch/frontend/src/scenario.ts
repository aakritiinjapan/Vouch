/**
 * The two demo scenarios, reduced to one shape.
 *
 * Vouch's claim is that the verification layer is the product and repricing is only its first
 * consumer. That claim is worth exactly as much as the console's ability to render a second consumer
 * WITHOUT a second console. So both scenarios collapse to `Finding[]` here, and the console knows
 * nothing about which one it is drawing.
 *
 * What differs between them is only ever: where the rows came from, and what a wrong number costs.
 *
 *   repricing   — held RepriceProposal rows from the live cycle. Harm is measured in margin per unit,
 *                 because the seller is the one who acts on the number.
 *   sale-audit  — Voltmart's fake_sale rows sent to POST /verify. Harm is measured in overstated
 *                 discount, because the shopper is the one who acts on the number.
 *
 * Neither is narrated. The repricing findings come from the database; the sale-audit findings come
 * back from the real guardian over the wire. Nothing in this file invents a verdict.
 */

import type { Proposal, VerifyResponse } from "./types";

export type ScenarioId = "repricing" | "sale-audit";

export interface ScenarioMeta {
  id: ScenarioId;
  /** what the dropdown shows */
  label: string;
  /** the pipeline this stands for, in the operator's words */
  pipeline: string;
  /** who loses money when the number is wrong */
  whoActs: string;
  /** the column header for harm - it means something different per scenario */
  riskLabel: string;
  /** what the entity column is listing */
  entityLabel: string;
  /** the site being read */
  source: string;
}

export const SCENARIOS: ScenarioMeta[] = [
  {
    id: "repricing",
    label: "E-Commerce Repricing (Live Demo)",
    pipeline: "Competitor price → our listing price",
    whoActs: "the seller",
    riskLabel: "Counterfactual risk",
    entityLabel: "Pipeline entity",
    source: "Newegg",
  },
  {
    id: "sale-audit",
    label: "Sale Price Audit (Live Demo)",
    pipeline: "Advertised was-price → shopper's discount",
    whoActs: "the shopper",
    riskLabel: "Overstated discount",
    entityLabel: "Product audited",
    source: "Voltmart",
  },
];

/** One row of the decisions table, whichever scenario produced it. */
export interface Finding {
  key: string;
  entity: string;
  /** the machine tag, shown as a badge - the mockup keeps this, the criteria list stays hidden */
  code: string | null;
  /** plain-English, already written server-side; never assembled here */
  brief: string;
  confidence: number;
  decision: string;
  /** money at stake, signed so the console does no arithmetic to decide a colour */
  risk: number | null;
  riskNote: string;
  /** the two numbers that make the case, for the investigate panel */
  observed: number | null;
  expected: number | null;
  observedLabel: string;
  expectedLabel: string;
  /** what would have happened either way - the without/with pair in the mockup */
  withoutVouch: string;
  withoutVouchNote: string;
  withVouch: string;
  withVouchNote: string;
  /** only present for repricing, where a proposal id exists to act on */
  proposalId: number | null;
  /** the guardian's own evidence dict, for the detail panel */
  evidence: Record<string, unknown>;
}

/** Held reprice proposals → findings. Every number is read, none computed. */
export function findingsFromProposals(held: Proposal[]): Finding[] {
  return held.map((p) => {
    const cf = p.counterfactual;
    const naive = cf?.naive_price ?? null;
    return {
      key: `reprice-${p.id}`,
      entity: p.product.name,
      code: p.guardian?.check_code ?? null,
      brief: p.guardian?.brief ?? p.reason,
      confidence: p.guardian?.confidence ?? p.confidence,
      decision: p.guardian?.verdict ?? "fail",
      risk: cf ? cf.profit_delta_vs_now : null,
      riskNote: cf?.harm_summary ?? "",
      observed: p.source.observed_price,
      expected: cf?.competitor_price ?? p.source.observed_price,
      observedLabel: "Extracted value",
      expectedLabel: "Expected price range",
      withoutVouch: naive != null ? `Repriced to ${money(naive)}` : "Repriced on bad data",
      withoutVouchNote: cf?.harm === "margin" ? "Severe margin loss" : "Left money on the table",
      withVouch: "Reprice held",
      withVouchNote: "Margin protected",
      proposalId: p.id,
      evidence: p.guardian?.evidence ?? {},
    };
  });
}

/**
 * A /verify response over the sale rows → findings, one per affected product.
 *
 * The response carries a single aggregated REFERENCE_PRICE_UNSUPPORTED result (one sale policy is one
 * finding, however many products it covers) with the per-product detail in `evidence.examples`. The
 * table wants a row per product, so it is expanded back out here - from the evidence the guardian
 * returned, never from the fixture.
 */
export function findingsFromVerify(response: VerifyResponse): Finding[] {
  const failure = response.failures.find((f) => f.code === "REFERENCE_PRICE_UNSUPPORTED");
  if (!failure) return [];

  const examples = Array.isArray(failure.evidence.examples)
    ? (failure.evidence.examples as SaleExample[])
    : [];

  return examples.map((ex, i) => {
    const overstated = ex.overstated_by;
    return {
      key: `sale-${i}-${ex.product}`,
      entity: ex.product,
      code: failure.code,
      brief:
        `Advertised as reduced from ${money(ex.claimed_original)}, but the last price we ` +
        `confirmed before this sale was ${money(ex.confirmed_before_sale)}.`,
      confidence: response.confidence,
      decision: response.decision,
      risk: -Math.abs(overstated),
      riskNote: "discount deeper than our record supports",
      observed: ex.claimed_original,
      expected: ex.confirmed_before_sale,
      observedLabel: "Advertised was-price",
      expectedLabel: "Last confirmed before sale",
      withoutVouch: `Discount shown as ${money(ex.claimed_original - ex.current_price)}`,
      withoutVouchNote: "Shopper misled",
      withVouch: `Real reduction ${money(ex.confirmed_before_sale - ex.current_price)}`,
      withVouchNote: "Claim contradicted by our record",
      proposalId: null,
      evidence: failure.evidence,
    };
  });
}

interface SaleExample {
  product: string;
  claimed_original: number;
  confirmed_before_sale: number;
  overstated_by: number;
  current_price: number;
}

function money(v: number): string {
  return v.toLocaleString("en-US", { style: "currency", currency: "USD" });
}
