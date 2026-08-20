/**
 * One bad fix, one card.
 *
 * This replaces one-card-per-held-product. Every product in an incident was put on hold by the SAME
 * bad heal on the SAME collector, so the old layout rendered one problem three times and left the
 * viewer unsure whether they were looking at one incident or three.
 *
 * Three rules this card is built around:
 *   1. State what went wrong before what it cost. The money is the stake, not the story.
 *   2. Offer the FIX as the primary action. The previous card offered Investigate / Show the damage /
 *      Approve anyway / Skip - four buttons, none of which fixed anything, while the actual remedy
 *      sat in the page header disconnected from the problem.
 *   3. One money figure at one altitude. Two aggregations of the same quantity read as two facts.
 */

import { useEffect, useState } from "react";

import { api } from "../api";
import { money, pct, signedMoney } from "../format";
import { plainCause, type Incident } from "../incident";
import type { History } from "../types";
import { Badge, Button, CheckBadge, ConfidenceMeter } from "./ui/Bits";
import { Evidence } from "./Evidence";
import { PriceChart } from "./PriceChart";

export function IncidentCard({
  incident,
  busy,
  onRefix,
  onOverride,
  onSkip,
}: {
  incident: Incident;
  busy: string | null;
  onRefix: () => void;
  onOverride: (id: number) => void;
  onSkip: (id: number) => void;
}) {
  const [showEvidence, setShowEvidence] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [history, setHistory] = useState<History | null>(null);
  const many = incident.proposals.length > 1;
  const worstId = incident.worst?.product.id;

  // Fetched only once the evidence is opened: it is the one request on this card, and most viewers
  // never open it.
  useEffect(() => {
    if (!showEvidence || worstId === undefined) return;
    let alive = true;
    api
      .history(worstId)
      .then((h) => alive && setHistory(h))
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [showEvidence, worstId]);

  return (
    <article className="rounded-lg bg-surface shadow-held">
      {/* ---- what happened, in one sentence ------------------------------------------- */}
      <header className="flex flex-wrap items-start justify-between gap-3 px-6 pt-5">
        <h2 className="flex items-center gap-2 text-base font-semibold text-ink">
          <span className="text-status-critical" aria-hidden>
            ⏸
          </span>
          One bad fix — caught before it moved a price
        </h2>
        {incident.checkCode && <CheckBadge code={incident.checkCode} />}
      </header>

      <p className="mt-3 px-6 text-[15px] leading-relaxed text-ink text-pretty">
        {plainCause(incident)}
      </p>

      {/* ---- who it affects, and what trusting it would have cost --------------------- */}
      <div className="mt-4 px-6">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <span className="text-3xl font-semibold leading-none text-status-critical">
            {signedMoney(-incident.totalExposure)}
          </span>
          <span className="text-sm text-ink-secondary">
            per unit{many ? ` across ${incident.proposals.length} products` : ""}, had we trusted it
          </span>
        </div>

        <p className="mt-3 text-sm text-ink-secondary text-pretty">
          {many
            ? `${incident.proposals.length} of your products price against this page, so all ${incident.proposals.length} are on hold.`
            : "This product prices against that page, so its reprice is on hold."}{" "}
          Nothing moved.
        </p>
      </div>

      {/* ---- the affected products, compact ------------------------------------------ */}
      <ul className="mt-3 divide-y divide-hair border-y border-hair">
        {incident.proposals.map((proposal) => (
          <li
            key={proposal.id}
            className="flex items-center justify-between gap-4 px-6 py-2 text-sm"
          >
            <span className="min-w-0 truncate text-ink-secondary" title={proposal.product.name}>
              {proposal.product.name}
            </span>
            <span className="num-tabular shrink-0 text-status-critical">
              {signedMoney(proposal.counterfactual?.profit_delta_vs_now ?? 0)}
            </span>
          </li>
        ))}
      </ul>

      {/* ---- how sure the guardian is ------------------------------------------------ */}
      <div className="px-6 pt-4">
        <ConfidenceMeter confidence={incident.confidence} />
        <p className="mt-2 text-xs text-ink-muted">
          source: <span className="text-ink-secondary">{incident.sourceHost}</span> ·{" "}
          <Badge tone="critical">unconfirmed</Badge> · {incident.staleness} · attempt{" "}
          {incident.attempt} of {incident.attemptsTotal}
        </p>
      </div>

      {/* ---- what to do about it ----------------------------------------------------- */}
      <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-hair px-6 py-4">
        {/* The primary action FIXES it. Everything else accepts or defers. */}
        <Button variant="primary" onClick={onRefix} busy={busy === "run-cycle"}>
          Re-prompt the scraper
        </Button>

        <button
          type="button"
          onClick={() => setShowEvidence((v) => !v)}
          className="text-sm text-ink-secondary underline-offset-4 hover:text-ink hover:underline"
          aria-expanded={showEvidence}
        >
          {showEvidence ? "Hide" : "Show"} the evidence
        </button>

        <span className="flex-1" />

        {confirming ? (
          <span className="flex flex-wrap items-center gap-3 text-sm">
            <span className="text-ink-secondary">
              Apply {money(incident.worst?.counterfactual?.applied_price ?? 0)} anyway?
            </span>
            <button
              type="button"
              onClick={() => incident.worst && onOverride(incident.worst.id)}
              className="font-medium text-status-critical hover:underline"
            >
              Yes, override
            </button>
            <button
              type="button"
              onClick={() => setConfirming(false)}
              className="text-ink-muted hover:text-ink"
            >
              Cancel
            </button>
          </span>
        ) : (
          <>
            <button
              type="button"
              onClick={() => setConfirming(true)}
              className="text-sm text-ink-muted hover:text-status-critical"
            >
              Override
            </button>
            <button
              type="button"
              onClick={() => incident.worst && onSkip(incident.worst.id)}
              className="text-sm text-ink-muted hover:text-ink"
            >
              Skip
            </button>
          </>
        )}
      </div>

      {showEvidence && incident.worst && (
        <div className="border-t border-hair px-6 pb-5 pt-4">
          <Evidence proposal={incident.worst} />
          {incident.harm === "margin" ? (
            <p className="mt-4 border-l-2 border-status-critical/40 pl-3 text-xs text-ink-secondary text-pretty">
              Our floor rule would have stopped the price at{" "}
              {money(incident.worst.counterfactual?.applied_price ?? 0)} rather than following the
              competitor all the way down. A repricer without one goes to{" "}
              {money(incident.worst.counterfactual?.naive_price ?? 0)} — margin{" "}
              {pct(incident.worst.counterfactual?.margin_pct_naive ?? null, 0)}. A floor caps the
              disaster; only checking the number prevents it.
            </p>
          ) : (
            <p className="mt-4 border-l-2 border-status-critical/40 pl-3 text-xs text-ink-secondary text-pretty">
              No floor rule helps here — the bad number pushed the price <em>up</em>, and a margin
              guard only ever looks down. Nothing but checking the data catches this one.
            </p>
          )}

          {/* The honest gap, README section 7: an unconfirmed cycle leaves a HOLE in the competitor
              line rather than an interpolated straight line. It is the clearest visual proof that we
              do not invent continuity when a source stops being trustworthy. */}
          {history && (
            <div className="mt-4">
              <PriceChart
                points={history.points}
                counterfactual={incident.worst.counterfactual}
                showCounterfactual
              />
            </div>
          )}
        </div>
      )}
    </article>
  );
}
