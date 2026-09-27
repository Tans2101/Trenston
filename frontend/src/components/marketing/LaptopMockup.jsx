import { cn } from "@/lib/utils";

/**
 * CSS/Tailwind laptop chrome for marketing mockups.
 * Screen (lid) on top, thin hinge line, and a shallow keyboard-deck bar
 * beneath it — narrower than the lid with a small front lip, so it reads
 * as a laptop base rather than another slab the same size as the screen.
 */
export default function LaptopMockup({ children, className }) {
  return (
    <div className={cn("relative mx-auto w-full max-w-full", className)}>
      {/* Screen / lid */}
      <div className="relative z-[1] rounded-t-xl rounded-b-sm bg-helm-ink p-2 sm:p-2.5 shadow-2xl shadow-black/30 ring-1 ring-black/40">
        {/* Camera / sensor notch */}
        <div className="mx-auto mb-1.5 flex h-2 items-center justify-center" aria-hidden>
          <span className="h-1 w-1 rounded-full bg-helm-cream/30" />
        </div>
        <div className="overflow-hidden rounded-[3px] bg-helm-ink-card ring-1 ring-inset ring-white/5">
          {children}
        </div>
      </div>

      {/* Hinge shadow */}
      <div
        aria-hidden
        className="relative z-[1] h-[5px] bg-gradient-to-b from-black/50 via-helm-slate/50 to-black/40"
      />

      {/* Base / keyboard deck — narrower than the lid, shallow, rounded bottom */}
      <div className="relative z-[1] mx-auto w-[96%]">
        <div className="h-3 rounded-b-2xl bg-gradient-to-b from-helm-slate/60 to-helm-ink shadow-lg shadow-black/30 sm:h-4" />
        {/* Front lip / trackpad-notch highlight */}
        <div className="mx-auto h-[3px] w-1/4 rounded-b-full bg-helm-slate/50" />
      </div>
    </div>
  );
}
