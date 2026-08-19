/**
 * Brand, mock-mode badge, and the demo controls.
 *
 * The MOCK MODE badge is deliberately always visible. Judges see a lot of demos that quietly imply
 * live data; stating it up front is both honest and the same posture the product itself takes.
 */

import { Button } from "./ui/Bits";

export function Header({
  mockMode,
  busy,
  onRunCycle,
  onBreak,
  onBreakSubtle,
  onResume,
  onReset,
}: {
  mockMode: boolean;
  busy: string | null;
  onRunCycle: () => void;
  onBreak: () => void;
  onBreakSubtle: () => void;
  onResume: () => void;
  onReset: () => void;
}) {
  return (
    <header className="mb-5 flex flex-wrap items-center justify-between gap-4">
      <div>
        <h1 className="flex items-center gap-2 text-lg font-semibold tracking-tight text-ink">
          Vouch
          {mockMode && (
            <span className="rounded border border-hair bg-raised px-1.5 py-0.5 font-mono text-[10px] font-normal uppercase tracking-wider text-ink-muted">
              mock mode
            </span>
          )}
        </h1>
        <p className="mt-0.5 text-xs text-ink-muted">
          Repricing that never acts on a number it can&rsquo;t verify.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Button variant="secondary" onClick={onRunCycle} busy={busy === "run-cycle"}>
          Run cycle
        </Button>
        {mockMode && (
          <>
            <Button
              variant="secondary"
              onClick={onBreak}
              busy={busy === "run-cycle"}
              title="The heal grabs the shipping cost - 100x off, so the distribution checks catch it"
            >
              Bad heal: shipping
            </Button>
            <Button
              variant="secondary"
              onClick={onBreakSubtle}
              busy={busy === "run-cycle"}
              title="The heal grabs the crossed-out original price - only ~14% off, so ONLY the price <= original_price invariant catches it"
            >
              Bad heal: original price
            </Button>
            <Button
              variant="secondary"
              onClick={onResume}
              busy={busy === "run-cycle"}
              title="Re-prompt the heal with the guardian's diagnosis, then re-validate"
            >
              Re-prompt &amp; resume
            </Button>
            <Button variant="ghost" onClick={onReset} busy={busy === "reset"}>
              Reset demo
            </Button>
          </>
        )}
      </div>
    </header>
  );
}
