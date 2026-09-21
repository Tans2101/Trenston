import { useEffect } from "react";
import { Link } from "react-router-dom";
import { motion } from "motion/react";
import { Check, ArrowRight } from "lucide-react";
import MarketingNav from "@/components/marketing/MarketingNav";
import MarketingFooter from "@/components/marketing/MarketingFooter";
import { useMarketingAuth } from "@/hooks/useMarketingAuth";
import {
  CATEGORY,
  PLANS,
  PRICING_FAQ,
  TAGLINE,
  paidPlanRenewalDisclosure,
} from "@/lib/marketingCopy";

const ease = [0.16, 1, 0.3, 1];
const fade = {
  hidden: { opacity: 0, y: 20 },
  show: (i = 0) => ({ opacity: 1, y: 0, transition: { duration: 0.7, ease, delay: i * 0.06 } }),
};

/** Standalone crawlable pricing page — PLANS from marketingCopy.js. */
export default function Pricing() {
  const { authed, enter } = useMarketingAuth();
  useEffect(() => {
    window.scrollTo(0, 0);
  }, []);

  return (
    <div className="min-h-screen bg-helm-cream text-helm-navy overflow-x-hidden">
      <MarketingNav authed={authed} onEnter={enter} active="/pricing" />

      <section className="px-6 pt-36 md:pt-48 pb-12">
        <div className="mx-auto max-w-3xl">
          <motion.p
            variants={fade}
            initial="hidden"
            animate="show"
            custom={0}
            className="font-mono text-xs uppercase tracking-[0.3em] text-helm-slate"
          >
            {CATEGORY}
          </motion.p>
          <motion.h1
            variants={fade}
            initial="hidden"
            animate="show"
            custom={1}
            className="font-display mt-8 text-5xl md:text-6xl font-medium tracking-[-0.03em] leading-[1.05]"
          >
            Pricing
          </motion.h1>
          <motion.p
            variants={fade}
            initial="hidden"
            animate="show"
            custom={2}
            className="mt-6 text-lg text-helm-slate leading-relaxed"
          >
            Start free. Paid plans include a 7-day free trial. Cancel anytime. Plans scale with Trenston seats
            (your team&apos;s product logins, separate from total company headcount) and how much AI document
            processing and Ask Trenston usage you need each month.
          </motion.p>
        </div>
      </section>

      <section className="px-6 pb-20" aria-label="Plans">
        <div className="mx-auto max-w-6xl grid sm:grid-cols-2 xl:grid-cols-4 gap-0 border border-helm-navy/[0.08] divide-y sm:divide-y-0 sm:divide-x divide-helm-cream/[0.08]">
          {PLANS.map((plan, i) => {
            const renewalDisclosure = paidPlanRenewalDisclosure(plan);
            return (
              <motion.article
                key={plan.id}
                variants={fade}
                initial="hidden"
                animate="show"
                custom={i}
                className="p-6 md:p-8 flex flex-col bg-helm-cream"
                data-testid={`pricing-plan-${plan.id}`}
              >
                {plan.highlighted && <div className="h-px w-8 bg-helm-gold mb-4" aria-hidden />}
                <h2 className="font-mono text-[10px] uppercase tracking-[0.2em] text-helm-slate">
                  {plan.label}
                </h2>
                <p className="font-mono text-4xl text-helm-navy mt-3 tabular-nums">
                  {plan.price === 0 ? "$0" : `$${plan.price}`}
                  {plan.price > 0 && <span className="text-base text-helm-slate">/mo</span>}
                </p>
                <p className="text-sm text-helm-slate mt-2 min-h-[2.5rem]">{plan.for}</p>
                <p className="text-[11px] font-mono text-helm-slate mt-1">
                  Up to {plan.seats} Trenston seats
                  {plan.trialDays > 0 ? ` · ${plan.trialDays}-day free trial` : ""}
                </p>
                <ul className="mt-6 space-y-2.5 flex-1">
                  {plan.includes.map((f) => (
                    <li key={f} className="flex items-start gap-2 text-sm text-helm-navy/75">
                      <Check className="w-3.5 h-3.5 text-helm-slate shrink-0 mt-0.5" aria-hidden />
                      {f}
                    </li>
                  ))}
                </ul>
                <div className="mt-8">
                  <button
                    type="button"
                    onClick={enter}
                    data-testid={`pricing-page-cta-${plan.id}`}
                    className="w-full rounded-md font-medium py-3 transition-colors bg-helm-navy text-helm-cream hover:bg-helm-ink focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-helm-gold"
                  >
                    {authed ? "Open cockpit" : plan.id === "free" ? "Get started free" : "Start free trial"}
                  </button>
                  <p
                    className={`mt-3 text-[11px] leading-relaxed min-h-[3.25rem] ${
                      renewalDisclosure ? "text-helm-slate" : "text-transparent select-none"
                    }`}
                    aria-hidden={!renewalDisclosure}
                  >
                    {renewalDisclosure || "\u00a0"}
                  </p>
                </div>
              </motion.article>
            );
          })}
        </div>
      </section>

      <section className="px-6 pb-24 border-t border-helm-navy/[0.05] pt-16">
        <div className="mx-auto max-w-2xl space-y-6">
          <p className="font-mono text-xs uppercase tracking-[0.25em] text-helm-slate">
            Common questions
          </p>
          {PRICING_FAQ.map((item) => (
            <div key={item.q} className="border-b border-helm-navy/[0.06] pb-5">
              <p className="text-base md:text-lg font-medium text-helm-navy tracking-tight">{item.q}</p>
              <p className="text-sm md:text-base text-helm-slate mt-2 leading-relaxed">{item.a}</p>
              {item.link ? (
                <Link
                  to={item.link.to}
                  className="inline-block mt-3 text-sm text-helm-navy hover:text-helm-gold transition-colors"
                >
                  {item.link.label} →
                </Link>
              ) : null}
            </div>
          ))}
          <div className="pt-8 text-center">
            <p className="font-display text-2xl text-helm-navy tracking-tight">{TAGLINE}</p>
            <Link
              to="/features"
              className="inline-flex items-center gap-2 mt-6 text-sm text-helm-navy hover:text-helm-gold transition-colors"
            >
              See features <ArrowRight className="w-4 h-4" />
            </Link>
          </div>
        </div>
      </section>

      <MarketingFooter />
    </div>
  );
}
