/**
 * The star of the console: a decision the guardian refused to make for you.
 *
 * Two design rules drive this card.
 *
 * The money leads. What the operator needs in the first half-second is not the check name or the
 * confidence score, it is "what would this have cost me?" - so profit_delta_vs_now is set at display
 * size on the COLLAPSED card. It used to live two clicks deep inside a disclosure, which buried the
 * single most persuasive fact the product produces.
 *
 * Every value here is supplied by the backend. The lead sentence is composed from the stored
 * observation price plus the check's stored evidence, so nothing on this card is a hardcoded string
 * pretending to be a finding.
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

/** Field names inside the guardian's evidence, rendered for a human without losing the machine name. */
const EVIDENCE_LABELS: Record<string, string> = {
  field: "field examined",
  looks_like: "now matches",
  proposed_median: "median in the proposed rows",
  baseline_own_median: "its own historical median",
  baseline_other_median: "the other field's median",
  own_distance: "distance from its own distribution",
  other_distance: "distance from the other's",
  upper: "must not exceed",
  inverted_rate: "rows where the order inverted",
  null_rate: "rows with no value",
  baseline_null_rate: "rows with no value, before",
};

function formatEvidence(key: string, value: unknown): string {
  if (typeof value !== "number") return String(value);
  if (key.endsWith("_rate") || key.endsWith("_distance")) {
    return key.endsWith("_rate") ? `${Math.round(value * 100)}%` : value.toFixed(3);
  }
  return money(value);
}

/**
 * What "Investigate" opens.
 *
 * This is the guardian's own working: the measured evidence behind the verdict, and the sharpened
 * instruction it then handed back to Scraper Studio. Showing the re-prompt is the point - it is the
 * clearest single proof that Vouch wraps the heal loop rather than watching it from outside.
 */
