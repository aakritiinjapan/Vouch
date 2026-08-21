/**
 * The verdict, as a shared vocabulary.
 *
 * The guardian's verdict is the product, and it renders as the SAME object on every surface — the
 * held card, the live receipts, the Trust API. These helpers are the single place that turns a raw
 * decision + confidence into the words and bands the UI shows, so PASS/FAIL/High/Med/Low can never
 * disagree between two screens.
 */

export type Decision = "pass" | "fail" | "review";

export interface Verdict {
  decision: Decision;
  /** 0–100 trust score. */
  score: number;
  brief?: string;
}

/** Normalise the many shapes a decision arrives in ("PASS", "fail", null) to our three states. */
export function toDecision(raw: string | null | undefined, score?: number): Decision {
  const s = (raw ?? "").toString().toLowerCase();
  if (s === "pass" || s === "confirmed") return "pass";
  if (s === "fail" || s === "rejected") return "fail";
  if (s === "review" || s === "held") return "review";
  // Fall back to the score when the label is missing.
  if (score !== undefined) return score >= 85 ? "pass" : score >= 60 ? "review" : "fail";
  return "review";
}

export const decisionLabel: Record<Decision, string> = {
  pass: "PASS",
  fail: "FAIL",
  review: "REVIEW",
};

export const decisionGlyph: Record<Decision, string> = {
  pass: "✓",
  fail: "✕",
  review: "!",
};

export type BandKey = "high" | "med" | "low";

export interface Band {
  key: BandKey;
  label: string;
  meaning: string;
}

/** The trust-score legend. High ≥ 85 · Med 60–84 · Low < 60. */
export function trustBand(score: number): Band {
  if (score >= 85)
    return { key: "high", label: "High", meaning: "safe to apply automatically" };
  if (score >= 60)
    return { key: "med", label: "Med", meaning: "worth a human glance" };
  return { key: "low", label: "Low", meaning: "very likely wrong — rejected" };
}

export const BAND_LEGEND: { key: BandKey; range: string; label: string; meaning: string }[] = [
  { key: "high", range: "≥ 85", label: "High", meaning: "safe to apply automatically" },
  { key: "med", range: "60–84", label: "Med", meaning: "worth a human glance" },
  { key: "low", range: "< 60", label: "Low", meaning: "very likely wrong — rejected" },
];

/** An accessible one-liner reflecting decision + score + band, used as the seal's aria-label. */
export function verdictAria(decision: Decision, score: number): string {
  return `Verdict: ${decisionLabel[decision]}, trust score ${score} of 100, ${trustBand(score).label} confidence`;
}
