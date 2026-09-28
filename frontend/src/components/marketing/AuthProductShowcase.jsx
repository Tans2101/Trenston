import { motion } from "motion/react";
import { Check } from "lucide-react";
import { DecisionScreen } from "@/components/marketing/ProductScreens";
import { DarkBackdrop, Eyebrow, ease } from "@/components/marketing/mk";
import { CATEGORY, TAGLINE } from "@/lib/marketingCopy";

const POINTS = [
  "What changed, what needs a decision, what you can hand off",
  "Approvals ranked by impact in Decision Center",
  "Ask Trenston, grounded in your own financials and pipeline",
];

/**
 * Non-form auth column: black panel with a real product frame, tilted for
 * depth. Reuses DecisionScreen — no fabricated product content.
 */
export default function AuthProductShowcase() {
  const [line1, line2] = TAGLINE.split(". ");
  return (
    <div className="relative hidden flex-col justify-center overflow-hidden bg-mk-black px-12 py-16 text-white lg:flex xl:px-20">
      <DarkBackdrop />
      <div className="relative z-[1] max-w-lg">
        <Eyebrow dark>{CATEGORY}</Eyebrow>
        <motion.h2
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.9, ease }}
          className="mt-8 text-5xl font-semibold leading-[0.98] tracking-[-0.04em] xl:text-6xl"
        >
          {line1}.<br />
          {line2}
        </motion.h2>
        <ul className="mt-10 space-y-4">
          {POINTS.map((p, i) => (
            <motion.li
              key={p}
              initial={{ opacity: 0, x: -12 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.6, ease, delay: 0.3 + i * 0.1 }}
              className="flex items-start gap-3 text-mk-gray-dark"
            >
              <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center bg-white text-mk-black">
                <Check className="h-3 w-3" aria-hidden />
              </span>
              {p}
            </motion.li>
          ))}
        </ul>
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 1, ease, delay: 0.5 }}
          className="mt-14 max-w-md shadow-2xl shadow-black/60 [transform:perspective(1400px)_rotateY(-8deg)_rotateZ(-2deg)]"
          data-testid="auth-product-showcase"
        >
          <DecisionScreen />
        </motion.div>
      </div>
    </div>
  );
}
