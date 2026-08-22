/**
 * Trust API — the verdict as a stateless primitive, wired to the REAL POST /verify.
 *
 * This is the reframe (demo Act 2): the same Verdict Gauge the console acted on, returned by an API
 * any pipeline can call. The scenario picker drives deterministic fixture rows (the real Newegg
 * collector runs) through the live endpoint, so this is genuinely round-tripping the guardian, not a
 * mockup. `bridgedFrom` names the row a viewer clicked through from on the console.
 */

import { useCallback, useEffect, useState } from "react";

import { api, ApiError } from "../api";
import type { VerifyResponse } from "../types";
import { BASELINE, SCENARIOS, type ScenarioKey, scenarioByKey } from "../trustSamples";
import { toDecision } from "../verdict";
import { VerdictGauge } from "../components/VerdictGauge";
import { TrustLegend } from "../components/TrustLegend";
import { Button, Card, CheckBadge } from "../components/ui/Bits";

/** Map the guardian's real severity to a state tone, so colour carries information not decoration. */
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
  const [status, setStatus] = useState<number | null>(null);
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
      setResponse(res.data);
      setStatus(res.status);
      setLatencyMs(Math.round(performance.now() - started));
    } catch (err) {
      setResponse(null);
      setStatus(err instanceof ApiError ? err.status : null);
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
    <div className="mx-auto max-w-[1200px] px-6 py-8">
      {bridgedFrom && (
        <p className="mb-6 inline-block rounded-md border border-brand/30 bg-brand/[0.08] px-3 py-2 text-xs text-ink-secondary">
          ↳ Verifying <span className="font-semibold text-ink">{bridgedFrom}</span> — the row you
          clicked on the Console.
        </p>
      )}

      <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-2">
        {/* TRY IT */}
        <Card className="p-6">
          <p className="eyebrow">Try it</p>

          <fieldset className="mt-4" aria-label="Scenario">
            <legend className="sr-only">Scenario</legend>
            <div className="space-y-2">
              {SCENARIOS.map((s) => {
                const active = s.key === scenarioKey;
                return (
                  <label
                    key={s.key}
                    className={`flex cursor-pointer items-start gap-3 rounded-md border px-3.5 py-3 transition-colors ${
                      active
                        ? "border-brand/60 bg-brand/[0.08]"
                        : "border-hair hover:bg-white/[0.03]"
                    }`}
                  >
                    <input
                      type="radio"
                      name="scenario"
                      value={s.key}
                      checked={active}
                      onChange={() => setScenarioKey(s.key)}
                      className="mt-0.5 accent-brand"
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

          <p className="mt-4 text-xs text-ink-muted">
            Sending:{" "}
            <span className="num text-ink-secondary">candidate {scenario.candidate.length}</span> +{" "}
            <span className="num text-ink-secondary">baseline {BASELINE.length}</span>
          </p>

          <div className="mt-4">
            <Button variant="primary" onClick={() => run(scenarioKey)} busy={running}>
              Run through the guardian
            </Button>
          </div>

          {decision && response && (
            <div className="mt-6 flex items-center gap-5 rounded-lg border border-hair bg-white/[0.02] p-5">
              <VerdictGauge decision={decision} score={response.confidence} size={104} />
              <div className="min-w-0">
                <p className="text-sm font-semibold text-ink">Same object the Console acted on.</p>
                <p className="mt-1.5 text-xs text-ink-secondary text-pretty">{response.brief}</p>
                <div className="mt-3">
                  <TrustLegend />
                </div>
              </div>
            </div>
          )}
        </Card>

        {/* RESPONSE */}
        <Card>
          <div className="flex items-center justify-between border-b border-hair px-5 py-3.5">
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

          <div className="p-5">
            {error ? (
              <p className="rounded-md border border-held/40 bg-held/10 px-3 py-2 text-xs text-held">
                {error} — is the backend running on :8000?
              </p>
            ) : (
              <pre className="scroll-slim max-h-[24rem] overflow-y-auto whitespace-pre-wrap break-words rounded-md border border-hair bg-canvas p-4 font-mono text-[11px] leading-relaxed text-ink-secondary">
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
                      className="rounded-md border border-hair bg-white/[0.02] px-3 py-2.5 text-xs"
                    >
                      <div className="flex flex-wrap items-center gap-2">
                        <CheckBadge code={f.code} />
                        <span
                          className={`rounded border px-1.5 py-0.5 font-mono text-[10px] font-medium uppercase ${severityTone(
                            f.severity,
                          )}`}
                        >
                          {f.severity}
                        </span>
                        <span className="text-ink-muted">· {f.field}</span>
                      </div>
                      <p className="mt-1.5 text-ink-secondary text-pretty">{f.message}</p>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <div className="mt-4">
              <p className="eyebrow mb-2">Call it yourself</p>
              <pre className="scroll-slim overflow-x-auto rounded-md border border-hair bg-canvas p-3 font-mono text-[11px] leading-relaxed text-ink-secondary">
                <code>{curlSnippet(scenario.candidate.length)}</code>
              </pre>
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
}
