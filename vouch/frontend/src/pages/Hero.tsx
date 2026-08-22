/**
 * The hero — the pitch, on the same continuous dark surface as the rest of the product. The product
 * IS the Trust API (the portable verdict primitive); the repricer is its first consumer, shown as the
 * demo that proves it. It leads with the trust layer and proves it with one visceral case: the
 * "without Vouch / with Vouch" contrast. The "verdict is the product" band shows the same Verdict
 * Gauge that appears on every other surface, and the teaser points at the reach (any scraped-data
 * pipeline).
 *
 * Personality is carried by the typography and the editorial hairline structure — no boxes, no orbs.
 * The one soft aurora glow lives in the canvas background (index.css); the gauge is the only place the
 * aurora gradient is used as an object.
 */

import type { Navigate } from "../hooks/useRoute";
import { VerdictGauge } from "../components/VerdictGauge";
import { Wordmark } from "../components/Wordmark";

function ContrastRow({ ok, children }: { ok: boolean; children: React.ReactNode }) {
  return (
    <li className="flex items-start gap-2.5 text-sm text-pretty">
      <span className={ok ? "text-verified" : "text-held"} aria-hidden>
        {ok ? "✓" : "✕"}
      </span>
      <span className={ok ? "text-ink" : "text-ink-secondary"}>{children}</span>
    </li>
  );
}

