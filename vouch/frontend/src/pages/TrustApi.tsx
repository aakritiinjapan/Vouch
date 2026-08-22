/**
 * Trust API — the product page, dev-first.
 *
 * One interactive playground, one reference, no duplication:
 *   1. Try it   — pick a preset (or the "repricer heal gate" case), EDIT the JSON or paste your own
 *                 rows, then run it against the real endpoint. The request is editable, so "your
 *                 data" is literally true; nothing runs until you click Run.
 *   2. Integrate — the request/response contract, the check-code legend, copy-able curl (incl.
 *                 bring-your-own-key), and a link to the endpoint's OWN OpenAPI docs (/trust/docs,
 *                 which shows only /verify).
 *
 * The repricer is just one preset here — selecting it loads the exact 1-row preview call the
 * orchestrator makes at the heal gate, and the verdict carries a "→ reprice HELD" consequence. That
 * folds the old separate "repricer" section into the one playground.
 *
 * Everything round-trips the real POST /verify (see api.verify), so nothing here is a mockup.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { api, ApiError } from "../api";
import type { VerifyRequest, VerifyResponse } from "../types";
import { BASELINE, type ScenarioKey, scenarioByKey } from "../trustSamples";
import { toDecision } from "../verdict";
import { VerdictGauge } from "../components/VerdictGauge";
import { TrustLegend } from "../components/TrustLegend";
import { Button, Card } from "../components/ui/Bits";

const DOCS_URL = "/trust/docs"; // the standalone Trust API docs — shows ONLY /verify

/** Every code the guardian can emit, so a dev knows what a failure means without reading the source. */
const CHECK_CODES: { code: string; tier: string; blurb: string }[] = [
  { code: "FIELD_MISSING", tier: "1", blurb: "a field vanished after the heal" },
  { code: "NULL_SPIKE", tier: "1", blurb: "values went empty on many rows" },
  { code: "DTYPE_CHANGED", tier: "1", blurb: "a field changed type (e.g. number → text)" },
  { code: "ROW_COUNT_SHIFT", tier: "1", blurb: "row count jumped beyond tolerance" },
  { code: "NUMERIC_DRIFT", tier: "2", blurb: "a median moved far from baseline" },
  { code: "CARDINALITY_COLLAPSE", tier: "2", blurb: "distinct values collapsed to a few" },
  { code: "BOOL_RATIO_SHIFT", tier: "2", blurb: "a boolean pinned to one value" },
  { code: "COLUMN_SWAP", tier: "2b", blurb: "two columns traded places (by distribution)" },
  { code: "VALUE_ORDER_INVERTED", tier: "2c", blurb: "your ordering invariant flipped" },
];

const CURL_BASIC = `curl -X POST "$VOUCH/verify" \\
  -H 'content-type: application/json' \\
  -d '{"candidate_records": [ … ], "baseline_records": [ … ]}'`;

const CURL_BYOK = `curl -X POST "$VOUCH/verify" \\
  -H 'content-type: application/json' \\
  -H "X-LLM-Key: $YOUR_MODEL_KEY" \\
  -d '{"candidate_records": [ … ], "baseline_records": [ … ],
       "orderings": [["min_salary","max_salary"]],
       "use_judge": true, "llm": {"provider": "anthropic"}}'`;

function severityTone(severity: string): string {
  switch (severity.toLowerCase()) {
    case "critical":
      return "border-held/40 bg-held/10 text-held";
    case "high":
      return "border-watch/40 bg-watch/10 text-watch";
    default:
      return "border-hair bg-white/[0.04] text-ink-secondary";
  }
}

// ----------------------------------------------------------------------------------------
// presets — the price scenarios, a non-price one, and the repricer's own call
// ----------------------------------------------------------------------------------------

interface Preset {
  key: string;
  label: string;
  blurb: string;
  body: VerifyRequest;
  repricer?: boolean;
}

function scenarioBody(key: ScenarioKey): VerifyRequest {
  const s = scenarioByKey(key);
  const body: VerifyRequest = { candidate_records: s.candidate, baseline_records: s.baseline ?? BASELINE };
  if (s.orderings) body.orderings = s.orderings;
  return body;
}

// The primary, default preset — the whole point of the page. Prefilled with a non-price example so
// the shape is obvious, but it's yours to replace.
const OWN_PRESET: Preset = {
  key: "own",
  label: "Try with your own scraper data",
  blurb:
    "This is your data — edit the JSON or paste your own candidate + baseline rows, then run. (Prefilled with a non-price example, using your own `orderings` invariant, so you can see the shape.)",
  body: scenarioBody("jobs-swap"),
};

