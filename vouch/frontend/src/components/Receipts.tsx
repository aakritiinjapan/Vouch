/**
 * HOW VOUCH DECIDED — the live, plain-English receipts.
 *
 * The right rail — a hairline-divided region, not a box. Secondary to the held card, but it carries
 * the same Verdict Gauge, so a viewer sees the identical object in the receipt, on the card, and in
 * the Trust API. The step vocabulary is generated server-side (service.heal_log_entries); `kind`
 * carries the emphasis so nothing here parses prose.
 */

import type { HealEvent, LogKind } from "../types";
import { toDecision } from "../verdict";
import { VerdictGauge } from "./VerdictGauge";
import { EmptyState } from "./ui/Bits";

const KIND_MARK: Record<LogKind, string> = {
  run: "1",
  heal: "2",
  verdict: "3",
  reprompt: "↻",
  commit: "✓",
};

export function Receipts({ events }: { events: HealEvent[] }) {
  return (
    <div className="lg:sticky lg:top-24">
      <div className="mb-1 flex flex-wrap items-baseline gap-x-2">
        <h2 className="font-display text-h2 font-semibold text-ink">How Vouch decided</h2>
        <span className="num text-xs text-ink-muted">{events.length}</span>
      </div>
      <p className="mb-4 text-xs text-ink-muted">
        Live, plain-English receipts — the same verdict, everywhere.
      </p>

      {events.length === 0 ? (
        <EmptyState
          title="No decisions yet"
          body="When a collector's output degrades, the heal and the guardian's verdict on it appear here."
        />
      ) : (
        <ol
          className="scroll-slim max-h-[min(68vh,44rem)] divide-y divide-hair overflow-y-auto"
          style={{
            maskImage: "linear-gradient(to bottom, black calc(100% - 24px), transparent 100%)",
            WebkitMaskImage: "linear-gradient(to bottom, black calc(100% - 24px), transparent 100%)",
          }}
        >
          {events.map((event) => {
            const decision = toDecision(event.verdict, event.proposed_confidence);
            return (
              <li key={event.id} className="py-4 first:pt-0">
                <div className="flex items-baseline justify-between gap-2">
                  <p className="truncate text-xs font-semibold text-ink">
                    {event.product?.name ?? event.collector_id}{" "}
                    <span className="font-normal text-ink-muted">· vs Newegg</span>
                  </p>
                  <time className="shrink-0 text-[10px] text-ink-muted">{event.created_label}</time>
                </div>

                <div className="mt-2.5 flex gap-3">
                  <ol className="min-w-0 flex-1 space-y-1.5">
                    {event.entries.map((entry, i) => (
                      <li
                        key={i}
                        className="flex gap-2 text-[11px] leading-snug text-ink-secondary"
                      >
                        <span
                          aria-hidden
                          className="grid size-4 shrink-0 place-items-center rounded-full border border-hair font-mono text-[9px] text-ink-muted"
                        >
                          {KIND_MARK[entry.kind]}
                        </span>
                        <span className="text-pretty">{entry.text}</span>
                      </li>
                    ))}
                  </ol>
                  <VerdictGauge
                    decision={decision}
                    score={event.proposed_confidence}
                    size={54}
                    animate={false}
                  />
                </div>

                {event.attempt > 1 && (
                  <details className="mt-2.5">
                    <summary className="cursor-pointer text-[10px] text-ink-muted hover:text-ink-secondary">
                      show the re-prompt
                    </summary>
                    <p className="mt-1.5 rounded-md border border-hair bg-white/[0.02] p-2.5 font-mono text-[10px] leading-relaxed text-ink-secondary">
                      {event.prompt}
                    </p>
                  </details>
                )}
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}
