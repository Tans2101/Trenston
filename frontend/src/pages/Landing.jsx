import { useEffect, useRef } from "react";
import { useLocation } from "react-router-dom";
import { motion, useScroll, useTransform } from "motion/react";
import { ArrowUpRight, Compass, FileText, ListChecks, Sparkles } from "lucide-react";
import LaptopMockup from "@/components/marketing/LaptopMockup";
import dashboardBriefing from "@/assets/marketing/dashboard-briefing.png";
import ProductScreens from "@/components/marketing/ProductScreens";
import DepartmentsShowcase from "@/components/marketing/DepartmentsShowcase";
import IntegrationsShowcase from "@/components/marketing/IntegrationsShowcase";
import PlanCards from "@/components/marketing/PlanCards";
import {
  CtaBand,
  DarkBackdrop,
  DrawLine,
  Eyebrow,
  Marquee,
  MkAccordion,
  MkButton,
  MkLink,
  MkPage,
  Reveal,
  SectionHeader,
  SplitHeadline,
  ease,
} from "@/components/marketing/mk";
import { useMarketingAuth } from "@/hooks/useMarketingAuth";
import {
  AUDIENCE,
  CATEGORY,
  CEO_DAY,
  FEATURE_HIGHLIGHTS,
  HERO_OUTCOME,
  HOME_FAQ,
  HOW_IT_WORKS,
  PRODUCT_FACTS,
  TAGLINE,
} from "@/lib/marketingCopy";

// CEO_DAY has no icon field in marketingCopy.js — map by title here rather
// than changing the shared data shape (it's also read by
// marketingClaimsVerification.test.js).
const CEO_DAY_ICONS = {
  Briefing: Compass,
  "Decision Center": ListChecks,
  "Ask Trenston": Sparkles,
  "CEO Pack": FileText,
};

/** Real module names only — the ticker is a list of what ships today. */
const MODULES = [
  "Briefing",
  "Decision Center",
  "Ask Trenston",
  "CEO Pack",
  "Financials & runway",
  "Production",
  "Procurement",
  "Sales",
  "Legal",
  "HR",
  "Maintenance",
];

