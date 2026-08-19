/** Small shared primitives. Kept in one file so the component tree stays scannable. */

import type { ReactNode } from "react";

import { confidenceSeverity, severityBg, severityText } from "../../format";

export function Card({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`rounded-lg bg-surface shadow-card ${className}`}>{children}</section>
  );
}

export function SectionHeader({
  title,
  count,
  hint,
  action,
}: {
  title: string;
  count?: number;
  hint?: string;
  action?: ReactNode;
}) {
  return (
    <header className="flex flex-wrap items-center justify-between gap-3 border-b border-hair px-5 py-4">
      <div>
        <h2 className="flex items-center gap-2 text-sm font-semibold text-ink">
          {title}
          {count !== undefined && (
            <span className="rounded-full bg-raised px-2 py-0.5 text-xs font-normal text-ink-secondary">
              {count}
            </span>
          )}
        </h2>
        {hint && <p className="mt-0.5 text-xs text-ink-muted">{hint}</p>}
      </div>
      {action}
    </header>
  );
}

/** The machine tag, e.g. COLUMN_SWAP. Monospace on purpose: it reads as evidence, not decoration. */
export function CheckBadge({ code }: { code: string }) {
  return (
    <span className="rounded border border-status-critical/40 bg-status-critical/10 px-1.5 py-0.5 font-mono text-[11px] tracking-wide text-status-critical">
      {code}
    </span>
  );
}

export function Badge({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "neutral" | "good" | "warning" | "critical";
}) {
  const tones = {
    neutral: "bg-raised text-ink-secondary",
    good: "bg-status-good/15 text-status-good",
    warning: "bg-status-warning/15 text-status-warning",
    critical: "bg-status-critical/15 text-status-critical",
  };
  return (
    <span className={`rounded px-1.5 py-0.5 text-[11px] font-medium ${tones[tone]}`}>
      {children}
    </span>
  );
}

export function Button({
  children,
  onClick,
  variant = "secondary",
  busy = false,
  disabled = false,
  title,
}: {
  children: ReactNode;
  onClick?: () => void;
  variant?: "primary" | "secondary" | "ghost" | "danger";
  busy?: boolean;
  disabled?: boolean;
  title?: string;
}) {
  const variants = {
    primary: "bg-series text-white hover:bg-series/85",
    secondary: "bg-raised text-ink hover:bg-raised/70 border border-hair",
    ghost: "text-ink-secondary hover:text-ink hover:bg-raised/60",
    danger:
      "bg-transparent text-status-critical border border-status-critical/40 hover:bg-status-critical/10",
  };
  return (
    <button
      type="button"
      title={title}
      onClick={onClick}
      disabled={disabled || busy}
      className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-45 ${variants[variant]}`}
    >
      {busy && (
        <span className="size-3 animate-spin rounded-full border-2 border-current border-t-transparent" />
      )}
      {children}
    </button>
  );
}

/**
 * The confidence meter.
 *
 * Colour carries severity in the fill, but it never carries the meaning alone - the icon and the
 * words "failed / unconfirmed / verified" say it too, so it survives a colourblind viewer and a
 * badly-calibrated projector. The unfilled track is the same hue at low opacity so the state reads
 * across the whole bar rather than only the filled part.
 */
export function ConfidenceMeter({ confidence }: { confidence: number }) {
  const severity = confidenceSeverity(confidence);
  const label = { good: "verified", warning: "unconfirmed", critical: "failed" }[severity];
  const icon = { good: "✓", warning: "!", critical: "✕" }[severity];

  return (
    <div className="flex items-center gap-3">
      <div
        className={`h-1.5 w-40 overflow-hidden rounded-full ${severityBg[severity]}/15`}
        role="meter"
        aria-valuenow={confidence}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="Guardian confidence"
      >
        <div
          className={`h-full rounded-full ${severityBg[severity]}`}
          style={{ width: `${Math.max(confidence, 2)}%` }}
        />
      </div>
      <span className={`text-xs font-medium ${severityText[severity]}`}>
        {icon} {label}
      </span>
      <span className="num-tabular text-xs text-ink-secondary">{confidence} / 100</span>
    </div>
  );
}

export function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <div className="px-5 py-10 text-center">
      <p className="text-sm font-medium text-ink-secondary">{title}</p>
      <p className="mx-auto mt-1 max-w-sm text-xs text-ink-muted text-pretty">{body}</p>
    </div>
  );
}

export function Skeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div className="space-y-2 px-5 py-4">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="h-9 animate-pulse rounded bg-raised/70" />
      ))}
    </div>
  );
}
