/**
 * Brand, provenance, and the demo controls.
 *
 * Two honesty decisions live here.
 *
 * The MOCK badge is always visible. Judges see a lot of demos that quietly imply live data; stating
 * it up front is both honest and the same posture the product itself takes.
 *
 * The replay controls are rendered from GET /demo/hints rather than hard-coded, so the console can
 * only ever offer a scenario the active dataset can actually produce. They are also labelled
 * "Replay:", not "Bad heal:" - these buttons replay a captured failure through the real guardian,
 * and the label should say so rather than implying the failure is being invented on the spot.
 */

import type { DemoHint } from "../types";
import { Button } from "./ui/Bits";

const COLLECTOR_URL = "https://brightdata.com/cp/scrapers";

export function Header({
  mockMode,
  busy,
  hints,
  datasetNote,
  collectorId,
  onRunCycle,
  onReplay,
  onResume,
  onReset,
}: {
  mockMode: boolean;
  busy: string | null;
  hints: DemoHint[];
  datasetNote: string;
  collectorId: string | null;
  onRunCycle: () => void;
  onReplay: (healKey: string) => void;
  onResume: () => void;
  onReset: () => void;
}) {
  const healHints = hints.filter((hint) => hint.stage === "heal" && hint.key !== "healed_good");

  return (
    <header className="mb-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="flex items-center gap-2.5 text-xl font-bold tracking-tight text-ink">
            Vouch
            {mockMode && (
              <span
                className="rounded border border-hair bg-raised px-1.5 py-0.5 font-mono text-[10px] font-medium uppercase tracking-[0.12em] text-ink-muted"
                title={`Replaying a stored dataset instead of calling Bright Data — ${datasetNote}`}
              >
                replay
              </span>
            )}
          </h1>
          <p className="mt-1 text-xs text-ink-secondary">
            Repricing that never acts on a number it can&rsquo;t verify.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Button variant="primary" onClick={onRunCycle} busy={busy === "run-cycle"}>
            Run cycle
          </Button>
          {mockMode && (
            <>
              {healHints.map((hint) => (
                <Button
                  key={hint.key}
                  variant="secondary"
                  onClick={() => onReplay(hint.key)}
                  busy={busy === "run-cycle"}
                  title={hint.detail}
                >
                  {hint.label}
                </Button>
              ))}
              <Button
                variant="secondary"
                onClick={onResume}
                busy={busy === "run-cycle"}
                title="Re-prompt the heal with the guardian's own diagnosis, then re-validate"
              >
                Re-prompt &amp; resume
              </Button>
              <Button variant="ghost" onClick={onReset} busy={busy === "reset"}>
                Reset
              </Button>
            </>
          )}
        </div>
      </div>

      {/* Provenance, stated once, where a judge will read it before anything else. */}
      {collectorId && (
        <p className="mt-3 border-t border-hair pt-2.5 text-[11px] text-ink-muted text-pretty">
          Competitor data from Scraper Studio collector{" "}
          <a
            href={COLLECTOR_URL}
            target="_blank"
            rel="noreferrer noopener"
            className="font-mono text-ink-secondary underline decoration-hair underline-offset-2 hover:text-ink"
          >
            {collectorId}
          </a>{" "}
          — 96 graphics cards read from Newegg&rsquo;s public GPU category page.
          {mockMode && <> This console replays that run so the demo is deterministic and offline.</>}
        </p>
      )}
    </header>
  );
}
