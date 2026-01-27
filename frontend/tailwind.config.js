/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        primary: "#A78BFA",       // 薰衣草紫
        "primary-hover": "#8B5CF6",
        secondary: "#60A5FA",     // 天空蓝
        success: "#34D399",       // 薄荷绿
        error: "#F87171",         // 珊瑚红
        surface: "#FAFAFA",       // 页面背景
        card: "#FFFFFF",          // 卡片色
        "text-primary": "#1F2937",  // 主文字
        "text-secondary": "#6B7280", // 次文字
        "text-weak": "#9CA3AF",     // 弱文字
      },
      fontFamily: {
        sans: ["Inter", "-apple-system", "BlinkMacSystemFont", "Segoe UI", "sans-serif"],
      },
      spacing: {
        grid: "8px",
      },
    },
  },
  plugins: [],
};
