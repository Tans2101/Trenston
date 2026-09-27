import { cn } from "@/lib/utils";
import styles from "./LaptopMockup.module.css";

/**
 * MacBook frame for marketing mockups — ported 1:1 from the founder-supplied
 * markup/CSS (top lid with camera notch + glass glare, bottom aluminum base
 * assembly with hinge highlight and thumb-cutout notch).
 */
export default function LaptopMockup({ src, alt = "", caption, className, children }) {
  return (
    <div className={cn("w-full", className)}>
      <div className={styles.macbookFrame}>
        {/* Top Lid / Screen Area */}
        <div className={styles.screenContainer}>
          <div className={styles.cameraNotch} aria-hidden>
            <div className={styles.lens} />
          </div>
          <div className={styles.screenContent}>
            {/* A real screenshot fills the panel edge-to-edge; when there
                isn't one yet, render a composed UI fragment instead (never
                stretched — same object-fit rules don't apply to markup). */}
            {src ? <img src={src} alt={alt} /> : <div className={styles.screenContentInner}>{children}</div>}
          </div>
        </div>

        {/* Bottom Base Assembly */}
        <div className={styles.baseContainer}>
          <div className={styles.macbookBase} aria-hidden />
          <div className={styles.macbookNotchBase} aria-hidden />
        </div>
      </div>
      {caption && (
        <p className="mt-4 text-center font-mono text-[10px] uppercase tracking-[0.2em] text-helm-slate">
          {caption}
        </p>
      )}
    </div>
  );
}
