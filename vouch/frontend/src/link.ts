/**
 * The bidirectional cross-link between a held decision and the receipt that explains it.
 *
 * Each hold in "Needs your decision" and its receipt in "How Vouch decided" share one exact id — the
 * guardian's `heal_event_id` on the proposal is the `id` of the HealEvent. Hovering or focusing either
 * side lifts that id into `activeLinkId` on the common parent; both lists highlight the row whose id
 * matches, so the pairing is exact rather than fuzzy.
 *
 * The highlight is a soft brand-violet ring + faint glow + a one-pixel lift — on-brand, never a flash.
 * Under prefers-reduced-motion the global stylesheet neutralises the transition, leaving it static.
 */

/** Applied to a hold (or its matching receipt) while either side of the pair is hovered/focused. */
export const LINK_HIGHLIGHT_CLASS =
  "ring-2 ring-brand/60 shadow-[0_0_26px_-6px_rgba(139,124,255,0.5)] -translate-y-px";

/** The stable id a proposal and its receipt share, or null when no heal was involved. */
export function proposalLinkId(guardianHealEventId: number | null | undefined): number | null {
  return guardianHealEventId ?? null;
}
