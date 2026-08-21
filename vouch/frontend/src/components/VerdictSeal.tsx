/**
 * The Verdict Seal — Vouch's signature object, reused on every surface (hero, console, receipts,
 * Trust API). It is the through-line that makes "the verdict is the product" *shown*, not claimed:
 * the same seal that stamps a held card is the same seal the API returns.
 *
 * A circular security seal: a guilloché tick-ring whose coloured arc encodes the 0–100 trust score,
 * an iridescent holographic sheen, microtext on the rim, and a mono center reading PASS/FAIL + score.
 * It "stamps in" on arrival (respecting prefers-reduced-motion, handled globally in index.css).
 */

import { type Decision, decisionGlyph, decisionLabel, trustBand, verdictAria } from "../verdict";

const RING_COLOR: Record<Decision, string> = {
  pass: "#0E9E6E",
  fail: "#EE4B34",
  review: "#E8A317",
};

export function VerdictSeal({
  decision,
  score,
  size = 96,
  animate = true,
  dark = false,
  className = "",
}: {
  decision: Decision;
  score: number;
  size?: number;
  animate?: boolean;
  dark?: boolean;
  className?: string;
}) {
  const clamped = Math.max(0, Math.min(100, score));
  const r = 42;
  const circ = 2 * Math.PI * r;
  const arc = (clamped / 100) * circ;
  const color = RING_COLOR[decision];
  const band = trustBand(clamped);
  // Below chip/receipt size the inner label/band microtext is illegible; show only the score.
  const compact = size < 70;

  // Guilloché rim: 60 tick marks around the seal.
  const ticks = Array.from({ length: 60 });

  return (
    <div
      role="img"
      aria-label={verdictAria(decision, clamped)}
      className={`relative inline-grid shrink-0 place-items-center ${animate ? "animate-stamp" : ""} ${className}`}
      style={{ width: size, height: size }}
    >
      <svg viewBox="0 0 100 100" className="h-full w-full -rotate-90" aria-hidden>
        <defs>
          <linearGradient id={`holo-${decision}`} x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#37E0D8" />
            <stop offset="50%" stopColor="#7C5CFF" />
            <stop offset="100%" stopColor="#F6C560" />
          </linearGradient>
        </defs>

        {/* guilloché tick rim */}
        <g className="rotate-90" style={{ transformOrigin: "50px 50px" }}>
          {ticks.map((_, i) => {
            const a = (i / ticks.length) * 2 * Math.PI;
            const inner = i % 5 === 0 ? 46 : 48;
            const x1 = 50 + Math.cos(a) * inner;
            const y1 = 50 + Math.sin(a) * inner;
            const x2 = 50 + Math.cos(a) * 49.5;
            const y2 = 50 + Math.sin(a) * 49.5;
            return (
              <line
                key={i}
                x1={x1}
                y1={y1}
                x2={x2}
                y2={y2}
                stroke="currentColor"
                strokeWidth={i % 5 === 0 ? 0.8 : 0.4}
                className={dark ? "text-white/25" : "text-ink/20"}
              />
            );
          })}
        </g>

        {/* base track */}
        <circle
          cx="50"
          cy="50"
          r={r}
          fill="none"
          stroke={dark ? "#ffffff1f" : "#00000012"}
          strokeWidth="5"
        />
        {/* holographic sheen underlay */}
        <circle
          cx="50"
          cy="50"
          r={r}
          fill="none"
          stroke={`url(#holo-${decision})`}
          strokeWidth="5"
          strokeLinecap="round"
          strokeDasharray={`${arc} ${circ}`}
          opacity="0.35"
        />
        {/* score arc */}
        <circle
          cx="50"
          cy="50"
          r={r}
          fill="none"
          stroke={color}
          strokeWidth="3.5"
          strokeLinecap="round"
          strokeDasharray={`${arc} ${circ}`}
          className={animate ? "animate-ringdraw" : ""}
          style={
            {
              "--ring-len": `${circ}`,
              "--ring-off": `${0}`,
              strokeDashoffset: 0,
            } as React.CSSProperties
          }
        />
      </svg>

      {/* center face. Below ~70px (chip/receipt sizes) the microtext is illegible, so only the score
          glyph is shown — the decision + band are printed beside the seal and in the aria-label. */}
      <div className="absolute inset-0 grid place-items-center text-center leading-none">
        <div>
          {!compact && (
            <div
              className="font-mono font-bold tracking-tight"
              style={{ color, fontSize: size * 0.15 }}
            >
              <span aria-hidden>{decisionGlyph[decision]}</span> {decisionLabel[decision]}
            </div>
          )}
          <div
            className={`num font-bold ${dark ? "text-navy-ink" : "text-ink"}`}
            style={{ fontSize: compact ? size * 0.34 : size * 0.26, lineHeight: 1 }}
          >
            {clamped}
          </div>
          {!compact && (
            <div
              className={`font-mono uppercase tracking-[0.14em] ${dark ? "text-navy-muted" : "text-ink-muted"}`}
              style={{ fontSize: size * 0.085 }}
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
 * The inline verdict chip — the horizontal `╭ VERDICT … ╮` from the wireframes. A compact seal beside
 * the plain-English line, with the `view as API →` bridge that links a held decision straight to the
 * Trust API preloaded with that row.
 */
export function VerdictChip({
  decision,
  score,
  line,
  onViewAsApi,
  dark = false,
}: {
  decision: Decision;
  score: number;
  line: string;
  onViewAsApi?: () => void;
  dark?: boolean;
}) {
  const color = RING_COLOR[decision];
  const band = trustBand(score);
  return (
    <div
      className={`flex items-center gap-3 rounded-xl border px-3 py-2.5 ${
        dark
          ? "border-navy-hair bg-navy-800/60"
          : "border-hair bg-raised/60"
      }`}
    >
      <VerdictSeal decision={decision} score={score} size={54} animate={false} dark={dark} />
      <div className="min-w-0">
        <p className="flex items-center gap-1.5 text-[13px] font-semibold">
          <span style={{ color }}>
            {decisionGlyph[decision]} {decisionLabel[decision]}
          </span>
          <span className={dark ? "text-navy-muted" : "text-ink-muted"}>
            · trust {score}/100 ({band.label})
          </span>
        </p>
        <p className={`mt-0.5 truncate text-xs ${dark ? "text-navy-muted" : "text-ink-secondary"}`}>
          {line}
        </p>
        {onViewAsApi && (
          <button
            type="button"
            onClick={onViewAsApi}
            className="mt-1 text-xs font-semibold text-holo-violet hover:underline"
          >
            view as API →
          </button>
        )}
      </div>
    </div>
  );
}
