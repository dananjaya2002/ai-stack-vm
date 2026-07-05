import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#172033",
        muted: "#667085",
        panel: "#ffffff",
        line: "#d9e2ec",
        good: "#138a54",
        warn: "#b7791f",
        bad: "#c2414b",
        ocean: "#2563eb",
      },
      boxShadow: {
        soft: "0 12px 40px rgba(23, 32, 51, 0.08)",
      },
    },
  },
  plugins: [],
} satisfies Config;
