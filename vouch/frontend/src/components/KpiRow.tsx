/**
 * Three stat tiles. Sentence-case labels, semibold values, and a qualifier line that names what the
 * number is measured against - a bare number with no reference point is decoration.
 */

import { money, pct } from "../format";
import type { Product, Proposal } from "../types";

function Tile({
  label,
  value,
  qualifier,
  tone = "default",
}: {
  label: string;
  value: string;
  qualifier: string;
  tone?: "default" | "critical" | "good";
}) {
  const valueTone = {
    default: "text-ink",
    critical: "text-status-critical",
    good: "text-status-good",
  }[tone];

  return (
    <div className="rounded-lg bg-surface px-4 py-3 shadow-card">
      <p className="text-xs text-ink-muted">{label}</p>
      <p className={`mt-1 text-2xl font-semibold leading-none ${valueTone}`}>{value}</p>
      <p className="mt-1 text-[11px] text-ink-muted">{qualifier}</p>
    </div>
  );
}

export function KpiRow({
  products,
  pending,
  held,
}: {
  products: Product[];
  pending: Proposal[];
  held: Proposal[];
}) {
  // Margin at risk: what acting on every held proposal would have cost, per unit, summed.
  const marginAtRisk = held.reduce(
    (total, p) => total + Math.abs(p.counterfactual?.profit_delta_vs_now ?? 0),
    0,
  );
  const unconfirmed = products.filter((p) => !p.source_confirmed).length;
  const avgMargin =
    products.length > 0
      ? products.reduce((t, p) => t + (p.margin_pct ?? 0), 0) / products.length
      : null;

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
      <Tile
        label="Margin protected"
        value={money(marginAtRisk, 0)}
        qualifier={
          held.length === 0
            ? "no reprices held this cycle"
            : `per unit, across ${held.length} held reprice${held.length === 1 ? "" : "s"}`
        }
        tone={marginAtRisk > 0 ? "good" : "default"}
      />
      <Tile
        label="Sources unconfirmed"
        value={String(unconfirmed)}
        qualifier={`of ${products.length} competitor source${products.length === 1 ? "" : "s"}`}
        tone={unconfirmed > 0 ? "critical" : "default"}
      />
      <Tile
        label="Average margin"
        value={pct(avgMargin)}
        qualifier={`${pending.length} routine change${pending.length === 1 ? "" : "s"} awaiting review`}
      />
    </div>
  );
}
