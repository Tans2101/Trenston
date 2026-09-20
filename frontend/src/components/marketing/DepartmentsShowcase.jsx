import { motion } from "motion/react";
import { DEPARTMENTS_SECTION } from "@/lib/marketingCopy";

const ease = [0.16, 1, 0.3, 1];
const fade = {
  hidden: { opacity: 0, y: 16 },
  show: (i = 0) => ({ opacity: 1, y: 0, transition: { duration: 0.65, ease, delay: i * 0.05 } }),
};

/** Department lanes — typographic list, no icon cards. */
export default function DepartmentsShowcase({ compact = false }) {
  const { title, intro, items } = DEPARTMENTS_SECTION;
  const maxWidth = compact ? "max-w-3xl" : "max-w-3xl";

  return (
    <section className="px-6 py-28 border-t border-helm-navy/[0.05]">
      <div className={`mx-auto ${maxWidth}`}>
        <motion.div variants={fade} initial="hidden" whileInView="show" viewport={{ once: true, margin: "-100px" }}>
          <div className="h-px w-10 bg-helm-navy/25 mb-6" aria-hidden />
          <h2 className="font-display text-4xl md:text-5xl font-medium tracking-tight leading-[1.1]">{title}</h2>
          <p className="mt-5 text-helm-slate leading-relaxed">{intro}</p>
        </motion.div>
        <div className="mt-14 border-t border-helm-navy/[0.06]">
          {items.map((dept, i) => (
            <motion.div
              key={dept.name}
              variants={fade}
              custom={i}
              initial="hidden"
              whileInView="show"
              viewport={{ once: true, margin: "-40px" }}
              className="grid sm:grid-cols-[9rem_1fr] gap-2 sm:gap-8 py-6 border-b border-helm-navy/[0.06]"
            >
              <h3 className="font-display text-base text-helm-navy tracking-tight pt-0.5">{dept.name}</h3>
              <p className="text-sm text-helm-slate leading-relaxed">{dept.body}</p>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
