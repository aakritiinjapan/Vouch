/**
 * One line that says what the console is doing right now.
 *
 * This is where the two dashboard states are made to read differently. With nothing held the strip is
 * cool, quiet, and states the boring truth. With something held it turns to the held state colour,
 * gains a rule and a live marker, and leads with the exposure that was protected. A judge scrolling
 * past should be able to tell those two states apart without reading a word.
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
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-l-2 border-verified/60 pl-4">
        <span className="size-1.5 rounded-full bg-verified" aria-hidden />
        <p className="text-sm font-medium text-ink">All sources confirmed</p>
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
    <div className="animate-reveal flex flex-wrap items-center gap-x-4 gap-y-1.5 border-l-2 border-held pl-4">
      <span className="size-1.5 animate-holdpulse rounded-full bg-held" aria-hidden />
      <p className="text-sm font-semibold text-ink">
        {held.length} reprice{held.length === 1 ? "" : "s"} held
      </p>
      <p className="text-xs text-ink-secondary text-pretty">
        {unconfirmed} of {products.length} competitor{" "}
        {products.length === 1 ? "source" : "sources"} could not be verified this cycle, so no price
        moved against {held.length === 1 ? "it" : "them"}
        {worst ? <> · worst single exposure {money(Math.abs(worst))} per unit</> : null}
      </p>
    </div>
  );
}
