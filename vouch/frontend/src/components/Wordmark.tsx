/** The Vouch wordmark — a small holographic seal-diamond beside a Fraunces wordmark. */

export function Wordmark({ dark = false }: { dark?: boolean }) {
  return (
    <span className="flex items-center gap-2">
      <svg viewBox="0 0 24 24" className="size-6" aria-hidden>
        <defs>
          <linearGradient id="wm-holo" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#37E0D8" />
            <stop offset="50%" stopColor="#7C5CFF" />
            <stop offset="100%" stopColor="#F6C560" />
          </linearGradient>
        </defs>
        <rect x="2" y="2" width="20" height="20" rx="6" fill="url(#wm-holo)" />
        <path d="M7 9h2.4l2.6 6 2.6-6H17l-4 9h-2z" fill="#0B1220" />
      </svg>
      <span
        className={`font-display text-lg font-semibold tracking-tight ${
          dark ? "text-navy-ink" : "text-ink"
        }`}
      >
        Vouch
      </span>
    </span>
  );
}
