import trenstonMark from "@/assets/trenston-mark.svg";
import trenstonMarkNavy from "@/assets/trenston-mark-navy.svg";

/**
 * Approved Trenston medallion (transparent). Use `navy` for the dark-background
 * colorway (cream ring/T — trenston-mark-navy.svg); omit for light/cream surfaces
 * (navy ring/T — trenston-mark.svg).
 */
export default function HelmMark({ size = 36, navy = true, className = "", alt = "" }) {
  const px = typeof size === "number" ? size : 36;
  return (
    <img
      src={navy ? trenstonMarkNavy : trenstonMark}
      alt={alt}
      width={px}
      height={px}
      className={`shrink-0 ${className}`}
      draggable={false}
    />
  );
}
