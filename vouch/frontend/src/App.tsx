/**
 * The app shell: four surfaces behind a tiny hash router.
 *
 * `/` → Hero (what Vouch is), `/console` → the one-decision console (the product), `/examples` → the
 * two worked examples (the argument that the layer generalises), `/trust-api` → how to consume the
 * verdict yourself. All console state lives in useVouch; the Verdict Seal and the `view as API →`
 * bridge are what tie the surfaces into one story.
 */

import { Nav } from "./components/Nav";
import { useRoute } from "./hooks/useRoute";
import { useVouch } from "./hooks/useVouch";
import { Console } from "./pages/Console";
import { Examples } from "./pages/Examples";
import { Hero } from "./pages/Hero";
import { TrustApi } from "./pages/TrustApi";
import type { ScenarioId } from "./scenario";
import type { Proposal } from "./types";
import type { ScenarioKey } from "./trustSamples";

/** Which Trust API scenario a held decision maps to, so the bridge preloads the matching case. */
function scenarioForProposal(proposal: Proposal): ScenarioKey {
  switch (proposal.guardian?.check_code) {
    case "VALUE_ORDER_INVERTED":
      return "crossed-out";
    case "COLUMN_SWAP":
    default:
      return "column-swap";
  }
}

export default function App() {
  const { route, navigate } = useRoute();
  const vouch = useVouch();

  const onViewAsApi = (proposal: Proposal) =>
    navigate("trust-api", {
      scenario: scenarioForProposal(proposal),
      from: proposal.product.name,
    });

  if (route.view === "home") {
    return <Hero navigate={navigate} />;
  }

  // The Demo control is Console-only (its actions run cycles) and, like the old strip, only exists in
  // MOCK_MODE. Passing it solely on the console route is what scopes it away from Hero / Trust API.
  const demo =
    route.view === "console" && vouch.mockMode
      ? {
          hints: vouch.hints?.hints ?? [],
          busy: vouch.mutating,
          onRunCycle: () => vouch.runCycle(),
          onReplay: (healKey: string) =>
            vouch.runCycle({ simulate_run: "run_degraded", simulate_heal: [healKey, healKey] }),
          onResume: () =>
            vouch.runCycle({ simulate_run: "run_degraded", simulate_heal: "healed_swapped" }),
          onReset: vouch.resetDemo,
          onOpenExample: (id: ScenarioId) => navigate("examples", { case: id }),
        }
      : undefined;

  return (
    <div className="min-h-screen">
      <Nav view={route.view} navigate={navigate} demo={demo} />

      {vouch.error && (
        <div className="mx-auto mt-4 max-w-[1200px] px-6">
          <div className="rounded-md border border-held/40 bg-held/10 px-4 py-2 text-xs text-held">
            {vouch.error}
          </div>
        </div>
      )}
      {vouch.notice && (
        <div className="mx-auto mt-4 max-w-[1200px] px-6">
          <button
            type="button"
            onClick={vouch.dismissNotice}
            className="block w-full rounded-md border border-hair bg-surface px-4 py-2 text-left text-xs text-ink-secondary hover:text-ink"
          >
            {vouch.notice} <span className="text-ink-muted">— dismiss</span>
          </button>
        </div>
      )}

      {route.view === "trust-api" ? (
        <TrustApi
          initialScenario={(route.params.get("scenario") as ScenarioKey) ?? undefined}
          bridgedFrom={route.params.get("from")}
        />
      ) : route.view === "examples" ? (
        <Examples
          held={vouch.held}
          healEvents={vouch.healEvents}
          initialCase={(route.params.get("case") as ScenarioId) ?? undefined}
        />
      ) : (
        <Console
          products={vouch.products}
          pending={vouch.pending}
          held={vouch.held}
          healEvents={vouch.healEvents}
          loading={vouch.loading}
          busy={vouch.mutating}
          onApprove={(id) => vouch.approve(id, true)}
          onReject={(id) => vouch.reject(id, "skipped")}
          onApproveAllSafe={vouch.approveAllSafe}
          onViewAsApi={onViewAsApi}
        />
      )}
    </div>
  );
}
