import { useEffect, useRef } from "react";
import { useLocation } from "react-router-dom";
import { motion, useScroll, useTransform } from "motion/react";
import LaptopMockup from "@/components/marketing/LaptopMockup";
import dashboardBriefing from "@/assets/marketing/dashboard-briefing.png";
import { AskScreen, DecisionScreen, PackScreen } from "@/components/marketing/ProductScreens";
import DepartmentsShowcase from "@/components/marketing/DepartmentsShowcase";
import IntegrationsShowcase from "@/components/marketing/IntegrationsShowcase";
import PlanCards from "@/components/marketing/PlanCards";
import {
  CtaBand,
  DISPLAY,
  DrawLine,
  Eyebrow,
  MkAccordion,
  MkButton,
  MkLink,
  MkPage,
  Reveal,
  RuledItem,
  SectionHeader,
  SplitHeadline,
  VisualPanel,
  ease,
} from "@/components/marketing/mk";
import { useMarketingAuth } from "@/hooks/useMarketingAuth";
import {
  AUDIENCE,
  CATEGORY,
  CEO_DAY,
  FOUNDER_NAME,
  FOUNDER_NOTE,
  FOUNDER_ROLE,
  HERO_OUTCOME,
  HOME_FAQ,
  HOW_IT_WORKS,
  PRODUCT_FACTS,
  TAGLINE,
} from "@/lib/marketingCopy";
import { cn } from "@/lib/utils";

/** CEO_DAY has no visual field in marketingCopy.js (it's also read by
 * marketingClaimsVerification.test.js) — map each to a real product surface. */
const CEO_DAY_VISUALS = {
  Briefing: () => <LaptopMockup src={dashboardBriefing} alt="The Briefing screen in Trenston" />,
  "Decision Center": () => <div className="mx-auto max-w-md origin-center lg:scale-[1.15]"><DecisionScreen /></div>,
  "Ask Trenston": () => <div className="mx-auto max-w-md origin-center lg:scale-[1.15]"><AskScreen /></div>,
  "CEO Pack": () => <div className="mx-auto max-w-md origin-center lg:scale-[1.15]"><PackScreen /></div>,
};

