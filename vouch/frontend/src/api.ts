/** The only module that knows URLs. Everything else talks to the hook. */

import type {
  ApproveResponse,
  BulkApproveResponse,
  CycleRunResponse,
  HealEvent,
  History,
  Product,
  Proposal,
} from "./types";

const BASE = "/api";

export class ApiError extends Error {
  status: number;
  /** The backend's structured detail - carries check_code and confidence on a 409 hold. */
  detail: Record<string, unknown>;

  constructor(status: number, detail: Record<string, unknown>, message: string) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });

  if (!response.ok) {
    let detail: Record<string, unknown> = {};
    let message = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      // FastAPI nests our structured errors under `detail`; ours is an object, validation is a list.
      const raw = body?.detail;
      if (raw && typeof raw === "object" && !Array.isArray(raw)) {
        detail = raw as Record<string, unknown>;
        if (typeof detail.detail === "string") message = detail.detail;
      } else if (typeof raw === "string") {
        message = raw;
      }
    } catch {
      /* non-JSON error body; keep the status line */
    }
    throw new ApiError(response.status, detail, message);
  }

  return response.json() as Promise<T>;
}

export const api = {
  products: () => request<Product[]>("/products"),

  proposals: (status: string[]) =>
    request<Proposal[]>(`/proposals?${status.map((s) => `status=${s}`).join("&")}`),

  healEvents: (limit = 50) => request<HealEvent[]>(`/heal-events?limit=${limit}`),

  history: (productId: number) => request<History>(`/products/${productId}/history`),

  approve: (id: number, force = false) =>
    request<ApproveResponse>(`/proposals/${id}/approve?force=${force}`, { method: "POST" }),

  reject: (id: number, note?: string) =>
    request<Proposal>(
      `/proposals/${id}/reject${note ? `?note=${encodeURIComponent(note)}` : ""}`,
      { method: "POST" },
    ),

  approveAllSafe: () =>
    request<BulkApproveResponse>("/proposals/approve-safe", {
      method: "POST",
      body: JSON.stringify({}),
    }),

  runCycle: (body: {
    simulate_run?: string | null;
    simulate_heal?: string | string[] | null;
  } = {}) =>
    request<CycleRunResponse>("/cycles/run", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  resetDemo: () => request<Record<string, unknown>>("/demo/reset", { method: "POST" }),
};
