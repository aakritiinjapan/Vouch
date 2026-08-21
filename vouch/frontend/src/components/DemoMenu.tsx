/**
 * The Demo control — a compact circular trigger that lives in the top bar (Console only). It relocates
 * the old full-width "simulate real scraping events" strip into an on-brand dropdown so the console
 * body can lead with the decision, not the demo scaffolding.
 *
 * The dashed brand ring reads as a "simulation" affordance; a hover/focus tooltip carries the old
 * strip's caption. The dropdown is a proper menu: keyboard-reachable (the tooltip is never the only
 * affordance), arrow-navigable, and it closes on Escape, outside-click, or selection — returning focus
 * to the trigger each time.
 */

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

import type { DemoHint } from "../types";

export interface DemoMenuProps {
  hints: DemoHint[];
  busy: string | null;
  onRunCycle: () => void;
  onReplay: (healKey: string) => void;
  onResume: () => void;
  onReset: () => void;
}

interface MenuItem {
  key: string;
  label: string;
  detail?: string;
  emphasized?: boolean;
  run: () => void;
}

export function DemoMenu({ hints, busy, onRunCycle, onReplay, onResume, onReset }: DemoMenuProps) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const itemRefs = useRef<(HTMLButtonElement | null)[]>([]);

  const healHints = hints.filter((h) => h.stage === "heal" && h.key !== "healed_good");

  const items: MenuItem[] = [
    { key: "run-cycle", label: "Check competitors now", emphasized: true, run: onRunCycle },
    ...healHints.map((hint) => ({
      key: `replay-${hint.key}`,
      label: hint.label,
      detail: hint.detail,
      run: () => onReplay(hint.key),
    })),
    {
      key: "resume",
      label: "Re-prompt & resume",
      detail: "Re-prompt the heal with the guardian's own diagnosis, then re-validate",
      run: onResume,
    },
    { key: "reset", label: "↻ Reset demo", run: onReset },
  ];

  const close = useCallback((returnFocus = true) => {
    setOpen(false);
    if (returnFocus) triggerRef.current?.focus();
  }, []);

  const select = useCallback(
    (item: MenuItem) => {
      item.run();
      close();
    },
    [close],
  );

  // Focus the first item when the menu opens (sensible focus management for a menu).
  useLayoutEffect(() => {
    if (open) itemRefs.current[0]?.focus();
  }, [open]);

  // Close on outside click.
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  const onMenuKeyDown = (e: React.KeyboardEvent) => {
    const count = items.length;
    const current = itemRefs.current.findIndex((el) => el === document.activeElement);
    if (e.key === "Escape") {
      e.preventDefault();
      close();
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      itemRefs.current[(current + 1) % count]?.focus();
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      itemRefs.current[(current - 1 + count) % count]?.focus();
    } else if (e.key === "Home") {
      e.preventDefault();
      itemRefs.current[0]?.focus();
    } else if (e.key === "End") {
      e.preventDefault();
      itemRefs.current[count - 1]?.focus();
    }
  };

  return (
    <div ref={wrapRef} className="group relative">
      <button
        ref={triggerRef}
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="Demo — simulate real scraping events"
        onClick={() => setOpen((o) => !o)}
        onKeyDown={(e) => {
          if ((e.key === "ArrowDown" || e.key === "Enter" || e.key === " ") && !open) {
            e.preventDefault();
            setOpen(true);
          }
        }}
        className={`grid size-10 shrink-0 place-items-center rounded-full border border-dashed text-[11px] font-medium transition-colors ${
          open
            ? "border-brand bg-brand/15 text-brand-soft"
            : "border-brand/45 text-brand-soft hover:border-brand/70 hover:bg-brand/10"
        }`}
      >
        {busy === "run-cycle" || busy === "reset" ? (
          <span className="size-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" />
        ) : (
          "Demo"
        )}
      </button>

      {/* Tooltip — a secondary affordance only; the menu itself is keyboard-reachable. Hidden while
          the menu is open so it never overlaps the panel. */}
      <span
        role="tooltip"
        className={`pointer-events-none absolute right-0 top-full z-30 mt-2 whitespace-nowrap rounded-md border border-hair bg-surface px-2.5 py-1 text-[11px] text-ink-secondary opacity-0 shadow-soft transition-opacity duration-150 ${
          open ? "hidden" : "group-hover:opacity-100 group-focus-within:opacity-100"
        }`}
      >
        Simulate real scraping events
      </span>

      {open && (
        <div
          role="menu"
          aria-label="Demo actions"
          onKeyDown={onMenuKeyDown}
          className="animate-reveal absolute right-0 top-full z-30 mt-2 w-64 origin-top-right overflow-hidden rounded-lg border border-hair bg-surface p-1.5 shadow-soft"
        >
          <p className="eyebrow px-2 pb-1.5 pt-1 text-brand-soft">Simulate scraping events</p>
          {items.map((item, i) => (
            <button
              key={item.key}
              ref={(el) => {
                itemRefs.current[i] = el;
              }}
              type="button"
              role="menuitem"
              tabIndex={-1}
              title={item.detail}
              onClick={() => select(item)}
              className={`block w-full rounded-md px-2.5 py-2 text-left text-xs transition-colors ${
                item.emphasized
                  ? "font-semibold text-ink hover:bg-brand/15"
                  : "text-ink-secondary hover:bg-white/[0.06] hover:text-ink"
              }`}
            >
              {item.label}
              {item.detail && (
                <span className="mt-0.5 block text-[11px] font-normal text-ink-muted">
                  {item.detail}
                </span>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
