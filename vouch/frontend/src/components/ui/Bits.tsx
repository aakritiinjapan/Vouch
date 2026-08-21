/** Small shared primitives. Kept in one file so the component tree stays scannable. */

import type { ReactNode } from "react";

export function Card({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`rounded-lg border border-hair bg-surface shadow-soft ${className}`}>
      {children}
    </section>
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
        <h2 className="flex items-center gap-2 font-display text-h2 font-semibold text-ink">
          {title}
          {count !== undefined && (
            <span className="num rounded-md border border-hair px-1.5 py-0.5 text-xs font-normal text-ink-secondary">
              {count}
            </span>
          )}
        </h2>
        {hint && <p className="mt-1 text-xs text-ink-muted">{hint}</p>}
      </div>
      {action}
    </header>
  );
}

/** The machine tag, e.g. COLUMN_SWAP. Monospace on purpose: it reads as evidence, not decoration. */
export function CheckBadge({ code }: { code: string }) {
  return (
    <span className="rounded-md border border-held/40 bg-held/10 px-1.5 py-0.5 font-mono text-[11px] font-medium tracking-wide text-held">
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
    neutral: "border-hair bg-white/[0.04] text-ink-secondary",
    good: "border-verified/40 bg-verified/10 text-verified",
    warning: "border-watch/40 bg-watch/10 text-watch",
    critical: "border-held/40 bg-held/10 text-held",
  };
  return (
    <span
      className={`rounded-md border px-1.5 py-0.5 text-[11px] font-medium ${tones[tone]}`}
    >
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
    primary:
      "bg-brand text-canvas font-semibold hover:bg-brand-soft",
    secondary:
      "border border-hairStrong bg-white/[0.03] text-ink hover:bg-white/[0.07] hover:border-white/20",
    ghost: "text-ink-secondary hover:text-ink hover:bg-white/[0.05]",
    danger:
      "border border-held/50 bg-transparent text-held hover:bg-held/10",
  };
  return (
    <button
      type="button"
      title={title}
      onClick={onClick}
      disabled={disabled || busy}
      className={`inline-flex items-center gap-1.5 rounded-md px-3.5 py-2 text-xs font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-45 ${variants[variant]}`}
    >
      {busy && (
        <span className="size-3 animate-spin rounded-full border-2 border-current border-t-transparent" />
      )}
      {children}
    </button>
  );
}

export function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <div className="px-5 py-12 text-center">
      <p className="text-sm font-medium text-ink-secondary">{title}</p>
      <p className="mx-auto mt-1.5 max-w-sm text-xs text-ink-muted">{body}</p>
    </div>
  );
}

export function Skeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div className="space-y-2 px-5 py-4">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="h-9 animate-pulse rounded-md bg-white/[0.04]" />
      ))}
    </div>
  );
}
