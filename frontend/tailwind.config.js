/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "Segoe UI Variable", "Segoe UI", "system-ui", "-apple-system", "Roboto", "Arial", "sans-serif"],
        mono: ["Cascadia Code", "Consolas", "ui-monospace", "monospace"],
      },
      colors: {
        ink: { DEFAULT: "#0f172a", soft: "#334155", muted: "#64748b", faint: "#94a3b8" },
      },
      boxShadow: { card: "0 1px 2px rgba(15,23,42,0.04), 0 1px 3px rgba(15,23,42,0.06)" },
    },
  },
  plugins: [],
};
