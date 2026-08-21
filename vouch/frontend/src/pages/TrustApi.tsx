/**
 * Trust API — the verdict as a stateless primitive, wired to the REAL POST /verify.
 *
 * This is the reframe (demo Act 2): the same Verdict Seal the console acted on, returned by an API
 * any pipeline can call. The scenario picker drives deterministic fixture rows (the real Newegg
 * collector runs) through the live endpoint, so this is genuinely round-tripping the guardian, not a
 * mockup. `bridgedFrom` names the row a viewer clicked through from on the console.
 */

import { useCallback, useEffect, useState } from "react";

import { api, ApiError } from "../api";
import type { VerifyResponse } from "../types";
import { BASELINE, SCENARIOS, type ScenarioKey, scenarioByKey } from "../trustSamples";
import { toDecision } from "../verdict";
import { VerdictSeal } from "../components/VerdictSeal";
import { TrustLegend } from "../components/TrustLegend";
import { Button, Card, CheckBadge } from "../components/ui/Bits";

function curlSnippet(candidateLen: number): string {
  return `curl -X POST $VOUCH/verify \\
  -H 'content-type: application/json' \\
  -d '{"candidate_records": [ …${candidateLen} rows… ],
       "baseline_records":  [ …${BASELINE.length} rows… ]}'`;
}

export function TrustApi({
  initialScenario,
  bridgedFrom,
}: {
  initialScenario?: ScenarioKey;
  bridgedFrom?: string | null;
}) {
  const [scenarioKey, setScenarioKey] = useState<ScenarioKey>(
    () => scenarioByKey(initialScenario).key,
  );
  const [response, setResponse] = useState<VerifyResponse | null>(null);
  const [latencyMs, setLatencyMs] = useState<number | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const scenario = scenarioByKey(scenarioKey);

  const run = useCallback(async (key: ScenarioKey) => {
    const s = scenarioByKey(key);
    setRunning(true);
    setError(null);
    const started = performance.now();
    try {
      const res = await api.verify({
        candidate_records: s.candidate,
        baseline_records: BASELINE,
        is_sample: false,
      });
      setResponse(res);
      setLatencyMs(Math.round(performance.now() - started));
    } catch (err) {
      setResponse(null);
      setError(
        err instanceof ApiError || err instanceof Error
          ? err.message
          : "Could not reach the Trust API",
      );
    } finally {
      setRunning(false);
    }
  }, []);

  // Auto-run on mount and whenever the scenario changes, so the verdict is always on screen.
  useEffect(() => {
    void run(scenarioKey);
  }, [scenarioKey, run]);

  const decision = response ? toDecision(response.decision, response.confidence) : null;

  return (
    <div className="mx-auto max-w-[1280px] px-5 py-6">
      <div className="mb-5">
        <h1 className="font-display text-2xl font-semibold tracking-tight text-ink">
          The verdict is the product.
        </h1>
        <p className="mt-1 text-sm text-ink-secondary text-pretty">
          The repricer is one consumer — anything can be. Send rows, get back trust. For developers &amp;
          platform teams: the guardian&rsquo;s verdict as a stateless API.
        </p>
        {bridgedFrom && (
          <p className="mt-2 rounded-lg border border-holo-violet/30 bg-holo-violet/5 px-3 py-2 text-xs text-ink-secondary">
            ↳ Verifying <span className="font-semibold text-ink">{bridgedFrom}</span> — the row you
            clicked on the Console.
          </p>
        )}
      </div>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        {/* TRY IT */}
        <Card className="p-5">
          <p className="eyebrow">Try it</p>

          <fieldset className="mt-3" aria-label="Scenario">
            <legend className="sr-only">Scenario</legend>
            <div className="space-y-2">
              {SCENARIOS.map((s) => {
                const active = s.key === scenarioKey;
                return (
                  <label
                    key={s.key}
                    className={`flex cursor-pointer items-start gap-3 rounded-lg border px-3 py-2.5 transition-colors ${
                      active ? "border-holo-violet bg-holo-violet/5" : "border-hair hover:bg-raised"
                    }`}
                  >
                    <input
                      type="radio"
                      name="scenario"
                      value={s.key}
                      checked={active}
                      onChange={() => setScenarioKey(s.key)}
                      className="mt-0.5 accent-holo-violet"
                    />
                    <span className="min-w-0">
                      <span className="text-sm font-medium text-ink">{s.label}</span>
                      <span className="mt-0.5 block text-xs text-ink-muted text-pretty">
                        {s.blurb}
                      </span>
                    </span>
                  </label>
                );
              })}
            </div>
          </fieldset>

          <p className="mt-3 text-xs text-ink-muted">
            Sending:{" "}
            <span className="num text-ink-secondary">candidate {scenario.candidate.length}</span> +{" "}
            <span className="num text-ink-secondary">baseline {BASELINE.length}</span>
          </p>

          <div className="mt-3">
            <Button variant="primary" onClick={() => run(scenarioKey)} busy={running}>
              Run through the guardian
            </Button>
          </div>

          {decision && response && (
            <div className="mt-5 flex items-center gap-4 rounded-xl border border-hair bg-raised/50 p-4">
              <VerdictSeal decision={decision} score={response.confidence} size={92} />
              <div className="min-w-0">
                <p className="text-sm font-semibold text-ink">
                  Same object the Console acted on.
                </p>
                <p className="mt-1 text-xs text-ink-secondary text-pretty">{response.brief}</p>
                <div className="mt-2">
                  <TrustLegend />
                </div>
              </div>
            </div>
          )}
        </Card>

        {/* RESPONSE */}
        <Card className="overflow-hidden">
          <div className="flex items-center justify-between border-b border-hair px-5 py-3">
            <p className="eyebrow">Response</p>
            <p className="font-mono text-[11px] text-ink-muted">
              POST /verify{" "}
              {response ? (
                <span className="text-status-good">200</span>
              ) : error ? (
                <span className="text-status-critical">error</span>
              ) : (
                "…"
              )}
              {latencyMs !== null && response ? ` · ${latencyMs}ms` : ""}
            </p>
          </div>

          <div className="p-5">
            {error ? (
              <p className="rounded-md border border-status-critical/40 bg-status-critical/10 px-3 py-2 text-xs text-status-critical">
                {error} — is the backend running on :8000?
              </p>
            ) : (
              <pre className="scroll-slim overflow-x-auto rounded-lg bg-navy-900 p-4 font-mono text-[11px] leading-relaxed text-navy-ink">
                <code>{response ? JSON.stringify(response, null, 2) : "Running…"}</code>
              </pre>
            )}

            {response && response.failures.length > 0 && (
              <div className="mt-4">
                <p className="eyebrow mb-2">Failures</p>
                <ul className="space-y-2">
                  {response.failures.map((f, i) => (
                    <li
                      key={i}
                      className="rounded-lg border border-hair bg-raised/40 px-3 py-2 text-xs"
                    >
                      <div className="flex items-center gap-2">
                        <CheckBadge code={f.code} />
                        <span className="font-mono text-[10px] uppercase text-status-critical">
                          {f.severity}
                        </span>
                        <span className="text-ink-muted">· {f.field}</span>
                      </div>
                      <p className="mt-1 text-ink-secondary text-pretty">{f.message}</p>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <div className="mt-4">
              <p className="eyebrow mb-1.5">Call it yourself</p>
              <pre className="scroll-slim overflow-x-auto rounded-lg border border-hair bg-surface p-3 font-mono text-[11px] leading-relaxed text-ink-secondary">
                <code>{curlSnippet(scenario.candidate.length)}</code>
              </pre>
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
}
