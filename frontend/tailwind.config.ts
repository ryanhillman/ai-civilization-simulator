import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        // Parchment / amber tones for the medieval theme
        parchment: {
          50: "#fdf8ee",
          100: "#f9edcc",
          200: "#f2d98a",
          300: "#e8bf4e",
          400: "#d4a227",
          500: "#b8841a",
        },
        stone: {
          850: "#1c1917",
          950: "#0c0a09",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};

export default config;
