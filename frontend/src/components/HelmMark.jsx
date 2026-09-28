// Monochrome marks (navy rays) — matches the black / navy / white system.
import trenstonMark from "@/assets/trenston-mark-mono.svg";
import trenstonMarkNavy from "@/assets/trenston-mark-mono-white.svg";

/**
 * Approved Trenston medallion (transparent). `navy` forces the dark-background
 * colorway (white ring/T — trenston-mark-mono-white.svg); omit for light/cream surfaces
 * (black ring/T — trenston-mark-mono.svg). Omitted, it follows html[data-theme].
 */
export default function HelmMark({ size = 36, navy, className = "", alt = "" }) {
  const px = typeof size === "number" ? size : 36;
  // Default follows the active theme: white mark on dark, black mark on light.
  const onDark = navy ?? (typeof document !== "undefined" && document.documentElement.dataset.theme === "dark");
  return (
    <img
      src={onDark ? trenstonMarkNavy : trenstonMark}
      alt={alt}
      width={px}
      height={px}
      className={`shrink-0 ${className}`}
      draggable={false}
    />
  );
}
