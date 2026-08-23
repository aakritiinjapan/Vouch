/**
 * The console — one question, asked of whichever pipeline is selected: is anything being held from
 * acting on a number we cannot stand behind?
 *
 * Two scenarios share this screen, and that is the point. If the verification layer is the product,
 * a second consumer must not need a second console. So both reduce to `Finding[]` in scenario.ts and
 * everything below is scenario-agnostic — the only per-scenario text comes from ScenarioMeta.
 *
 * Presentational, with one exception: the sale-audit scenario fetches its own verdict from
 * POST /verify, because it is stateless by design and has no rows in our database. That fetch lives
 * here rather than in useVouch so the repricing path keeps working untouched if it fails.
 */

import { useEffect, useMemo, useState } from "react";

import { api } from "../api";
import { Receipts } from "../components/Receipts";
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
import type { HealEvent, Product, Proposal, VerifyResponse } from "../types";
import { toDecision } from "../verdict";

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
  const { products, pending, held, healEvents, loading, busy, onApprove, onViewAsApi } = props;

  const [scenarioId, setScenarioId] = useState<ScenarioId>("repricing");
  const [sale, setSale] = useState<VerifyResponse | null>(null);
  const [saleError, setSaleError] = useState<string | null>(null);
  const [saleLoading, setSaleLoading] = useState(false);
  const [openKey, setOpenKey] = useState<string | null>(null);
  const [activeLinkId, setActiveLinkId] = useState<number | null>(null);

  const meta = SCENARIOS.find((s) => s.id === scenarioId)!;

  // The sale audit has no rows in our database — it is a claim about a page, judged on demand. Fetch
  // once per selection, and keep the failure local so a dead endpoint cannot take the console with it.
  useEffect(() => {
    if (scenarioId !== "sale-audit" || sale || saleLoading) return;
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
  }, [scenarioId, sale, saleLoading]);

  const findings: Finding[] = useMemo(
    () => (scenarioId === "repricing" ? findingsFromProposals(held) : sale ? findingsFromVerify(sale) : []),
    [scenarioId, held, sale],
  );

  const open = findings.find((f) => f.key === openKey) ?? null;
  const busyHere = scenarioId === "repricing" ? busy : null;

  // ── the three tiles ──────────────────────────────────────────────────────────────────────
  const exposure = findings.reduce((sum, f) => sum + Math.abs(f.risk ?? 0), 0);
  const worst = findings.reduce(
    (lowest, f) => (f.risk != null && f.risk < lowest ? f.risk : lowest),
    0,
  );
  // Accuracy is over the heals we actually judged this session, not a target. Null when none ran,
  // because a percentage of zero events is not 100% — it is nothing to report.
  const judged = healEvents.length;
  const accuracy = judged
    ? healEvents.reduce((sum, e) => sum + e.proposed_confidence, 0) / judged
    : null;

  return (
    <div className="mx-auto max-w-[1200px] px-6 py-7">
      <div className="grid grid-cols-1 gap-3.5 sm:grid-cols-3">
        <Tile
          tone="held"
          label="Silent corruptions intercepted"
          value={`${findings.length} Held`}
          foot={
            findings.length === 0
              ? "nothing is being withheld"
              : `every one caught before it committed`
          }
        />
        <Tile
          tone="verified"
          label={
            scenarioId === "repricing" ? "Downstream value protected" : "Overstated discount exposed"
          }
          value={money(exposure)}
          foot={worst < 0 ? `Worst single case: ${money(worst)}` : "no exposure measured"}
        />
        <Tile
          tone="brand"
          label="Self-heal accuracy score"
          value={accuracy == null ? "—" : `${accuracy.toFixed(1)}%`}
          foot={
            accuracy == null
              ? "no heals judged yet this session"
              : `mean confidence over ${judged} judged heal${judged === 1 ? "" : "s"}`
          }
        />
      </div>

      <section className="mt-7 rounded-xl border border-hair bg-surface" aria-label="Decisions needing review">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-hair px-5 py-4">
          <div>
            <h2 className="font-display text-h2 font-semibold text-ink">Decisions needing review</h2>
            <p className="mt-0.5 text-xs text-ink-muted">
              {meta.pipeline} · reading {meta.source} · {meta.whoActs} acts on this number
            </p>
          </div>
          <label className="flex items-center gap-2 text-xs text-ink-muted">
            <span className="sr-only">Example pipeline</span>
            <select
              value={scenarioId}
              onChange={(e) => {
                setScenarioId(e.target.value as ScenarioId);
                setOpenKey(null);
              }}
              className="rounded-lg border border-hair bg-surface-raised px-3 py-2 text-sm text-ink focus-visible:outline-none"
            >
              {SCENARIOS.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.label}
                </option>
              ))}
            </select>
          </label>
        </div>

        {saleLoading && (
          <p className="px-5 py-8 text-center text-sm text-ink-muted">
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
            title="Nothing to hold"
            body={
              scenarioId === "repricing"
                ? "Vouch holds a change whenever it cannot stand behind the number behind it. Nothing is being withheld right now."
                : "No advertised was-price on this page exceeds what we recorded before the sale."
            }
          />
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-[10.5px] uppercase tracking-[0.09em] text-ink-muted">
                <th scope="col" className="px-5 py-2.5 font-semibold">{meta.entityLabel}</th>
                <th scope="col" className="px-3 py-2.5 font-semibold">Anomaly finding</th>
                <th scope="col" className="px-3 py-2.5 font-semibold">{meta.riskLabel}</th>
                <th scope="col" className="px-5 py-2.5 text-right font-semibold">Actions</th>
              </tr>
            </thead>
            <tbody>
              {findings.map((f) => (
                <tr key={f.key} className="border-t border-hair/70 align-middle">
                  <td className="px-5 py-3.5 font-medium text-ink">{f.entity}</td>
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
                        <span className="ml-1 text-[11px] font-normal text-ink-muted">/ unit</span>
                      </span>
                    )}
                  </td>
                  <td className="px-5 py-3.5">
                    <div className="flex justify-end gap-2">
                      <button
                        type="button"
                        onClick={() => setOpenKey(openKey === f.key ? null : f.key)}
                        aria-expanded={openKey === f.key}
                        className="rounded-md bg-brand px-3 py-1.5 text-xs font-semibold text-white hover:bg-brand/85"
                      >
                        {openKey === f.key ? "Close" : "Investigate"}
                      </button>
                      {f.proposalId != null && (
                        <button
                          type="button"
                          disabled={!!busyHere}
                          onClick={() => onApprove(f.proposalId!)}
                          className="rounded-md border border-hair bg-surface-raised px-3 py-1.5 text-xs text-ink-secondary hover:text-ink disabled:opacity-50"
                        >
                          Force approve
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {open && <Investigate finding={open} judgeConsulted={sale?.judge_consulted ?? false} />}

      <div className="mt-7 border-t border-hair pt-6">
        <Receipts events={healEvents} activeLinkId={activeLinkId} onLinkActivate={setActiveLinkId} />
      </div>

      {scenarioId === "repricing" && held.length > 0 && (
        <p className="mt-5 text-xs text-ink-muted">
          {pending.length} routine change{pending.length === 1 ? "" : "s"} ready ·{" "}
          {products.length} products tracked
          {loading ? " · refreshing…" : ""} ·{" "}
          <button
            type="button"
            onClick={() => onViewAsApi(held[0])}
            className="text-brand hover:underline"
          >
            view this verdict as an API response →
          </button>
        </p>
      )}
    </div>
  );
}

/** The detail panel: the two numbers that make the case, then what each path would have cost. */
function Investigate({ finding, judgeConsulted }: { finding: Finding; judgeConsulted: boolean }) {
  const decision = toDecision(finding.decision, finding.confidence);
  return (
    <section className="mt-3.5 rounded-xl border border-hair bg-surface p-5" aria-label="Investigation detail">
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
          {finding.riskNote && (
            <p className="mt-3 text-[11.5px] text-ink-muted">{finding.riskNote}</p>
          )}
        </div>
      </div>
    </section>
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
