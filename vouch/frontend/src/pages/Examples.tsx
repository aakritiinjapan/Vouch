/**
 * Worked examples — two pipelines, side by side, showing what a verified heal was worth.
 *
 * Separate from the console on purpose. The console is the PRODUCT: one seller's live pricing desk.
 * This page is the ARGUMENT: the same verification layer serving two consumers who lose money in
 * opposite directions. Collapsing them would make the console a demo, and the demo a product.
 *
 * Both examples reduce to `Finding[]` (scenario.ts) and render through the same table, which is the
 * claim being made visible — a second consumer needed no second screen. What differs is only where
 * the rows came from and who the wrong number costs.
 *
 * Nothing here is narrated. The repricing rows are held proposals from the live cycle; the sale-audit
 * rows are the real guardian's response to POST /verify, expanded from the evidence it returned.
 */

import { useEffect, useMemo, useState } from "react";

import { api } from "../api";
import { VerdictGauge } from "../components/VerdictGauge";
import { EmptyState } from "../components/ui/Bits";
import { money } from "../format";
import { SALE_BASELINE, SALE_CANDIDATE, SALE_REFERENCE_PRICES } from "../saleAudit";
import {
  SCENARIOS,
  findingsFromProposals,
  findingsFromVerify,
  type Finding,
  type ScenarioId,
} from "../scenario";
import type { HealEvent, Proposal, VerifyResponse } from "../types";
import { toDecision } from "../verdict";

export interface ExamplesProps {
  /** held proposals from the live cycle — the repricing example's rows */
  held: Proposal[];
  healEvents: HealEvent[];
  initialCase?: ScenarioId;
}

