/**
 * The trust metrics — three readings across the top of the console, repurposed from the old KPIs to
 * speak in the product's own terms: bad reprices caught, margin protected, and source coverage. Each
 * figure names what it is measured against; a bare number is decoration, not a reading.
 */

import { money } from "../format";
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
    <div className="relative overflow-hidden rounded-xl border border-hair bg-surface px-4 py-3 shadow-card">
      <div className="pointer-events-none absolute inset-x-0 top-0 h-0.5 bg-holo-cta opacity-40" />
      <p className="eyebrow">{label}</p>
      <p className={`num mt-1.5 text-2xl font-bold leading-none ${valueTone}`}>{value}</p>
      <p className="mt-1.5 text-[11px] text-ink-muted text-pretty">{qualifier}</p>
    </div>
  );
}

export function TrustMetrics({
  products,
  held,
}: {
  products: Product[];
  held: Proposal[];
}) {
  const marginProtected = held.reduce(
    (total, p) => total + Math.abs(p.counterfactual?.profit_delta_vs_now ?? 0),
    0,
  );
  const unconfirmed = products.filter((p) => !p.source_confirmed).length;
  const confirmed = products.length - unconfirmed;

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
      <Tile
        label="Bad reprices caught"
        value={String(held.length)}
        qualifier={
          held.length === 0
            ? "nothing blocked this cycle"
            : "blocked before acting on bad data"
        }
        tone={held.length > 0 ? "critical" : "default"}
      />
      <Tile
        label="Margin protected"
        value={money(marginProtected, 0)}
        qualifier={
          held.length === 0
            ? "no reprices held this cycle"
            : `margin bad data would have cost, per unit`
        }
        tone={marginProtected > 0 ? "good" : "default"}
      />
      <Tile
        label="Sources"
        value={`${confirmed} ok · ${unconfirmed} held`}
        qualifier={`of ${products.length} tracked vs Newegg`}
        tone={unconfirmed > 0 ? "critical" : "good"}
      />
    </div>
  );
}
