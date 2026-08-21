/**
 * The hero — dark, atmospheric, the pitch. It leads with the trust layer, not repricing, and proves
 * it with one visceral commodity case: the "without Vouch / with Vouch" contrast. The "verdict is the
 * product" band shows the same Verdict Seal that appears on every other surface, and the teaser points
 * at the reach (branded catalogs, any scraped-data pipeline).
 */

import type { Navigate } from "../hooks/useRoute";
import { VerdictChip, VerdictSeal } from "../components/VerdictSeal";
import { Wordmark } from "../components/Wordmark";

function HoloOrbs() {
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
      <div className="absolute -left-32 -top-32 size-[36rem] rounded-full bg-holo-violet/25 blur-[120px] animate-floaty" />
      <div className="absolute -right-24 top-24 size-[30rem] rounded-full bg-holo-cyan/20 blur-[120px] animate-floaty [animation-delay:-6s]" />
      <div className="absolute bottom-0 left-1/3 size-[28rem] rounded-full bg-holo-gold/10 blur-[120px] animate-floaty [animation-delay:-3s]" />
      {/* guilloché line-work */}
      <div
        className="absolute inset-0 opacity-[0.06]"
        style={{
          backgroundImage:
            "repeating-linear-gradient(60deg, #fff 0 1px, transparent 1px 14px), repeating-linear-gradient(-60deg, #fff 0 1px, transparent 1px 14px)",
        }}
      />
    </div>
  );
}

function ContrastRow({
  ok,
  children,
}: {
  ok: boolean;
  children: React.ReactNode;
}) {
  return (
    <li className="flex items-start gap-2 text-sm text-navy-ink text-pretty">
      <span className={ok ? "text-status-good" : "text-status-critical"} aria-hidden>
        {ok ? "✓" : "✕"}
      </span>
      <span className={ok ? "" : "text-navy-muted"}>{children}</span>
    </li>
  );
}

export function Hero({ navigate }: { navigate: Navigate }) {
  return (
    <div className="relative min-h-screen overflow-hidden bg-navy-900 text-navy-ink">
      <HoloOrbs />

      <div className="relative mx-auto max-w-[1120px] px-6">
        {/* nav */}
        <header className="flex items-center justify-between py-6">
          <Wordmark dark />
          <nav className="flex items-center gap-4 text-sm">
            <button
              type="button"
              onClick={() => navigate("trust-api")}
              className="text-navy-muted hover:text-navy-ink"
            >
              Trust API
            </button>
            <button
              type="button"
              onClick={() => navigate("console")}
              className="rounded-full bg-holo-cta bg-[length:200%_auto] px-4 py-2 text-sm font-semibold text-white shadow-seal hover:bg-right"
            >
              Launch console
            </button>
          </nav>
        </header>

        {/* headline */}
        <section className="animate-rise pt-14 sm:pt-20">
          <p className="eyebrow text-holo-cyan">The trust layer for scraped data</p>
          <h1 className="mt-4 max-w-3xl font-display text-hero font-semibold tracking-tight sm:text-display">
            Never act on a number{" "}
            <span className="holo-text animate-sheen">you can&rsquo;t verify.</span>
          </h1>
          <p className="mt-6 max-w-2xl text-lg text-navy-muted text-pretty">
            Vouch returns a verdict on every scrape — validated and self-healed before anything acts
            on it. Its first job: making sure a broken competitor scrape never moves your price.
          </p>
          <div className="mt-8 flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={() => navigate("console")}
              className="rounded-full bg-holo-cta bg-[length:200%_auto] px-6 py-3 text-sm font-semibold text-white shadow-seal transition-all hover:bg-right"
            >
              See it catch a bad price →
            </button>
            <button
              type="button"
              onClick={() => navigate("console")}
              className="rounded-full border border-navy-hair px-6 py-3 text-sm font-medium text-navy-ink hover:bg-navy-700"
            >
              Launch console
            </button>
          </div>
        </section>

        {/* contrast proof */}
        <section className="mt-16 animate-rise rounded-3xl border border-navy-hair bg-navy-800/70 p-6 backdrop-blur sm:p-8">
          <p className="text-sm text-navy-muted text-pretty">
            The competitor page changed. Your scraper &ldquo;self-healed&rdquo;
            <span className="text-navy-ink">
              {" "}
              … and started reading the $19.99 SHIPPING cost as the product price.
            </span>
          </p>
          <div className="mt-6 grid gap-6 sm:grid-cols-2">
            <div className="rounded-2xl border border-status-critical/30 bg-status-critical/[0.06] p-5">
              <p className="eyebrow text-status-critical">Without Vouch</p>
              <ul className="mt-3 space-y-2">
                <ContrastRow ok={false}>auto-reprices to $19.99</ContrastRow>
                <ContrastRow ok={false}>−$179.99/unit, margin gone</ContrastRow>
                <ContrastRow ok={false}>you find out from your P&amp;L</ContrastRow>
              </ul>
            </div>
            <div className="rounded-2xl border border-status-good/30 bg-status-good/[0.06] p-5">
              <p className="eyebrow text-status-good">With Vouch</p>
              <ul className="mt-3 space-y-2">
                <ContrastRow ok>catches the bad data</ContrastRow>
                <ContrastRow ok>holds price at $1,279.99</ContrastRow>
                <ContrastRow ok>nothing bad happens</ContrastRow>
              </ul>
            </div>
          </div>
        </section>

        {/* the verdict is the product */}
        <section className="mt-20 grid items-center gap-8 sm:grid-cols-[1fr_auto]">
          <div>
            <h2 className="font-display text-3xl font-semibold tracking-tight">
              The verdict is the product
            </h2>
            <p className="mt-3 max-w-xl text-navy-muted text-pretty">
              Every scrape returns one portable verdict. The repricer is just its first consumer —
              send rows, get back trust.
            </p>
            <div className="mt-5 max-w-md">
              <VerdictChip
                dark
                decision="fail"
                score={40}
                line="scraper mixed up two columns"
                onViewAsApi={() => navigate("trust-api", { scenario: "column-swap" })}
              />
            </div>
            <button
              type="button"
              onClick={() => navigate("trust-api")}
              className="mt-5 rounded-full border border-navy-hair px-5 py-2.5 text-sm font-semibold text-navy-ink hover:bg-navy-700"
            >
              Try the Trust API →
            </button>
          </div>
          <div className="hidden justify-self-center sm:block">
            <VerdictSeal decision="fail" score={40} size={160} dark />
          </div>
        </section>

        {/* teaser / provenance */}
        <footer className="mt-24 border-t border-navy-hair py-10 text-sm text-navy-muted">
          <p>
            Powered by <span className="text-navy-ink">◇ Bright Data</span> self-healing scrapers ·{" "}
            <span className="text-navy-ink">Anthropic</span> guardian
          </p>
          <p className="mt-2 text-pretty">
            Next: the same trust layer for branded catalogs (similar-but-not-identical goods).
          </p>
        </footer>
      </div>
    </div>
  );
}
