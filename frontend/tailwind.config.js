/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      keyframes: {
        "fade-in-up": {
          "0%": { opacity: "0", transform: "translateY(12px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "pulse-glow": {
          "0%, 100%": { boxShadow: "0 0 8px 2px rgba(239, 68, 68, 0.3)" },
          "50%": { boxShadow: "0 0 20px 6px rgba(239, 68, 68, 0.5)" },
        },
        "pulse-glow-orange": {
          "0%, 100%": { boxShadow: "0 0 8px 2px rgba(249, 115, 22, 0.25)" },
          "50%": { boxShadow: "0 0 18px 5px rgba(249, 115, 22, 0.45)" },
        },
        "pulse-alert": {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.6" },
        },
      },
      animation: {
        "fade-in-up": "fade-in-up 0.5s ease-out both",
        "pulse-glow": "pulse-glow 2s ease-in-out infinite",
        "pulse-glow-orange": "pulse-glow-orange 2.5s ease-in-out infinite",
        "pulse-alert": "pulse-alert 2s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
