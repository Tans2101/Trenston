import { cn } from "@/lib/utils";
import styles from "./LaptopMockup.module.css";

/**
 * MacBook-style frame for marketing mockups: dark screen bezel with a
 * camera notch, a slot for a screenshot/image, and a light aluminum base.
 */
export default function LaptopMockup({ src, alt = "", caption, className }) {
  return (
    <div className={cn("w-full", className)}>
      <div className={styles.macbookFrame}>
        <div className={styles.screenContainer}>
          <div className={styles.cameraNotch} aria-hidden />
          <div className={styles.screenContent}>
            <img src={src} alt={alt} />
          </div>
        </div>
        <div className={styles.macbookBase} aria-hidden />
        <div className={styles.macbookNotchBase} aria-hidden />
      </div>
      {caption && (
        <p className="mt-4 text-center font-mono text-[10px] uppercase tracking-[0.2em] text-helm-slate">
          {caption}
        </p>
      )}
    </div>
  );
}