const EXAMPLE_PRESETS: Preset[] = [
  ...(["column-swap", "clean", "crossed-out"] as ScenarioKey[]).map((k) => {
    const s = scenarioByKey(k);
    return { key: k, label: s.label, blurb: s.blurb, body: scenarioBody(k) };
  }),
  {
    key: "repricer",
    label: "Repricer API call data",
    blurb:
      "The exact call the repricer makes at Bright Data's approval gate: a 1-row healed preview + its baseline (is_sample).",
    body: {
      candidate_records: [scenarioByKey("column-swap").candidate[0]],
      baseline_records: BASELINE,
      is_sample: true,
    },
    repricer: true,
  },
];

const PRESETS: Preset[] = [OWN_PRESET, ...EXAMPLE_PRESETS];

const pretty = (body: VerifyRequest) => JSON.stringify(body, null, 2);

// ----------------------------------------------------------------------------------------
// small bits
// ----------------------------------------------------------------------------------------

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setCopied(true);
          setTimeout(() => setCopied(false), 1200);
        } catch {
          /* clipboard unavailable */
        }
      }}
      className="absolute right-2 top-2 rounded-md border border-hair bg-surface/80 px-2 py-0.5 text-[10px] font-medium text-ink-secondary hover:text-ink"
    >
      {copied ? "Copied" : "Copy"}
    </button>
  );
}

function CodeBlock({ text }: { text: string }) {
  return (
    <div className="relative">
      <CopyButton text={text} />
      <pre className="scroll-slim overflow-x-auto rounded-md border border-hair bg-canvas p-3 pr-14 font-mono text-[11px] leading-relaxed text-ink-secondary">
        <code>{text}</code>
      </pre>
    </div>
  );
}

function Failures({ response }: { response: VerifyResponse | null }) {
  if (!response || response.failures.length === 0) return null;
  return (
    <ul className="mt-3 space-y-2">
      {response.failures.map((f, i) => (
        <li key={i} className="rounded-md border border-hair bg-white/[0.02] px-3 py-2.5 text-xs">
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-md border border-held/40 bg-held/10 px-1.5 py-0.5 font-mono text-[11px] font-medium tracking-wide text-held">
              {f.code}
            </span>
            <span
              className={`rounded border px-1.5 py-0.5 font-mono text-[10px] font-medium uppercase ${severityTone(f.severity)}`}
            >
              {f.severity}
            </span>
            <span className="text-ink-muted">· {f.field}</span>
          </div>
          <p className="mt-1.5 text-ink-secondary text-pretty">{f.message}</p>
        </li>
      ))}
    </ul>
  );
}

// ----------------------------------------------------------------------------------------
// page
// ----------------------------------------------------------------------------------------

