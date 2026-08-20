/**
 * The one screen that matters.
 *
 * Exception-based, not a data display: the seller's job is to touch only what needs judgement. Two
 * columns — the decision queue on the left, the operator log on the right, sticky. On a projector the
 * log must never push the held card below the fold, which is why the grid is fixed at 380px rather
 * than a fraction.
 *
 * The section order is not fixed. When something is held, held decisions come FIRST; routine
 * proposals are what you do when there is nothing to judge, so they should never sit above the thing
 * that needs judging.
 */

import { HealEventLog } from "./components/HealEventLog";
import { HeldCard } from "./components/HeldCard";
import { Header } from "./components/Header";
import { KpiRow } from "./components/KpiRow";
import { SafeChangesPanel } from "./components/SafeChangesPanel";
import { StatusRibbon } from "./components/StatusRibbon";
import { Card, EmptyState, SectionHeader } from "./components/ui/Bits";
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

  const heldSection = (
    <section>
      <div className="mb-2 flex flex-wrap items-baseline gap-x-2 px-1">
        <h2 className="text-[13px] font-semibold tracking-tight text-ink">Held decisions</h2>
        <span className="text-xs text-ink-muted">
          {held.length === 0
            ? "nothing is being withheld"
            : `${held.length} reprice${held.length === 1 ? "" : "s"} withheld pending a verified source`}
        </span>
      </div>

      {held.length === 0 ? (
        <Card>
          <EmptyState
            title="Every source is confirmed"
            body="Vouch holds a reprice whenever it can't stand behind the number behind it. Nothing is being withheld right now."
          />
        </Card>
      ) : (
        <div className="space-y-4">
          {held.map((proposal) => (
            <HeldCard
              key={proposal.id}
              proposal={proposal}
              busy={mutating}
              onApproveAnyway={(id) => approve(id, true)}
              onSkip={(id) => reject(id, "skipped")}
            />
          ))}
        </div>
      )}
    </section>
  );

  const routineSection = (
    <SafeChangesPanel
      proposals={pending}
      loading={loading}
      busy={mutating}
      onApprove={approve}
      onReject={reject}
      onApproveAllSafe={approveAllSafe}
    />
  );

  return (
    <div className="mx-auto max-w-[1240px] px-5 py-6">
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
        onResume={() => runCycle({ simulate_run: "run_degraded", simulate_heal: "healed_swapped" })}
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
        <StatusRibbon held={held} pending={pending} products={products} />

        <div className="mt-4">
          <KpiRow products={products} pending={pending} held={held} />
        </div>

        <div className="mt-5 grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1fr)_380px]">
          <div className="space-y-5">
            {held.length > 0 ? (
              <>
                {heldSection}
                {routineSection}
              </>
            ) : (
              <>
                {routineSection}
                {heldSection}
              </>
            )}

            <Card>
              <SectionHeader title="Catalogue" count={products.length} />
              <div className="overflow-x-auto">
                <table className="w-full min-w-[560px] text-xs">
                  <thead>
                    <tr className="border-b border-hair text-left">
                      <th className="eyebrow whitespace-nowrap px-5 py-2 font-normal">SKU</th>
                      <th className="eyebrow whitespace-nowrap px-3 py-2 text-right font-normal">Our price</th>
                      <th className="eyebrow whitespace-nowrap px-3 py-2 text-right font-normal">Floor</th>
                      <th className="eyebrow whitespace-nowrap px-3 py-2 text-right font-normal">Competitor</th>
                      <th className="eyebrow whitespace-nowrap px-5 py-2 font-normal">Source</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-hair">
                    {products.map((product) => (
                      <tr key={product.id} className="hover:bg-raised/40">
                        <td className="px-5 py-2.5">
                          <div className="flex items-baseline gap-2">
                            <span className="shrink-0 font-mono text-[11px] text-ink">
                              {product.sku}
                            </span>
                            <span
                              className="min-w-0 max-w-[240px] truncate text-ink-muted"
                              title={product.name}
                            >
                              {product.name}
                            </span>
                          </div>
                        </td>
                        <td className="num px-3 py-2.5 text-right text-ink">
                          ${product.my_price.toFixed(2)}
                        </td>
                        <td className="num px-3 py-2.5 text-right text-ink-muted">
                          ${product.floor_price.toFixed(2)}
                        </td>
                        <td className="num px-3 py-2.5 text-right text-ink-secondary">
                          {product.last_confirmed_price === null
                            ? "—"
                            : `$${product.last_confirmed_price.toFixed(2)}`}
                        </td>
                        <td className="px-5 py-2.5">
                          {product.source_confirmed ? (
                            <span className="text-ink-muted">{product.last_confirmed_label}</span>
                          ) : (
                            <span className="font-medium text-status-critical">unconfirmed</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          </div>

          <HealEventLog events={healEvents} />
        </div>
      </div>
    </div>
  );
}
