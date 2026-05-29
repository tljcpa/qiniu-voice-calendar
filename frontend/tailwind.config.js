/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // 科技感深色主题色板
        ink: {
          900: "#0a0e1a", // 最深背景
          800: "#0f1525",
          700: "#161d33",
          600: "#1e2742",
        },
        neon: {
          cyan: "#22d3ee",
          blue: "#3b82f6",
          violet: "#a855f7",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "-apple-system", "Segoe UI", "sans-serif"],
      },
      boxShadow: {
        glow: "0 0 24px rgba(34, 211, 238, 0.35)",
        "glow-lg": "0 0 48px rgba(34, 211, 238, 0.45)",
      },
      keyframes: {
        pulseRing: {
          "0%": { transform: "scale(0.95)", opacity: "0.7" },
          "70%": { transform: "scale(1.3)", opacity: "0" },
          "100%": { transform: "scale(1.3)", opacity: "0" },
        },
        fadeInUp: {
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        pulseRing: "pulseRing 1.8s cubic-bezier(0.4,0,0.6,1) infinite",
        fadeInUp: "fadeInUp 0.3s ease-out",
      },
    },
  },
  plugins: [],
};
