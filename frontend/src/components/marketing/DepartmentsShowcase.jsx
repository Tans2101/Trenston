import { Package, Factory, Landmark, Briefcase, Scale, Users, Wrench, LayoutGrid } from "lucide-react";
import { DEPARTMENTS_SECTION } from "@/lib/marketingCopy";
import { Reveal, SectionHeader } from "@/components/marketing/mk";

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

/**
 * Decorative only — this is the logged-out marketing page, not the real
 * per-workspace department toggle (that lives in Settings once you're
 * signed in). Shown "on" because every lane here ships in the product today.
 */
function EnabledToggle() {
  return (
    <span className="relative inline-flex h-5 w-9 shrink-0 items-center rounded-full bg-mk-black" aria-hidden title="Available to enable for your workspace">
      <span className="absolute right-0.5 h-4 w-4 rounded-full bg-white" />
    </span>
  );
}

/** Department lanes — ruled columns on a mist band. */
export default function DepartmentsShowcase({ compact = false }) {
  const { label, title, intro, items } = DEPARTMENTS_SECTION;

  return (
    <section className={`bg-mk-mist px-6 ${compact ? "py-20" : "py-24 md:py-28"}`}>
      <div className="mx-auto max-w-7xl">
        <SectionHeader eyebrow={label || "Departments"} title={title} intro={intro} />
        <div className="mt-14 grid gap-x-8 gap-y-12 sm:grid-cols-2 lg:grid-cols-4">
          {items.map((dept, i) => {
            const Icon = DEPT_ICONS[dept.icon] || LayoutGrid;
            return (
              <Reveal key={dept.name} i={i % 4} className="mk-item group">
                <div className="flex items-center justify-between">
                  <Icon className="h-6 w-6 text-mk-navy" strokeWidth={1.5} aria-hidden />
                  <EnabledToggle />
                </div>
                <h3 className="mt-6 text-lg font-semibold tracking-tight text-mk-black">{dept.name}</h3>
                <p className="mt-2 text-sm leading-relaxed text-mk-gray">{dept.body}</p>
              </Reveal>
            );
          })}
        </div>
      </div>
    </section>
  );
}
