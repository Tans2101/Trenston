import { useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Activity, Check, Factory, Radar, TrendingUp, Users } from "lucide-react";
import FeatureShowcase from "@/components/marketing/FeatureShowcase";
import DepartmentsShowcase from "@/components/marketing/DepartmentsShowcase";
import IntegrationsShowcase from "@/components/marketing/IntegrationsShowcase";
import {
  CtaBand,
  Eyebrow,
  MkButton,
  MkLink,
  MkPage,
  PageHero,
  Reveal,
  SectionHeader,
  ease,
} from "@/components/marketing/mk";
import { useMarketingAuth } from "@/hooks/useMarketingAuth";
import { CATEGORY, FEATURE_CATEGORIES, FEATURE_MODULES, PLANS, PRO_FEATURES, TAGLINE } from "@/lib/marketingCopy";
import { cn } from "@/lib/utils";

const CATEGORY_ICONS = {
  intelligence: Radar,
  finance: TrendingUp,
  operations: Factory,
  people: Users,
};

/** Illustrative briefing lines (same sample data the page has always used). */
const HERO_LINES = [
  "Sales: $3.0M confirmed · $5.0M target · gap $2.0M",
  "Procurement: 4 orders late · spend $184k this month",
  "Production: today’s output 820 / 1,000 units",
  "Maintenance: 2 spares low · overhead over budget",
];

const STARTER_PLAN = PLANS.find((p) => p.id === "starter");

function BriefingTicker() {
  const [idx, setIdx] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setIdx((i) => (i + 1) % HERO_LINES.length), 3200);
    return () => clearInterval(t);
  }, []);
  return (
    <div className="border border-white/15 bg-mk-ink/80 p-6 backdrop-blur-sm">
      <div className="flex items-center justify-between">
        <p className="flex items-center gap-2.5 text-xs font-semibold uppercase tracking-[0.16em] text-mk-gray-dark">
          <span className="mk-live-dot" aria-hidden />
          From a morning Briefing
        </p>
        <span className="font-mono text-[11px] text-mk-gray-dark">
          {String(idx + 1).padStart(2, "0")} / {String(HERO_LINES.length).padStart(2, "0")}
        </span>
      </div>
      <div className="relative mt-6 min-h-[4.5rem]">
        <AnimatePresence mode="wait">
          <motion.p
            key={idx}
            initial={{ opacity: 0, y: 10, filter: "blur(4px)" }}
            animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
            exit={{ opacity: 0, y: -10, filter: "blur(4px)" }}
            transition={{ duration: 0.45, ease }}
            className="font-mono text-base leading-relaxed text-white md:text-lg"
          >
            {HERO_LINES[idx]}
          </motion.p>
        </AnimatePresence>
      </div>
      <div className="mt-6 flex gap-1.5" aria-hidden>
        {HERO_LINES.map((_, i) => (
          <span key={i} className="h-0.5 flex-1 overflow-hidden bg-white/15">
            {i === idx && (
              <motion.span
                className="block h-full bg-white"
                initial={{ width: "0%" }}
                animate={{ width: "100%" }}
                transition={{ duration: 3.2, ease: "linear" }}
              />
            )}
            {i < idx && <span className="block h-full w-full bg-white/60" />}
          </span>
        ))}
      </div>
      <p className="mt-5 font-mono text-[11px] tracking-wide text-mk-gray-dark">
        4 departments · 1 daily briefing · 0 spreadsheets
      </p>
    </div>
  );
}