export default function Landing() {
  const { authed, enter } = useMarketingAuth();
  const location = useLocation();
  const heroRef = useRef(null);
  const { scrollYProgress } = useScroll({ target: heroRef, offset: ["start start", "end start"] });
  const laptopY = useTransform(scrollYProgress, [0, 1], [0, 90]);
  const laptopRotate = useTransform(scrollYProgress, [0, 1], [0, -2]);

  useEffect(() => {
    const id = (location.hash || "").replace(/^#/, "");
    if (!id) {
      window.scrollTo(0, 0);
      return;
    }
    // Wait a frame so layout (and lazy sections) are ready after route entry.
    const t = window.setTimeout(() => {
      document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 50);
    return () => window.clearTimeout(t);
  }, [location.hash, location.pathname]);

  const [line1, line2] = TAGLINE.split(". ");

  return (
    <MkPage authed={authed} onEnter={enter} active={location.hash === "#pricing" ? "/#pricing" : "/"}>
      {/* Hero — black, typography-led, real product screenshot */}
      <section ref={heroRef} className="relative overflow-hidden bg-mk-black text-white">
        <DarkBackdrop />
        <div className="relative mx-auto grid max-w-7xl items-center gap-14 px-6 pb-20 pt-32 md:pt-40 lg:min-h-[92vh] lg:grid-cols-[1.05fr_1fr] lg:pb-24">
          <div>
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.6 }}>
              <Eyebrow dark>{CATEGORY}</Eyebrow>
            </motion.div>
            <SplitHeadline
              lines={[`${line1}.`, line2]}
              className="mt-8 text-[3.1rem] font-semibold leading-[0.95] tracking-[-0.045em] sm:text-7xl lg:text-[4.4rem] xl:text-[5.4rem]"
            />
            <motion.p
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.8, ease, delay: 0.45 }}
              className="mt-8 max-w-xl text-lg leading-relaxed text-mk-gray-dark md:text-xl"
            >
              {HERO_OUTCOME}
            </motion.p>
            <motion.div
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.8, ease, delay: 0.6 }}
              className="mt-10 flex flex-wrap gap-3"
            >
              <MkButton variant="light" onClick={enter} data-testid="hero-cta-btn">
                {authed ? "Open your cockpit" : "Start free"}
              </MkButton>
              <MkButton variant="outline-light" href="#how" arrow={false}>
                See how it works
              </MkButton>
            </motion.div>
            <motion.p
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.8, delay: 0.8 }}
              className="mt-10 max-w-md border-l border-white/20 pl-4 text-sm leading-relaxed text-mk-gray-dark"
            >
              {AUDIENCE}
            </motion.p>
          </div>

          <motion.div
            initial={{ opacity: 0, y: 40, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            transition={{ duration: 1.1, ease, delay: 0.3 }}
            style={{ y: laptopY, rotate: laptopRotate }}
            className="lg:-mr-10 xl:-mr-24"
          >
            <LaptopMockup
              src={dashboardBriefing}
              alt="The Briefing screen in Trenston, showing revenue, burn, runway and a revenue-by-month chart"
            />
          </motion.div>
        </div>
      </section>

      {/* Module ticker */}
      <div className="bg-mk-navy text-white">
        <Marquee items={MODULES} />
      </div>

      {/* At a glance */}
      <section className="bg-white px-6 py-20 md:py-24">
        <div className="mx-auto grid max-w-7xl gap-10 sm:grid-cols-2 lg:grid-cols-4">
          {PRODUCT_FACTS.map((s, i) => (
            <Reveal key={s.l} i={i}>
              <DrawLine className="bg-mk-black" />
              <p className="mt-6 text-3xl font-semibold tracking-[-0.03em] text-mk-black">{s.v}</p>
              <p className="mt-3 text-sm leading-relaxed text-mk-gray">{s.l}</p>
            </Reveal>
          ))}
        </div>
      </section>

      {/* What CEOs open Trenston for */}
      <section className="bg-white px-6 pb-24 md:pb-32">
        <div className="mx-auto max-w-7xl">
          <SectionHeader eyebrow="The cockpit" title="What CEOs open Trenston for." />
          <div className="mt-14 grid gap-5 md:grid-cols-2">
            {CEO_DAY.map((step, i) => {
              const Icon = CEO_DAY_ICONS[step.title] || Compass;
              return (
                <Reveal key={step.title} i={i % 2} className="mk-card group flex flex-col p-8 md:p-10">
                  <div className="flex items-start justify-between">
                    <span className="mk-icon-tile">
                      <Icon className="h-5 w-5" strokeWidth={1.75} aria-hidden />
                    </span>
                    <span className="font-mono text-sm text-mk-gray">0{i + 1}</span>
                  </div>
                  <h3 className="mt-8 text-2xl font-semibold tracking-tight text-mk-black">{step.title}</h3>
                  <p className="mt-3 max-w-md leading-relaxed text-mk-gray">{step.body}</p>
                  <ArrowUpRight
                    className="absolute bottom-8 right-8 h-5 w-5 text-mk-navy opacity-0 transition-all duration-500 group-hover:translate-x-1 group-hover:-translate-y-1 group-hover:opacity-100 md:bottom-10 md:right-10"
                    aria-hidden
                  />
                </Reveal>
              );
            })}
          </div>
        </div>
      </section>

      {/* How it works — black band */}
      <section id="how" className="relative scroll-mt-16 overflow-hidden bg-mk-black px-6 py-24 text-white md:py-32">
        <div className="relative mx-auto max-w-7xl">
          <SectionHeader dark eyebrow="How it works" title="How Trenston fits together." />
          <div className="relative mt-16">
            <DrawLine className="absolute left-0 right-0 top-[3.25rem] hidden bg-white/25 md:block" />
            <div className="grid gap-12 md:grid-cols-3 md:gap-10">
              {HOW_IT_WORKS.map((s, i) => (
                <Reveal key={s.n} i={i} className="relative">
                  <p className="text-7xl font-semibold leading-none tracking-[-0.05em] text-transparent [-webkit-text-stroke:1.5px_rgba(255,255,255,0.55)] md:text-8xl">
                    {s.n}
                  </p>
                  <span className="relative z-10 mt-6 block h-3 w-3 rotate-45 bg-mk-sky" aria-hidden />
                  <h3 className="mt-6 text-2xl font-semibold tracking-tight">{s.title}</h3>
                  <p className="mt-3 leading-relaxed text-mk-gray-dark">{s.body}</p>
                </Reveal>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* Product surfaces */}
      <section className="bg-mk-mist px-6 py-24 md:py-32">
        <div className="mx-auto max-w-7xl">
          <SectionHeader
            eyebrow="Product"
            title="Everything a CEO needs, nothing they do not."
            intro="Real surfaces from the cockpit, not illustrations."
            action={<MkLink to="/features" className="text-mk-navy">See all features</MkLink>}
          />
          <Reveal className="mt-14">
            <ProductScreens />
          </Reveal>
          <div className="mt-16 grid gap-10 sm:grid-cols-2 lg:grid-cols-4">
            {FEATURE_HIGHLIGHTS.map((f, i) => (
              <Reveal key={f.title} i={i}>
                <DrawLine className="bg-mk-navy" />
                <h3 className="mt-5 text-xl font-semibold tracking-tight text-mk-black">{f.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-mk-gray">{f.body}</p>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      <IntegrationsShowcase />

      <DepartmentsShowcase />

      {/* Pricing */}
      <section id="pricing" className="scroll-mt-16 bg-white px-6 py-24 md:py-32">
        <div className="mx-auto max-w-7xl">
          <SectionHeader
            eyebrow="Pricing"
            title="Plans that scale with you."
            intro="Start free. Paid plans include a 7-day free trial. Cancel anytime."
            action={<MkLink to="/pricing" className="text-mk-navy">Full pricing page</MkLink>}
          />
          <div className="mt-16">
            <PlanCards authed={authed} onEnter={enter} ctaTestIdPrefix="pricing-cta" renewalTestIdPrefix="pricing-renewal" />
          </div>

          <div className="mt-28 grid gap-12 lg:grid-cols-[0.8fr_1.2fr]">
            <Reveal>
              <Eyebrow>Questions</Eyebrow>
              <h2 className="mt-5 text-4xl font-semibold leading-[1.02] tracking-[-0.035em]">Common questions.</h2>
            </Reveal>
            <Reveal i={1}>
              <MkAccordion items={HOME_FAQ} idPrefix="home-faq" />
            </Reveal>
          </div>
        </div>
      </section>

      <CtaBand
        title={TAGLINE}
        sub="Quiet control for the owner everyone is counting on. Free to start, 7-day free trials, sign in with Google."
        authed={authed}
        onEnter={enter}
        secondary={<MkButton variant="outline-light" to="/features">Explore features</MkButton>}
      />
    </MkPage>
  );
}
