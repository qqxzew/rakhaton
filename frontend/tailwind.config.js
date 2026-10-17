/** @type {import('tailwindcss').Config} */
// NIS look (see DESIGN.md). Root font is 14 px, so the type scale below is in rem of 14 px.
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Roboto", "Segoe UI", "Arial", "sans-serif"],
      },
      fontSize: {
        "2xs": ["0.786rem", { lineHeight: "1rem" }], // 11 px field labels
        xs: ["0.857rem", { lineHeight: "1.143rem" }], // 12 px
        sm: ["0.929rem", { lineHeight: "1.286rem" }], // 13 px tables
        base: ["1rem", { lineHeight: "1.43rem" }], // 14 px
        lg: ["1.143rem", { lineHeight: "1.57rem" }], // 16 px
        xl: ["1.286rem", { lineHeight: "1.71rem" }], // 18 px
        "2xl": ["1.571rem", { lineHeight: "2rem" }], // 22 px patient name
        "3xl": ["1.857rem", { lineHeight: "2.29rem" }], // 26 px
      },
      colors: {
        // single accent color: NIS blue
        accent: {
          50: "#eef5ff",
          100: "#dcebff",
          500: "#2a80f5",
          600: "#0b6cf0",
          700: "#0957c3",
        },
        nis: {
          page: "#e9edf3",
          line: "#d6dce5",
          head: "#f1f4f8",
          text: "#1f2a37",
          muted: "#5f6b7a",
          icon: "#6b7685",
          ink: "#3c4858",
          // pastel row backgrounds
          ready: "#e2f0d9",
          attention: "#fff4c2",
          danger: "#fbe1e1",
          info: "#e8f2fb",
          // solid tag colors
          green: "#2e7d32",
          amber: "#f2b705",
          red: "#d32f2f",
          teal: "#1a96a0",
          slate: "#3c4858",
        },
      },
      borderRadius: {
        nis: "5px",
      },
    },
  },
  plugins: [],
};
