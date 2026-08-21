/** @type {import('tailwindcss').Config} */

// Design direction: "Certified".
//
// Vouch's product is the verdict — a portable stamp of trust. The visual language borrows from
// trust/security documents: seals, guilloché line-work, holographic sheen, microtext. Two worlds:
//
//   - The HERO is dark and atmospheric (navy with holographic orbs) — the pitch, the reframe.
//   - The CONSOLE is light and crisp (warm paper) — light reads as clarity; this is where a human
//     acts on a verdict, so nothing hides in shadow.
//
// One object crosses both: the Verdict Seal. Its iridescent sheen (cyan → violet → gold) is reserved
// for the seal and primary CTAs, never used to decorate.
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Console (light) — the working surface.
        paper: "#FBF9F4",
        surface: "#FFFFFF",
        raised: "#F3F0E8", // inset wells, quiet controls
        hair: "#E7E2D8", // hairlines
        axis: "#CFC9BC", // dividers that must be seen
        ink: {
          DEFAULT: "#1A1A22",
          secondary: "#41414C",
          muted: "#6B6B76",
        },
        // Hero (dark) — atmosphere.
        navy: {
          900: "#0B1220",
          800: "#0F1626",
          700: "#141B2E",
          600: "#1B2540",
          hair: "#26304A",
          ink: "#EDF0F7",
          muted: "#93A0BF",
        },
        // Status — reserved for state, never decoration.
        status: {
          good: "#0E9E6E", // verified / PASS
          warning: "#E8A317", // watch / REVIEW
          serious: "#E8722F",
          critical: "#EE4B34", // held / FAIL
        },
        // Iridescent hologram — the seal sheen + primary CTAs only.
        holo: {
          cyan: "#37E0D8",
          violet: "#7C5CFF",
          gold: "#F6C560",
        },
        series: "#7C5CFF", // chart emphasis (our price)
      },
      fontFamily: {
        display: ["'Fraunces Variable'", "Fraunces", "Georgia", "serif"],
        sans: ["Chivo", "system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"],
        mono: ["'JetBrains Mono'", "ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      fontSize: {
        hero: ["3.5rem", { lineHeight: "1.02", letterSpacing: "-0.02em" }],
        display: ["4.5rem", { lineHeight: "0.98", letterSpacing: "-0.025em" }],
      },
      backgroundImage: {
        "holo-sheen":
          "linear-gradient(115deg, #37E0D8 0%, #7C5CFF 45%, #F6C560 100%)",
        "holo-cta": "linear-gradient(120deg, #37E0D8 0%, #7C5CFF 55%, #F6C560 120%)",
      },
      boxShadow: {
        card: "0 1px 2px rgba(26,26,34,.05), 0 8px 24px -18px rgba(26,26,34,.25)",
        raised: "0 1px 3px rgba(26,26,34,.08), 0 18px 40px -24px rgba(26,26,34,.28)",
        held: "0 0 0 1px rgba(238,75,52,.22), 0 24px 48px -26px rgba(238,75,52,.35)",
        seal: "0 6px 22px -8px rgba(124,92,255,.45)",
      },
      keyframes: {
        rise: {
          from: { opacity: "0", transform: "translateY(8px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        stamp: {
          "0%": { opacity: "0", transform: "scale(1.6) rotate(-8deg)" },
          "60%": { opacity: "1", transform: "scale(0.94) rotate(1deg)" },
          "100%": { opacity: "1", transform: "scale(1) rotate(0deg)" },
        },
        scan: {
          "0%": { transform: "translateY(-100%)", opacity: "0" },
          "35%": { opacity: "1" },
          "100%": { transform: "translateY(220%)", opacity: "0" },
        },
        ringdraw: {
          from: { "stroke-dashoffset": "var(--ring-len)" },
          to: { "stroke-dashoffset": "var(--ring-off)" },
        },
        sheen: {
          "0%": { backgroundPosition: "0% 50%" },
          "100%": { backgroundPosition: "200% 50%" },
        },
        holdpulse: {
          "0%, 100%": { opacity: "0.55" },
          "50%": { opacity: "1" },
        },
        floaty: {
          "0%, 100%": { transform: "translate(0,0)" },
          "50%": { transform: "translate(2%,3%)" },
        },
        sweep: {
          from: { transform: "scaleX(0)" },
          to: { transform: "scaleX(1)" },
        },
      },
      animation: {
        rise: "rise .4s cubic-bezier(.16,1,.3,1) both",
        stamp: "stamp .55s cubic-bezier(.2,1.1,.3,1) both",
        scan: "scan 1s cubic-bezier(.4,0,.2,1) both",
        ringdraw: "ringdraw .8s cubic-bezier(.16,1,.3,1) both",
        sheen: "sheen 6s linear infinite",
        holdpulse: "holdpulse 2.4s ease-in-out infinite",
        floaty: "floaty 14s ease-in-out infinite",
        sweep: "sweep .5s cubic-bezier(.16,1,.3,1) both",
      },
    },
  },
  plugins: [],
};
