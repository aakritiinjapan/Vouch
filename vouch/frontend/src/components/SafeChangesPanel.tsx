/**
 * The routine batch — changes Vouch is confident about (verdict: PASS on verified competitor data).
 * The seller's job here is one click; anything needing judgment belongs in the held section, not here.
 * A single raised region with a hairline header, matching the console's few-boxes rhythm.
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
    <li className="flex flex-wrap items-center gap-x-4 gap-y-2 px-5 py-3.5 transition-colors hover:bg-white/[0.02]">
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm text-ink">{proposal.product.name}</p>
        <p className="text-xs text-ink-muted">
          {proposal.product.sku} · {proposal.source.last_confirmed_label}
        </p>
      </div>

      <div className="num flex items-baseline gap-2 text-sm">
        <span className="text-ink-muted line-through">{money(proposal.current_price)}</span>
        <span className="text-ink">{money(proposal.proposed_price)}</span>
        <span className={up ? "text-xs text-verified" : "text-xs text-watch"}>
          {signedMoney(proposal.delta)}
        </span>
      </div>

      <div className="num w-24 text-right text-xs text-ink-secondary">
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

  // Nothing routine to review: a slim one-line note rather than a tall empty card.
  if (!loading && proposals.length === 0) {
    return (
      <p className="border-t border-hair pt-4 text-sm text-ink-muted text-pretty">
        <span className="font-medium text-ink-secondary">Ready to apply</span> — Nothing routine to
        review; every confirmed source is already priced where Vouch would put it.
      </p>
    );
  }

  return (
    <Card>
      <SectionHeader
        title="Ready to apply"
        count={proposals.length}
        hint="Verdict: PASS — confident changes on verified competitor data."
        action={
          <Button
            variant="primary"
            onClick={onApproveAllSafe}
            busy={busy === "approve-safe"}
            disabled={safeCount === 0}
            title={safeCount === 0 ? "Nothing currently qualifies as a safe change" : undefined}
          >
            Approve all{safeCount > 0 ? ` ${safeCount}` : ""}
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
