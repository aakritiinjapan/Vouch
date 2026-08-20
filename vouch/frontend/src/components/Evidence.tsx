/**
 * The guardian's working: the measured evidence behind a verdict, and the sharpened instruction it
 * handed back to Scraper Studio.
 *
 * Extracted from HeldCard so the incident view can reuse it unchanged. Showing the re-prompt is the
 * point of this panel - it is the clearest single proof that Vouch wraps the heal loop rather than
 * watching it from outside.
 */

import { money } from "../format";
import type { Proposal } from "../types";

/** Field names inside the guardian's evidence, rendered for a human without losing the machine name. */
const EVIDENCE_LABELS: Record<string, string> = {
  field: "field examined",
  looks_like: "now matches",
  proposed_median: "median across the proposed rows",
  baseline_own_median: "its own historical median",
  baseline_other_median: "the other field's median",
  own_distance: "distance from its own distribution",
  other_distance: "distance from the other's",
  upper: "must not exceed",
  inverted_rate: "rows where the order inverted",
  null_rate: "rows with no value",
  baseline_null_rate: "rows with no value, before",
  rows_checked: "rows compared",
  example_lower: "example: the lower field",
  example_upper: "example: the upper field",
};

function formatEvidence(key: string, value: unknown): string {
  if (typeof value !== "number") return String(value);
  if (key.endsWith("_rate")) return `${Math.round(value * 100)}%`;
  if (key.endsWith("_distance")) return value.toFixed(3);
  if (key === "rows_checked") return String(value);
  return money(value);
}

export function Evidence({ proposal }: { proposal: Proposal }) {
  const guardian = proposal.guardian;
  if (!guardian) return null;

  const rows = Object.entries(guardian.evidence ?? {});

  return (
    <div className="animate-rise rounded-md border border-hair bg-plane/70 p-4">
      <p className="eyebrow">The guardian&rsquo;s working</p>

      {rows.length > 0 ? (
        <dl className="mt-2.5 grid grid-cols-[minmax(0,1fr)_auto] gap-x-6 gap-y-1.5 text-xs">
          {rows.map(([key, value]) => (
            <div key={key} className="contents">
              <dt className="min-w-0 text-ink-muted">
                {EVIDENCE_LABELS[key] ?? key.replace(/_/g, " ")}
                <span className="ml-1.5 font-mono text-[10px] text-ink-muted/60">{key}</span>
              </dt>
              <dd className="num text-right text-ink">{formatEvidence(key, value)}</dd>
            </div>
          ))}
        </dl>
      ) : (
        <p className="mt-2 text-xs text-ink-muted">
          This verdict came from the risk brief alone; the check produced no structured evidence.
        </p>
      )}

      <div className="mt-4 border-t border-hair pt-3">
        <p className="eyebrow">
          Instruction sent back to Scraper Studio · attempt {guardian.attempt} of{" "}
          {guardian.attempts_total}
        </p>
        <p className="mt-2 whitespace-pre-wrap rounded border border-hair bg-surface px-3 py-2 font-mono text-[11px] leading-relaxed text-ink-secondary">
          {guardian.prompt}
        </p>
        <p className="mt-2 text-[11px] text-ink-muted text-pretty">
          Written by the validator, not by a person — the medians above are what it put in the prompt.
          Collector <span className="font-mono text-ink-secondary">{guardian.collector_id}</span> was
          left unchanged; the heal was rejected before anything committed.
        </p>
      </div>
    </div>
  );
}
