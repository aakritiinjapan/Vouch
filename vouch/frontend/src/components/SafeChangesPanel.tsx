/**
 * README section 7, TOP: the routine batch.
 *
 * These are changes Vouch is confident about. The seller's job here is one click - anything needing
 * judgment belongs in HeldDecisions below, not in this list.
 */

import { money, pct, signedMoney } from "../format";
import type { Proposal } from "../types";
import { Button, Card, EmptyState, SectionHeader, Skeleton } from "./ui/Bits";

function ProposalRow({
  proposal,
  onApprove,
  onReject,
  busy,
}: {
  proposal: Proposal;
  onApprove: () => void;
  onReject: () => void;
  busy: string | null;
}) {
  const up = proposal.delta > 0;

  return (
    <li className="flex flex-wrap items-center gap-x-4 gap-y-2 px-5 py-3 hover:bg-raised/40">
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm text-ink">{proposal.product.name}</p>
        <p className="text-xs text-ink-muted">
          {proposal.product.sku} · {proposal.source.last_confirmed_label}
        </p>
      </div>

      <div className="num-tabular flex items-baseline gap-2 text-sm">
        <span className="text-ink-muted line-through">{money(proposal.current_price)}</span>
        <span className="text-ink">{money(proposal.proposed_price)}</span>
        <span className={up ? "text-status-good text-xs" : "text-status-warning text-xs"}>
          {signedMoney(proposal.delta)}
        </span>
      </div>

      <div className="num-tabular w-24 text-right text-xs text-ink-secondary">
        margin {pct(proposal.margin_pct_after)}
      </div>

      <div className="flex items-center gap-1.5">
        <Button variant="secondary" onClick={onApprove} busy={busy === `approve-${proposal.id}`}>
          Approve
        </Button>
        <Button variant="ghost" onClick={onReject} busy={busy === `reject-${proposal.id}`}>
          Skip
        </Button>
      </div>
    </li>
  );
}

export function SafeChangesPanel({
  proposals,
  loading,
  busy,
  onApprove,
  onReject,
  onApproveAllSafe,
}: {
  proposals: Proposal[];
  loading: boolean;
  busy: string | null;
  onApprove: (id: number) => void;
  onReject: (id: number) => void;
  onApproveAllSafe: () => void;
}) {
  const safeCount = proposals.filter((p) => p.is_safe).length;

  return (
    <Card>
      <SectionHeader
        title="Routine reprice proposals"
        count={proposals.length}
        hint="Confident changes, within the safe margin band."
        action={
          <Button
            variant="primary"
            onClick={onApproveAllSafe}
            busy={busy === "approve-safe"}
            disabled={safeCount === 0}
            title={safeCount === 0 ? "Nothing currently qualifies as a safe change" : undefined}
          >
            Approve all safe changes{safeCount > 0 ? ` (${safeCount})` : ""}
          </Button>
        }
      />

      {loading && proposals.length === 0 ? (
        <Skeleton rows={3} />
      ) : proposals.length === 0 ? (
        <EmptyState
          title="Nothing routine to review"
          body="Every confirmed source is already priced where Vouch would put it. Run a cycle to check again."
        />
      ) : (
        <ul className="divide-y divide-hair">
          {proposals.map((proposal) => (
            <ProposalRow
              key={proposal.id}
              proposal={proposal}
              busy={busy}
              onApprove={() => onApprove(proposal.id)}
              onReject={() => onReject(proposal.id)}
            />
          ))}
        </ul>
      )}
    </Card>
  );
}
