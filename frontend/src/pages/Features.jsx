import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { motion, AnimatePresence } from "motion/react";
import {
  Activity,
  ArrowRight,
  Check,
  Factory,
  Radar,
  TrendingUp,
  Users,
} from "lucide-react";
import MarketingNav from "@/components/marketing/MarketingNav";
import MarketingFooter from "@/components/marketing/MarketingFooter";
import ProductScreens from "@/components/marketing/ProductScreens";
import DepartmentsShowcase from "@/components/marketing/DepartmentsShowcase";
import { useMarketingAuth } from "@/hooks/useMarketingAuth";
import { CATEGORY, FEATURE_CATEGORIES, FEATURE_MODULES, PLANS, PRO_FEATURES, TAGLINE } from "@/lib/marketingCopy";
import IntegrationsShowcase from "@/components/marketing/IntegrationsShowcase";
import { cn } from "@/lib/utils";

const ease = [0.16, 1, 0.3, 1];
const fade = {
  hidden: { opacity: 0, y: 20 },
  show: (i = 0) => ({ opacity: 1, y: 0, transition: { duration: 0.7, ease, delay: i * 0.06 } }),
};

const CATEGORY_ICONS = {
  intelligence: Radar,
  finance: TrendingUp,
  operations: Factory,
  people: Users,
};

const HERO_LINES = [
  "Sales: $3.0M confirmed · $5.0M target · gap $2.0M",
  "Procurement: 4 orders late · spend $184k this month",
  "Production: today’s output 820 / 1,000 units",
  "Maintenance: 2 spares low · overhead over budget",
];

const STARTER_PLAN = PLANS.find((p) => p.id === "starter");

