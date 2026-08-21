/**
 * HOW VOUCH DECIDED — the live, plain-English receipts.
 *
 * The right rail — a hairline-divided region, not a box. Secondary to the held card, but it carries
 * the same Verdict Gauge, so a viewer sees the identical object in the receipt, on the card, and in
 * the Trust API. The step vocabulary is generated server-side (service.heal_log_entries); `kind`
 * carries the emphasis so nothing here parses prose.
 *
 * Each receipt is collapsible, matching the held-card collapse language (chevron + hairline). Collapsed
 * it reads as one calm line — product · small gauge · terse verdict; expanded it reveals the numbered
 * steps and the re-prompt. It also cross-links to its held card: hovering/focusing either side lifts
 * the shared heal-event id into `activeLinkId`, and the matching row glows (see link.ts).
 */

import { useState } from "react";

import { LINK_HIGHLIGHT_CLASS } from "../link";
import type { HealEvent, LogKind } from "../types";
import { decisionLabel, toDecision } from "../verdict";
import { VerdictGauge } from "./VerdictGauge";
import { EmptyState } from "./ui/Bits";

const KIND_MARK: Record<LogKind, string> = {
  run: "1",
  heal: "2",
  verdict: "3",
  reprompt: "↻",
  commit: "✓",
};

/** The one-line verdict summary: "FAIL · COLUMN_SWAP · 40/100" or "PASS · 100/100". */
function terseVerdict(event: HealEvent): string {
  const decision = toDecision(event.verdict, event.proposed_confidence);
  const parts = [decisionLabel[decision]];
  if (event.primary_check_code) parts.push(event.primary_check_code);
  parts.push(`${event.proposed_confidence}/100`);
  return parts.join(" · ");
}

function Receipt({
  event,
  active,
  onLinkActivate,
}: {
  event: HealEvent;
  active: boolean;
  onLinkActivate?: (id: number | null) => void;
}) {
  const [open, setOpen] = useState(false);
  const decision = toDecision(event.verdict, event.proposed_confidence);

  // onFocus/onBlur on the wrapper catch keyboard focus of any inner control (React focus bubbles).
  const linkHandlers = onLinkActivate
    ? {
        onMouseEnter: () => onLinkActivate(event.id),
        onMouseLeave: () => onLinkActivate(null),
        onFocus: () => onLinkActivate(event.id),
        onBlur: () => onLinkActivate(null),
      }
    : {};

  return (
    <li
      data-link-id={event.id}
      className={`rounded-lg transition duration-200${active ? ` ${LINK_HIGHLIGHT_CLASS}` : ""}`}
      {...linkHandlers}
    >
      {/* collapsed summary row — product · small gauge · terse verdict · chevron */}
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center gap-3 py-4 text-left"
      >
        <VerdictGauge
          decision={decision}
          score={event.proposed_confidence}
          size={40}
          animate={false}
        />
        <div className="min-w-0 flex-1">
          <p className="truncate text-xs font-semibold text-ink">
            {event.product?.name ?? event.collector_id}{" "}
            <span className="font-normal text-ink-muted">· vs Newegg</span>
          </p>
          <p className="mt-0.5 truncate font-mono text-[10px] uppercase tracking-[0.08em] text-ink-muted">
            {terseVerdict(event)}
          </p>
        </div>
        <time className="shrink-0 text-[10px] text-ink-muted">{event.created_label}</time>
        <span
          aria-hidden
          className={`shrink-0 text-ink-muted transition-transform duration-200${
            open ? " rotate-90" : ""
          }`}
        >
          ▸
        </span>
      </button>

      {/* expanded: the existing numbered steps + the re-prompt control */}
      {open && (
        <div className="animate-reveal pb-4">
          <ol className="min-w-0 space-y-1.5">
            {event.entries.map((entry, i) => (
              <li key={i} className="flex gap-2 text-[11px] leading-snug text-ink-secondary">
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
        </div>
      )}
    </li>
  );
}

export function Receipts({
  events,
  activeLinkId = null,
  onLinkActivate,
}: {
  events: HealEvent[];
  /** The heal-event id hovered/focused on either list; highlights the matching receipt. */
  activeLinkId?: number | null;
  onLinkActivate?: (id: number | null) => void;
}) {
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
          {events.map((event) => (
            <Receipt
              key={event.id}
              event={event}
              active={activeLinkId !== null && activeLinkId === event.id}
              onLinkActivate={onLinkActivate}
            />
          ))}
        </ol>
      )}
    </div>
  );
}
