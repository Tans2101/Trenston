import { Link } from "react-router-dom";
import { motion } from "motion/react";
import { INTEGRATIONS_SHOWCASE } from "@/lib/marketingCopy";

const ease = [0.16, 1, 0.3, 1];
const fade = {
  hidden: { opacity: 0, y: 16 },
  show: (i = 0) => ({ opacity: 1, y: 0, transition: { duration: 0.65, ease, delay: i * 0.05 } }),
};

/**
 * Text wordmarks for real, shipped integrations only.
 * Avoids trademarked logo assets when usage terms are unclear.
 */
export default function IntegrationsShowcase({ compact = false }) {
  return (
    <section
      className={`px-6 border-t border-helm-navy/[0.05] ${compact ? "py-16" : "py-24"}`}
      data-testid="integrations-showcase"
      aria-label="Works with"
    >
      <div className="mx-auto max-w-6xl">
        <motion.div variants={fade} initial="hidden" whileInView="show" viewport={{ once: true, margin: "-60px" }}>
          <div className="h-px w-10 bg-helm-gold mb-6" aria-hidden />
          <p className="font-mono text-[10px] uppercase tracking-[0.25em] text-helm-slate">Works with</p>
          <h2 className="font-display mt-4 text-2xl md:text-3xl font-medium tracking-tight text-helm-navy max-w-xl">
            Tools your team already uses.
          </h2>
          <p className="mt-3 text-sm text-helm-slate max-w-xl leading-relaxed">
            Connect what you run today. Nothing requires an integration — manual entry stays available.
          </p>
        </motion.div>
        <ul className="mt-12 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-x-8 gap-y-10 list-none p-0 m-0">
          {INTEGRATIONS_SHOWCASE.map((item, i) => (
            <motion.li
              key={item.name}
              variants={fade}
              custom={i}
              initial="hidden"
              whileInView="show"
              viewport={{ once: true, margin: "-40px" }}
              className="border-t border-helm-navy/[0.08] pt-4"
            >
              <p className="font-display text-lg md:text-xl tracking-tight text-helm-navy">{item.name}</p>
              <p className="mt-1 font-mono text-[10px] uppercase tracking-[0.18em] text-helm-slate">{item.note}</p>
            </motion.li>
          ))}
        </ul>
        <p className="mt-10">
          <Link
            to="/integrations"
            className="inline-flex items-center gap-2 text-sm text-helm-navy hover:text-helm-ember transition-colors"
          >
            See what each integration does
            <span aria-hidden>→</span>
          </Link>
        </p>
      </div>
    </section>
  );
}
