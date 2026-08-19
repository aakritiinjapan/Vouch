/** @type {import('tailwindcss').Config} */
export default {
  // Omitting `content` silently produces an empty stylesheet - the single most common Tailwind bug.
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        plane: "#0d0d0d",
        surface: "#1a1a19",
        raised: "#232322",
        hair: "#2c2c2a",
        axis: "#383835",
        ink: {
          DEFAULT: "#ffffff",
          secondary: "#c3c2b7",
          muted: "#898781",
        },
        series: "#3987e5",
        status: {
          good: "#0ca30c",
          warning: "#fab219",
          serious: "#ec835a",
          critical: "#d03b3b",
        },
      },
      fontFamily: {
        sans: ["system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"],
      },
      boxShadow: {
        card: "0 1px 2px rgba(0,0,0,.4), 0 0 0 1px rgba(255,255,255,.06)",
        held: "0 0 0 1px rgba(208,59,59,.35), 0 8px 24px rgba(0,0,0,.45)",
      },
      keyframes: {
        holdpulse: {
          "0%, 100%": { opacity: "0.55" },
          "50%": { opacity: "1" },
        },
      },
      animation: {
        holdpulse: "holdpulse 2.4s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
