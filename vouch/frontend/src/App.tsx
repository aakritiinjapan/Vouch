/**
 * The console, organised around one question: does anything need me right now?
 *
 * The previous layout answered that question four times before you reached a card — a ribbon, a row
 * of stat tiles, a section header, then the cards — and rendered a single bad heal as three separate
 * held decisions, because three SKUs happened to read the same collector. See docs/UX_REVIEW.md.
 *
 * The shape now:
 *   1. One answer. Either something needs judgement, or nothing does.
 *   2. If something does: ONE incident per bad fix, with the remedy as its primary button.
 *   3. Everything else — routine changes, the catalogue, the heal log — sits below, folded.
 *
 * Single column on purpose. The old two-column grid gave the operator log the same visual weight as
 * the decision it was meant to be subordinate to.
 */

import { useMemo } from "react";

import { Catalogue } from "./components/Catalogue";
import { HealEventLog } from "./components/HealEventLog";
import { Header } from "./components/Header";
import { IncidentCard } from "./components/IncidentCard";
import { SafeChangesPanel } from "./components/SafeChangesPanel";
import { groupIntoIncidents } from "./incident";
import { useVouch } from "./hooks/useVouch";

export default function App() {
  const {
    products,
    pending,
    held,
    healEvents,
    hints,
    loading,
    mutating,
    error,
    notice,
    mockMode,
    approve,
    reject,
    approveAllSafe,
    runCycle,
    resetDemo,
    dismissNotice,
  } = useVouch();

  const collectorId = products.find((p) => p.collector_id)?.collector_id ?? null;
  const incidents = useMemo(() => groupIntoIncidents(held), [held]);

  /** Re-prompt with the guardian's diagnosis and re-validate — the incident card's primary action. */
  const refix = () => runCycle({ simulate_run: "run_degraded", simulate_heal: "healed_swapped" });

  return (
    <div className="mx-auto max-w-[900px] px-5 py-6">
      <Header
        mockMode={mockMode}
        busy={mutating}
        hints={hints?.hints ?? []}
        datasetNote={hints?.dataset_note ?? ""}
        collectorId={collectorId}
        onRunCycle={() => runCycle()}
        onReplay={(healKey) =>
          runCycle({ simulate_run: "run_degraded", simulate_heal: [healKey, healKey] })
        }
        onReset={resetDemo}
      />

      {error && (
        <div className="mb-4 rounded-md border border-status-critical/40 bg-status-critical/10 px-4 py-2 text-xs text-status-critical">
          {error}
        </div>
      )}
      {notice && (
        <button
          type="button"
          onClick={dismissNotice}
          className="mb-4 block w-full rounded-md border border-hair bg-raised px-4 py-2 text-left text-xs text-ink-secondary hover:text-ink"
        >
          {notice} <span className="text-ink-muted">— dismiss</span>
        </button>
      )}

      {/* Refetches render over the previous data at reduced opacity rather than flashing skeletons,
          so nothing jumps mid-sentence while the demo is being narrated. */}
      <div
        className={
          mutating ? "pointer-events-none opacity-60 transition-opacity" : "transition-opacity"
        }
      >
        {/* ---- 1. the answer ----------------------------------------------------------- */}
        <section aria-label="What needs your judgement">
          {incidents.length === 0 ? (
            <div className="flex items-start gap-3 rounded-lg border border-hair bg-surface px-6 py-5">
              <span
                className="mt-1.5 size-2 shrink-0 rounded-full bg-status-good"
                aria-hidden
              />
              <div>
                <h2 className="text-base font-semibold text-ink">Nothing needs you</h2>
                <p className="mt-0.5 text-sm text-ink-secondary text-pretty">
                  {loading
                    ? "Checking every competitor source…"
                    : pending.length > 0
                      ? `Every competitor source checked out. ${pending.length} routine change${pending.length === 1 ? "" : "s"} below, all inside the safe band.`
                      : "Every competitor source checked out, and every price is already where Vouch would put it."}
                </p>
              </div>
            </div>
          ) : (
            <div className="space-y-4">
              {incidents.map((incident) => (
                <IncidentCard
                  key={incident.key}
                  incident={incident}
                  busy={mutating}
                  onRefix={refix}
                  onOverride={(id) => approve(id, true)}
                  onSkip={(id) => reject(id, "skipped")}
                />
              ))}
            </div>
          )}
        </section>

        {/* ---- 2. the routine work, only when there is some ---------------------------- */}
        {pending.length > 0 && (
          <div className="mt-5">
            <SafeChangesPanel
              proposals={pending}
              loading={loading}
              busy={mutating}
              onApprove={approve}
              onReject={reject}
              onApproveAllSafe={approveAllSafe}
            />
          </div>
        )}

        {/* ---- 3. reference, folded away ----------------------------------------------- */}
        <div className="mt-5 space-y-3">
          <Catalogue products={products} />
          <HealEventLog events={healEvents} />
        </div>
      </div>
    </div>
  );
}
