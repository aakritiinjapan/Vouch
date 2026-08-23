/** The Vouch wordmark — a precise aurora seal-diamond beside the Bricolage wordmark. */

export function Wordmark({
  size = "md",
  tagline = false,
}: {
  size?: "md" | "lg";
  /** The subtitle only earns its space in the header, where it says what the product IS. */
  tagline?: boolean;
}) {
  const text = size === "lg" ? "text-2xl" : "text-lg";
  return (
    <span className="flex items-center gap-2.5">
      <svg viewBox="0 0 24 24" className="size-6 shrink-0" aria-hidden>
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
      <span className="flex flex-col items-start leading-none">
        <span className={`font-display font-extrabold tracking-tight text-ink ${text}`}>Vouch</span>
        {tagline && (
          <span className="mt-0.5 hidden text-[10.5px] font-medium text-ink-muted sm:block">
            Universal self-heal verification engine
          </span>
        )}
      </span>
    </span>
  );
}
