/**
 * The entire state layer. One hook, no state library.
 *
 * Mutations are deliberately NOT optimistic. A guardian product must show server truth: an
 * optimistically-dismissed held card that the server then refuses is the worst bug this app could
 * have live. `mutating` drives per-button spinners so it still feels immediate.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, api } from "../api";
import type { HealEvent, Product, Proposal } from "../types";

const POLL_MS = 5000;

interface VouchState {
  products: Product[];
  pending: Proposal[];
  held: Proposal[];
  healEvents: HealEvent[];
  mockMode: boolean;
}

const EMPTY: VouchState = {
  products: [],
  pending: [],
  held: [],
  healEvents: [],
  mockMode: true,
};

export function useVouch() {
  const [state, setState] = useState<VouchState>(EMPTY);
  const [loading, setLoading] = useState(true);
  const [mutating, setMutating] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  // Read inside the polling interval without making it a dependency (which would reset the timer).
  const mutatingRef = useRef(mutating);
  mutatingRef.current = mutating;

  const refresh = useCallback(async () => {
    try {
      // One round trip's worth of latency, one setState, one render - no cascade of spinners.
      const [products, queue, healEvents] = await Promise.all([
        api.products(),
        api.proposals(["pending", "held"]),
        api.healEvents(),
      ]);
      setState((prev) => ({
        ...prev,
        products,
        pending: queue.filter((p) => p.status === "pending"),
        held: queue.filter((p) => p.status === "held"),
        healEvents,
      }));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not reach the Vouch API");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    const id = window.setInterval(() => {
      // Never poll over an in-flight mutation, and never poll a hidden tab.
      if (mutatingRef.current) return;
      if (document.visibilityState !== "visible") return;
      void refresh();
    }, POLL_MS);
    return () => window.clearInterval(id);
  }, [refresh]);

  /** Run a mutation, then repaint from the server. Errors surface, they do not get swallowed. */
  const mutate = useCallback(
    async (key: string, fn: () => Promise<unknown>, onError?: (err: ApiError) => void) => {
      setMutating(key);
      setError(null);
      setNotice(null);
      try {
        await fn();
        await refresh();
      } catch (err) {
        if (err instanceof ApiError && onError) onError(err);
        setError(err instanceof Error ? err.message : "Something went wrong");
      } finally {
        setMutating(null);
      }
    },
    [refresh],
  );

  const approve = useCallback(
    (id: number, force = false) => mutate(`approve-${id}`, () => api.approve(id, force)),
    [mutate],
  );

  const reject = useCallback(
    (id: number, note?: string) => mutate(`reject-${id}`, () => api.reject(id, note)),
    [mutate],
  );

  const approveAllSafe = useCallback(
    () =>
      mutate("approve-safe", async () => {
        const result = await api.approveAllSafe();
        const skipped = result.skipped.length
          ? ` ${result.skipped.length} skipped (${result.skipped[0].why}).`
          : "";
        setNotice(`Approved ${result.applied_count} safe change${
          result.applied_count === 1 ? "" : "s"
        }.${skipped}`);
      }),
    [mutate],
  );

  const runCycle = useCallback(
    (body: { simulate_run?: string | null; simulate_heal?: string | string[] | null } = {}) =>
      mutate("run-cycle", async () => {
        const result = await api.runCycle(body);
        const heldNow = result.cycles.filter((c) => !c.source_confirmed).length;
        const parts = [`Ran ${result.cycles.length} cycle${result.cycles.length === 1 ? "" : "s"}.`];
        if (heldNow) parts.push(`${heldNow} held by the guardian.`);
        // Surface the backend's refusal to honour a simulate hint outside MOCK_MODE.
        parts.push(...result.warnings);
        setNotice(parts.join(" "));
      }),
    [mutate],
  );

  const resetDemo = useCallback(
    () =>
      mutate("reset", async () => {
        await api.resetDemo();
        setNotice("Demo state reset to the opening position.");
      }),
    [mutate],
  );

  return {
    ...state,
    loading,
    mutating,
    error,
    notice,
    refresh,
    approve,
    reject,
    approveAllSafe,
    runCycle,
    resetDemo,
    dismissNotice: () => setNotice(null),
  };
}

export type UseVouch = ReturnType<typeof useVouch>;
