import { useMemo, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Activity, Factory, Radar, TrendingUp, Users } from "lucide-react";
import LaptopMockup from "@/components/marketing/LaptopMockup";
import {
  ProductionScreen,
  ProcurementScreen,
  DecisionScreen,
  FinanceScreen,
  TeamScreen,
} from "@/components/marketing/ProductScreens";
import dashboardBriefing from "@/assets/marketing/dashboard-briefing.png";
import { FEATURE_CATEGORIES, FEATURE_MODULES } from "@/lib/marketingCopy";
import { cn } from "@/lib/utils";

const ease = [0.16, 1, 0.3, 1];

const CATEGORY_ICONS = {
  intelligence: Radar,
  finance: TrendingUp,
  operations: Factory,
  people: Users,
};

/**
 * Only "Executive intelligence" has a real product screenshot (the same
 * Briefing capture used on the homepage). The other tabs compose the same
 * real cockpit-surface fragments used elsewhere on the site (ProductScreens)
 * rather than a fabricated full-dashboard photo — see the homepage laptop
 * mockup history for why a fake "dashboard" mockup isn't the right call here.
 */
const TAB_PANELS = {
  intelligence: { kind: "photo", src: dashboardBriefing, alt: "The Briefing screen in Trenston" },
  finance: { kind: "fragments", screens: [FinanceScreen, DecisionScreen] },
  operations: { kind: "fragments", screens: [ProductionScreen, ProcurementScreen] },
  people: { kind: "fragments", screens: [TeamScreen] },
};

export default function FeatureShowcase() {
  const [activeId, setActiveId] = useState(FEATURE_CATEGORIES[0]?.id || "intelligence");

  const modulesByTitle = useMemo(
    () => Object.fromEntries(FEATURE_MODULES.map((m) => [m.title, m])),
    [],
  );

  const activeCategory = FEATURE_CATEGORIES.find((c) => c.id === activeId) || FEATURE_CATEGORIES[0];
  const panel = TAB_PANELS[activeCategory?.id] || TAB_PANELS.intelligence;
  const highlightTitles = (activeCategory?.modules || []).slice(0, 3);

  return (
    <div data-testid="feature-showcase">
      {/* Tabs */}
      <div className="flex flex-wrap gap-1" role="tablist" aria-label="Feature showcase">
        {FEATURE_CATEGORIES.map((cat) => {
          const Icon = CATEGORY_ICONS[cat.id] || Activity;
          const active = activeId === cat.id;
          return (
            <button
              key={cat.id}
              type="button"
              role="tab"
              aria-selected={active}
              id={`showcase-tab-${cat.id}`}
              aria-controls="showcase-panel"
              onClick={() => setActiveId(cat.id)}
              data-testid={`showcase-tab-${cat.id}`}
              className={cn(
                "inline-flex items-center gap-2 rounded-md px-3 py-2.5 text-left border-b-2 transition-colors",
                active
                  ? "border-helm-gold text-helm-navy"
                  : "border-transparent text-helm-slate hover:text-helm-navy",
              )}
            >
              <Icon className={cn("w-3.5 h-3.5", active ? "text-helm-gold" : "text-helm-slate")} aria-hidden />
              <span className="font-mono text-[10px] uppercase tracking-[0.14em] whitespace-nowrap">
                {cat.label}
              </span>
            </button>
          );
        })}
      </div>

      {/* Main display + text column */}
      <div id="showcase-panel" role="tabpanel" className="mt-8 grid lg:grid-cols-[1.35fr_1fr] gap-8 lg:gap-10 items-center">
        <AnimatePresence mode="wait">
          <motion.div
            key={activeCategory.id}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -12 }}
            transition={{ duration: 0.4, ease }}
          >
            {panel.kind === "photo" ? (
              <LaptopMockup src={panel.src} alt={panel.alt} />
            ) : (
              <LaptopMockup>
                <div
                  className={cn(
                    "grid gap-3 w-full",
                    panel.screens.length > 1 ? "grid-cols-2" : "max-w-sm mx-auto",
                  )}
                >
                  {panel.screens.map((Screen, i) => (
                    <Screen key={i} />
                  ))}
                </div>
              </LaptopMockup>
            )}
          </motion.div>
        </AnimatePresence>

        <AnimatePresence mode="wait">
          <motion.div
            key={`text-${activeCategory.id}`}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -12 }}
            transition={{ duration: 0.4, ease, delay: 0.05 }}
            className="space-y-6"
          >
            <p className="text-sm text-helm-navy/70 leading-relaxed">{activeCategory.intro}</p>
            <ul className="space-y-4">
              {highlightTitles.map((title) => {
                const mod = modulesByTitle[title];
                if (!mod) return null;
                return (
                  <li key={title} className="border-l-2 border-helm-gold/40 pl-4">
                    <p className="font-display text-base text-helm-navy tracking-tight">{mod.ceoValue}</p>
                    <p className="mt-1 text-sm text-helm-navy/70 leading-relaxed">{mod.body}</p>
                  </li>
                );
              })}
            </ul>
          </motion.div>
        </AnimatePresence>
      </div>
    </div>
  );
}
