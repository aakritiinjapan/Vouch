/**
 * The shared top nav for the app surfaces (Trust API · Repricer · Sale checker), with the tenant
 * identity always in the top-right so a viewer never loses their place. The Trust API leads — it is
 * the product; the repricer is its reference consumer. One continuous dark surface — the hero shares
 * the same wordmark and identity treatment.
 */

import type { Navigate, View } from "../hooks/useRoute";
import { Wordmark } from "./Wordmark";
import { DemoMenu, type DemoMenuProps } from "./DemoMenu";

const TABS: { view: View; label: string }[] = [
  { view: "trust-api", label: "Trust API" },
  { view: "console", label: "Repricer" },
  { view: "examples", label: "Sale checker" },
];

export function Nav({
  view,
  navigate,
  demo,
}: {
  view: View;
  navigate: Navigate;
  /** The Demo control's handlers + replay hints. Console-only — its actions run cycles, so it is
   *  passed (and thus rendered) only on the console route, never on Hero or Trust API. */
  demo?: DemoMenuProps;
}) {
  return (
    <header className="sticky top-0 z-20 border-b border-hair bg-canvas/80 backdrop-blur-md">
      <div className="mx-auto flex max-w-[1200px] flex-wrap items-center gap-x-6 gap-y-2 px-6 py-3.5">
        <button
          type="button"
          onClick={() => navigate("home")}
          className="flex items-center gap-2"
          aria-label="Vouch home"
        >
          <Wordmark tagline />
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
                className={`rounded-full px-3.5 py-1.5 text-sm font-medium transition-colors ${
                  active
                    ? "bg-white/[0.08] text-ink"
                    : "text-ink-muted hover:bg-white/[0.05] hover:text-ink"
                }`}
              >
                {tab.label}
              </button>
            );
          })}
        </nav>

        <div className="ml-auto flex min-w-0 items-center gap-2.5 text-sm text-ink-secondary">
          {demo && <DemoMenu {...demo} />}
          {/* Attribution, not decoration: every verdict here is judged on rows a Scraper Studio
              collector returned, and the heal loop being validated is Bright Data's own. */}
          <span className="hidden rounded-full border border-hair bg-surface px-3 py-1.5 text-[11.5px] text-ink-muted lg:inline">
            Powered by Bright Data Scraper Studio
          </span>
          <span className="grid size-6 shrink-0 place-items-center rounded-md bg-aurora text-xs font-bold text-canvas">
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
