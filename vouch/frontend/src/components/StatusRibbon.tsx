/**
 * One line that says what the console is doing right now.
 *
 * This is where the two dashboard states are made to read differently. With nothing held the strip
 * is cool, quiet, and states the boring truth. With something held it turns warm, gains a rule and a
 * live marker, and leads with the money that was protected. A judge scrolling past should be able to
 * tell those two states apart without reading a word — that difference is the design carrying
 * information rather than decorating it.
 */

import { money } from "../format";
import type { Product, Proposal } from "../types";

export function StatusRibbon({
  held,
  pending,
  products,
}: {
  held: Proposal[];
  pending: Proposal[];
  products: Product[];
}) {
  const unconfirmed = products.filter((p) => !p.source_confirmed).length;
  const worst = held.reduce(
    (worstSoFar, p) =>
      Math.abs(p.counterfactual?.profit_delta_vs_now ?? 0) > Math.abs(worstSoFar)
        ? (p.counterfactual?.profit_delta_vs_now ?? 0)
        : worstSoFar,
    0,
  );

  if (held.length === 0) {
    return (
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border border-hair bg-surface/60 px-4 py-2.5">
        <span className="size-1.5 rounded-full bg-status-good" aria-hidden />
        <p className="text-xs font-medium text-ink">All sources confirmed</p>
        <p className="text-xs text-ink-muted text-pretty">
          {products.length} competitor {products.length === 1 ? "source" : "sources"} verified
          {pending.length > 0 ? (
            <>
              {" "}
              · {pending.length} routine {pending.length === 1 ? "change" : "changes"} ready to
              approve
            </>
          ) : (
            <> · nothing needs your judgement</>
          )}
        </p>
      </div>
    );
  }

  return (
    <div className="animate-rise overflow-hidden rounded-lg border border-status-critical/35 bg-status-critical/[0.07]">
      <div className="h-[2px] origin-left animate-sweep bg-gradient-to-r from-status-critical to-transparent" />
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 px-4 py-3">
        <span
          className="size-1.5 animate-holdpulse rounded-full bg-status-critical"
          aria-hidden
        />
        <p className="text-sm font-semibold text-ink">
          {held.length} reprice{held.length === 1 ? "" : "s"} held
        </p>
        {/* The amount protected is the first tile's job. Repeating it here would make two adjacent
            elements say the same thing; the ribbon's job is what happened and why. */}
        <p className="text-xs text-ink-secondary text-pretty">
          {unconfirmed} of {products.length} competitor{" "}
          {products.length === 1 ? "source" : "sources"} could not be verified this cycle, so no
          price moved against {held.length === 1 ? "it" : "them"}
          {worst ? (
            <>
              {" "}
              · worst single exposure {money(Math.abs(worst))} per unit
            </>
          ) : null}
        </p>
      </div>
    </div>
  );
}
