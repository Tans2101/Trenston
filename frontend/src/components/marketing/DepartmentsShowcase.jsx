import { motion } from "motion/react";
import { Package, Factory, Landmark, Briefcase, Scale, Users, Wrench, LayoutGrid } from "lucide-react";
import { DEPARTMENTS_SECTION } from "@/lib/marketingCopy";

const ease = [0.16, 1, 0.3, 1];
const fade = {
  hidden: { opacity: 0, y: 16 },
  show: (i = 0) => ({ opacity: 1, y: 0, transition: { duration: 0.65, ease, delay: i * 0.05 } }),
};

// DEPARTMENTS_SECTION items already carry an `icon` string (see
// marketingCopy.js) — map it to the matching lucide component here.
const DEPT_ICONS = {
  package: Package,
  factory: Factory,
  landmark: Landmark,
  briefcase: Briefcase,
  scale: Scale,
  users: Users,
  wrench: Wrench,
};

/** Department lanes — icon card grid. */
export default function DepartmentsShowcase({ compact = false }) {
  const { title, intro, items } = DEPARTMENTS_SECTION;

  return (
    <section className={`px-6 border-t border-helm-navy/[0.05] ${compact ? "py-12" : "py-16"}`}>
      <div className="mx-auto max-w-6xl">
        <motion.div variants={fade} initial="hidden" whileInView="show" viewport={{ once: true, margin: "-100px" }} className="max-w-2xl">
          <div className="h-px w-10 bg-helm-navy/25 mb-6" aria-hidden />
          <h2 className="font-display text-4xl md:text-5xl font-medium tracking-tight leading-[1.1]">{title}</h2>
          <p className="mt-5 text-helm-navy/70 leading-relaxed">{intro}</p>
        </motion.div>
        <div className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((dept, i) => {
            const Icon = DEPT_ICONS[dept.icon] || LayoutGrid;
            return (
              <motion.div
                key={dept.name}
                variants={fade}
                custom={i}
                initial="hidden"
                whileInView="show"
                viewport={{ once: true, margin: "-40px" }}
                className="rounded-lg border border-helm-navy/[0.08] p-6 transition-colors hover:border-helm-navy/20"
              >
                <Icon className="w-5 h-5 text-helm-navy/70" strokeWidth={1.75} aria-hidden />
                <h3 className="font-display mt-4 text-base text-helm-navy tracking-tight">{dept.name}</h3>
                <p className="mt-2 text-sm text-helm-navy/70 leading-relaxed">{dept.body}</p>
              </motion.div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
