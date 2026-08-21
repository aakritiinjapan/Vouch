/**
 * The console — the one-decision screen. It answers exactly one question: do I trust this competitor
 * price enough to let it move my listing — yes / no / not yet?
 *
 * Presentational: all state and mutations live in useVouch (wired in App). Section order is not
 * fixed — when something is held, held decisions come FIRST; routine changes are what you do when
 * there is nothing to judge, so they never sit above the thing that needs judging.
 */

import type { DemoHint, HealEvent, Product, Proposal } from "../types";
import { Receipts } from "../components/Receipts";
import { HeldCard } from "../components/HeldCard";
import { SafeChangesPanel } from "../components/SafeChangesPanel";
import { StatusRibbon } from "../components/StatusRibbon";
import { TrustMetrics } from "../components/TrustMetrics";
import { Button, Card, EmptyState } from "../components/ui/Bits";

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
      <div className="mb-2 flex flex-wrap items-baseline gap-x-2 px-1">
        <h2 className="text-[13px] font-bold uppercase tracking-wide text-ink">
          Needs your decision
        </h2>
        <span className="text-xs text-ink-muted">
          {held.length === 0
            ? "nothing is being withheld"
            : `${held.length} on hold pending a verified source`}
        </span>
      </div>
      {held.length === 0 ? (
        <Card>
          <EmptyState
            title="Nothing to hold"
            body="Vouch holds a reprice whenever it can't stand behind the number behind it. Nothing is being withheld right now."
          />
        </Card>
      ) : (
        <div className="space-y-4">
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
    <div className="mx-auto max-w-[1280px] px-5 py-6">
      {/* identity + purpose */}
      <div className="mb-4">
        <h1 className="font-display text-2xl font-semibold tracking-tight text-ink">Pricing desk</h1>
        <p className="mt-1 text-sm text-ink-secondary text-pretty">
          We move your price only on competitor data we can prove is real.
        </p>
      </div>

      {/* scope */}
      <div className="mb-4 flex flex-wrap items-center gap-x-2 rounded-xl border border-hair bg-surface px-4 py-2.5 text-sm shadow-card">
        <span className="eyebrow">Checking against</span>
        <span className="font-semibold text-ink">Newegg</span>
        <span className="text-ink-muted">·</span>
        <span className="num text-ink-secondary">{products.length} products</span>
      </div>

      {/* demo strip */}
      {mockMode && (
        <div className="mb-4 rounded-xl border border-dashed border-axis bg-raised/40 px-4 py-3">
          <p className="eyebrow mb-2">▶ Demo — simulate real scraping events</p>
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
        <StatusRibbon held={held} pending={pending} products={products} />

        <div className="mt-4">
          <TrustMetrics products={products} held={held} />
        </div>

        <div className="mt-5 grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1fr)_400px]">
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
          </div>

          <Receipts events={healEvents} />
        </div>
      </div>
    </div>
  );
}
