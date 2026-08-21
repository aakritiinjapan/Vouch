/**
 * The Precision Verdict Gauge — Vouch's signature object, reused on every surface (hero, console,
 * receipts, Trust API). It is the through-line that makes "the verdict is the product" *shown*, not
 * claimed: the identical gauge that stamps a held card is the one the API returns.
 *
 * Precision is the point. A mathematically-exact 270° arc meter: a hairline track ring, an accent arc
 * drawn from 0 to the 0–100 score in the state colour, exact tick marks at the 60 and 85 thresholds,
 * and a centered tabular-mono score with a small PASS/FAIL glyph. Round-capped crisp SVG with arc
 * geometry computed to sub-pixel precision. The arc draws in on mount (respecting
 * prefers-reduced-motion, handled globally). It simplifies — never clutters — at small sizes, dropping
 * ticks and glyph while keeping the score, and reuses identical geometry at every size.
 */

import { type Decision, decisionGlyph, decisionLabel, trustBand, verdictAria } from "../verdict";

const STATE_COLOR: Record<Decision, string> = {
  pass: "#4ADE9E",
  fail: "#FF5C5C",
  review: "#F2C14E",
};

// Gauge geometry, in the 0–100 SVG viewBox. A 270° sweep, open at the bottom, reads as an instrument.
const CX = 50;
const CY = 50;
const R = 40;
const START_DEG = 135; // bottom-left
const SWEEP_DEG = 270; // clockwise through the top to bottom-right
const THRESHOLDS = [60, 85]; // High/Med/Low band edges, drawn as ticks

/** Point on the gauge circle for an angle measured in degrees (SVG convention: 0°=east, CW). */
function polar(r: number, deg: number): { x: number; y: number } {
  const rad = (deg * Math.PI) / 180;
  return { x: CX + r * Math.cos(rad), y: CY + r * Math.sin(rad) };
}

/** SVG arc path from `fromDeg` to `toDeg` on radius `r`, drawn clockwise. */
function arcPath(r: number, fromDeg: number, toDeg: number): string {
  const a = polar(r, fromDeg);
  const b = polar(r, toDeg);
  const largeArc = Math.abs(toDeg - fromDeg) > 180 ? 1 : 0;
  return `M ${a.x.toFixed(3)} ${a.y.toFixed(3)} A ${r} ${r} 0 ${largeArc} 1 ${b.x.toFixed(3)} ${b.y.toFixed(3)}`;
}

/** The angle, in degrees, where a 0–100 value sits on the sweep. */
function valueAngle(v: number): number {
  return START_DEG + (Math.max(0, Math.min(100, v)) / 100) * SWEEP_DEG;
}

export function VerdictGauge({
  decision,
  score,
  size = 104,
  animate = true,
  className = "",
}: {
  decision: Decision;
  score: number;
  size?: number;
  animate?: boolean;
  className?: string;
}) {
  const clamped = Math.max(0, Math.min(100, Math.round(score)));
  const color = STATE_COLOR[decision];
  const band = trustBand(clamped);
  // Below ~72px the ticks and glyph become visual noise; keep only the score.
  const compact = size < 72;
  const stroke = compact ? 5 : 4;

  const trackPath = arcPath(R, START_DEG, START_DEG + SWEEP_DEG);
  const valuePath = arcPath(R, START_DEG, valueAngle(clamped));

  return (
    <div
      role="img"
      aria-label={verdictAria(decision, clamped)}
      className={`relative inline-grid shrink-0 place-items-center ${className}`}
      style={{ width: size, height: size }}
    >
      <svg viewBox="0 0 100 100" className="h-full w-full overflow-visible" aria-hidden>
        <defs>
          <linearGradient id={`aurora-${decision}`} x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#8B7CFF" />
            <stop offset="55%" stopColor="#7CC6FF" />
            <stop offset="100%" stopColor="#4ADE9E" />
          </linearGradient>
        </defs>

        {/* hairline track ring */}
        <path
          d={trackPath}
          fill="none"
          stroke="rgba(255,255,255,0.10)"
          strokeWidth={stroke}
          strokeLinecap="round"
        />

        {/* threshold ticks — exact radial marks at the 60 and 85 band edges */}
        {!compact &&
          THRESHOLDS.map((t) => {
            const deg = valueAngle(t);
            const inner = polar(R - stroke / 2 - 2.5, deg);
            const outer = polar(R + stroke / 2 + 2.5, deg);
            const reached = clamped >= t;
            return (
              <line
                key={t}
                x1={inner.x.toFixed(3)}
                y1={inner.y.toFixed(3)}
                x2={outer.x.toFixed(3)}
                y2={outer.y.toFixed(3)}
                stroke={reached ? color : "rgba(255,255,255,0.22)"}
                strokeWidth={1}
                strokeLinecap="round"
              />
            );
          })}

        {/* the score arc, 0 → score, in the state colour, drawing in on mount */}
        {clamped > 0 && (
          <path
            d={valuePath}
            fill="none"
            stroke={color}
            strokeWidth={stroke}
            strokeLinecap="round"
            pathLength={100}
            strokeDasharray={100}
            className={animate ? "animate-gaugedraw" : ""}
            style={
              {
                "--arc-len": "100",
                "--arc-off": "0",
                strokeDashoffset: 0,
              } as React.CSSProperties
            }
          />
        )}
      </svg>

      {/* center face: tabular-mono score, and (above compact) a small PASS/FAIL glyph */}
      <div className="absolute inset-0 grid place-items-center text-center leading-none">
        <div>
          <div
            className="num font-bold text-ink"
            style={{ fontSize: compact ? size * 0.38 : size * 0.3, lineHeight: 1 }}
          >
            {clamped}
          </div>
          {!compact && (
            <div
              className="mt-1 font-mono font-bold uppercase tracking-[0.14em]"
              style={{ color, fontSize: size * 0.1 }}
            >
              <span aria-hidden>{decisionGlyph[decision]}</span> {decisionLabel[decision]}
            </div>
          )}
          {!compact && (
            <div
              className="mt-0.5 font-mono uppercase tracking-[0.12em] text-ink-muted"
              style={{ fontSize: size * 0.075 }}
            >
              {band.label} · /100
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/**
 * The inline verdict chip — the horizontal `╭ VERDICT … ╮` from the wireframes. A compact gauge beside
 * the plain-English line, with the `view as API →` bridge that links a held decision straight to the
 * Trust API preloaded with that row.
 */
export function VerdictChip({
  decision,
  score,
  line,
  onViewAsApi,
}: {
  decision: Decision;
  score: number;
  line: string;
  onViewAsApi?: () => void;
}) {
  const color = STATE_COLOR[decision];
  const band = trustBand(score);
  return (
    <div className="flex items-center gap-3 rounded-lg border border-hair bg-surface-raised px-3.5 py-3">
      <VerdictGauge decision={decision} score={score} size={56} animate={false} />
      <div className="min-w-0">
        <p className="flex flex-wrap items-center gap-x-1.5 text-[13px] font-semibold">
          <span style={{ color }}>
            {decisionGlyph[decision]} {decisionLabel[decision]}
          </span>
          <span className="text-ink-muted">
            · trust {score}/100 ({band.label})
          </span>
        </p>
        <p className="mt-0.5 truncate text-xs text-ink-secondary">{line}</p>
        {onViewAsApi && (
          <button
            type="button"
            onClick={onViewAsApi}
            className="mt-1 text-xs font-semibold text-brand hover:text-brand-soft hover:underline"
          >
            view as API →
          </button>
        )}
      </div>
    </div>
  );
}
