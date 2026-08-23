/**
 * The core of the console: a decision the guardian refused to make for you.
 *
 * Card order follows UI_PLAN: price facts → Verdict Gauge → plain-English reason → consequence +
 * "show the damage" → actions. The gauge is the pivot; the same object appears in the receipts and the
 * Trust API, and `view as API →` bridges this exact row to that surface.
 *
 * Every value is supplied by the backend — the lead sentence is composed from the stored observation
 * plus the check's evidence, so nothing here is a hardcoded finding.
 */

import { useEffect, useState } from "react";

import { api } from "../api";
import { money, pct, signedMoney } from "../format";
import { LINK_HIGHLIGHT_CLASS, proposalLinkId } from "../link";
import type { History, Proposal } from "../types";
import { toDecision } from "../verdict";
import { PriceChart } from "./PriceChart";
import { VerdictGauge } from "./VerdictGauge";
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
    <div className="mt-4 animate-reveal rounded-lg border border-hair bg-white/[0.02] p-4">
      <p className="eyebrow">The guardian&rsquo;s working</p>

      {rows.length > 0 ? (
        <dl className="mt-3 grid grid-cols-[minmax(0,1fr)_auto] gap-x-6 gap-y-2 text-xs">
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
        <p className="mt-2 whitespace-pre-wrap rounded-md border border-hair bg-canvas px-3 py-2.5 font-mono text-[11px] leading-relaxed text-ink-secondary">
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
            className="text-xs font-semibold text-brand hover:text-brand-soft hover:underline"
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
    <div className="mt-4 animate-reveal rounded-lg border border-hair bg-white/[0.02] p-4">
      <p className="eyebrow">What acting on this would have done</p>
      <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-2 text-xs sm:grid-cols-4">
        <div className="contents">
          <dt className="text-ink-muted">Our price</dt>
          <dd className="num text-right sm:text-left">
            <span className="text-ink-secondary">{money(cf.current_price)}</span>
            <span className="text-ink-muted"> → </span>
            <span className="text-held">{money(cf.applied_price)}</span>
          </dd>
          <dt className="text-ink-muted">Our margin</dt>
          <dd className="num text-right sm:text-left">
            <span className="text-ink-secondary">{pct(cf.margin_pct_now)}</span>
            <span className="text-ink-muted"> → </span>
            <span className={cf.harm === "competitiveness" ? "text-ink-secondary" : "text-held"}>
              {pct(cf.margin_pct_applied)}
            </span>
          </dd>
        </div>
      </dl>

      <p className="mt-3 border-l-2 border-held/50 pl-3 text-xs leading-relaxed text-ink-secondary text-pretty">
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
      <dd className="num mt-1.5 text-sm text-ink">{children}</dd>
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
  defaultExpanded = true,
  activeLinkId = null,
  onLinkActivate,
}: {
  proposal: Proposal;
  busy: string | null;
  onApproveAnyway: (id: number) => void;
  onSkip: (id: number) => void;
  onViewAsApi?: (proposal: Proposal) => void;
  defaultExpanded?: boolean;
  /** The heal-event id currently hovered/focused on either list; highlights the matching pair. */
  activeLinkId?: number | null;
  onLinkActivate?: (id: number | null) => void;
}) {
  const [panel, setPanel] = useState<Panel>("none");
  const [confirming, setConfirming] = useState(false);
  const [expanded, setExpanded] = useState(defaultExpanded);
  const cf = proposal.counterfactual;
  const applied = cf?.applied_price ?? null;
  const decision = toDecision(proposal.guardian?.verdict, proposal.confidence);

  const toggle = (next: Panel) => setPanel((current) => (current === next ? "none" : next));

  // The exact id this hold shares with its receipt (see link.ts) — drives the cross-highlight.
  const linkId = proposalLinkId(proposal.guardian?.heal_event_id);
  const linked = linkId !== null && linkId === activeLinkId;
  // onFocus/onBlur on the article catch keyboard focus of any inner control (React focus bubbles).
  const linkHandlers = onLinkActivate
    ? {
        onMouseEnter: () => onLinkActivate(linkId),
        onMouseLeave: () => onLinkActivate(null),
        onFocus: () => onLinkActivate(linkId),
        onBlur: () => onLinkActivate(null),
      }
    : {};

  // Restrained held treatment: a held-colour left accent bar + one hairline + subtle elevation —
  // the state reads without three full cards engulfing the page like alarms.
  const shell = `animate-reveal overflow-hidden rounded-lg border border-hair border-l-[3px] border-l-held bg-surface shadow-soft transition duration-200${
    linked ? ` ${LINK_HIGHLIGHT_CLASS}` : ""
  }`;

  // Collapsed: a compact summary row — name · gauge · exposure · chevron to expand in place.
  if (!expanded) {
    return (
      <article className={shell} data-link-id={linkId ?? undefined} {...linkHandlers}>
        <button
          type="button"
          onClick={() => setExpanded(true)}
          className="flex w-full items-center gap-4 px-5 py-3.5 text-left"
          aria-expanded={false}
          aria-label="Expand this decision"
        >
          <VerdictGauge decision={decision} score={proposal.confidence} size={44} animate={false} />
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium text-ink" title={proposal.product.name}>
              {proposal.product.name}
            </p>
            <p className="mt-0.5 truncate text-xs text-ink-muted">
              {proposal.guardian?.check_code ?? "held"} · couldn&rsquo;t verify · vs {new URL(proposal.source.url).hostname}
            </p>
          </div>
          {cf && (
            <div className="hidden shrink-0 text-right sm:block">
              <p className="eyebrow">If auto-applied</p>
              <p className="num mt-0.5 text-sm font-bold text-held">
                {signedMoney(cf.profit_delta_vs_now)}
              </p>
            </div>
          )}
          <span aria-hidden className="shrink-0 text-ink-muted">
            ▸
          </span>
        </button>
      </article>
    );
  }

  return (
    <article className={shell} data-link-id={linkId ?? undefined} {...linkHandlers}>
      <div className="flex items-start justify-between px-6 pt-5">
        <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.12em] text-held">
            <span
              className="inline-block size-2 animate-holdpulse rounded-full bg-held"
              aria-hidden
            />
            Reprice on hold
          </h3>
          {proposal.guardian?.check_code && <CheckBadge code={proposal.guardian.check_code} />}
        </div>
          <p className="mt-2 truncate text-sm font-medium text-ink" title={proposal.product.name}>
            {proposal.product.name} <span className="text-ink-muted">· vs {new URL(proposal.source.url).hostname}</span>
          </p>
        </div>
        <button
          type="button"
          onClick={() => setExpanded(false)}
          aria-expanded
          aria-label="Collapse this decision"
          className="ml-3 shrink-0 rounded-md px-1.5 text-ink-muted hover:text-ink"
        >
          ▾
        </button>
      </div>

      {/* 1. price facts */}
      <dl className="mt-5 grid grid-cols-3 gap-4 px-6">
        <Fact label="Our price">{money(proposal.current_price)}</Fact>
        <Fact label="Our margin">
          {pct(proposal.margin_pct_now)}{" "}
          <span className="text-[11px] font-normal text-ink-muted">
            (floor ≈ {money(proposal.floor_price)})
          </span>
        </Fact>
        <Fact label="Competitor price">
          <span className="text-held">⚠ couldn&rsquo;t verify</span>
        </Fact>
      </dl>

      {/* 2. Verdict Gauge + 3. plain-English reason */}
      <div className="mt-6 flex items-center gap-5 px-6">
        <VerdictGauge decision={decision} score={proposal.confidence} size={104} />
        <div className="min-w-0">
          <p className="text-[15px] leading-relaxed text-ink text-pretty">
            {leadSentence(proposal)}
          </p>
          {onViewAsApi && (
            <button
              type="button"
              onClick={() => onViewAsApi(proposal)}
              className="mt-2.5 text-xs font-semibold text-brand hover:text-brand-soft hover:underline"
            >
              view as API →
            </button>
          )}
        </div>
      </div>

      <p className="mt-3.5 px-6 text-xs text-ink-muted">
        source: <span className="text-ink-secondary">{new URL(proposal.source.url).hostname}</span> ·{" "}
        <Badge tone="critical">unconfirmed</Badge> · {proposal.source.last_confirmed_label}
      </p>

      {/* 4. consequence */}
      {cf && (
        <div className="mt-4 flex flex-wrap items-baseline gap-x-2.5 px-6">
          <span className="eyebrow">If auto-applied</span>
          <span className="num text-xl font-bold text-held">
            {signedMoney(cf.profit_delta_vs_now)}
          </span>
          <span className="text-xs text-ink-muted text-pretty">
            {cf.harm === "competitiveness"
              ? "per unit above today's price — we'd lose the sale"
              : "per unit of margin, on every one sold"}
          </span>
        </div>
      )}

      <div className="mt-4 px-6">
        <TrustLegend />
      </div>

      {panel === "evidence" && (
        <div className="px-6">
          <EvidencePanel
            proposal={proposal}
            onViewAsApi={onViewAsApi && (() => onViewAsApi(proposal))}
          />
        </div>
      )}
      {panel === "counterfactual" && (
        <div className="px-6">
          <CounterfactualPanel proposal={proposal} />
        </div>
      )}

      <div className="mt-5 flex flex-wrap items-center gap-2 border-t border-hair px-6 py-4">
        {confirming ? (
          <>
            <p className="mr-auto text-xs text-watch">
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