export function Hero({ navigate }: { navigate: Navigate }) {
  return (
    <div className="relative min-h-screen">
      <div className="relative mx-auto max-w-[1100px] px-6">
        {/* nav */}
        <header className="flex items-center justify-between py-5">
          <Wordmark />
          <nav className="flex items-center gap-2 text-sm sm:gap-4">
            <button
              type="button"
              onClick={() => navigate("console")}
              className="rounded-full px-3 py-1.5 text-ink-secondary hover:text-ink"
            >
              Repricer demo
            </button>
            <button
              type="button"
              onClick={() => navigate("trust-api")}
              className="rounded-full border border-hairStrong px-4 py-2 text-sm font-medium text-ink transition-colors hover:bg-white/[0.05]"
            >
              Open the Trust API
            </button>
          </nav>
        </header>

        {/* headline */}
        <section className="animate-reveal pt-16 sm:pt-24">
          <p className="eyebrow text-brand-soft">The trust layer for scraped data</p>
          <h1 className="mt-5 max-w-4xl font-display text-hero font-extrabold text-ink">
            Never act on a number{" "}
            <span className="text-aurora">you can&rsquo;t verify.</span>
          </h1>
          <p className="mt-7 max-w-2xl text-lead text-ink-secondary text-pretty">
            Vouch is a trust layer for scraped data: send the rows a self-heal wants to commit, get
            back one portable verdict — PASS / REVIEW / FAIL, a confidence score and a plain-English
            brief — so any pipeline can refuse to act on data it can&rsquo;t verify.
          </p>
          <div className="mt-9 flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={() => navigate("trust-api")}
              className="rounded-full bg-brand px-6 py-3 text-sm font-semibold text-canvas transition-colors hover:bg-brand-soft"
            >
              Try the Trust API →
            </button>
            <button
              type="button"
              onClick={() => navigate("console")}
              className="rounded-full border border-hairStrong px-6 py-3 text-sm font-medium text-ink transition-colors hover:bg-white/[0.05]"
            >
              See the repricer demo →
            </button>
          </div>
        </section>

        {/* contrast proof — one region, split by a hairline, not two boxes */}
        <section className="mt-20 animate-reveal rounded-lg border border-hair bg-surface p-7 shadow-soft sm:p-9">
          <p className="max-w-3xl text-sm text-ink-secondary text-pretty">
            The competitor page changed, and your scraper &ldquo;self-healed&rdquo; by{" "}
            <span className="text-ink">
              quietly reading the $19.99 SHIPPING cost as the product price.
            </span>
          </p>
          <div className="mt-7 grid gap-8 sm:grid-cols-2">
            <div>
              <p className="eyebrow text-held">Without Vouch</p>
              <ul className="mt-4 space-y-2.5">
                <ContrastRow ok={false}>auto-reprices to $19.99</ContrastRow>
                <ContrastRow ok={false}>−$951.00/unit, margin gone</ContrastRow>
                <ContrastRow ok={false}>you find out from your P&amp;L</ContrastRow>
              </ul>
            </div>
            <div className="sm:border-l sm:border-hair sm:pl-8">
              <p className="eyebrow text-verified">With Vouch</p>
              <ul className="mt-4 space-y-2.5">
                <ContrastRow ok>catches the bad data</ContrastRow>
                <ContrastRow ok>holds price at $6,999.00</ContrastRow>
                <ContrastRow ok>nothing bad happens</ContrastRow>
              </ul>
            </div>
          </div>
        </section>

        {/* the verdict is the product — the large gauge is the single hero object here */}
        <section className="mt-20 grid items-center gap-10 sm:grid-cols-[1fr_auto]">
          <div>
            <p className="eyebrow">The through-line</p>
            <h2 className="mt-3 font-display text-title font-bold text-ink">
              The verdict is the product.
            </h2>
            <p className="mt-4 max-w-xl text-ink-secondary text-pretty">
              Every scrape returns one portable verdict. The repricer is just its first consumer —
              it runs on the very same <code className="text-ink">/verify</code> this page calls.
            </p>
            <p className="mt-5 flex flex-wrap items-center gap-x-2 text-sm">
              <span className="font-semibold text-held">✕ FAIL</span>
              <span className="text-ink-muted">· trust 40/100 (Low) · scraper mixed up two columns</span>
            </p>
          </div>
          <div className="hidden justify-self-center sm:block">
            <VerdictGauge decision="fail" score={40} size={188} />
          </div>
        </section>

        {/* surfaces — what's inside */}
        <section className="mt-20">
          <p className="eyebrow">What&rsquo;s inside</p>
          <div className="mt-6 grid gap-5 sm:grid-cols-2">
            <div className="flex flex-col rounded-lg border border-brand/40 bg-surface p-7 shadow-soft">
              <div className="flex items-center gap-2">
                <p className="font-display text-h2 font-semibold text-ink">Trust API</p>
                <span className="rounded-full border border-brand/40 px-2 py-0.5 text-[11px] font-medium text-brand-soft">
                  the product
                </span>
              </div>
              <p className="mt-2.5 flex-1 text-sm text-ink-secondary text-pretty">
                The verdict as a stateless primitive: <code className="text-ink">POST /verify</code>.
                Send rows, get back trust — bring your own columns and (optionally) your own model
                key. Callable by any pipeline, not just this one.
              </p>
              <button
                type="button"
                onClick={() => navigate("trust-api")}
                className="mt-6 self-start rounded-full bg-brand px-5 py-2.5 text-sm font-semibold text-canvas transition-colors hover:bg-brand-soft"
              >
                Explore the API →
              </button>
            </div>
            <div className="flex flex-col rounded-lg border border-hair bg-surface p-7 shadow-soft">
              <div className="flex items-center gap-2">
                <p className="font-display text-h2 font-semibold text-ink">Repricer</p>
                <span className="rounded-full border border-hairStrong px-2 py-0.5 text-[11px] font-medium text-ink-muted">
                  reference consumer
                </span>
              </div>
              <p className="mt-2.5 flex-1 text-sm text-ink-secondary text-pretty">
                What the verdict looks like in a real product: Vouch holds any price move it
                can&rsquo;t verify — you see exactly why, and approve or skip with full evidence in
                front of you.
              </p>
              <button
                type="button"
                onClick={() => navigate("console")}
                className="mt-6 self-start rounded-full border border-hairStrong px-5 py-2.5 text-sm font-medium text-ink transition-colors hover:bg-white/[0.05]"
              >
                Open the demo →
              </button>
            </div>
          </div>
        </section>

        {/* teaser / provenance */}
        <footer className="mt-20 border-t border-hair py-10 text-sm text-ink-muted">
          <p>
            Powered by <span className="text-ink-secondary">◇ Bright Data</span> self-healing
            scrapers · <span className="text-ink-secondary">Anthropic</span> guardian
          </p>
          <p className="mt-2 text-pretty">
            Next: the same trust layer for branded catalogs (similar-but-not-identical goods).
          </p>
        </footer>
      </div>
    </div>
  );
}
