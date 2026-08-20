/**
 * Grouping held reprices into incidents.
 *
 * Several products price against the same competitor page, so they share one Scraper Studio
 * collector. A layout change is therefore ONE event that puts SEVERAL reprices on hold. Rendering
 * one card per product told the viewer there were three problems when there was one, which is both
 * harder to read and less accurate.
 *
 * Grouping happens here, not in JSX, so it can be reasoned about and tested on its own.
 */

import type { Proposal } from "./types";

export interface Incident {
  /** Stable key: one bad heal on one collector. */
  key: string;
  collectorId: string;
  /** e.g. "COLUMN_SWAP" - null if the guardian reported no specific check. */
  checkCode: string | null;
  /** The guardian's own sentence. Identical across the group, so stated once. */
  brief: string;
  confidence: number;
  /** Which attempt of how many the hold rests on. */
  attempt: number;
  attemptsTotal: number;
  /** How stale this source is, in the backend's words. */
  staleness: string;
  sourceHost: string;
  /** The row-level price the bad fix read, if the guardian recorded one. */
  observedPrice: number | null;
  /** Which way it hurt. Mixed groups fall back to "margin". */
  harm: "margin" | "competitiveness" | "none";
  /** Per-unit exposure summed across every product on hold. */
  totalExposure: number;
  /** Worst single product, for the headline when a group has one obvious victim. */
  worst: Proposal | null;
  /** Every held reprice this one bad fix caused, worst first. */
  proposals: Proposal[];
}

function hostOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

function exposureOf(proposal: Proposal): number {
  return Math.abs(proposal.counterfactual?.profit_delta_vs_now ?? 0);
}

/**
 * Collapse held proposals into one incident per (collector, bad heal).
 *
 * Keyed on collector + heal event rather than collector alone: two separate layout changes on the
 * same page a day apart are genuinely two incidents, and merging them would hide one.
 */
export function groupIntoIncidents(held: Proposal[]): Incident[] {
  const byKey = new Map<string, Proposal[]>();

  for (const proposal of held) {
    const guardian = proposal.guardian;
    const key = guardian
      ? `${guardian.collector_id}#${guardian.heal_event_id}`
      : `unattributed#${proposal.product.id}`;
    const group = byKey.get(key);
    if (group) group.push(proposal);
    else byKey.set(key, [proposal]);
  }

  const incidents = [...byKey.entries()].map(([key, group]) => {
    const sorted = [...group].sort((a, b) => exposureOf(b) - exposureOf(a));
    const lead = sorted[0];
    const guardian = lead.guardian;

    // The harm direction should be unanimous within a group - they share one bad heal. If it is
    // somehow mixed, prefer the margin framing: understating a margin loss is the worse error.
    const harms = new Set(sorted.map((p) => p.counterfactual?.harm).filter(Boolean));
    const harm = harms.size === 1 ? [...harms][0]! : "margin";

    return {
      key,
      collectorId: guardian?.collector_id ?? "unknown",
      checkCode: guardian?.check_code ?? null,
      brief: guardian?.brief ?? lead.reason,
      confidence: lead.confidence,
      attempt: guardian?.attempt ?? 1,
      attemptsTotal: guardian?.attempts_total ?? 1,
      staleness: lead.source.last_confirmed_label,
      sourceHost: hostOf(lead.source.url),
      observedPrice: lead.source.observed_price,
      harm,
      totalExposure: sorted.reduce((sum, p) => sum + exposureOf(p), 0),
      worst: lead ?? null,
      proposals: sorted,
    } satisfies Incident;
  });

  // Biggest exposure first: the most expensive thing to get wrong should be read first.
  return incidents.sort((a, b) => b.totalExposure - a.totalExposure);
}

/**
 * The one sentence that says what actually went wrong, in the seller's language.
 *
 * Built from stored evidence rather than hardcoded per check, so a check the UI has never heard of
 * still degrades to the guardian's own brief instead of rendering nothing.
 */
export function plainCause(incident: Incident): string {
  const evidence = (incident.worst?.guardian?.evidence ?? {}) as Record<string, unknown>;
  const money = (n: unknown) =>
    typeof n === "number"
      ? n.toLocaleString("en-US", { style: "currency", currency: "USD" })
      : null;

  switch (incident.checkCode) {
    case "COLUMN_SWAP": {
      const looksLike = evidence.looks_like;
      const read = money(incident.observedPrice);
      // baseline_own_median is the median across the WHOLE page, not this product's own price, so it
      // must be described as such. Saying "$19.99 instead of about $809.99" of a $7,000 card would
      // be a plainly wrong number on the most-read line of the screen.
      const typical = money(evidence.baseline_own_median);
      const column = typeof looksLike === "string" ? looksLike.replace(/_/g, " ").toUpperCase() : null;
      if (column && read) {
        return typical
          ? `The fix started reading the ${column} column as the item price — it came back ${read}, on a page where prices run around ${typical}.`
          : `The fix started reading the ${column} column as the item price — it came back ${read}.`;
      }
      break;
    }
    case "VALUE_ORDER_INVERTED": {
      const upper = String(evidence.upper ?? "original price").replace(/_/g, " ");
      return `The fix started reading the crossed-out ${upper} instead of the price a customer actually pays.`;
    }
    case "NULL_SPIKE":
      return "The fix left the price blank on most of the page.";
    case "FIELD_MISSING":
      return "The fix dropped the price field altogether.";
  }
  return incident.brief;
}
