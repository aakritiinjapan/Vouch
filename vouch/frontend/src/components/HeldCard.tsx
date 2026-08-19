/**
 * README section 7, CENTER - the star.
 *
 * The seller sees a HELD DECISION, not a healing animation. Every value on this card is supplied by
 * the backend: the lead sentence is composed from the stored observation price plus the check's
 * stored evidence, so nothing here is a hardcoded string pretending to be a finding.
 */

import { useEffect, useState } from "react";

import { api } from "../api";
import { money, pct, signedMoney } from "../format";
import type { History, Proposal } from "../types";
import { PriceChart } from "./PriceChart";
import { Badge, Button, CheckBadge, ConfidenceMeter } from "./ui/Bits";

/**
 * "The healed price ($19.99) matches this competitor's SHIPPING column, not their item price."
 *
 * Built from stored facts - observation.observed_price is the row-level number, evidence.looks_like
 * is the field the guardian matched it against. Falls back to the guardian's own brief when the
 * check did not produce that shape of evidence.
 */
function leadSentence(proposal: Proposal): string {
  const evidence = proposal.guardian?.evidence ?? {};
  const observed = proposal.source.observed_price;

  switch (proposal.guardian?.check_code) {
    case "COLUMN_SWAP": {
      const looksLike = evidence.looks_like;
      if (looksLike && observed !== null) {
        return `The healed price (${money(observed)}) matches this competitor's ${String(
          looksLike,
        ).toUpperCase()} column, not their item price.`;
      }
      break;
    }
    case "VALUE_ORDER_INVERTED": {
      const upper = String(evidence.upper ?? "original price").replace(/_/g, " ");
      const rate = typeof evidence.inverted_rate === "number" ? evidence.inverted_rate : null;
      const where = rate === null ? "" : ` on ${Math.round(rate * 100)}% of rows`;
      const price = observed === null ? "The healed price" : `The healed price (${money(observed)})`;
      return `${price} came back ABOVE this competitor's ${upper}${where} — it is reading the crossed-out ${upper}, not the price a customer pays.`;
    }
  }
  return proposal.guardian?.brief ?? proposal.reason;
}

