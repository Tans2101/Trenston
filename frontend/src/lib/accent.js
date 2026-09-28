/**
 * App accent colour. The accent is theme-driven (index.css sets
 * --helm-accent per html[data-theme]): navy #0B2A5B in light, pale
 * navy-white #C8D4EC in dark. Use ACCENT for SVG/Recharts fills and strokes;
 * use the hex scales where a component needs a list of concrete colours.
 */
export const ACCENT = "rgb(var(--helm-accent))";
export const accentAlpha = (a) => `rgb(var(--helm-accent) / ${a})`;

export const ACCENT_SCALE = {
  light: ["#0B2A5B", "#3D5A8A", "#7B8FB3", "#9CA3AF", "#D1D5DB"],
  dark: ["#C8D4EC", "#8FA3C7", "#6B7280", "#4B5563", "#374151"],
};
