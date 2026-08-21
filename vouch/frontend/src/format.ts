/**
 * Presentation only.
 *
 * Nothing here derives a business value - margins, deltas, floor prices and staleness labels all
 * arrive precomputed from the backend, so the UI can never disagree with what Vouch would actually
 * do. These helpers just choose how to render numbers that already exist.
 */

const money0 = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 0,
  maximumFractionDigits: 0,
});

const money2 = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

export function money(value: number | null | undefined, decimals = 2): string {
  if (value === null || value === undefined) return "—";
  return decimals === 0 ? money0.format(value) : money2.format(value);
}

/** Signed, for deltas: "+$19.02" / "−$165.98". Uses a real minus sign, not a hyphen. */
export function signedMoney(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  const sign = value > 0 ? "+" : value < 0 ? "−" : "";
  return `${sign}${money(Math.abs(value))}`;
}

/** A ratio (0.1923) as a percentage. Clamped display for the catastrophic negative margins. */
export function pct(value: number | null | undefined, decimals = 1): string {
  if (value === null || value === undefined) return "—";
  const asPct = value * 100;
  if (asPct < -999) return `${Math.round(asPct).toLocaleString("en-US")}%`;
  return `${asPct.toFixed(decimals)}%`;
}

export function signedPct(value: number | null | undefined, decimals = 1): string {
  if (value === null || value === undefined) return "—";
  const sign = value > 0 ? "+" : value < 0 ? "−" : "";
  return `${sign}${pct(Math.abs(value), decimals)}`;
}

/** good | warning | critical, matching the confidence thresholds in guardian/verdict.py. */
export type Severity = "good" | "warning" | "critical";

export function confidenceSeverity(confidence: number): Severity {
  if (confidence >= 85) return "good";
  if (confidence >= 60) return "warning";
  return "critical";
}

export const severityText: Record<Severity, string> = {
  good: "text-verified",
  warning: "text-watch",
  critical: "text-held",
};

export const severityBg: Record<Severity, string> = {
  good: "bg-verified",
  warning: "bg-watch",
  critical: "bg-held",
};
