import { cn } from "@/lib/utils";
import styles from "./LaptopMockup.module.css";

/**
 * MacBook Air-style frame for marketing mockups: thin bezel with a top
 * camera notch cut into the screen, a metal hinge line, and a slim
 * tapered aluminum keyboard deck with a front lip.
 */
export default function LaptopMockup({ src, alt = "", caption, className }) {
  return (
    <div className={cn("w-full", className)}>
      <div className={styles.macbookFrame}>
        <div className={styles.screenContainer}>
          <div className={styles.notch} aria-hidden>
            <span className={styles.cameraDot} />
          </div>
          <div className={styles.screenContent}>
            <img src={src} alt={alt} />
          </div>
        </div>
        <div className={styles.hinge} aria-hidden />
        <div className={styles.baseWrap}>
          <div className={styles.macbookBase} aria-hidden />
        </div>
        <div className={styles.frontLip} aria-hidden />
      </div>
      {caption && (
        <p className="mt-4 text-center font-mono text-[10px] uppercase tracking-[0.2em] text-helm-slate">
          {caption}
        </p>
      )}
    </div>
  );
}