export default function Features() {
  const { authed, enter } = useMarketingAuth();
  const [activeCat, setActiveCat] = useState(FEATURE_CATEGORIES[0]?.id || "intelligence");
  const [heroIdx, setHeroIdx] = useState(0);

  const modulesByTitle = useMemo(
    () => Object.fromEntries(FEATURE_MODULES.map((m) => [m.title, m])),
    [],
  );

  useEffect(() => { window.scrollTo(0, 0); }, []);

  useEffect(() => {
    const t = setInterval(() => {
      setHeroIdx((i) => (i + 1) % HERO_LINES.length);
    }, 3200);
    return () => clearInterval(t);
  }, []);

  const activeCategory = FEATURE_CATEGORIES.find((c) => c.id === activeCat) || FEATURE_CATEGORIES[0];
  const ActiveIcon = CATEGORY_ICONS[activeCategory?.id] || Activity;

  const selectCategory = (id) => {
    setActiveCat(id);
  };

  return (
    <div className="min-h-screen bg-helm-cream text-helm-navy overflow-x-hidden">
      <MarketingNav authed={authed} onEnter={enter} active="/features" />

      <section className="px-6 pt-36 md:pt-48 pb-16">
        <div className="mx-auto max-w-3xl">
          <motion.p variants={fade} initial="hidden" animate="show" custom={0}
            className="font-mono text-xs uppercase tracking-[0.3em] text-helm-slate">{CATEGORY}</motion.p>
          <motion.h1 variants={fade} initial="hidden" animate="show" custom={1}
            className="font-display mt-8 text-5xl md:text-6xl font-medium tracking-[-0.03em] leading-[1.05]">
            Everything in the cockpit
          </motion.h1>
          <motion.p variants={fade} initial="hidden" animate="show" custom={2}
            className="mt-6 text-lg text-helm-slate leading-relaxed">
            Briefing, decisions, departments, and the rest of the cockpit,
            each designed to answer a specific leadership question:
            what changed, what to decide, what to delegate, and whether it landed.
          </motion.p>

          <motion.div
            variants={fade}
            initial="hidden"
            animate="show"
            custom={3}
            className="mt-10 rounded-md border border-helm-navy/[0.08] bg-helm-cream/[0.02] px-4 py-4 md:px-5"
          >
            <div className="flex items-center gap-2 mb-3">
              <Activity className="w-3.5 h-3.5 text-helm-gold" aria-hidden />
              <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-helm-slate">
                From a morning Briefing
              </p>
            </div>
            <div className="relative min-h-[3.25rem]">
              <AnimatePresence mode="wait">
                <motion.p
                  key={heroIdx}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -8 }}
                  transition={{ duration: 0.35, ease }}
                  className="font-mono text-sm md:text-[15px] text-helm-navy leading-relaxed"
                >
                  {HERO_LINES[heroIdx]}
                </motion.p>
              </AnimatePresence>
            </div>
            <p className="mt-4 font-mono text-[11px] text-helm-slate tracking-wide">
              4 departments · 1 daily briefing · 0 spreadsheets
            </p>
          </motion.div>
        </div>
      </section>

      <section className="px-6 pb-20">
        <div className="mx-auto max-w-6xl">
          <motion.div variants={fade} initial="hidden" whileInView="show" viewport={{ once: true }}>
            <div className="h-px w-10 bg-helm-gold mb-6" aria-hidden />
            <h2 className="font-display text-3xl md:text-4xl font-medium tracking-tight max-w-xl leading-tight">
              Production, Procurement, and Decision Center as they appear in Trenston.
            </h2>
          </motion.div>
          <div className="mt-12">
            <ProductScreens />
          </div>
        </div>
      </section>

      <section className="px-6 pb-16 border-t border-helm-navy/[0.05] pt-16">
        <div className="mx-auto max-w-6xl">
          <div className="h-px w-10 bg-helm-gold mb-6" aria-hidden />
          <p className="font-mono text-[10px] uppercase tracking-[0.25em] text-helm-slate mb-2">
            Included on Starter
          </p>
          <p className="text-sm text-helm-slate mb-6 max-w-xl">
            What you get on the {STARTER_PLAN?.label || "Starter"} plan
            {STARTER_PLAN?.price != null ? ` ($${STARTER_PLAN.price}/mo)` : ""}.
            {" "}
            <Link to="/pricing" className="text-helm-navy hover:text-helm-gold transition-colors">
              Compare Free, Growth, and Business →
            </Link>
          </p>
          <ul className="grid sm:grid-cols-2 gap-x-8 gap-y-3">
            {PRO_FEATURES.map((f) => (
              <li key={f} className="flex items-start gap-2.5 text-sm text-helm-navy/85 border-b border-helm-navy/[0.06] pb-3">
                <Check className="w-3.5 h-3.5 text-helm-gold shrink-0 mt-0.5" aria-hidden />
                <span>{f}</span>
              </li>
            ))}
          </ul>
        </div>
      </section>

      <nav
        aria-label="Feature categories"
        className="sticky top-16 z-30 border-y border-helm-navy/[0.06] bg-helm-cream/90 backdrop-blur-md"
      >
        <div className="mx-auto max-w-6xl px-4 md:px-6">
          <div className="flex gap-1 overflow-x-auto scrollbar-none py-1 -mx-1 px-1" role="tablist">
            {FEATURE_CATEGORIES.map((cat) => {
              const Icon = CATEGORY_ICONS[cat.id] || Activity;
              const active = activeCat === cat.id;
              return (
                <button
                  key={cat.id}
                  type="button"
                  role="tab"
                  aria-selected={active}
                  id={`features-tab-${cat.id}`}
                  aria-controls={`features-panel-${cat.id}`}
                  onClick={() => selectCategory(cat.id)}
                  className={cn(
                    "shrink-0 inline-flex items-center gap-2 rounded-md px-3 py-2.5 text-left border-b-2 transition-colors",
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
        </div>
      </nav>

      {activeCategory && (
        <section
          key={activeCategory.id}
          id={`features-panel-${activeCategory.id}`}
          role="tabpanel"
          aria-labelledby={`features-tab-${activeCategory.id}`}
          className="px-6 py-16 md:py-20 border-t border-helm-navy/[0.05]"
        >
          <div className="mx-auto max-w-6xl">
            <motion.div
              key={`head-${activeCategory.id}`}
              variants={fade}
              initial="hidden"
              animate="show"
              className="mb-10 md:mb-12 max-w-2xl"
            >
              <ActiveIcon className="w-8 h-8 text-helm-gold mb-5" aria-hidden />
              <h2 className="font-display text-3xl md:text-4xl font-medium tracking-tight text-helm-navy">
                {activeCategory.label}
              </h2>
              <p className="mt-3 text-helm-slate text-sm md:text-base leading-relaxed">{activeCategory.intro}</p>
            </motion.div>

            <div className="grid md:grid-cols-2 gap-4 md:gap-5">
              {activeCategory.modules.map((title, i) => {
                const mod = modulesByTitle[title];
                if (!mod) return null;
                return (
                  <motion.article
                    key={mod.title}
                    variants={fade}
                    custom={i}
                    initial="hidden"
                    animate="show"
                    className="group rounded-md border border-helm-navy/[0.08] bg-helm-cream/[0.015] p-5 md:p-6 transition-all duration-300 hover:border-helm-gold/30 hover:-translate-y-0.5"
                  >
                    <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-helm-slate">
                      {mod.title}
                    </p>
                    <h3 className="font-display mt-3 text-xl md:text-2xl tracking-tight text-helm-navy leading-snug">
                      {mod.ceoValue}
                    </h3>
                    <p className="mt-3 text-sm text-helm-slate leading-relaxed">{mod.body}</p>
                    {mod.link ? (
                      <p className="mt-3">
                        <Link
                          to={mod.link.to}
                          className="text-sm text-helm-navy hover:text-helm-gold transition-colors"
                        >
                          {mod.link.label} →
                        </Link>
                      </p>
                    ) : null}
                    <p className="mt-4 text-sm text-helm-slate/90 leading-relaxed pl-3 border-l border-helm-gold/25">
                      {mod.example}
                    </p>
                  </motion.article>
                );
              })}
            </div>
          </div>
        </section>
      )}

      <DepartmentsShowcase compact />

      <IntegrationsShowcase compact />

      <section className="px-6 py-24 border-t border-helm-navy/[0.05]">
        <div className="mx-auto max-w-2xl text-center">
          <div className="mx-auto h-px w-10 bg-helm-gold mb-8" aria-hidden />
          <p className="font-display text-3xl md:text-4xl font-medium tracking-tight text-helm-navy leading-tight">{TAGLINE}</p>
          <p className="mt-4 text-sm text-helm-slate">
            Everything below is shipping in the product today. Nothing on this page is a roadmap item.
          </p>
          <p className="mt-4 text-sm text-helm-slate">Free to start. Full cockpit on every plan.</p>
          <button type="button" onClick={enter}
            className="mt-10 group inline-flex items-center gap-2 rounded-md bg-helm-navy text-helm-cream font-medium px-6 py-3 hover:bg-helm-gold transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-helm-gold">
            {authed ? "Open your cockpit" : "Get started with Trenston"}
            <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-1" />
          </button>
          <p className="mt-6 text-sm text-helm-slate flex flex-wrap items-center justify-center gap-x-5 gap-y-1">
            <Link to="/pricing" className="hover:text-helm-navy transition-colors">
              View pricing
            </Link>
            <Link to="/about" className="hover:text-helm-navy transition-colors">About Trenston</Link>
            <Link to="/integrations" className="hover:text-helm-navy transition-colors">Integrations</Link>
            <Link to="/security" className="hover:text-helm-navy transition-colors">Security</Link>
            <Link to="/changelog" className="hover:text-helm-navy transition-colors">Changelog</Link>
          </p>
        </div>
      </section>

      <MarketingFooter />
    </div>
  );
}
