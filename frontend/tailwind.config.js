/** @type {import('tailwindcss').Config} */
// 设计令牌（手账气质）：暖炭灰底 + 米白字 + 蜜琥珀强调；
// 标题/事件用霞鹜文楷 LXGW WenKai，正文用 Noto Sans SC。
// 禁用：紫蓝渐变 / Inter·Roboto·OpenSans / 玻璃拟态 / 卡片套卡片 / 标题大圆角图标 /
//      装饰 emoji / bounce 缓动 / 纯黑纯白 / 过量留白。
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas: "#1c1813", // 暖炭灰（非纯黑，带暖褐）
        panel: "#25201a",
        panel2: "#2e2820",
        line: "#423a2e", // 暖色硬线
        "line-soft": "#2c261e",
        fg: {
          DEFAULT: "#f2ead9", // 米白（非纯白）
          muted: "#b8ab92",
          dim: "#84775f",
        },
        // 单一强调：蜜琥珀
        accent: {
          DEFAULT: "#e2a749",
          soft: "#2f2616", // 强调色极暗底纹
          line: "#6e5a30",
        },
        // 功能语义色（暖调）
        danger: "#cf6f4a",
        ok: "#9aa15a",
      },
      fontFamily: {
        // UI 正文
        sans: [
          '"Noto Sans SC"',
          '"PingFang SC"',
          '"Microsoft YaHei"',
          "system-ui",
          "sans-serif",
        ],
        // 标题 / 事件：霞鹜文楷（手账手写气质）
        title: [
          '"LXGW WenKai Screen"',
          '"Noto Sans SC"',
          "KaiTi",
          "serif",
        ],
        // 时间/数据：沿用正文族（tabular-nums 对齐），不用等宽 techy 字体
        mono: ['"Noto Sans SC"', "ui-monospace", "monospace"],
      },
      borderRadius: {
        DEFAULT: "5px",
        md: "6px",
        lg: "9px",
      },
      keyframes: {
        fadeIn: {
          "0%": { opacity: "0", transform: "translateY(4px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        blink: {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.4" },
        },
      },
      animation: {
        fadeIn: "fadeIn 0.2s ease-out",
        blink: "blink 1.3s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
