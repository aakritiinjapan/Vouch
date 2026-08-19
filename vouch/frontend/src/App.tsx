/**
 * The one screen that matters (README section 7).
 *
 * Exception-based, not a data display: the seller's job is to touch only what needs judgment. Layout
 * is two columns - the decision queue on the left, the operator log on the right, sticky. On a
 * projector the log must never push the held card below the fold, which is why the grid is fixed at
 * 360px rather than a fraction.
 */

import { HealEventLog } from "./components/HealEventLog";
import { HeldCard } from "./components/HeldCard";
import { Header } from "./components/Header";
import { KpiRow } from "./components/KpiRow";
import { SafeChangesPanel } from "./components/SafeChangesPanel";
import { Card, EmptyState, SectionHeader } from "./components/ui/Bits";
import { useVouch } from "./hooks/useVouch";

export default function App() {
  const vouch = useVouch();
  const {
    products,
    pending,
    held,
    healEvents,
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
  } = vouch;

  return (
    <div className="mx-auto max-w-[1180px] px-5 py-6">
      <Header
        mockMode={mockMode}
        busy={mutating}
        onRunCycle={() => runCycle()}
        onBreak={() =>
          runCycle({
            simulate_run: "run_degraded",
            simulate_heal: ["healed_swapped", "healed_swapped"],
          })
        }
        onBreakSubtle={() =>
          runCycle({
            simulate_run: "run_degraded",
            simulate_heal: ["healed_swapped_original", "healed_swapped_original"],
          })
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
      <div className={mutating ? "pointer-events-none opacity-60 transition-opacity" : "transition-opacity"}>
        <KpiRow products={products} pending={pending} held={held} />

        <div className="mt-5 grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1fr)_360px]">
          <div className="space-y-5">
            <SafeChangesPanel
              proposals={pending}
              loading={loading}
              busy={mutating}
              onApprove={approve}
              onReject={reject}
              onApproveAllSafe={approveAllSafe}
            />

            <section>
              <div className="mb-2 flex items-baseline gap-2 px-1">
                <h2 className="text-sm font-semibold text-ink">Held decisions</h2>
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

            <Card>
              <SectionHeader title="Catalogue" count={products.length} />
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-hair text-left text-ink-muted">
                    <th className="px-5 py-2 font-normal">SKU</th>
                    <th className="px-3 py-2 font-normal">Our price</th>
                    <th className="px-3 py-2 font-normal">Floor</th>
                    <th className="px-3 py-2 font-normal">Competitor</th>
                    <th className="px-5 py-2 font-normal">Source</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-hair">
                  {products.map((product) => (
                    <tr key={product.id} className="hover:bg-raised/40">
                      <td className="px-5 py-2">
                        <span className="text-ink">{product.sku}</span>
                        <span className="ml-2 text-ink-muted">{product.name}</span>
                      </td>
                      <td className="num-tabular px-3 py-2 text-ink">
                        ${product.my_price.toFixed(2)}
                      </td>
                      <td className="num-tabular px-3 py-2 text-ink-muted">
                        ${product.floor_price.toFixed(2)}
                      </td>
                      <td className="num-tabular px-3 py-2 text-ink-secondary">
                        {product.last_confirmed_price === null
                          ? "—"
                          : `$${product.last_confirmed_price.toFixed(2)}`}
                      </td>
                      <td className="px-5 py-2">
                        <span
                          className={
                            product.source_confirmed ? "text-ink-muted" : "text-status-critical"
                          }
                        >
                          {product.source_confirmed ? product.last_confirmed_label : "unconfirmed"}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          </div>

          <HealEventLog events={healEvents} />
        </div>
      </div>
    </div>
  );
}
