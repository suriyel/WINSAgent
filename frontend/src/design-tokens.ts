/** UCD Design Tokens — Neo-Swiss International Typographic Style */

export const colors = {
  primary: "#A78BFA",       // 薰衣草紫 – 交互高亮、确认按钮
  primaryHover: "#8B5CF6",
  secondary: "#60A5FA",     // 天空蓝   – 运行中状态
  success: "#34D399",       // 薄荷绿   – 完成状态
  error: "#F87171",         // 珊瑚红   – 失败状态
  background: "#FAFAFA",    // 页面背景
  card: "#FFFFFF",          // 组件卡片
  textPrimary: "#1F2937",   // 主文字
  textSecondary: "#6B7280", // 次文字
  textWeak: "#9CA3AF",      // 弱文字
} as const;

export const spacing = {
  grid: 8,       // 8px 基准网格
  gutter: 24,    // 栅格间距
  columns: 12,   // 12 栏网格
} as const;

export const typography = {
  fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
} as const;