export function Examples({ held, healEvents, initialCase }: ExamplesProps) {
  const [active, setActive] = useState<ScenarioId>(initialCase ?? "repricing");
  const [sale, setSale] = useState<VerifyResponse | null>(null);
  const [saleError, setSaleError] = useState<string | null>(null);
  const [saleLoading, setSaleLoading] = useState(false);
  const [openKey, setOpenKey] = useState<string | null>(null);

  // The audit has no rows in our database — it is a claim about a page, judged on demand. Fetched
  // once, with the failure kept local so a dead endpoint cannot take the page down with it.
  useEffect(() => {
    if (active !== "sale-audit" || sale || saleLoading) return;
    setSaleLoading(true);
    setSaleError(null);
    api
      .verify({
        candidate_records: SALE_CANDIDATE as unknown as Record<string, unknown>[],
        baseline_records: SALE_BASELINE as unknown as Record<string, unknown>[],
        reference_prices: SALE_REFERENCE_PRICES,
      })
      .then(({ data }) => setSale(data))
      .catch((err: Error) => setSaleError(err.message))
      .finally(() => setSaleLoading(false));
  }, [active, sale, saleLoading]);

  const meta = SCENARIOS.find((s) => s.id === active)!;
  const findings: Finding[] = useMemo(
    () =>
      active === "repricing"
        ? findingsFromProposals(held)
        : sale
          ? findingsFromVerify(sale)
          : [],
    [active, held, sale],
  );

  const open = findings.find((f) => f.key === openKey) ?? null;
  const exposure = findings.reduce((sum, f) => sum + Math.abs(f.risk ?? 0), 0);
  const worst = findings.reduce((low, f) => (f.risk != null && f.risk < low ? f.risk : low), 0);
  const judged = healEvents.length;
  const accuracy = judged
    ? healEvents.reduce((sum, e) => sum + e.proposed_confidence, 0) / judged
    : null;

  return (
    <div className="mx-auto max-w-[1200px] px-6 py-8">
      <header>
        <p className="eyebrow">Worked examples</p>
        <h1 className="mt-1 font-display text-title font-bold text-ink">
          One verification layer, two things it protects
        </h1>
        <p className="mt-2 max-w-3xl text-ink-secondary text-pretty">
          Both examples run the same guardian over a real Bright Data self-heal. The only difference is
          who acts on the number afterwards — and therefore what being wrong costs.
        </p>
      </header>

      {/* Two examples, named and numbered, so they never read as one screen with a filter. */}
      <div
        role="tablist"
        aria-label="Examples"
        className="mt-6 flex flex-wrap gap-2 border-b border-hair"
      >
        {SCENARIOS.map((s) => {
          const on = s.id === active;
          return (
            <button
              key={s.id}
              type="button"
              role="tab"
              aria-selected={on}
              onClick={() => {
                setActive(s.id);
                setOpenKey(null);
              }}
              className={`-mb-px rounded-t-lg border-x border-t px-4 py-2.5 text-left text-sm transition-colors ${
                on
                  ? "border-hair bg-surface text-ink"
                  : "border-transparent text-ink-muted hover:text-ink"
              }`}
            >
              <span className="block font-semibold">{s.label}</span>
              <span className="mt-0.5 block text-[11.5px] font-normal text-ink-muted">
                {s.headline}
              </span>
            </button>
          );
        })}
      </div>

      <section className="mt-6" aria-label={meta.label}>
        {/* What broke, and what it would have cost — the impact, before any table. */}
        <div className="rounded-xl border border-hair bg-surface p-5">
          <div className="flex flex-wrap items-start justify-between gap-x-8 gap-y-3">
            <div className="max-w-2xl">
              <p className="eyebrow">What happened</p>
              <p className="mt-1.5 text-sm text-ink-secondary text-pretty">{meta.trigger}</p>
              <p className="mt-2.5 text-sm text-ink text-pretty">{meta.impact}</p>
            </div>
            <dl className="grid shrink-0 grid-cols-2 gap-x-7 gap-y-2 text-xs">
              <Fact label="Pipeline" value={meta.pipeline} />
              <Fact label="Source read" value={meta.source} />
              <Fact label="Who acts on it" value={meta.whoActs} />
              <Fact
                label="Heals judged"
                value={accuracy == null ? "—" : `${judged} · mean ${accuracy.toFixed(1)}/100`}
              />
            </dl>
          </div>
        </div>

        <div className="mt-3.5 grid grid-cols-1 gap-3.5 sm:grid-cols-3">
          <Tile
            tone="held"
            label="Silent corruptions intercepted"
            value={`${findings.length} Held`}
            foot={findings.length ? "each caught before it committed" : "nothing being withheld"}
          />
          <Tile
            tone="verified"
            label={active === "repricing" ? "Downstream value protected" : "Overstated discount exposed"}
            value={money(exposure)}
            foot={worst < 0 ? `Worst single case ${money(worst)}` : "no exposure measured"}
          />
          <Tile
            tone="brand"
            label="Verdict on the heal"
            value={
              active === "repricing"
                ? "Rejected"
                : sale
                  ? sale.decision.toUpperCase()
                  : "—"
            }
            foot={
              active === "repricing"
                ? "extraction was wrong — the repair was refused"
                : "extraction was right — the retailer's claim was not"
            }
          />
        </div>

        <div className="mt-3.5 overflow-hidden rounded-xl border border-hair bg-surface">
          {saleLoading && (
            <p className="px-5 py-10 text-center text-sm text-ink-muted">
              asking the guardian to judge {SALE_CANDIDATE.length} advertised discounts…
            </p>
          )}
          {saleError && (
            <p className="px-5 py-6 text-sm text-held">
              Could not reach the verification API: {saleError}
            </p>
          )}

          {!saleLoading && !saleError && findings.length === 0 ? (
            <EmptyState
              title="Nothing held in this example right now"
              body={
                active === "repricing"
                  ? "Run the repricing demo from the Demo control on the console to produce a hold, then come back."
                  : "No advertised was-price on this page exceeds what we recorded before the sale."
              }
            />
          ) : (
            !saleLoading &&
            !saleError && (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-hair text-left text-[10.5px] uppercase tracking-[0.09em] text-ink-muted">
                    <th scope="col" className="px-5 py-2.5 font-semibold">{meta.entityLabel}</th>
                    <th scope="col" className="px-3 py-2.5 font-semibold">Anomaly finding</th>
                    <th scope="col" className="px-3 py-2.5 font-semibold">{meta.riskLabel}</th>
                    <th scope="col" className="px-5 py-2.5 text-right font-semibold">Evidence</th>
                  </tr>
                </thead>
                <tbody>
                  {findings.map((f) => (
                    <tr key={f.key} className="border-t border-hair/70">
                      <td className="max-w-[26rem] px-5 py-3.5 font-medium text-ink">{f.entity}</td>
                      <td className="px-3 py-3.5">
                        {f.code ? (
                          <code className="text-[12px] text-watch">{f.code}</code>
                        ) : (
                          <span className="text-ink-muted">—</span>
                        )}
                      </td>
                      <td className="px-3 py-3.5">
                        {f.risk == null ? (
                          <span className="text-ink-muted">—</span>
                        ) : (
                          <span className="num font-semibold text-held">
                            {money(f.risk)}
                            <span className="ml-1 text-[11px] font-normal text-ink-muted">
                              / unit
                            </span>
                          </span>
                        )}
                      </td>
                      <td className="px-5 py-3.5 text-right">
                        <button
                          type="button"
                          onClick={() => setOpenKey(openKey === f.key ? null : f.key)}
                          aria-expanded={openKey === f.key}
                          className="rounded-md bg-brand px-3 py-1.5 text-xs font-semibold text-white hover:bg-brand/85"
                        >
                          {openKey === f.key ? "Close" : "Investigate"}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )
          )}
        </div>

        {open && (
          <Investigate finding={open} judgeConsulted={sale?.judge_consulted ?? false} />
        )}
      </section>
    </div>
  );
}

/** The two numbers that make the case, then what each path would have cost. */
function Investigate({ finding, judgeConsulted }: { finding: Finding; judgeConsulted: boolean }) {
  const decision = toDecision(finding.decision, finding.confidence);
  return (
    <section
      className="mt-3.5 rounded-xl border border-hair bg-surface p-5"
      aria-label="Investigation detail"
    >
      <p className="eyebrow mb-4">Investigate: {finding.entity}</p>

      <div className="grid grid-cols-1 gap-3.5 lg:grid-cols-2">
        <div className="rounded-lg border border-hair bg-surface-raised p-4">
          <h3 className="mb-3 text-[10.5px] font-semibold uppercase tracking-[0.09em] text-ink-muted">
            Historical baseline vs extracted sample
          </h3>
          <dl className="space-y-1.5 text-sm">
            <Row label={finding.expectedLabel} value={finding.expected} tone="verified" />
            <Row label={finding.observedLabel} value={finding.observed} tone="held" />
          </dl>

          <div className="mt-4 grid grid-cols-2 gap-3">
            <Outcome
              tone="held"
              head="Without Vouch"
              value={finding.withoutVouch}
              note={finding.withoutVouchNote}
            />
            <Outcome
              tone="verified"
              head="With Vouch"
              value={finding.withVouch}
              note={finding.withVouchNote}
            />
          </div>
        </div>

        <div className="rounded-lg border border-hair bg-surface-raised p-4">
          <h3 className="mb-3 text-[10.5px] font-semibold uppercase tracking-[0.09em] text-ink-muted">
            {judgeConsulted ? "Tier-3 LLM-as-a-judge verdict" : "What the guardian found"}
          </h3>
          <div className="flex items-start gap-4">
            <VerdictGauge decision={decision} score={finding.confidence} size={92} />
            <p className="flex-1 text-sm text-ink-secondary text-pretty">{finding.brief}</p>
          </div>
          {!judgeConsulted && (
            <p className="mt-3 border-t border-hair pt-3 text-[11.5px] text-ink-muted">
              Decided by the deterministic tiers alone — the semantic judge is consulted only when the
              statistics are ambiguous, and it was not needed here.
            </p>
          )}
          {finding.riskNote && <p className="mt-3 text-[11.5px] text-ink-muted">{finding.riskNote}</p>}
        </div>
      </div>
    </section>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-[10.5px] uppercase tracking-[0.08em] text-ink-muted">{label}</dt>
      <dd className="mt-0.5 font-medium text-ink">{value}</dd>
    </div>
  );
}

function Row({
  label,
  value,
  tone,
}: {
  label: string;
  value: number | null;
  tone: "verified" | "held";
}) {
  return (
    <div className="flex items-baseline justify-between gap-4">
      <dt className="text-ink-muted">{label}</dt>
      <dd className={`num font-semibold ${tone === "held" ? "text-held" : "text-verified"}`}>
        {value == null ? "—" : money(value)}
      </dd>
    </div>
  );
}

function Outcome({
  tone,
  head,
  value,
  note,
}: {
  tone: "held" | "verified";
  head: string;
  value: string;
  note: string;
}) {
  const ring = tone === "held" ? "border-held/40 bg-held/10" : "border-verified/40 bg-verified/10";
  const text = tone === "held" ? "text-held" : "text-verified";
  return (
    <div className={`rounded-lg border p-3 text-center ${ring}`}>
      <p className={`text-[10.5px] font-semibold uppercase tracking-[0.08em] ${text}`}>{head}</p>
      <p className="mt-1.5 font-display text-sm font-bold text-ink">{value}</p>
      <p className={`mt-0.5 text-[11px] ${text}`}>{note}</p>
    </div>
  );
}

function Tile({
  tone,
  label,
  value,
  foot,
}: {
  tone: "held" | "verified" | "brand";
  label: string;
  value: string;
  foot: string;
}) {
  const ring = {
    held: "border-held/45 bg-held/[0.07]",
    verified: "border-verified/45 bg-verified/[0.07]",
    brand: "border-brand/45 bg-brand/[0.07]",
  }[tone];
  const dot = { held: "bg-held", verified: "bg-verified", brand: "bg-brand" }[tone];
  const text = { held: "text-held", verified: "text-verified", brand: "text-brand" }[tone];
  return (
    <div className={`rounded-xl border p-4 ${ring}`}>
      <p className={`text-[10.5px] font-semibold uppercase tracking-[0.09em] ${text}`}>{label}</p>
      <p className="num mt-1.5 font-display text-[30px] font-bold leading-none text-ink">{value}</p>
      <p className="mt-2.5 flex items-center gap-1.5 text-[11.5px] text-ink-muted">
        <span className={`inline-block h-2 w-2 rounded-full ${dot}`} aria-hidden="true" />
        {foot}
      </p>
    </div>
  );
}
