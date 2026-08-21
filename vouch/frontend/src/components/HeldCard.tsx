/**
 * The core of the console: a decision the guardian refused to make for you.
 *
 * Card order follows UI_PLAN: price facts → Verdict Seal → plain-English reason → consequence +
 * "show the damage" → actions. The seal is the pivot; the same object appears in the receipts and the
 * Trust API, and `view as API →` bridges this exact row to that surface.
 *
 * Every value is supplied by the backend — the lead sentence is composed from the stored observation
 * plus the check's evidence, so nothing here is a hardcoded finding.
 */

import { useEffect, useState } from "react";

import { api } from "../api";
import { money, pct, signedMoney } from "../format";
import type { History, Proposal } from "../types";
import { toDecision } from "../verdict";
import { PriceChart } from "./PriceChart";
import { VerdictSeal } from "./VerdictSeal";
import { Badge, Button, CheckBadge } from "./ui/Bits";
import { TrustLegend } from "./TrustLegend";

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

function EvidencePanel({
  proposal,
  onViewAsApi,
}: {
  proposal: Proposal;
  onViewAsApi?: () => void;
}) {
  const guardian = proposal.guardian;
  if (!guardian) return null;
  const rows = Object.entries(guardian.evidence ?? {});

  return (
    <div className="mt-3 animate-rise rounded-lg border border-hair bg-raised/50 p-4">
      <p className="eyebrow">The guardian&rsquo;s working</p>

      {rows.length > 0 ? (
        <dl className="mt-2.5 grid grid-cols-[minmax(0,1fr)_auto] gap-x-6 gap-y-1.5 text-xs">
          {rows.map(([key, value]) => (
            <div key={key} className="contents">
              <dt className="min-w-0 text-ink-muted">
                {EVIDENCE_LABELS[key] ?? key.replace(/_/g, " ")}
                <span className="ml-1.5 font-mono text-[10px] text-ink-muted/70">{key}</span>
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
          What we told the scraper to fix · attempt {guardian.attempt} of {guardian.attempts_total}
        </p>
        <p className="mt-2 whitespace-pre-wrap rounded border border-hair bg-surface px-3 py-2 font-mono text-[11px] leading-relaxed text-ink-secondary">
          {guardian.prompt}
        </p>
        <p className="mt-2 text-[11px] text-ink-muted text-pretty">
          Written by the validator, not a person. Collector{" "}
          <span className="font-mono text-ink-secondary">{guardian.collector_id}</span> was left
          unchanged — rejected before anything committed.
        </p>
      </div>

      {onViewAsApi && (
        <div className="mt-3 flex justify-end">
          <button
            type="button"
            onClick={onViewAsApi}
            className="text-xs font-semibold text-holo-violet hover:underline"
          >
            view this verdict as API →
          </button>
        </div>
      )}
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
    <div className="mt-3 animate-rise rounded-lg border border-hair bg-raised/50 p-4">
      <p className="eyebrow">What acting on this would have done</p>
      <dl className="mt-2.5 grid grid-cols-2 gap-x-6 gap-y-1.5 text-xs sm:grid-cols-4">
        <div className="contents">
          <dt className="text-ink-muted">Our price</dt>
          <dd className="num text-right sm:text-left">
            <span className="text-ink-secondary">{money(cf.current_price)}</span>
            <span className="text-ink-muted"> → </span>
            <span className="text-status-critical">{money(cf.applied_price)}</span>
          </dd>
          <dt className="text-ink-muted">Our margin</dt>
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
            Our floor rule would clamp this to {money(cf.applied_price)} rather than following the
            competitor all the way down — a repricer <em>without</em> one goes to{" "}
            {money(cf.naive_price)}, margin {pct(cf.margin_pct_naive, 0)}. A floor caps the disaster;
            only verifying the number prevents it.
          </>
        ) : (
          <>
            No floor rule helps here — the bad number pushed the price <em>up</em>, and a margin guard
            only ever looks down. Nothing but validating the data catches this one.
          </>
        )}
      </p>

      {history && history.points.length > 1 && (
        <div className="mt-4">
          <PriceChart points={history.points} counterfactual={cf} showCounterfactual />
        </div>
      )}
    </div>
  );
}

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="eyebrow">{label}</dt>
      <dd className="num mt-1 text-sm text-ink">{children}</dd>
    </div>
  );
}

type Panel = "none" | "evidence" | "counterfactual";

export function HeldCard({
  proposal,
  busy,
  onApproveAnyway,
  onSkip,
  onViewAsApi,
}: {
  proposal: Proposal;
  busy: string | null;
  onApproveAnyway: (id: number) => void;
  onSkip: (id: number) => void;
  onViewAsApi?: (proposal: Proposal) => void;
}) {
  const [panel, setPanel] = useState<Panel>("none");
  const [confirming, setConfirming] = useState(false);
  const cf = proposal.counterfactual;
  const applied = cf?.applied_price ?? null;
  const decision = toDecision(proposal.guardian?.verdict, proposal.confidence);

  const toggle = (next: Panel) => setPanel((current) => (current === next ? "none" : next));

  return (
    <article className="animate-rise overflow-hidden rounded-2xl bg-surface shadow-held">
      <div className="h-[3px] bg-holo-cta bg-[length:200%_auto] animate-sheen" />

      <div className="px-5 pt-4">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="flex items-center gap-2 text-[13px] font-semibold tracking-tight text-ink">
            <span
              className="inline-block size-2 animate-holdpulse rounded-full bg-status-critical"
              aria-hidden
            />
            Reprice on hold
          </h3>
          {proposal.guardian?.check_code && <CheckBadge code={proposal.guardian.check_code} />}
        </div>
        <p className="mt-1 truncate text-xs text-ink-secondary" title={proposal.product.name}>
          {proposal.product.name} · vs Newegg
        </p>
      </div>

      {/* 1. price facts */}
      <dl className="mt-4 grid grid-cols-3 gap-3 px-5">
        <Fact label="Our price">{money(proposal.current_price)}</Fact>
        <Fact label="Our margin">
          {pct(proposal.margin_pct_now)}{" "}
          <span className="text-[11px] font-normal text-ink-muted">
            (floor ≈ {money(proposal.floor_price)})
          </span>
        </Fact>
        <Fact label="Competitor price">
          <span className="text-status-critical">⚠ couldn&rsquo;t verify</span>
        </Fact>
      </dl>

      {/* 2. Verdict Seal + 3. plain-English reason */}
      <div className="mt-4 flex items-start gap-4 px-5">
        <VerdictSeal decision={decision} score={proposal.confidence} size={92} />
        <div className="min-w-0">
          <p className="text-sm leading-relaxed text-ink text-pretty">{leadSentence(proposal)}</p>
          {onViewAsApi && (
            <button
              type="button"
              onClick={() => onViewAsApi(proposal)}
              className="mt-2 text-xs font-semibold text-holo-violet hover:underline"
            >
              view as API →
            </button>
          )}
        </div>
      </div>

      <p className="mt-3 px-5 text-xs text-ink-muted">
        source: <span className="text-ink-secondary">{new URL(proposal.source.url).hostname}</span>{" "}
        · <Badge tone="critical">unconfirmed</Badge> · {proposal.source.last_confirmed_label}
      </p>

      {/* 4. consequence */}
      {cf && (
        <div className="mt-3 flex flex-wrap items-baseline gap-x-2 px-5">
          <span className="eyebrow">If auto-applied</span>
          <span className="num text-lg font-bold text-status-critical">
            {signedMoney(cf.profit_delta_vs_now)}
          </span>
          <span className="text-xs text-ink-muted text-pretty">
            {cf.harm === "competitiveness"
              ? "per unit above today’s price — we’d lose the sale"
              : "per unit of margin, on every one sold"}
          </span>
        </div>
      )}

      <div className="mt-3 px-5">
        <TrustLegend />
      </div>

      {panel === "evidence" && (
        <div className="px-5">
          <EvidencePanel proposal={proposal} onViewAsApi={onViewAsApi && (() => onViewAsApi(proposal))} />
        </div>
      )}
      {panel === "counterfactual" && (
        <div className="px-5">
          <CounterfactualPanel proposal={proposal} />
        </div>
      )}

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
              Skip
            </Button>
          </>
        )}
      </div>
    </article>
  );
}
