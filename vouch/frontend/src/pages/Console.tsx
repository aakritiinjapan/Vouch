/**
 * The console — the one-decision screen. It answers exactly one question: do I trust this competitor
 * price enough to let it move my listing — yes / no / not yet?
 *
 * Presentational: all state and mutations live in useVouch (wired in App). Laid out as five regions
 * separated by space and hairlines rather than nested boxed cards: ① header (identity · scope · demo)
 * ② trust metrics ③ the decision / held (the hero region) ④ ready to apply ⑤ receipts (right rail).
 * Section order is not fixed — when something is held, held decisions come FIRST.
 */

import { useState } from "react";

import type { HealEvent, Product, Proposal } from "../types";
import { Receipts } from "../components/Receipts";
import { HeldCard } from "../components/HeldCard";
import { SafeChangesPanel } from "../components/SafeChangesPanel";
import { StatusRibbon } from "../components/StatusRibbon";
import { TrustMetrics } from "../components/TrustMetrics";
import { EmptyState } from "../components/ui/Bits";

export interface ConsoleProps {
  products: Product[];
  pending: Proposal[];
  held: Proposal[];
  healEvents: HealEvent[];
  loading: boolean;
  busy: string | null;
  onApprove: (id: number) => void;
  onReject: (id: number) => void;
  onApproveAllSafe: () => void;
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
    onApprove,
    onReject,
    onApproveAllSafe,
    onViewAsApi,
  } = props;

  // The heal-event id currently hovered/focused on either list. Lifted here so the held cards and the
  // receipts can highlight each other's matching row (see link.ts) — the two lists share this id.
  const [activeLinkId, setActiveLinkId] = useState<number | null>(null);

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
        <div className="space-y-3">
          {held.map((proposal) => (
            <HeldCard
              key={proposal.id}
              proposal={proposal}
              busy={busy}
              defaultExpanded={false}
              activeLinkId={activeLinkId}
              onLinkActivate={setActiveLinkId}
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
      {/* ① scope */}
      <div className="flex items-center gap-2 text-sm">
        <span className="eyebrow">Checking against</span>
        <span className="font-semibold text-ink">Newegg</span>
        <span className="text-ink-muted">·</span>
        <span className="num text-ink-secondary">{products.length} products</span>
      </div>

      <div
        className={busy ? "pointer-events-none opacity-60 transition-opacity" : "transition-opacity"}
      >
        <div className="mt-8">
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
            <Receipts
              events={healEvents}
              activeLinkId={activeLinkId}
              onLinkActivate={setActiveLinkId}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
