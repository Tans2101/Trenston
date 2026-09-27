import { Link } from "react-router-dom";
import { motion } from "motion/react";
import { INTEGRATIONS_SHOWCASE } from "@/lib/marketingCopy";

const ease = [0.16, 1, 0.3, 1];
const fade = {
  hidden: { opacity: 0, y: 16 },
  show: (i = 0) => ({ opacity: 1, y: 0, transition: { duration: 0.65, ease, delay: i * 0.05 } }),
};

/**
 * Generic monogram badges, not real vendor logos — trademarked marks
 * (Google, QuickBooks, Xero, ...) need written permission we don't have,
 * so each badge is just the integration's first letter in a plain circle.
 * See PUBLIC_INTEGRATIONS_ATTRIBUTION in marketingCopy.js.
 */
function IntegrationBadge({ name }) {
  return (
    <div
      aria-hidden
      className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full border border-helm-navy/[0.1] bg-helm-navy/[0.03] font-mono text-sm text-helm-navy/70"
    >
      {name.trim().charAt(0)}
    </div>
  );
}

export default function IntegrationsShowcase({ compact = false }) {
  return (
    <section
      className={`px-6 border-t border-helm-navy/[0.05] ${compact ? "py-12" : "py-16"}`}
      data-testid="integrations-showcase"
      aria-label="Works with"
    >
      <div className="mx-auto max-w-6xl">
        <motion.div variants={fade} initial="hidden" whileInView="show" viewport={{ once: true, margin: "-60px" }}>
          <div className="h-px w-10 bg-helm-navy/25 mb-6" aria-hidden />
          <p className="font-mono text-[10px] uppercase tracking-[0.25em] text-helm-slate">Works with</p>
          <h2 className="font-display mt-4 text-2xl md:text-3xl font-medium tracking-tight text-helm-navy max-w-xl">
            Tools your team already uses.
          </h2>
          <p className="mt-3 text-sm text-helm-navy/70 max-w-xl leading-relaxed">
            Connect what you run today. Nothing requires an integration. Manual entry stays available.
          </p>
        </motion.div>
        <ul className="mt-10 flex flex-wrap gap-x-8 gap-y-6 list-none p-0 m-0">
          {INTEGRATIONS_SHOWCASE.map((item, i) => (
            <motion.li
              key={item.name}
              variants={fade}
              custom={i}
              initial="hidden"
              whileInView="show"
              viewport={{ once: true, margin: "-40px" }}
              className="flex items-center gap-3 rounded-lg border border-helm-navy/[0.08] px-4 py-3"
            >
              <IntegrationBadge name={item.name} />
              <div>
                <p className="font-display text-base tracking-tight text-helm-navy">{item.name}</p>
                <p className="mt-0.5 font-mono text-[10px] uppercase tracking-[0.15em] text-helm-slate">{item.note}</p>
              </div>
            </motion.li>
          ))}
        </ul>
        <p className="mt-10">
          <Link
            to="/integrations"
            className="inline-flex items-center gap-2 text-sm text-helm-navy hover:text-helm-ink transition-colors"
          >
            See what each integration does
            <span aria-hidden>→</span>
          </Link>
        </p>
      </div>
    </section>
  );
}
