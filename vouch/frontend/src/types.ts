/**
 * Mirrors backend/app/api/schemas.py. If a field is missing here, add it there first - the backend
 * is the only place allowed to compute derived money, margins, or date labels.
 */

export type ProposalStatus =
  | "pending"
  | "held"
  | "approved"
  | "rejected"
  /** a later cycle confirmed the source, so the hold stopped being an open question */
  | "superseded";

export interface ProductRef {
  id: number;
  sku: string;
  name: string;
}

export interface Product {
  id: number;
  sku: string;
  name: string;
  my_price: number;
  cost: number;
  floor_margin: number;
  floor_price: number;
  margin_pct: number | null;
  competitor_url: string;
  collector_id: string | null;
  last_confirmed_price: number | null;
  last_confirmed_at: string | null;
  last_confirmed_label: string;
  source_confirmed: boolean;
  held_proposal_id: number | null;
  updated_at: string;
}

export interface Source {
  url: string;
  confirmed: boolean;
  observed_price: number | null;
  last_confirmed_at: string | null;
  last_confirmed_label: string;
}

/** What the guardian found. Present only when a heal was involved in this proposal. */
export interface Guardian {
  heal_event_id: number;
  collector_id: string;
  verdict: string | null;
  confidence: number;
  check_code: string | null;
  brief: string;
  evidence: Record<string, unknown>;
  attempt: number;
  attempts_total: number;
  prompt: string;
}

export interface Counterfactual {
  competitor_price: number;
  current_price: number;
  floor_price: number;
  applied_price: number;
  applied_reason: string;
  naive_price: number;
  margin_pct_now: number | null;
  margin_pct_applied: number | null;
  margin_pct_naive: number | null;
  profit_per_unit_now: number;
  profit_per_unit_applied: number;
  profit_per_unit_naive: number;
  profit_delta_vs_now: number;
  /** which way this bad heal would have hurt - the card's framing depends on it */
  harm: "margin" | "competitiveness" | "none";
  harm_summary: string;
  source: string;
}

export interface Proposal {
  id: number;
  status: ProposalStatus;
  confidence: number;
  current_price: number;
  proposed_price: number;
  delta: number;
  delta_pct: number | null;
  reason: string;
  created_at: string;
  created_label: string;
  decided_at: string | null;
  floor_price: number;
  margin_pct_now: number | null;
  margin_pct_after: number | null;
  is_safe: boolean;
  safe_reason: string | null;
  product: ProductRef;
  source: Source;
  guardian: Guardian | null;
  counterfactual: Counterfactual | null;
}

export type LogKind = "run" | "heal" | "verdict" | "commit" | "reprompt";

export interface LogEntry {
  kind: LogKind;
  text: string;
}

export interface HealEvent {
  id: number;
  cycle_id: string | null;
  collector_id: string;
  attempt: number;
  verdict: string | null;
  proposed_confidence: number;
  primary_check_code: string | null;
  risk_brief: string;
  prompt: string;
  trigger_reason: string;
  status: string;
  created_at: string;
  created_label: string;
  product: ProductRef | null;
  entries: LogEntry[];
}

export interface CycleSummary {
  sku: string;
  cycle_id: string;
  source_confirmed: boolean;
  competitor_price: number | null;
  trigger_reason: string | null;
  proposal_id: number | null;
  proposal_status: string | null;
  confidence: number | null;
  heal_event_ids: number[];
  attempts: number;
  baseline_refreshed: boolean;
  superseded_proposal_ids: number[];
}

export interface CycleRunResponse {
  mock_mode: boolean;
  simulate_requested: unknown;
  simulate_applied: unknown;
  warnings: string[];
  cycles: CycleSummary[];
}

export interface BulkApproveResponse {
  approved: number[];
  applied_count: number;
  skipped: { id: number; why: string }[];
  products: Product[];
}

export interface ApproveResponse {
  proposal: Proposal;
  product: Product;
  applied_price: number;
}

export interface HistoryPoint {
  ts: string;
  ts_label: string;
  my_price: number;
  /** null on an unconfirmed cycle. The gap is in the data so it cannot be interpolated across. */
  competitor_price: number | null;
  confirmed: boolean;
}

export interface History {
  product: ProductRef;
  points: HistoryPoint[];
  counterfactual: Counterfactual | null;
  last_confirmed_label: string;
}

/**
 * One replay scenario the active dataset can honour, as a control the header can render.
 *
 * The dashboard renders its demo controls from the API rather than hard-coding them: the dataset
 * derived from the live collector carries no `original_price`, so the crossed-out-price scenario
 * genuinely cannot be replayed against it. Offering a button the data cannot honour would be a
 * small lie in exactly the place this product claims not to tell one.
 */
export interface DemoHint {
  key: string;
  label: string;
  detail: string;
  /** "run" feeds simulate_run; "heal" feeds simulate_heal. */
  stage: "run" | "heal";
}

export interface DemoHints {
  mock_mode: boolean;
  dataset: string;
  dataset_note: string;
  hints: DemoHint[];
}
