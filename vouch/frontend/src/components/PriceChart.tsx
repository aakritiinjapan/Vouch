/**
 * Hand-rolled inline SVG rather than a chart library.
 *
 * The one thing this chart must do is the one thing a library makes hardest: leave an HONEST GAP
 * where the guardian could not confirm the source (README section 7), instead of interpolating a
 * straight line across it. That is implemented structurally - the confirmed series is split into
 * separate <path> elements at every null, so there is no code path that could join them.
 *
 * Colour assignment is by EMPHASIS, not identity: our price is the point, the competitor is context,
 * the counterfactual is the story. The obvious "three categorical colours" assignment fails contrast
 * checking - a categorical orange sits too close to the critical red the counterfactual needs.
 */

import { money } from "../format";
import type { Counterfactual, HistoryPoint } from "../types";

const W = 620;
const H = 190;
const PAD = { top: 14, right: 58, bottom: 26, left: 8 };

interface Props {
  points: HistoryPoint[];
  counterfactual?: Counterfactual | null;
  showCounterfactual?: boolean;
}

export function PriceChart({ points, counterfactual, showCounterfactual = false }: Props) {
  if (points.length < 2) {
    return (
      <div className="flex h-[190px] items-center justify-center text-xs text-ink-muted">
        Not enough price history yet.
      </div>
    );
  }

  const cfPrice = showCounterfactual && counterfactual ? counterfactual.naive_price : null;

  const values = [
    ...points.map((p) => p.my_price),
    ...points.map((p) => p.competitor_price).filter((v): v is number => v !== null),
    ...(cfPrice !== null ? [cfPrice] : []),
  ];
  const rawMin = Math.min(...values);
  const rawMax = Math.max(...values);
  const span = rawMax - rawMin || 1;
  const min = rawMin - span * 0.12;
  const max = rawMax + span * 0.12;

  const innerW = W - PAD.left - PAD.right;
  const innerH = H - PAD.top - PAD.bottom;
  const x = (i: number) => PAD.left + (i / (points.length - 1)) * innerW;
  const y = (v: number) => PAD.top + innerH - ((v - min) / (max - min)) * innerH;

  const line = (pts: { i: number; v: number }[]) =>
    pts.map((p, k) => `${k === 0 ? "M" : "L"}${x(p.i).toFixed(1)},${y(p.v).toFixed(1)}`).join(" ");

  // Split the competitor series at every unconfirmed point. This is the honest gap.
  const segments: { i: number; v: number }[][] = [];
  let current: { i: number; v: number }[] = [];
  points.forEach((point, i) => {
    if (point.competitor_price === null) {
      if (current.length) segments.push(current);
      current = [];
    } else {
      current.push({ i, v: point.competitor_price });
    }
  });
  if (current.length) segments.push(current);

  const ourSeries = points.map((p, i) => ({ i, v: p.my_price }));
  const lastConfirmed = segments.at(-1)?.at(-1);
  const gapIndexes = points.map((p, i) => (p.competitor_price === null ? i : -1)).filter((i) => i >= 0);

  return (
    <figure className="m-0">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img"
           aria-label="Our price against the confirmed competitor price over time">
        <defs>
          {/* Hatching, not a grey wash. A flat tint reads as "shaded region"; hatching reads as
              "nothing was recorded here", which is the whole point of the gap. */}
          <pattern id="unverified-hatch" width="7" height="7" patternUnits="userSpaceOnUse"
                   patternTransform="rotate(45)">
            <rect width="7" height="7" fill="transparent" />
            <line x1="0" y1="0" x2="0" y2="7" stroke="#FF5C5C" strokeWidth="1.4" opacity="0.30" />
          </pattern>
        </defs>

        {/* gridlines stay solid hairlines - dashed gridlines are the anti-pattern, dashed data is not */}
        {[0, 0.5, 1].map((t) => {
          const gy = PAD.top + innerH * t;
          return (
            <line key={t} x1={PAD.left} x2={PAD.left + innerW} y1={gy} y2={gy}
                  stroke="rgba(255,255,255,0.08)" strokeWidth="1" />
          );
        })}

        {/* the unverified band, so the gap is visibly labelled rather than merely absent */}
        {gapIndexes.length > 0 && (
          <>
            <rect
              x={x(Math.min(...gapIndexes)) - innerW / (points.length - 1) / 2}
              y={PAD.top}
              width={
                (Math.max(...gapIndexes) - Math.min(...gapIndexes) + 1) *
                (innerW / (points.length - 1))
              }
              height={innerH}
              fill="url(#unverified-hatch)"
              stroke="rgba(255,255,255,0.14)"
              strokeWidth="1"
              strokeDasharray="3 3"
            />
            {/* Anchored to whichever edge of the band keeps the label inside the plot. The gap is
                usually the most recent cycle, so a left-anchored label runs off the right edge. */}
            <text
              x={
                x(Math.min(...gapIndexes)) > PAD.left + innerW * 0.5
                  ? x(Math.max(...gapIndexes)) + innerW / (points.length - 1) / 2
                  : x(Math.min(...gapIndexes)) + 4
              }
              y={PAD.top + innerH + 17}
              textAnchor={
                x(Math.min(...gapIndexes)) > PAD.left + innerW * 0.5 ? "end" : "start"
              }
              className="fill-held text-[9px] font-medium"
            >
              unverified — no line drawn
            </text>
          </>
        )}

        {/* competitor: context, deliberately de-emphasised */}
        {segments.map((seg, k) => (
          <path key={k} d={line(seg)} fill="none" stroke="#8A8896" strokeWidth="2"
                strokeLinecap="round" />
        ))}
        {lastConfirmed && (
          <circle cx={x(lastConfirmed.i)} cy={y(lastConfirmed.v)} r="3.5"
                  fill="#0B0A10" stroke="#8A8896" strokeWidth="2" />
        )}

        {/* our price: the emphasis series */}
        <path d={line(ourSeries)} fill="none" stroke="#8B7CFF" strokeWidth="2"
              strokeLinecap="round" />
        <circle cx={x(points.length - 1)} cy={y(points.at(-1)!.my_price)} r="4"
                fill="#8B7CFF" stroke="#0B0A10" strokeWidth="2" />
        <text x={x(points.length - 1) + 8} y={y(points.at(-1)!.my_price) + 4}
              className="fill-ink text-[10px]">
          {money(points.at(-1)!.my_price, 0)}
        </text>

        {/* the counterfactual: dashed because it is a projection that never happened */}
        {cfPrice !== null && (
          <>
            <path
              d={`M${x(points.length - 2).toFixed(1)},${y(points.at(-2)!.my_price).toFixed(1)} L${x(
                points.length - 1,
              ).toFixed(1)},${y(cfPrice).toFixed(1)}`}
              fill="none"
              stroke="#FF5C5C"
              strokeWidth="2"
              strokeDasharray="5 4"
            />
            <circle cx={x(points.length - 1)} cy={y(cfPrice)} r="4" fill="#FF5C5C" />
            <text x={x(points.length - 1) + 8} y={y(cfPrice) + 4}
                  className="fill-held text-[10px]">
              {money(cfPrice, 0)}
            </text>
          </>
        )}
      </svg>

      <figcaption className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 px-1 text-[11px] text-ink-muted">
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-0.5 w-4 rounded bg-brand" /> our price
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-0.5 w-4 rounded bg-ink-muted" /> competitor (verified)
        </span>
        {cfPrice !== null && (
          <span className="flex items-center gap-1.5 text-held">
            <span
              className="inline-block h-0.5 w-4 rounded"
              style={{
                backgroundImage:
                  "repeating-linear-gradient(90deg,#FF5C5C 0 5px,transparent 5px 9px)",
              }}
            />
            if we had auto-approved
          </span>
        )}
      </figcaption>
    </figure>
  );
}