export function TrustApi({
  initialScenario,
  bridgedFrom,
}: {
  initialScenario?: ScenarioKey;
  bridgedFrom?: string | null;
}) {
  const initialKey = PRESETS.find((p) => p.key === initialScenario)?.key ?? PRESETS[0].key;
  const [presetKey, setPresetKey] = useState<string>(initialKey);
  const [requestText, setRequestText] = useState<string>(() =>
    pretty(PRESETS.find((p) => p.key === initialKey)!.body),
  );

  const [response, setResponse] = useState<VerifyResponse | null>(null);
  const [status, setStatus] = useState<number | null>(null);
  const [latencyMs, setLatencyMs] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  const activePreset = PRESETS.find((p) => p.key === presetKey);
  const requestRef = useRef<HTMLTextAreaElement>(null);

  // Selecting a preset loads its JSON into the editor — it does NOT run. The button runs.
  const loadPreset = useCallback((key: string) => {
    const preset = PRESETS.find((p) => p.key === key);
    if (!preset) return;
    setPresetKey(key);
    setRequestText(pretty(preset.body));
  }, []);

  // "Try with your own scraper data" is an invitation to type — drop the cursor into the editor.
  const startOwn = useCallback(() => {
    loadPreset(OWN_PRESET.key);
    requestAnimationFrame(() => {
      const el = requestRef.current;
      if (el) {
        el.focus();
        const end = el.value.length;
        el.setSelectionRange(end, end);
      }
    });
  }, [loadPreset]);

  const run = useCallback(async (text: string) => {
    let body: VerifyRequest;
    try {
      body = JSON.parse(text) as VerifyRequest;
    } catch (err) {
      setResponse(null);
      setStatus(null);
      setError(`Invalid JSON: ${err instanceof Error ? err.message : "could not parse the request"}`);
      return;
    }
    setRunning(true);
    setError(null);
    const started = performance.now();
    try {
      const res = await api.verify(body);
      setResponse(res.data);
      setStatus(res.status);
      setLatencyMs(Math.round(performance.now() - started));
    } catch (err) {
      setResponse(null);
      setStatus(err instanceof ApiError ? err.status : null);
      setError(
        err instanceof ApiError || err instanceof Error ? err.message : "Could not reach the Trust API",
      );
    } finally {
      setRunning(false);
    }
  }, []);

  // Auto-run ONCE on mount so a verdict is on screen; after that, running is the button's job.
  useEffect(() => {
    void run(requestText);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const decision = response ? toDecision(response.decision, response.confidence) : null;

  return (
    <div className="mx-auto max-w-[1200px] px-6 py-8">
      <header className="mb-7 max-w-3xl">
        <div className="flex items-center gap-3">
          <h1 className="font-display text-title font-bold text-ink">Trust API</h1>
          <code className="rounded-md border border-hair bg-white/[0.04] px-2 py-0.5 text-xs text-ink-secondary">
            POST /verify
          </code>
        </div>
        <p className="mt-3 text-ink-secondary text-pretty">
          Drop one stateless call into your own pipeline and refuse to act on data it can&rsquo;t
          verify. Send the rows a self-heal wants to commit; get back a verdict — PASS / REVIEW /
          FAIL, a confidence score and a plain-English brief. No database, no repricing, no writes.
          Bring your own columns and, for the optional judge, your own model key.
        </p>
      </header>

      {bridgedFrom && (
        <p className="mb-6 inline-block rounded-md border border-brand/30 bg-brand/[0.08] px-3 py-2 text-xs text-ink-secondary">
          ↳ Verifying <span className="font-semibold text-ink">{bridgedFrom}</span> — deep-linked
          from the repricer console.
        </p>
      )}

      {/* ZONE 1 — TRY IT ------------------------------------------------------------------ */}
      <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-2">
        <Card className="p-6">
          <p className="eyebrow">Try it</p>
          <p className="mt-2 text-xs text-ink-muted text-pretty">
            Load a preset, then <span className="text-ink">edit the JSON or paste your own rows</span>{" "}
            and run it against the live endpoint.
          </p>

          {/* Row 1: the primary "your own data" preset, on its own. */}
          <div className="mt-4">
            <button
              type="button"
              onClick={startOwn}
              aria-pressed={presetKey === OWN_PRESET.key}
              className={`w-full rounded-md border px-3.5 py-2.5 text-left text-sm font-medium transition-colors ${
                presetKey === OWN_PRESET.key
                  ? "border-brand/60 bg-brand/[0.10] text-ink"
                  : "border-hairStrong text-ink hover:bg-white/[0.04]"
              }`}
            >
              {OWN_PRESET.label}
            </button>
          </div>

          {/* Row 2: canned examples. */}
          <p className="eyebrow mt-4">Preset examples</p>
          <div className="mt-2 flex flex-wrap gap-2" role="group" aria-label="Preset examples">
            {EXAMPLE_PRESETS.map((p) => {
              const active = p.key === presetKey;
              return (
                <button
                  key={p.key}
                  type="button"
                  onClick={() => loadPreset(p.key)}
                  aria-pressed={active}
                  className={`rounded-full border px-3 py-1.5 text-xs font-medium transition-colors ${
                    active
                      ? "border-brand/60 bg-brand/[0.10] text-ink"
                      : "border-hair text-ink-secondary hover:bg-white/[0.04] hover:text-ink"
                  }`}
                >
                  {p.label}
                </button>
              );
            })}
          </div>

          {activePreset && (
            <p className="mt-3 text-xs text-ink-muted text-pretty">{activePreset.blurb}</p>
          )}

          <label className="mt-4 block">
            <span className="eyebrow">Request body</span>
            <textarea
              ref={requestRef}
              value={requestText}
              onChange={(e) => {
                setRequestText(e.target.value);
                // Editing a canned example means you're now working with your own data.
                if (presetKey !== OWN_PRESET.key) setPresetKey(OWN_PRESET.key);
              }}
              spellCheck={false}
              rows={14}
              aria-label="Request body"
              className="scroll-slim mt-2 w-full resize-y rounded-md border border-hair bg-canvas p-3 font-mono text-[11px] leading-relaxed text-ink-secondary focus:border-brand/50 focus:outline-none"
            />
          </label>

          <div className="mt-3">
            <Button variant="primary" onClick={() => run(requestText)} busy={running}>
              Run through the guardian
            </Button>
          </div>
        </Card>

        {/* RESPONSE */}
        <Card className="p-5">
          <div className="mb-3 flex items-center justify-between">
            <p className="eyebrow">Response</p>
            <p className="font-mono text-[11px] text-ink-muted">
              POST /verify{" "}
              {status !== null ? (
                <span className={status < 400 ? "text-verified" : "text-held"}>{status}</span>
              ) : error ? (
                <span className="text-held">error</span>
              ) : (
                "…"
              )}
              {latencyMs !== null && response ? ` · ${latencyMs}ms` : ""}
            </p>
          </div>

          {decision && response && (
            <div className="mb-4 flex items-center gap-5 rounded-lg border border-hair bg-white/[0.02] p-4">
              <VerdictGauge decision={decision} score={response.confidence} size={92} />
              <div className="min-w-0">
                <p className="text-xs text-ink-secondary text-pretty">{response.brief}</p>
                {activePreset?.repricer && (
                  <p className="mt-2 text-xs">
                    <span className="text-ink-muted">In the repricer this means → </span>
                    <span className={response.confirmed ? "text-verified" : "text-held"}>
                      reprice {response.confirmed ? "applied" : "HELD"}
                    </span>
                    .{" "}
                    <a href="#/console" className="text-brand-soft hover:text-ink">
                      Open the console →
                    </a>
                  </p>
                )}
                <div className="mt-2">
                  <TrustLegend />
                </div>
              </div>
            </div>
          )}

          {error ? (
            <p className="rounded-md border border-held/40 bg-held/10 px-3 py-2 text-xs text-held">
              {error}
            </p>
          ) : (
            <pre className="scroll-slim max-h-[20rem] overflow-y-auto whitespace-pre-wrap break-words rounded-md border border-hair bg-canvas p-4 font-mono text-[11px] leading-relaxed text-ink-secondary">
              <code>{response ? JSON.stringify(response, null, 2) : "Run to see the verdict."}</code>
            </pre>
          )}
          <Failures response={response} />
        </Card>
      </div>

      {/* ZONE 2 — INTEGRATE --------------------------------------------------------------- */}
      <section className="mt-10">
        <div className="mb-4 flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="font-display text-h2 font-semibold text-ink">Integrate</h2>
          <a href={DOCS_URL} target="_blank" rel="noreferrer" className="text-sm text-brand-soft hover:text-ink">
            Open the OpenAPI docs →
          </a>
        </div>

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <Card className="p-5">
            <p className="eyebrow mb-3">The contract</p>
            <dl className="space-y-2 text-xs">
              {[
                ["candidate_records", "the rows a heal wants to commit — required"],
                ["baseline_records | baseline_profiles", "the last-known-good reference — exactly one"],
                ["is_sample", "candidate is a preview → volume checks stand down"],
                ["orderings", "your (lower, upper) invariant pairs"],
                ["field_descriptions", "what each field means, for the judge"],
                ["use_judge + X-LLM-Key", "opt into Tier 3 with your own model key"],
              ].map(([k, v]) => (
                <div key={k} className="flex flex-col gap-0.5 border-b border-hair/60 pb-2 sm:flex-row sm:gap-3">
                  <code className="shrink-0 font-mono text-ink sm:w-64">{k}</code>
                  <span className="text-ink-muted">{v}</span>
                </div>
              ))}
            </dl>
            <p className="eyebrow mb-2 mt-4">Response</p>
            <p className="font-mono text-[11px] leading-relaxed text-ink-secondary">
              {"{ decision, confirmed, confidence, brief, failures[], judge_consulted }"}
            </p>
          </Card>

          <Card className="p-5">
            <p className="eyebrow mb-3">Failure codes</p>
            <ul className="space-y-1.5 text-xs">
              {CHECK_CODES.map((c) => (
                <li key={c.code} className="flex items-baseline gap-2">
                  <span className="rounded border border-hair bg-white/[0.04] px-1 py-0.5 font-mono text-[10px] text-ink-muted">
                    T{c.tier}
                  </span>
                  <code className="font-mono text-ink">{c.code}</code>
                  <span className="text-ink-muted">— {c.blurb}</span>
                </li>
              ))}
            </ul>
          </Card>
        </div>

        <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
          <div>
            <p className="eyebrow mb-2">Call it — deterministic tiers, free, no key</p>
            <CodeBlock text={CURL_BASIC} />
          </div>
          <div>
            <p className="eyebrow mb-2">Add the Tier 3 judge — bring your own key</p>
            <CodeBlock text={CURL_BYOK} />
          </div>
        </div>
      </section>
    </div>
  );
}
