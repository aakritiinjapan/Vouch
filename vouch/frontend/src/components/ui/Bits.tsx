/** Small shared primitives. Kept in one file so the component tree stays scannable. */

import { useState, type ReactNode } from "react";

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
    <header className="flex flex-wrap items-center justify-between gap-3 border-b border-hair px-5 py-3.5">
      <div>
        <h2 className="flex items-center gap-2 text-[13px] font-semibold tracking-tight text-ink">
          {title}
          {count !== undefined && (
            <span className="num rounded bg-raised px-1.5 py-0.5 text-[11px] font-normal text-ink-secondary">
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
    <span className="rounded border border-status-critical/40 bg-status-critical/10 px-1.5 py-0.5 font-mono text-[11px] font-medium tracking-wide text-status-critical">
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
    primary: "bg-series text-plane font-semibold hover:bg-series/85",
    secondary: "bg-raised text-ink hover:bg-raised/70 border border-hair hover:border-axis",
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
 * The confidence gauge.
 *
 * Deliberately not a progress bar. A thin filled track reads as "loading", which is the opposite of
 * what this number is: a completed measurement the operator is being asked to act on. So it is drawn
 * as a discrete scale - twenty ticks, filled to the score - with the figure set large in mono beside
 * it. That is what a gauge on an instrument looks like, and it makes the reading the thing you see
 * first rather than the coloured bar.
 *
 * Colour carries severity, but never alone: the icon and the words "failed / unconfirmed /
 * verified" say it too, so it survives a colourblind viewer and a badly-calibrated projector.
 */
export function ConfidenceMeter({
  confidence,
  size = "default",
}: {
  confidence: number;
  size?: "default" | "large";
}) {
  const severity = confidenceSeverity(confidence);
  const label = { good: "verified", warning: "unconfirmed", critical: "failed" }[severity];
  const icon = { good: "✓", warning: "!", critical: "✕" }[severity];

  const TICKS = 20;
  const lit = Math.round((Math.max(0, Math.min(100, confidence)) / 100) * TICKS);

  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
      <div
        className="flex items-end gap-[3px]"
        role="meter"
        aria-valuenow={confidence}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="Guardian confidence"
      >
        {Array.from({ length: TICKS }).map((_, i) => (
          <span
            key={i}
            className={`w-[3px] rounded-[1px] transition-colors ${
              i < lit ? severityBg[severity] : "bg-axis/45"
            } ${size === "large" ? "h-4" : "h-3"} ${i % 5 === 0 ? "opacity-100" : "opacity-80"}`}
          />
        ))}
      </div>

      <span
        className={`num font-bold leading-none ${severityText[severity]} ${
          size === "large" ? "text-xl" : "text-base"
        }`}
      >
        {confidence}
        <span className="text-ink-muted font-normal text-xs"> / 100</span>
      </span>

      <span className={`text-xs font-semibold ${severityText[severity]}`}>
        {icon} {label}
      </span>
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

/**
 * A folded section for reference material.
 *
 * Anything that is not a decision belongs behind one of these. The console's job is to surface what
 * needs judgement; the catalogue and the operator log are things you consult, not things you answer.
 */
export function Disclosure({
  title,
  count,
  hint,
  defaultOpen = false,
  children,
}: {
  title: string;
  count?: number;
  hint?: string;
  defaultOpen?: boolean;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <section className="overflow-hidden rounded-lg border border-hair bg-surface">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center gap-2 px-5 py-3 text-left hover:bg-raised/40"
      >
        <span
          className={`text-ink-muted transition-transform ${open ? "rotate-90" : ""}`}
          aria-hidden
        >
          ▸
        </span>
        <span className="text-sm font-medium text-ink">{title}</span>
        {count !== undefined && (
          <span className="rounded bg-raised px-1.5 py-0.5 text-[11px] text-ink-muted">
            {count}
          </span>
        )}
        {hint && <span className="ml-1 truncate text-xs text-ink-muted">{hint}</span>}
      </button>
      {open && <div className="border-t border-hair">{children}</div>}
    </section>
  );
}