function CounterfactualPanel({ proposal }: { proposal: Proposal }) {
  const cf = proposal.counterfactual;
  const [history, setHistory] = useState<History | null>(null);

  useEffect(() => {
    let alive = true;
    api
      .history(proposal.product.id)
      .then((h) => alive && setHistory(h))
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [proposal.product.id]);

  if (!cf) return null;

  return (
    <div className="mt-4 rounded-md border border-hair bg-plane/60 p-4">
      {/* The hero figure. Leads with the FLOOR-CLAMPED reality, because that is what our engine
          would actually have done - and it pre-empts "wouldn't your floor rule have caught this?" */}
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-xs text-ink-muted">If we had auto-approved this</p>
          <p className="mt-1 text-5xl font-semibold leading-none text-status-critical">
            {signedMoney(cf.profit_delta_vs_now)}
          </p>
          {/* Both directions are harm, but they are not the same harm. Reading the shipping cost
              pushes the price DOWN and destroys margin; reading the crossed-out original pushes it UP
              and loses the sale. Labelling the second one "margin" would be plainly wrong. */}
          <p className="mt-1 text-xs text-ink-secondary">
            {cf.harm === "competitiveness"
              ? "per unit above today’s price — we’d lose the sale, not the margin"
              : "per unit of margin, on every one sold"}
          </p>
        </div>

        <dl className="grid grid-cols-2 gap-x-6 gap-y-1 text-xs">
          <dt className="text-ink-muted">Our price</dt>
          <dd className="num-tabular text-right">
            <span className="text-ink-secondary">{money(cf.current_price)}</span>
            <span className="text-ink-muted"> → </span>
            <span className="text-status-critical">{money(cf.applied_price)}</span>
          </dd>
          <dt className="text-ink-muted">Margin</dt>
          <dd className="num-tabular text-right">
            <span className="text-ink-secondary">{pct(cf.margin_pct_now)}</span>
            <span className="text-ink-muted"> → </span>
            <span
              className={
                cf.harm === "competitiveness" ? "text-ink-secondary" : "text-status-critical"
              }
            >
              {pct(cf.margin_pct_applied)}
            </span>
          </dd>
        </dl>
      </div>

      <p className="mt-3 border-l-2 border-status-critical/40 pl-3 text-xs text-ink-secondary text-pretty">
        {cf.harm_summary}{" "}
        {cf.harm === "margin" ? (
          <>
            Our floor rule would have clamped this to {money(cf.applied_price)} rather than following
            the competitor all the way down — a repricer <em>without</em> one goes to{" "}
            {money(cf.naive_price)}, margin {pct(cf.margin_pct_naive, 0)}. A floor caps the disaster;
            only verifying the number prevents the damage.
          </>
        ) : (
          <>
            No floor rule helps here — the bad number pushed the price <em>up</em>, and a margin guard
            only ever looks down. Nothing but validating the data catches this one.
          </>
        )}
      </p>

      {history && (
        <div className="mt-4">
          <PriceChart points={history.points} counterfactual={cf} showCounterfactual />
        </div>
      )}
    </div>
  );
}

export function HeldCard({
  proposal,
  busy,
  onApproveAnyway,
  onSkip,
}: {
  proposal: Proposal;
  busy: string | null;
  onApproveAnyway: (id: number) => void;
  onSkip: (id: number) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const applied = proposal.counterfactual?.applied_price ?? null;

  return (
    <article className="rounded-lg bg-surface shadow-held">
      <div className="flex flex-wrap items-start justify-between gap-3 px-5 pt-4">
        <h3 className="flex items-center gap-2 text-sm font-semibold text-ink">
          <span className="animate-holdpulse text-status-critical" aria-hidden>
            ⏸
          </span>
          Reprice held
          <span className="font-normal text-ink-secondary">· {proposal.product.name}</span>
        </h3>
        {proposal.guardian?.check_code && <CheckBadge code={proposal.guardian.check_code} />}
      </div>

      <p className="mt-2 px-5 text-sm leading-relaxed text-ink text-pretty">
        {leadSentence(proposal)}
      </p>

      <div className="mt-3 px-5">
        <ConfidenceMeter confidence={proposal.confidence} />
      </div>

      <p className="mt-2 px-5 text-xs text-ink-muted">
        source: <span className="text-ink-secondary">{new URL(proposal.source.url).hostname}</span>{" "}
        · <Badge tone="critical">unconfirmed</Badge> · {proposal.source.last_confirmed_label}
        {proposal.guardian && (
          <>
            {" "}
            · attempt {proposal.guardian.attempt} of {proposal.guardian.attempts_total}
          </>
        )}
      </p>

      {proposal.counterfactual && (
        <div className="mt-3 px-5">
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className="text-xs font-medium text-ink-secondary hover:text-ink"
            aria-expanded={expanded}
          >
            <span className="inline-block w-3">{expanded ? "▾" : "▸"}</span> What if we&rsquo;d
            auto-approved this?
          </button>
          {expanded && <CounterfactualPanel proposal={proposal} />}
        </div>
      )}

      {/* Approving a hold is deliberate by design: it takes a second, explicit confirmation that
          states the price being applied. The backend also refuses it without force=true. */}
      <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-hair px-5 py-3">
        {confirming ? (
          <>
            <p className="mr-auto text-xs text-status-warning">
              Apply {applied !== null ? money(applied) : "the clamped floor price"} despite
              confidence {proposal.confidence}/100?
            </p>
            <Button
              variant="danger"
              onClick={() => {
                setConfirming(false);
                onApproveAnyway(proposal.id);
              }}
              busy={busy === `approve-${proposal.id}`}
            >
              Yes, approve anyway
            </Button>
            <Button variant="ghost" onClick={() => setConfirming(false)}>
              Cancel
            </Button>
          </>
        ) : (
          <>
            <Button variant="secondary" onClick={() => setExpanded(true)}>
              Investigate
            </Button>
            <Button variant="danger" onClick={() => setConfirming(true)}>
              Approve anyway
            </Button>
            <Button
              variant="ghost"
              onClick={() => onSkip(proposal.id)}
              busy={busy === `reject-${proposal.id}`}
            >
              Skip this cycle
            </Button>
          </>
        )}
      </div>
    </article>
  );
}