export default function Landing() {
  const { authed, enter } = useMarketingAuth();
  const location = useLocation();
  const heroRef = useRef(null);
  const { scrollYProgress } = useScroll({ target: heroRef, offset: ["start start", "end start"] });
  const laptopY = useTransform(scrollYProgress, [0, 1], [0, 60]);

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
      {/* Hero — flat black, typography-led, real product screenshot */}
      <section ref={heroRef} className="bg-mk-black text-white">
        <div className="mx-auto grid max-w-7xl items-center gap-14 px-6 pb-20 pt-32 md:pt-40 lg:min-h-[88vh] lg:grid-cols-[1.05fr_1fr] lg:pb-24">
          <div>
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.6 }}>
              <Eyebrow dark>{CATEGORY}</Eyebrow>
            </motion.div>
            <SplitHeadline
              lines={[`${line1}.`, line2]}
              className={cn("mt-6 text-[3.1rem] leading-[1] sm:text-7xl lg:text-[4.4rem] xl:text-[5.25rem]", DISPLAY)}
            />
            <motion.p
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.7, ease, delay: 0.35 }}
              className="mt-8 max-w-xl text-lg leading-relaxed text-mk-gray-dark md:text-xl"
            >
              {HERO_OUTCOME}
            </motion.p>
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.7, ease, delay: 0.45 }}
              className="mt-10 flex flex-wrap items-center gap-x-8 gap-y-4"
            >
              <MkButton variant="light" onClick={enter} data-testid="hero-cta-btn">
                {authed ? "Open your cockpit" : "Start free"}
              </MkButton>
              <MkLink href="#how" className="text-base text-white">See how it works</MkLink>
            </motion.div>
            <motion.p
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.7, delay: 0.6 }}
              className="mt-12 max-w-md text-sm leading-relaxed text-mk-gray-dark"
            >
              {AUDIENCE}
            </motion.p>
          </div>

          <motion.div
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 1, ease, delay: 0.2 }}
            style={{ y: laptopY }}
            className="lg:-mr-10 xl:-mr-20"
          >
            <LaptopMockup
              src={dashboardBriefing}
              alt="The Briefing screen in Trenston, showing revenue, burn, runway and a revenue-by-month chart"
            />
          </motion.div>
        </div>
      </section>

      {/* At a glance — large left-aligned statements, no boxes */}
      <section className="border-b border-mk-line bg-white px-6 py-20">
        <div className="mx-auto grid max-w-7xl gap-10 sm:grid-cols-2 lg:grid-cols-4">
          {PRODUCT_FACTS.map((s, i) => (
            <Reveal key={s.l} i={i}>
              <p className={cn("text-4xl text-mk-black", DISPLAY)}>{s.v}</p>
              <p className="mt-3 max-w-[16rem] text-sm leading-relaxed text-mk-gray">{s.l}</p>
            </Reveal>
          ))}
        </div>
      </section>

      {/* The cockpit — alternating image + text rows */}
      <section className="bg-white px-6 py-24 md:py-28">
        <div className="mx-auto max-w-7xl">
          <SectionHeader
            eyebrow="The cockpit"
            title="What CEOs open Trenston for."
            action={<MkLink to="/features" className="text-mk-navy">See all features</MkLink>}
          />
          <div className="mt-16 space-y-20 md:space-y-28">
            {CEO_DAY.map((step, i) => {
              const Visual = CEO_DAY_VISUALS[step.title];
              const flip = i % 2 === 1;
              return (
                <div key={step.title} className="grid items-center gap-10 lg:grid-cols-2 lg:gap-16">
                  <Reveal className={cn(flip && "lg:order-2")}>
                    <VisualPanel className="min-h-[18rem] lg:min-h-[26rem]">{Visual ? <Visual /> : null}</VisualPanel>
                  </Reveal>
                  <Reveal i={1} className={cn("max-w-lg", flip && "lg:order-1")}>
                    <p className="font-mono text-sm text-mk-gray">0{i + 1}</p>
                    <DrawLine className="mt-4 bg-mk-black" />
                    <h3 className={cn("mt-8 text-4xl md:text-5xl", DISPLAY)}>{step.title}</h3>
                    <p className="mt-5 text-lg leading-relaxed text-mk-gray">{step.body}</p>
                    <MkLink to="/features" className="mt-8 text-mk-navy">Explore {step.title}</MkLink>
                  </Reveal>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* How it works — flat black band, ruled columns */}
      <section id="how" className="scroll-mt-16 bg-mk-black px-6 py-24 text-white md:py-28">
        <div className="mx-auto max-w-7xl">
          <SectionHeader dark eyebrow="How it works" title="How Trenston fits together." />
          <div className="mt-16 grid gap-12 md:grid-cols-3 md:gap-10">
            {HOW_IT_WORKS.map((s, i) => (
              <RuledItem key={s.n} dark i={i} index={Number(s.n)} title={s.title} body={s.body} />
            ))}
          </div>
        </div>
      </section>

      <IntegrationsShowcase />

      <DepartmentsShowcase />

      {/* Founder note — BlackRock-style letter callout */}
      <section className="bg-white px-6 py-24 md:py-28">
        <Reveal className="mx-auto grid max-w-7xl gap-10 border-l-4 border-mk-navy bg-mk-mist p-8 md:grid-cols-[0.6fr_1.4fr] md:p-14">
          <div>
            <Eyebrow>A note from the founder</Eyebrow>
            <p className="mt-6 text-lg font-semibold">{FOUNDER_NAME}</p>
            <p className="text-sm text-mk-gray">{FOUNDER_ROLE}</p>
          </div>
          <div>
            <p className={cn("text-2xl leading-snug md:text-3xl", DISPLAY)}>{FOUNDER_NOTE}</p>
            <MkLink to="/about" className="mt-8 text-mk-navy">Read our story</MkLink>
          </div>
        </Reveal>
      </section>

      {/* Pricing */}
      <section id="pricing" className="scroll-mt-16 border-t border-mk-line bg-white px-6 py-24 md:py-28">
        <div className="mx-auto max-w-7xl">
          <SectionHeader
            eyebrow="Pricing"
            title="Plans that scale with you."
            intro="Start free. Paid plans include a 7-day free trial. Cancel anytime."
            action={<MkLink to="/pricing" className="text-mk-navy">Full pricing page</MkLink>}
          />
          <div className="mt-14">
            <PlanCards authed={authed} onEnter={enter} ctaTestIdPrefix="pricing-cta" renewalTestIdPrefix="pricing-renewal" />
          </div>

          <div className="mt-28 grid gap-12 lg:grid-cols-[0.8fr_1.2fr]">
            <Reveal>
              <Eyebrow>Questions</Eyebrow>
              <h2 className={cn("mt-4 text-4xl leading-[1.05]", DISPLAY)}>Common questions.</h2>
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
