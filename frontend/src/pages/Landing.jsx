import { useEffect } from "react";
import { Link, useLocation } from "react-router-dom";
import { motion } from "motion/react";
import { ArrowRight, Check } from "lucide-react";
import MarketingNav from "@/components/marketing/MarketingNav";
import MarketingFooter from "@/components/marketing/MarketingFooter";
import ProductScreens from "@/components/marketing/ProductScreens";
import DepartmentsShowcase from "@/components/marketing/DepartmentsShowcase";
import IntegrationsShowcase from "@/components/marketing/IntegrationsShowcase";
import { useMarketingAuth } from "@/hooks/useMarketingAuth";
import {
  TAGLINE, CATEGORY, AUDIENCE, HERO_SUB,
  PLANS, PRODUCT_FACTS, HOW_IT_WORKS, FEATURE_HIGHLIGHTS, CEO_DAY, PRICING_FAQ,
  paidPlanRenewalDisclosure,
} from "@/lib/marketingCopy";

const ease = [0.16, 1, 0.3, 1];
const fade = {
  hidden: { opacity: 0, y: 20 },
  show: (i = 0) => ({ opacity: 1, y: 0, transition: { duration: 0.7, ease, delay: i * 0.08 } }),
};

function BriefingPreview() {
  return (
    <div className="relative">
      {/* Decorative depth layer */}
      <div
        aria-hidden
        className="absolute inset-0 translate-x-2 translate-y-3 rounded-lg border border-helm-cream/10 bg-helm-ink-card/80"
      />
      <div className="relative z-[1] rounded-lg border border-helm-navy/10 bg-helm-cream p-5 md:p-7 shadow-xl shadow-black/20">
        <div className="flex items-center justify-between border-b border-helm-navy/10 pb-3">
          <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-helm-slate">Briefing</p>
          <span className="text-[10px] text-helm-slate">Sample briefing</span>
        </div>
        <p className="font-display text-helm-navy text-2xl md:text-3xl font-medium mt-6 leading-snug tracking-tight">Welcome back, Alex.</p>
        <p className="text-helm-slate text-sm mt-3 leading-relaxed">Revenue is ahead of plan. Engineering capacity needs a decision today.</p>
        <div className="grid grid-cols-3 gap-3 mt-6 border-y border-helm-navy/10 py-4">
          {[
            ["Monthly revenue", "$248K", "Up $12K this month"],
            ["Cash runway", "17 months", "No change"],
            ["Monthly burn", "$182K", "Down $8K this month"],
          ].map(([l, v, change]) => (
            <div key={l}>
              <p className="text-[9px] font-mono uppercase tracking-wider text-helm-slate">{l}</p>
              <p className="font-mono text-helm-navy text-base mt-1 font-medium tabular-nums">{v}</p>
              <p className="mt-1 text-[10px] text-helm-slate">{change}</p>
            </div>
          ))}
        </div>
        <div className="mt-5">
          <div className="h-px w-8 bg-helm-gold mb-3" aria-hidden />
          <p className="font-mono text-[10px] uppercase tracking-wider text-helm-slate">One decision today</p>
          <p className="mt-2 text-sm text-helm-navy/85 leading-snug">Approve the $40K infrastructure reservation. It pays back in four months and cuts cloud spend by 18%.</p>
          <p className="mt-4 text-xs text-helm-slate">Review decision →</p>
        </div>
      </div>
    </div>
  );
}

