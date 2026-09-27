/**
 * Hero social-proof strip. Placeholder marks only — generic monogram
 * badges, not real customer logos (Trenston has not collected logo
 * permission from clients yet). The trust line is deliberately soft
 * ("early customers", not a fabricated headcount like "500+ businesses")
 * since Trenston is pre-scale; swap in real names/logos and a true count
 * once there's something to point to.
 */
const PLACEHOLDER_MARKS = ["A", "M", "R", "K"];

export default function SocialProofBar({ className = "" }) {
  return (
    <div className={`flex flex-wrap items-center gap-x-6 gap-y-3 ${className}`} data-testid="social-proof-bar">
      <div className="flex items-center -space-x-2" aria-hidden>
        {PLACEHOLDER_MARKS.map((letter) => (
          <span
            key={letter}
            className="flex h-8 w-8 items-center justify-center rounded-full border-2 border-white bg-helm-navy/[0.06] font-mono text-[11px] font-medium text-helm-navy/60"
          >
            {letter}
          </span>
        ))}
      </div>
      <p className="text-xs text-helm-navy/70">
        Built with early founder-led customers, not a demo.
      </p>
    </div>
  );
}
