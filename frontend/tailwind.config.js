/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        bg: "#0A0A0F",
        surface: "#111117",
        card: "#16161E",
        border: "#2A2A3A",
        red: "#FF2D55",
        cyan: "#69C9D0",
        muted: "#8B8B9E",
        success: "#00D37C",
        error: "#FF4444",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "monospace"],
      },
    },
  },
  plugins: [],
};