export default function Landing() {
  const { authed, enter } = useMarketingAuth();
  const location = useLocation();

  useEffect(() => {
    const id = (location.hash || "").replace(/^#/, "");
    if (!id) {
      window.scrollTo(0, 0);
      return;
    }
    const scroll = () => {
      document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
    };
    // Wait a frame so layout (and lazy sections) are ready after route entry.
    const t = window.setTimeout(scroll, 50);
    return () => window.clearTimeout(t);
  }, [location.hash, location.pathname]);

  return (
    <div className="min-h-screen bg-helm-ink text-helm-cream overflow-x-hidden relative">
      <MarketingNav authed={authed} onEnter={enter} active={location.hash === "#pricing" ? "/#pricing" : "/"} />

      {/* Hero — flat ink, typography leads */}
      <section className="relative z-10 px-6 pt-36 md:pt-48 pb-24 bg-helm-ink">
        <div className="relative mx-auto max-w-6xl grid lg:grid-cols-[1.1fr_0.9fr] gap-16 items-center">
          <div>
            <motion.p variants={fade} initial="hidden" animate="show" custom={0}
              className="font-mono text-xs uppercase tracking-[0.3em] text-helm-slate">
              {CATEGORY}
            </motion.p>
            <motion.h1 variants={fade} initial="hidden" animate="show" custom={1}
              className="font-display mt-8 text-5xl sm:text-6xl lg:text-[4.25rem] font-medium tracking-[-0.03em] leading-[1.05] text-helm-cream">
              {TAGLINE.split(". ").map((part, i, arr) => (
                <span key={part}>
                  {i === 0 ? <span className="text-helm-gold">{part}.</span> : part}
                  {i < arr.length - 1 && i !== 0 ? "." : ""}
                  {i < arr.length - 1 && <br />}
                </span>
              ))}
            </motion.h1>
            <motion.p variants={fade} initial="hidden" animate="show" custom={2}
              className="mt-8 text-lg text-helm-slate leading-relaxed max-w-xl">{HERO_SUB}</motion.p>
            <motion.div variants={fade} initial="hidden" animate="show" custom={3} className="mt-10 flex flex-wrap items-center gap-3 relative z-10">
              <button data-testid="hero-cta-btn" onClick={enter} type="button"
                className="group inline-flex items-center gap-2 rounded-md bg-helm-cream text-helm-navy font-medium px-6 py-3 transition-colors hover:bg-helm-gold focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-helm-gold">
                {authed ? "Open your cockpit" : "Start free"}
                <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-1" />
              </button>
              <a href="#how" className="inline-flex items-center gap-2 rounded-md border border-helm-cream/15 px-6 py-3 text-sm text-helm-cream transition-colors hover:border-helm-cream/30 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-helm-gold">
                See the 3-minute workflow
              </a>
            </motion.div>
            <motion.p variants={fade} initial="hidden" animate="show" custom={4} className="mt-8 text-xs text-helm-slate">{AUDIENCE}</motion.p>
            <motion.p variants={fade} initial="hidden" animate="show" custom={5} className="mt-3 text-xs text-helm-slate">
              <Link to="/security" className="text-helm-slate hover:text-helm-cream transition-colors">
                How Trenston protects company data →
              </Link>
            </motion.p>
          </div>
          <motion.div initial={{ opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.85, ease, delay: 0.2 }}>
            <BriefingPreview />
          </motion.div>
        </div>
      </section>

      <section className="relative z-10 px-6 py-16 border-t border-helm-cream/[0.05]">
        <div className="mx-auto max-w-6xl">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-y-10 gap-x-8">
            {PRODUCT_FACTS.map((s, i) => (
              <motion.div key={s.l} variants={fade} custom={i} initial="hidden" whileInView="show" viewport={{ once: true }} className="text-left md:text-center">
                <p className={`font-mono text-3xl md:text-4xl tabular-nums ${i === 0 ? "text-helm-gold" : "text-helm-cream"}`}>{s.v}</p>
                <p className="mt-2 text-xs text-helm-slate leading-snug">{s.l}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      <section className="px-6 py-28 border-t border-helm-cream/[0.05]">
        <div className="mx-auto max-w-6xl">
          <motion.div variants={fade} initial="hidden" whileInView="show" viewport={{ once: true, margin: "-100px" }} className="max-w-2xl">
            <div className="h-px w-10 bg-helm-gold mb-6" aria-hidden />
            <h2 className="font-display text-4xl md:text-5xl font-medium tracking-tight leading-[1.1]">What CEOs open Trenston for.</h2>
          </motion.div>
          <div className="mt-16 space-y-0 border-t border-helm-cream/[0.06]">
            {CEO_DAY.map((step, i) => (
              <motion.div key={step.title} variants={fade} custom={i} initial="hidden" whileInView="show" viewport={{ once: true, margin: "-60px" }}
                className="grid sm:grid-cols-[10rem_1fr] gap-3 sm:gap-10 py-7 border-b border-helm-cream/[0.06]">
                <p className="font-mono text-[10px] uppercase tracking-wider text-helm-gold pt-1">{step.title}</p>
                <div>
                  <p className="text-sm text-helm-slate leading-relaxed max-w-xl">{step.body}</p>
                </div>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      <section id="how" className="px-6 py-28 border-t border-helm-cream/[0.05]">
        <div className="mx-auto max-w-6xl">
          <motion.div variants={fade} initial="hidden" whileInView="show" viewport={{ once: true, margin: "-100px" }} className="max-w-2xl">
            <div className="h-px w-10 bg-helm-gold mb-6" aria-hidden />
            <h2 className="font-display text-4xl md:text-5xl font-medium tracking-tight leading-[1.1]">How Trenston fits together.</h2>
          </motion.div>
          <div className="mt-16 grid md:grid-cols-3 gap-12 md:gap-10">
            {HOW_IT_WORKS.map((s, i) => (
              <motion.div key={s.n} variants={fade} custom={i} initial="hidden" whileInView="show" viewport={{ once: true, margin: "-80px" }}>
                <p className="font-mono text-helm-slate text-sm">{s.n}</p>
                <h3 className="font-display mt-4 text-2xl text-helm-cream tracking-tight">{s.title}</h3>
                <p className="mt-3 text-sm text-helm-slate leading-relaxed">{s.body}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      <IntegrationsShowcase />

      <section className="px-6 py-28 border-t border-helm-cream/[0.05]">
        <div className="mx-auto max-w-6xl">
          <motion.div variants={fade} initial="hidden" whileInView="show" viewport={{ once: true, margin: "-100px" }} className="max-w-2xl">
            <div className="h-px w-10 bg-helm-gold mb-6" aria-hidden />
            <h2 className="font-display text-4xl md:text-5xl font-medium tracking-tight leading-[1.1]">
              Everything a CEO needs, nothing they do not.
            </h2>
            <p className="mt-5 text-helm-slate leading-relaxed">
              Real surfaces from the cockpit, not illustrations.
            </p>
          </motion.div>
          <motion.div variants={fade} initial="hidden" whileInView="show" viewport={{ once: true }} className="mt-14">
            <ProductScreens />
          </motion.div>
          <div className="mt-16 max-w-2xl space-y-8 border-t border-helm-cream/[0.06] pt-10">
            {FEATURE_HIGHLIGHTS.map((f) => (
              <div key={f.title}>
                <h3 className="font-display text-xl text-helm-cream tracking-tight">{f.title}</h3>
                <p className="mt-2 text-sm text-helm-slate leading-relaxed">{f.body}</p>
              </div>
            ))}
          </div>
          <div className="mt-10">
            <Link to="/features" className="inline-flex items-center gap-2 text-sm text-helm-cream hover:text-helm-gold transition-colors">
              See all features <ArrowRight className="w-4 h-4" />
            </Link>
          </div>
        </div>
      </section>

      <DepartmentsShowcase />

      <section id="pricing" className="scroll-mt-24 px-6 py-28 border-t border-helm-cream/[0.05]">
        <div className="mx-auto max-w-6xl">
          <motion.div variants={fade} initial="hidden" whileInView="show" viewport={{ once: true }} className="mb-14 max-w-2xl">
            <div className="h-px w-10 bg-helm-gold mb-6" aria-hidden />
            <h2 className="font-display text-4xl md:text-5xl font-medium tracking-tight leading-[1.1]">Plans that scale with you</h2>
            <p className="mt-4 text-helm-slate">Start free. Paid plans include a 7-day free trial. Cancel anytime.</p>
            <Link to="/pricing" className="inline-flex items-center gap-2 mt-4 text-sm text-helm-cream hover:text-helm-gold transition-colors">
              Full pricing page <ArrowRight className="w-4 h-4" />
            </Link>
          </motion.div>
          <div className="grid sm:grid-cols-2 xl:grid-cols-4 gap-0 border border-helm-cream/[0.08] divide-y sm:divide-y-0 sm:divide-x divide-helm-cream/[0.08]">
            {PLANS.map((plan) => {
              const renewalDisclosure = paidPlanRenewalDisclosure(plan);
              return (
              <motion.div
                key={plan.id}
                variants={fade}
                initial="hidden"
                whileInView="show"
                viewport={{ once: true }}
                className="p-6 md:p-8 flex flex-col bg-helm-ink"
              >
                {plan.highlighted && <div className="h-px w-8 bg-helm-gold mb-4" aria-hidden />}
                <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-helm-slate">{plan.label}</p>
                <p className="font-mono text-4xl text-helm-cream mt-3 tabular-nums">
                  {plan.price === 0 ? "$0" : `$${plan.price}`}
                  {plan.price > 0 && <span className="text-base text-helm-slate">/mo</span>}
                </p>
                <p className="text-sm text-helm-slate mt-2 min-h-[2.5rem]">{plan.for}</p>
                {plan.trialDays > 0 && (
                  <p className="text-[11px] font-mono text-helm-slate mt-1">{plan.trialDays}-day free trial</p>
                )}
                <ul className="mt-6 space-y-2.5 flex-1">
                  {plan.includes.map((f) => (
                    <li key={f} className="flex items-start gap-2 text-sm text-helm-cream/75">
                      <Check className="w-3.5 h-3.5 text-helm-slate shrink-0 mt-0.5" /> {f}
                    </li>
                  ))}
                </ul>
                <button type="button" onClick={enter} data-testid={`pricing-cta-${plan.id}`}
                  className={`mt-8 w-full rounded-md font-medium py-3 transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-helm-gold ${
                    plan.highlighted
                      ? "bg-helm-cream text-helm-navy hover:bg-helm-gold"
                      : "border border-helm-cream/15 text-helm-cream hover:border-helm-cream/30"
                  }`}>
                  {authed ? "Open cockpit" : plan.id === "free" ? "Get started free" : "Start free trial"}
                </button>
                {renewalDisclosure ? (
                  <p
                    data-testid={`pricing-renewal-${plan.id}`}
                    className="mt-3 text-[11px] leading-relaxed text-helm-slate"
                  >
                    {renewalDisclosure}
                  </p>
                ) : null}
              </motion.div>
              );
            })}
          </div>
          <div className="mt-14 max-w-2xl space-y-5 text-left">
            <p className="font-mono text-[10px] uppercase tracking-[0.25em] text-helm-slate">Common questions</p>
            {PRICING_FAQ.map((item) => (
              <div key={item.q} className="border-b border-helm-cream/[0.06] pb-4">
                <p className="text-sm text-helm-cream">{item.q}</p>
                <p className="text-xs text-helm-slate mt-1.5 leading-relaxed">{item.a}</p>
                {item.link ? (
                  <Link
                    to={item.link.to}
                    className="inline-block mt-2 text-xs text-helm-cream hover:text-helm-gold transition-colors"
                  >
                    {item.link.label} →
                  </Link>
                ) : null}
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="relative z-10 px-6 py-28 border-t border-helm-cream/[0.05]">
        <motion.div variants={fade} initial="hidden" whileInView="show" viewport={{ once: true }}
          className="relative mx-auto max-w-2xl text-center">
          <div className="mx-auto h-px w-10 bg-helm-gold mb-8" aria-hidden />
          <h2 className="font-display text-4xl md:text-5xl font-medium tracking-tight leading-[1.1]">{TAGLINE}</h2>
          <p className="mt-6 text-helm-slate">Quiet control for the owner everyone is counting on.</p>
          <div className="mt-10">
            <button data-testid="footer-cta-btn" onClick={enter} type="button"
              className="group inline-flex items-center gap-2 rounded-md bg-helm-cream text-helm-navy font-medium px-7 py-3 transition-colors hover:bg-helm-gold focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-helm-gold">
              {authed ? "Open your cockpit" : "Get started"}
              <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-1" />
            </button>
          </div>
          <p className="mt-8 text-xs text-helm-slate">Free to start · 7-day free trials · Sign in with Google</p>
        </motion.div>
      </section>

      <MarketingFooter />
    </div>
  );
}
