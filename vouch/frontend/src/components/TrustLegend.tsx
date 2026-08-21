/**
 * The trust-score legend, so the number means something: High ≥ 85 · Med 60–84 · Low < 60.
 * A small inline row with an ⓘ that expands the plain-English meaning of each band.
 */

import { useState } from "react";

import { BAND_LEGEND } from "../verdict";

const DOT: Record<string, string> = {
  high: "bg-verified",
  med: "bg-watch",
  low: "bg-held",
};

export function TrustLegend() {
  const [open, setOpen] = useState(false);

  return (
    <div className="text-[11px] text-ink-muted">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="eyebrow">Trust</span>
        {BAND_LEGEND.map((b) => (
          <span key={b.key} className="inline-flex items-center gap-1">
            <span className={`inline-block size-1.5 rounded-full ${DOT[b.key]}`} aria-hidden />
            {b.label} {b.range}
          </span>
        ))}
        <button
          type="button"
          aria-label="What the trust score means"
          aria-expanded={open}
          onClick={() => setOpen((o) => !o)}
          className="grid size-4 place-items-center rounded-full border border-hair text-[9px] hover:text-ink"
        >
          ⓘ
        </button>
      </div>
      {open && (
        <dl className="mt-2 space-y-1">
          {BAND_LEGEND.map((b) => (
            <div key={b.key} className="flex gap-2">
              <dt className="w-24 shrink-0 font-medium text-ink-secondary">
                {b.label} <span className="font-mono">{b.range}</span>
              </dt>
              <dd>{b.meaning}</dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  );
}
