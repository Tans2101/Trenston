import { DecisionScreen } from "@/components/marketing/ProductScreens";
import { CATEGORY, TAGLINE } from "@/lib/marketingCopy";

/**
 * Non-form auth column: ink panel with a real product frame, tilted for depth.
 * Reuses DecisionScreen — no fabricated product content.
 */
export default function AuthProductShowcase() {
  return (
    <div className="relative hidden lg:flex flex-col items-center justify-center overflow-hidden bg-helm-cream px-10 py-16">
      <div className="absolute inset-0 bg-helm-navy/[0.03]" aria-hidden />
      <div className="relative z-[1] w-full max-w-md">
        <p className="font-mono text-[10px] uppercase tracking-[0.28em] text-helm-slate mb-6 text-center">
          {CATEGORY}
        </p>
        <div
          className="origin-center shadow-2xl shadow-black/40 [transform:perspective(1400px)_rotateY(-10deg)_rotateZ(-3deg)]"
          data-testid="auth-product-showcase"
        >
          <DecisionScreen />
        </div>
        <p className="mt-10 text-center font-display text-xl text-helm-navy/80 tracking-tight leading-snug max-w-sm mx-auto">
          {TAGLINE}
        </p>
      </div>
    </div>
  );
}
