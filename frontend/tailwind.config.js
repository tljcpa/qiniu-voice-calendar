/** @type {import('tailwindcss').Config} */
// 设计令牌（见复盘 D-19 / memory 反AI味）：
// 中性冷调 charcoal（非 slate/zinc 默认）+ 单一克制暖金强调色，
// 数据用 IBM Plex Mono 承载，硬线边框、最小圆角阴影、无渐变无霓虹。
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas: "#0e1014", // 最底背景（冷调近黑，非纯黑非 slate）
        panel: "#15181e", // 面板
        panel2: "#1b1f27", // 次级面板 / 输入框
        line: "#272c36", // 硬线边框
        "line-soft": "#1f242d",
        fg: {
          DEFAULT: "#e3e6ea", // 主文字
          muted: "#9298a3", // 次要文字
          dim: "#616773", // 弱化文字
        },
        // 单一强调色：克制暖金（区别于 AI 默认蓝/紫）
        accent: {
          DEFAULT: "#c9a25a",
          soft: "#221d12", // 强调色的极暗底纹
          line: "#5a4d30",
        },
        // 功能色：仅用于语义（冲突/危险）
        danger: "#c8604a",
        ok: "#6f9a6a",
      },
      fontFamily: {
        sans: [
          '"IBM Plex Sans"',
          '"PingFang SC"',
          '"Microsoft YaHei"',
          '"Source Han Sans SC"',
          "system-ui",
          "sans-serif",
        ],
        // 时间/日期/数据用等宽，强化"工具"质感
        mono: [
          '"IBM Plex Mono"',
          '"SFMono-Regular"',
          "ui-monospace",
          "Menlo",
          "monospace",
        ],
      },
      borderRadius: {
        // 克制圆角
        DEFAULT: "4px",
        md: "5px",
        lg: "7px",
      },
      keyframes: {
        fadeIn: {
          "0%": { opacity: "0", transform: "translateY(4px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        blink: {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.35" },
        },
      },
      animation: {
        fadeIn: "fadeIn 0.18s ease-out",
        blink: "blink 1.2s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
