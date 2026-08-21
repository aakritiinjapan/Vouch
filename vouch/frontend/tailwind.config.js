/** @type {import('tailwindcss').Config} */

// Design direction: "Verdict" — UNIFIED DARK · BOLD EDITORIAL, TYPE-LED · PRECISION VERDICT GAUGE.
//
// One continuous dark surface across Hero, Console, and Trust API — no light/dark split. Hierarchy
// comes from elevation, light, and space, not boxes. Personality is carried by typography and
// structure; colour is disciplined — state colours mean things (verified / held / watch), they never
// decorate. ONE violet→mint aurora gradient is reserved for the gauge sweep + the hero atmosphere.
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Canvas — deep ink with a whisper of violet. Never flat black.
        canvas: "#0B0A10",
        // The few raised regions. Two stops so a region can sit a hair above its neighbour.
        surface: {
          DEFAULT: "#151420",
          raised: "#1B1A26",
        },
        // Hairline — a single rgba(255,255,255,.07) rule, expressed as an opaque approximation too.
        hair: "rgba(255,255,255,0.07)",
        hairStrong: "rgba(255,255,255,0.12)",
        // Ink — warm off-white primary, then two muted steps. All AA on the canvas.
        ink: {
          DEFAULT: "#F4F2EC",
          secondary: "#A6A4B0",
          muted: "#6B6978",
        },
        // State — reserved for meaning. verified / held / watch.
        verified: "#4ADE9E",
        held: "#FF5C5C",
        watch: "#F2C14E",
        // Brand / interactive — links, focus, primary action. Distinct from every state colour.
        brand: {
          DEFAULT: "#8B7CFF",
          soft: "#A79BFF",
        },
        // Aurora stops (violet → mint). Used ONLY for the gauge sweep + hero atmosphere.
        aurora: {
          violet: "#8B7CFF",
          mint: "#4ADE9E",
        },
      },
      fontFamily: {
        display: ["'Bricolage Grotesque Variable'", "'Bricolage Grotesque'", "Georgia", "serif"],
        sans: ["'Inter Variable'", "Inter", "system-ui", "-apple-system", "Segoe UI", "sans-serif"],
        mono: ["'JetBrains Mono'", "ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      fontSize: {
        // Exact scale from UI_PLAN.
        hero: ["clamp(2.75rem,6vw,4.5rem)", { lineHeight: "0.98", letterSpacing: "-0.03em" }],
        title: ["2.5rem", { lineHeight: "1.02", letterSpacing: "-0.02em" }],
        h2: ["1.375rem", { lineHeight: "1.2", letterSpacing: "-0.01em" }],
        lead: ["1.125rem", { lineHeight: "1.5", letterSpacing: "0" }],
        body: ["15px", { lineHeight: "1.55" }],
      },
      borderRadius: {
        // One radius across the product.
        DEFAULT: "14px",
        lg: "14px",
        xl: "14px",
      },
      boxShadow: {
        // One shadow — a low, soft elevation. Regions lift off the canvas, they are not boxed.
        soft: "0 1px 0 0 rgba(255,255,255,0.04) inset, 0 24px 60px -32px rgba(0,0,0,0.8)",
        held: "0 0 0 1px rgba(255,92,92,0.20), 0 30px 70px -34px rgba(255,92,92,0.28)",
      },
      backgroundImage: {
        aurora: "linear-gradient(115deg, #8B7CFF 0%, #7CC6FF 45%, #4ADE9E 100%)",
      },
      keyframes: {
        reveal: {
          from: { opacity: "0", transform: "translateY(10px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        gaugedraw: {
          from: { "stroke-dashoffset": "var(--arc-len)" },
          to: { "stroke-dashoffset": "var(--arc-off)" },
        },
        holdpulse: {
          "0%, 100%": { opacity: "0.5" },
          "50%": { opacity: "1" },
        },
      },
      animation: {
        reveal: "reveal .6s cubic-bezier(.16,1,.3,1) both",
        gaugedraw: "gaugedraw 1s cubic-bezier(.16,1,.3,1) both",
        holdpulse: "holdpulse 2.4s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
