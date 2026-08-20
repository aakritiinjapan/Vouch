/**
 * The operator log, in real Scraper Studio vocabulary.
 *
 * Secondary on purpose, and now folded shut by default. README section 7 always called this a
 * secondary panel, but as a full-height sticky column it carried the same visual weight as the
 * decision it was supposed to be subordinate to.
 *
 * The vocabulary is generated server-side (service.heal_log_entries) so it lives in one reviewable
 * place, and `kind` carries the colour so nothing here parses prose.
 */

import type { HealEvent, LogKind } from "../types";
import { Disclosure, EmptyState } from "./ui/Bits";

const KIND_STYLE: Record<LogKind, string> = {
  run: "text-ink-muted",
  heal: "text-ink-secondary",
  verdict: "text-ink",
  reprompt: "text-series",
  commit: "text-ink-muted",
};

const KIND_MARK: Record<LogKind, string> = {
  run: "▸",
  heal: "◆",
  verdict: "●",
  reprompt: "↻",
  commit: "✓",
};

export function HealEventLog({ events }: { events: HealEvent[] }) {
  return (
    <Disclosure
      title="Heal log"
      count={events.length}
      hint="Scraper Studio's heal loop, as it happened"
    >
      {events.length === 0 ? (
        <EmptyState
          title="No heals yet"
          body="When a collector's output degrades, the heal and the guardian's verdict on it appear here."
        />
      ) : (
        /* The list scrolls inside the panel rather than growing it. Without this the log runs past
           the fold and clips mid-entry, which on a projector looks like a rendering bug rather than
           a long log. The mask fades the last few pixels so "there is more" is visible without a
           scrollbar having to be. */
        <ol
          className="scroll-slim max-h-[min(64vh,40rem)] divide-y divide-hair overflow-y-auto"
          style={{
            maskImage: "linear-gradient(to bottom, black calc(100% - 24px), transparent 100%)",
            WebkitMaskImage: "linear-gradient(to bottom, black calc(100% - 24px), transparent 100%)",
          }}
        >
          {events.map((event) => (
            <li key={event.id} className="px-5 py-2.5">
              <div className="flex items-baseline justify-between gap-2">
                <p className="truncate text-xs font-medium text-ink-secondary">
                  {event.product?.sku ?? event.collector_id}
                </p>
                <time className="shrink-0 text-[10px] text-ink-muted">{event.created_label}</time>
              </div>

              <ul className="mt-1.5 space-y-1">
                {event.entries.map((entry, i) => (
                  <li
                    key={i}
                    className={`flex gap-1.5 text-[11px] leading-snug ${KIND_STYLE[entry.kind]}`}
                  >
                    <span aria-hidden className="shrink-0 opacity-70">
                      {KIND_MARK[entry.kind]}
                    </span>
                    <span className="text-pretty">{entry.text}</span>
                  </li>
                ))}
              </ul>

              {/* The sharpened prompt: Vouch's validator writing Scraper Studio's next instruction.
                  This is the most legible evidence that we wrapped the heal loop. */}
              {event.attempt > 1 && (
                <details className="mt-2">
                  <summary className="cursor-pointer text-[10px] text-ink-muted hover:text-ink-secondary">
                    show the re-prompt
                  </summary>
                  <p className="mt-1 rounded bg-plane/70 p-2 font-mono text-[10px] leading-relaxed text-ink-secondary">
                    {event.prompt}
                  </p>
                </details>
              )}
            </li>
          ))}
        </ol>
      )}
    </Disclosure>
  );
}
