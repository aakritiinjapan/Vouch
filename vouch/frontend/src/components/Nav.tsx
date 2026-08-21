/**
 * The shared top nav for the app surfaces (Console · Trust API), with the tenant identity always in
 * the top-right so a viewer never loses their place. The hero has its own lighter nav.
 */

import type { Navigate, View } from "../hooks/useRoute";
import { Wordmark } from "./Wordmark";

const TABS: { view: View; label: string }[] = [
  { view: "console", label: "Console" },
  { view: "trust-api", label: "Trust API" },
];

export function Nav({ view, navigate }: { view: View; navigate: Navigate }) {
  return (
    <header className="sticky top-0 z-20 border-b border-hair bg-paper/85 backdrop-blur">
      <div className="mx-auto flex max-w-[1280px] flex-wrap items-center gap-x-6 gap-y-2 px-5 py-3">
        <button
          type="button"
          onClick={() => navigate("home")}
          className="flex items-center gap-2"
          aria-label="Vouch home"
        >
          <Wordmark />
        </button>

        <nav className="flex items-center gap-1" aria-label="Primary">
          {TABS.map((tab) => {
            const active = view === tab.view;
            return (
              <button
                key={tab.view}
                type="button"
                onClick={() => navigate(tab.view)}
                aria-current={active ? "page" : undefined}
                className={`rounded-full px-3 py-1.5 text-sm font-medium transition-colors ${
                  active
                    ? "bg-ink text-paper"
                    : "text-ink-muted hover:bg-raised hover:text-ink"
                }`}
              >
                {tab.label}
              </button>
            );
          })}
        </nav>

        <div className="ml-auto flex min-w-0 items-center gap-2 text-sm text-ink-secondary">
          <span className="grid size-6 shrink-0 place-items-center rounded-md bg-holo-cta text-xs font-bold text-white">
            V
          </span>
          <span data-testid="tenant-label" className="hidden truncate sm:inline">
            Voltix Components
          </span>
        </div>
      </div>
    </header>
  );
}
