/**
 * The console — the one-decision screen. It answers exactly one question: do I trust this competitor
 * price enough to let it move my listing — yes / no / not yet?
 *
 * Presentational: all state and mutations live in useVouch (wired in App). Laid out as five regions
 * separated by space and hairlines rather than nested boxed cards: ① header (identity · scope · demo)
 * ② trust metrics ③ the decision / held (the hero region) ④ ready to apply ⑤ receipts (right rail).
 * Section order is not fixed — when something is held, held decisions come FIRST.
 */

import type { DemoHint, HealEvent, Product, Proposal } from "../types";
import { Receipts } from "../components/Receipts";
import { HeldCard } from "../components/HeldCard";
import { SafeChangesPanel } from "../components/SafeChangesPanel";
import { StatusRibbon } from "../components/StatusRibbon";
import { TrustMetrics } from "../components/TrustMetrics";
import { Button, EmptyState } from "../components/ui/Bits";

export interface ConsoleProps {
  products: Product[];
  pending: Proposal[];
  held: Proposal[];
  healEvents: HealEvent[];
  loading: boolean;
  busy: string | null;
  mockMode: boolean;
  hints: DemoHint[];
  datasetNote: string;
  collectorId: string | null;
  onApprove: (id: number) => void;
  onReject: (id: number) => void;
  onApproveAllSafe: () => void;
  onRunCycle: () => void;
  onReplay: (healKey: string) => void;
  onResume: () => void;
  onReset: () => void;
  onViewAsApi: (proposal: Proposal) => void;
}

export function Console(props: ConsoleProps) {
  const {
    products,
    pending,
    held,
    healEvents,
    loading,
    busy,
    mockMode,
    hints,
    onApprove,
    onReject,
    onApproveAllSafe,
    onRunCycle,
    onReplay,
    onResume,
    onReset,
    onViewAsApi,
  } = props;

  const healHints = hints.filter((h) => h.stage === "heal" && h.key !== "healed_good");

  const heldSection = (
    <section aria-label="Needs your decision">
      <div className="mb-3 flex flex-wrap items-baseline gap-x-3">
        <h2 className="font-display text-h2 font-semibold text-ink">Needs your decision</h2>
        <span className="text-xs text-ink-muted">
          {held.length === 0
            ? "nothing is being withheld"
            : `${held.length} on hold pending a verified source`}
        </span>
      </div>
      {held.length === 0 ? (
        <div className="rounded-lg border border-hair bg-surface">
          <EmptyState
            title="Nothing to hold"
            body="Vouch holds a reprice whenever it can't stand behind the number behind it. Nothing is being withheld right now."
          />
        </div>
      ) : (
        <div className="space-y-5">
          {held.map((proposal) => (
            <HeldCard
              key={proposal.id}
              proposal={proposal}
              busy={busy}
              onApproveAnyway={(id) => onApprove(id)}
              onSkip={(id) => onReject(id)}
              onViewAsApi={onViewAsApi}
            />
          ))}
        </div>
      )}
    </section>
  );

  const routineSection = (
    <section aria-label="Ready to apply">
      <SafeChangesPanel
        proposals={pending}
        loading={loading}
        busy={busy}
        onApprove={onApprove}
        onReject={onReject}
        onApproveAllSafe={onApproveAllSafe}
      />
    </section>
  );

  return (
    <div className="mx-auto max-w-[1200px] px-6 py-8">
      {/* ① identity + purpose + scope */}
      <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
        <div>
          <h1 className="font-display text-title font-bold text-ink">Pricing desk</h1>
          <p className="mt-1.5 max-w-xl text-ink-secondary text-pretty">
            We move your price only on competitor data we can prove is real.
          </p>
        </div>
        <div className="flex items-center gap-2 text-sm">
          <span className="eyebrow">Checking against</span>
          <span className="font-semibold text-ink">Newegg</span>
          <span className="text-ink-muted">·</span>
          <span className="num text-ink-secondary">{products.length} products</span>
        </div>
      </div>

      {/* demo strip */}
      {mockMode && (
        <div className="mt-5 rounded-lg border border-dashed border-hairStrong bg-white/[0.02] px-4 py-3.5">
          <p className="eyebrow mb-2.5 text-brand-soft">▶ Demo — simulate real scraping events</p>
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="primary" onClick={onRunCycle} busy={busy === "run-cycle"}>
              Check competitors now
            </Button>
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
              ↻ Reset demo
            </Button>
          </div>
        </div>
      )}

      <div
        className={busy ? "pointer-events-none opacity-60 transition-opacity" : "transition-opacity"}
      >
        <div className="mt-6">
          <StatusRibbon held={held} pending={pending} products={products} />
        </div>

        {/* ② trust metrics */}
        <div className="mt-6">
          <TrustMetrics products={products} held={held} />
        </div>

        {/* ③④ decision + ready · ⑤ receipts */}
        <div className="mt-8 grid grid-cols-1 gap-x-10 gap-y-8 lg:grid-cols-[minmax(0,1fr)_380px]">
          <div className="space-y-8">
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
          </div>

          <div className="lg:border-l lg:border-hair lg:pl-10">
            <Receipts events={healEvents} />
          </div>
        </div>
      </div>
    </div>
  );
}