function EvidencePanel({ proposal }: { proposal: Proposal }) {
  const guardian = proposal.guardian;
  if (!guardian) return null;

  const rows = Object.entries(guardian.evidence ?? {});

  return (
    <div className="mt-3 animate-rise rounded-md border border-hair bg-plane/70 p-4">
      <p className="eyebrow">The guardian&rsquo;s working</p>

      {rows.length > 0 ? (
        <dl className="mt-2.5 grid grid-cols-[minmax(0,1fr)_auto] gap-x-6 gap-y-1.5 text-xs">
          {rows.map(([key, value]) => (
            <div key={key} className="contents">
              <dt className="min-w-0 text-ink-muted">
                {EVIDENCE_LABELS[key] ?? key.replace(/_/g, " ")}
                <span className="ml-1.5 font-mono text-[10px] text-ink-muted/60">{key}</span>
              </dt>
              <dd className="num text-right text-ink">{formatEvidence(key, value)}</dd>
            </div>
          ))}
        </dl>
      ) : (
        <p className="mt-2 text-xs text-ink-muted">
          This verdict came from the risk brief alone; the check produced no structured evidence.
        </p>
      )}

      <div className="mt-4 border-t border-hair pt-3">
        <p className="eyebrow">
          Instruction sent back to Scraper Studio · attempt {guardian.attempt} of{" "}
          {guardian.attempts_total}
        </p>
        <p className="mt-2 whitespace-pre-wrap rounded border border-hair bg-surface px-3 py-2 font-mono text-[11px] leading-relaxed text-ink-secondary">
          {guardian.prompt}
        </p>
        <p className="mt-2 text-[11px] text-ink-muted text-pretty">
          Written by the validator, not by a person — the medians above are what it put in the
          prompt. Collector{" "}
          <span className="font-mono text-ink-secondary">{guardian.collector_id}</span> was left
          unchanged; the heal was rejected before anything committed.
        </p>
      </div>
    </div>
  );
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
    <div className="mt-3 animate-rise rounded-md border border-hair bg-plane/70 p-4">
      <dl className="grid grid-cols-2 gap-x-6 gap-y-1.5 text-xs sm:grid-cols-4">
        <div className="contents">
          <dt className="text-ink-muted">Our price</dt>
          <dd className="num text-right sm:text-left">
            <span className="text-ink-secondary">{money(cf.current_price)}</span>
            <span className="text-ink-muted"> → </span>
            <span className="text-status-critical">{money(cf.applied_price)}</span>
          </dd>
          <dt className="text-ink-muted">Margin</dt>
          <dd className="num text-right sm:text-left">
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
        </div>
      </dl>

      <p className="mt-3 border-l-2 border-status-critical/40 pl-3 text-xs leading-relaxed text-ink-secondary text-pretty">
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

type Panel = "none" | "evidence" | "counterfactual";

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
  const [panel, setPanel] = useState<Panel>("none");
  const [confirming, setConfirming] = useState(false);
  const cf = proposal.counterfactual;
  const applied = cf?.applied_price ?? null;

  const toggle = (next: Panel) => setPanel((current) => (current === next ? "none" : next));

  return (
    <article className="animate-rise overflow-hidden rounded-lg bg-surface shadow-held">
      {/* A warm hairline across the top. The whole console runs cool until something is held. */}
      <div className="h-[3px] origin-left animate-sweep bg-gradient-to-r from-status-critical via-status-critical/60 to-transparent" />

      {/* The check badge sits beside the title, never floated to the far right: these product names
          run to 120 characters, and a justify-between header wraps the badge onto its own line for
          some cards and not others, which reads as a layout bug across a stack of them. */}
      <div className="px-5 pt-4">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="flex items-center gap-2 text-[13px] font-semibold tracking-tight text-ink">
            <span className="animate-holdpulse text-status-critical" aria-hidden>
              ⏸
            </span>
            Reprice held
          </h3>
          {proposal.guardian?.check_code && <CheckBadge code={proposal.guardian.check_code} />}
        </div>
        <p className="mt-1 truncate text-xs text-ink-secondary" title={proposal.product.name}>
          {proposal.product.name}
        </p>
      </div>

      {/* THE HERO. What this would have cost, on the collapsed card, at display size. */}
      {cf && (
        <div className="mt-3 flex flex-wrap items-end gap-x-5 gap-y-1 px-5">
          <p className="num text-hero font-bold text-status-critical">
            {signedMoney(cf.profit_delta_vs_now)}
          </p>
          <p className="pb-1.5 text-xs text-ink-secondary text-pretty">
            {cf.harm === "competitiveness"
              ? "per unit above today’s price — we’d lose the sale, not the margin"
              : "per unit of margin, on every one sold, had we auto-approved"}
          </p>
        </div>
      )}

      <p className="mt-3 px-5 text-sm leading-relaxed text-ink text-pretty">
        {leadSentence(proposal)}
      </p>

      <div className="mt-3.5 px-5">
        <ConfidenceMeter confidence={proposal.confidence} size="large" />
      </div>

      <p className="mt-3 px-5 text-xs text-ink-muted">
        source: <span className="text-ink-secondary">{new URL(proposal.source.url).hostname}</span>{" "}
        · <Badge tone="critical">unconfirmed</Badge> · {proposal.source.last_confirmed_label}
        {proposal.guardian && (
          <>
            {" "}
            · attempt {proposal.guardian.attempt} of {proposal.guardian.attempts_total}
          </>
        )}
      </p>

      {panel === "evidence" && (
        <div className="px-5">
          <EvidencePanel proposal={proposal} />
        </div>
      )}
      {panel === "counterfactual" && (
        <div className="px-5">
          <CounterfactualPanel proposal={proposal} />
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
            <Button
              variant="secondary"
              onClick={() => toggle("evidence")}
              title="The measured evidence behind this verdict, and the instruction sent back to Scraper Studio"
            >
              {panel === "evidence" ? "Hide evidence" : "Investigate"}
            </Button>
            {cf && (
              <Button
                variant="ghost"
                onClick={() => toggle("counterfactual")}
                title="What acting on this number would have done to the price and the margin"
              >
                {panel === "counterfactual" ? "Hide" : "Show the damage"}
              </Button>
            )}
            <span className="mx-auto" />
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
