/** @type {import('tailwindcss').Config} */

// Design direction: "instrument".
//
// Vouch's whole job is to refuse to act on a number it cannot stand behind, so the console should
// read like a measuring instrument rather than a SaaS dashboard: cool graphite housing, numerals set
// in a real mono, and colour reserved for state. It commits to a single dark theme on purpose - an
// operator console that follows the viewer's OS theme is a website, not an instrument.
//
// Two rules hold the palette together:
//   1. Status colours (hold / verified / watch) are reserved for state and are never used to
//      decorate. `series` is a separate hue so chart marks can never be mistaken for a verdict.
//   2. The two dashboard states run at different temperatures. Nothing held reads cool and quiet;
//      something held pulls warm. That difference is the design carrying information, not styling.
export default {
  // Omitting `content` silently produces an empty stylesheet - the single most common Tailwind bug.
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        plane: "#080d0f",     // the housing
        surface: "#0e1518",   // panels
        raised: "#161f23",    // controls, inset wells
        hair: "#222e33",      // hairlines
        axis: "#33434a",      // chart axes, dividers that need to be seen
        ink: {
          DEFAULT: "#f2f7f8",
          secondary: "#9fb3ba",
          muted: "#6b8189",
        },
        // Chart marks. Deliberately not one of the status hues.
        series: "#57b8e0",
        status: {
          good: "#3fd8a4",      // verified - the source is confirmed
          warning: "#f2b134",   // review - ambiguous, needs a human
          serious: "#ff9a4a",
          critical: "#ff6b4a",  // held - the state this product exists to produce
        },
      },
      fontFamily: {
        sans: ["Chivo", "system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"],
        mono: ["'JetBrains Mono'", "ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      fontSize: {
        // One display step, used only for the money figure on a held card.
        hero: ["3.25rem", { lineHeight: "1", letterSpacing: "-0.03em" }],
      },
      boxShadow: {
        card: "0 1px 2px rgba(0,0,0,.5), 0 0 0 1px rgba(242,247,248,.05)",
        held: "0 0 0 1px rgba(255,107,74,.30), 0 16px 40px -20px rgba(255,107,74,.35), 0 8px 24px rgba(0,0,0,.5)",
        panel: "0 0 0 1px rgba(242,247,248,.05)",
      },
      keyframes: {
        holdpulse: {
          "0%, 100%": { opacity: "0.5" },
          "50%": { opacity: "1" },
        },
        // A held card arriving is the moment the product exists for, so it gets the one piece of
        // motion in the app. Everything else is static on purpose.
        rise: {
          from: { opacity: "0", transform: "translateY(6px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        sweep: {
          from: { transform: "scaleX(0)" },
          to: { transform: "scaleX(1)" },
        },
      },
      animation: {
        holdpulse: "holdpulse 2.4s ease-in-out infinite",
        rise: "rise .34s cubic-bezier(.16,1,.3,1) both",
        sweep: "sweep .5s cubic-bezier(.16,1,.3,1) both",
      },
    },
  },
  plugins: [],
};
