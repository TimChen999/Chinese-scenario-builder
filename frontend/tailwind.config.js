/**
 * Tailwind config. We pre-load CJK font fallbacks so Chinese text
 * renders cleanly on every OS without each component having to set
 * font-family by hand. (DESIGN.md Section 8.)
 *
 * Class prefix: NONE. We rely on Tailwind utility class names which
 * do not start with `hg-`, so they cannot collide with the Pinyin
 * Tool extension's overlay CSS (Section 9 implication #3).
 */
/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        cjk: [
          '"PingFang SC"',
          '"Hiragino Sans GB"',
          '"Microsoft YaHei"',
          '"Source Han Sans CN"',
          "system-ui",
          "sans-serif",
        ],
      },
    },
  },
  plugins: [],
};
