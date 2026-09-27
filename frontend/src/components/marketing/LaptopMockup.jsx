import { cn } from "@/lib/utils";

/**
 * CSS/Tailwind laptop chrome for marketing mockups.
 * Dark bezel lid, screen slot for children, hinge, keyboard deck + trackpad.
 */
export default function LaptopMockup({ children, className }) {
  return (
    <div className={cn("relative mx-auto w-full max-w-full overflow-x-hidden", className)}>
      {/* Soft depth shadow shaped for the laptop silhouette */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-[4%] top-[6%] bottom-[2%] translate-y-3 rounded-[1.25rem] bg-helm-navy/20 blur-[2px]"
      />

      {/* Lid + screen */}
      <div className="relative z-[1] mx-auto w-[94%] sm:w-[92%]">
        <div className="rounded-t-lg rounded-b-[3px] bg-helm-ink p-[5px] sm:p-1.5 md:p-2 shadow-xl shadow-black/25">
          {/* Camera / sensor */}
          <div className="mx-auto mb-1 flex h-2 items-center justify-center sm:mb-1.5" aria-hidden>
            <span className="h-1 w-1 rounded-full bg-helm-cream/35" />
          </div>
          <div className="overflow-hidden rounded-[2px] bg-helm-ink-card ring-1 ring-inset ring-helm-cream/10">
            {children}
          </div>
        </div>
      </div>

      {/* Hinge */}
      <div
        aria-hidden
        className="relative z-[1] mx-auto h-[3px] w-[96%] bg-gradient-to-b from-helm-ink via-helm-navy to-helm-ink shadow-sm"
      />

      {/* Base / keyboard deck */}
      <div className="relative z-[1] mx-auto w-full">
        <div
          className="rounded-b-xl bg-helm-navy px-3 pb-2 pt-1.5 sm:px-5 sm:pb-2.5"
          style={{
            clipPath: "polygon(1.5% 0, 98.5% 0, 100% 100%, 0 100%)",
          }}
        >
          {/* Keyboard suggestion */}
          <div
            aria-hidden
            className="mx-auto h-1 w-[72%] max-w-md rounded-sm bg-helm-ink/45 sm:h-1.5"
          />
          {/* Trackpad */}
          <div
            aria-hidden
            className="mx-auto mt-1.5 h-5 w-[26%] max-w-[6.5rem] rounded-md border border-helm-cream/10 bg-helm-ink/35 sm:mt-2 sm:h-7 sm:max-w-[7.5rem]"
          />
        </div>
        {/* Front lip */}
        <div
          aria-hidden
          className="mx-auto h-1 w-[99%] rounded-b-full bg-helm-ink"
        />
      </div>
    </div>
  );
}