export default function Features() {
  const { authed, enter } = useMarketingAuth();
  const [activeCat, setActiveCat] = useState(FEATURE_CATEGORIES[0]?.id || "intelligence");

  const modulesByTitle = useMemo(() => Object.fromEntries(FEATURE_MODULES.map((m) => [m.title, m])), []);

  useEffect(() => { window.scrollTo(0, 0); }, []);

  const activeCategory = FEATURE_CATEGORIES.find((c) => c.id === activeCat) || FEATURE_CATEGORIES[0];
  const ActiveIcon = CATEGORY_ICONS[activeCategory?.id] || Activity;
  const modules = (activeCategory?.modules || []).map((t) => modulesByTitle[t]).filter(Boolean);

  return (
    <MkPage authed={authed} onEnter={enter} active="/features">
      <PageHero
        eyebrow={CATEGORY}
        lines={["Everything", "in the cockpit."]}
        sub="Briefing, decisions, departments, and the rest of the cockpit, each designed to answer a specific leadership question: what changed, what to decide, what to delegate, and whether it landed."
        aside={<BriefingTicker />}
      >
        <div className="flex flex-wrap gap-3">
          <MkButton variant="light" onClick={enter}>{authed ? "Open your cockpit" : "Get started free"}</MkButton>
          <MkButton variant="outline-light" to="/pricing">View pricing</MkButton>
        </div>
      </PageHero>

      {/* Category tabs */}
      <nav aria-label="Feature categories" className="sticky top-16 z-30 border-b border-mk-line bg-white">
        <div className="mx-auto max-w-7xl overflow-x-auto px-6">
          <div className="flex gap-8" role="tablist">
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
                  data-testid={`showcase-tab-${cat.id}`}
                  onClick={() => setActiveCat(cat.id)}
                  className={cn(
                    "relative flex shrink-0 items-center gap-2 py-5 text-sm font-semibold transition-colors",
                    active ? "text-mk-black" : "text-mk-gray hover:text-mk-black",
                  )}
                >
                  <Icon className={cn("h-4 w-4", active ? "text-mk-navy" : "")} aria-hidden />
                  {cat.label}
                  {active && (
                    <motion.span
                      layoutId="features-tab-underline"
                      className="absolute inset-x-0 bottom-0 h-[3px] bg-mk-navy"
                      transition={{ duration: 0.45, ease }}
                    />
                  )}
                </button>
              );
            })}
          </div>
        </div>
      </nav>

      {activeCategory && (
        <section
          id={`features-panel-${activeCategory.id}`}
          role="tabpanel"
          aria-labelledby={`features-tab-${activeCategory.id}`}
          className="bg-white px-6 py-20 md:py-24"
        >
          <div className="mx-auto max-w-7xl">
            <AnimatePresence mode="wait">
              <motion.div
                key={activeCategory.id}
                initial={{ opacity: 0, y: 18 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -12 }}
                transition={{ duration: 0.45, ease }}
              >
                <div className="grid items-center gap-14 lg:grid-cols-[0.9fr_1.1fr]">
                  <div>
                    <span className="inline-flex h-12 w-12 items-center justify-center bg-mk-navy text-white">
                      <ActiveIcon className="h-5 w-5" aria-hidden />
                    </span>
                    <h2 className="mt-8 text-4xl font-semibold leading-[1.02] tracking-[-0.035em] md:text-5xl">
                      {activeCategory.label}
                    </h2>
                    <p className="mt-5 text-lg leading-relaxed text-mk-gray">{activeCategory.intro}</p>
                    <ul className="mt-10 space-y-6">
                      {modules.slice(0, 3).map((mod) => (
                        <li key={mod.title} className="border-l-2 border-mk-navy pl-5">
                          <p className="font-semibold tracking-tight text-mk-black">{mod.ceoValue}</p>
                          <p className="mt-1 text-sm leading-relaxed text-mk-gray">{mod.body}</p>
                        </li>
                      ))}
                    </ul>
                  </div>
                  <FeatureShowcase categoryId={activeCategory.id} />
                </div>

                <div className="mt-20 grid gap-5 md:grid-cols-2">
                  {modules.map((mod, i) => (
                    <motion.article
                      key={mod.title}
                      initial={{ opacity: 0, y: 20 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ duration: 0.5, ease, delay: 0.1 + i * 0.06 }}
                      className="mk-card group flex flex-col p-7 md:p-8"
                    >
                      <div className="flex items-center justify-between">
                        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-mk-navy">{mod.title}</p>
                        <span className="font-mono text-xs text-mk-gray">{String(i + 1).padStart(2, "0")}</span>
                      </div>
                      <h3 className="mt-5 text-2xl font-semibold leading-snug tracking-tight text-mk-black">{mod.ceoValue}</h3>
                      <p className="mt-3 leading-relaxed text-mk-gray">{mod.body}</p>
                      {mod.example && (
                        <p className="mt-6 border-t border-mk-line pt-5 text-sm italic leading-relaxed text-mk-gray">
                          {mod.example}
                        </p>
                      )}
                      {mod.link ? (
                        <MkLink to={mod.link.to} className="mt-5 self-start text-mk-navy">{mod.link.label}</MkLink>
                      ) : null}
                    </motion.article>
                  ))}
                </div>
              </motion.div>
            </AnimatePresence>
          </div>
        </section>
      )}

      {/* Included on Starter — black band */}
      <section className="bg-mk-black px-6 py-24 text-white md:py-28">
        <div className="mx-auto grid max-w-7xl gap-14 lg:grid-cols-[0.8fr_1.2fr]">
          <Reveal>
            <Eyebrow dark>Included on {STARTER_PLAN?.label || "Starter"}</Eyebrow>
            <p className="mt-6 text-7xl font-semibold tracking-[-0.05em]">
              ${STARTER_PLAN?.price}
              <span className="text-2xl font-normal text-mk-gray-dark">/mo</span>
            </p>
            <p className="mt-5 max-w-sm leading-relaxed text-mk-gray-dark">
              What you get on the {STARTER_PLAN?.label || "Starter"} plan, with a {STARTER_PLAN?.trialDays}-day free trial.
            </p>
            <MkLink to="/pricing" className="mt-8 text-white">Compare Free, Growth, and Business</MkLink>
          </Reveal>
          <ul className="grid gap-px self-start border border-white/15 bg-white/15 sm:grid-cols-2">
            {PRO_FEATURES.map((f, i) => (
              <Reveal as="li" key={f} i={i % 2} className="flex items-start gap-3 bg-mk-black p-6">
                <span className="flex h-6 w-6 shrink-0 items-center justify-center bg-white text-mk-black">
                  <Check className="h-3.5 w-3.5" aria-hidden />
                </span>
                <span className="leading-relaxed">{f}</span>
              </Reveal>
            ))}
          </ul>
        </div>
      </section>

      <DepartmentsShowcase compact />

      <IntegrationsShowcase compact />

      <section className="border-t border-mk-line bg-white px-6 py-16">
        <SectionHeader
          className="mx-auto max-w-7xl"
          eyebrow="No roadmap items"
          title="Everything on this page is shipping in the product today."
          intro="Free to start. Full cockpit on every plan."
        />
      </section>

      <CtaBand
        title={TAGLINE}
        sub="Open one place and see what the business is actually saying today."
        authed={authed}
        onEnter={enter}
        secondary={<MkButton variant="outline-light" to="/pricing">View pricing</MkButton>}
      />
    </MkPage>
  );
}
