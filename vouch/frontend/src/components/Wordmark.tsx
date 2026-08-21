/** The Vouch wordmark — a precise aurora seal-diamond beside the Bricolage wordmark. */

export function Wordmark({ size = "md" }: { size?: "md" | "lg" }) {
  const text = size === "lg" ? "text-2xl" : "text-lg";
  return (
    <span className="flex items-center gap-2.5">
      <svg viewBox="0 0 24 24" className="size-6" aria-hidden>
        <defs>
          <linearGradient id="wm-aurora" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#8B7CFF" />
            <stop offset="55%" stopColor="#7CC6FF" />
            <stop offset="100%" stopColor="#4ADE9E" />
          </linearGradient>
        </defs>
        <rect x="2.5" y="2.5" width="19" height="19" rx="5.5" fill="url(#wm-aurora)" />
        <path d="M7 9h2.4l2.6 6 2.6-6H17l-4 9h-2z" fill="#0B0A10" />
      </svg>
      <span className={`font-display font-extrabold tracking-tight text-ink ${text}`}>Vouch</span>
    </span>
  );
}
