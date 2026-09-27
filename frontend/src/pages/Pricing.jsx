import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "motion/react";
import { Check, ChevronDown, ArrowRight } from "lucide-react";
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

/**
 * Annual prices shown by the billing toggle below. These are a preview of
 * ~20% annual savings, not a live Paddle plan — checkout today is monthly
 * only (see backend/plans.py), so the toggle carries an honest note instead
 * of implying annual invoicing already happens at checkout.
 */
const ANNUAL_MONTHLY_EQUIVALENT = {
  free: 0,
  starter: 12,
  growth: 31,
  business: 79,
};

function FaqAccordion({ items }) {
  const [openIndex, setOpenIndex] = useState(0);

  return (
    <div className="divide-y divide-helm-navy/[0.08] rounded-2xl border border-helm-navy/[0.08] bg-white">
      {items.map((item, index) => {
        const open = openIndex === index;
        const panelId = `pricing-faq-panel-${index}`;
        return (
          <div key={item.q}>
            <h3>
              <button
                type="button"
                id={`pricing-faq-trigger-${index}`}
                aria-expanded={open}
                aria-controls={panelId}
                onClick={() => setOpenIndex(open ? -1 : index)}
                className="flex w-full cursor-pointer items-center justify-between gap-4 px-6 py-5 text-left"
              >
                <span className="font-semibold text-helm-navy">{item.q}</span>
                <ChevronDown
                  className={`h-4 w-4 shrink-0 text-helm-gold transition-transform duration-200 ${open ? "rotate-180" : ""}`}
                  aria-hidden
                />
              </button>
            </h3>
            {open && (
              <div id={panelId} role="region" aria-labelledby={`pricing-faq-trigger-${index}`} className="px-6 pb-5">
                <p className="text-sm leading-relaxed text-helm-navy/85">{item.a}</p>
                {item.link ? (
                  <Link
                    to={item.link.to}
                    className="mt-3 inline-block text-sm text-helm-navy hover:text-helm-gold transition-colors"
                  >
                    {item.link.label} →
                  </Link>
                ) : null}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

/** Standalone crawlable pricing page — PLANS from marketingCopy.js. */
export default function Pricing() {
  const { authed, enter } = useMarketingAuth();
  const [billing, setBilling] = useState("monthly");
  useEffect(() => {
    window.scrollTo(0, 0);
  }, []);

  return (
    <div className="min-h-screen bg-white text-helm-navy overflow-x-hidden">
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
            Start free. Paid plans include a 7-day free trial. Cancel anytime. Plans scale with Trenston users
            (your team&apos;s product logins, separate from total company headcount) and how much AI document
            processing and Ask Trenston usage you need each month.
          </motion.p>
        </div>
      </section>

      <section className="px-6 pb-6" aria-label="Billing period">
        <div className="mx-auto flex max-w-6xl justify-center">
          <div
            role="radiogroup"
            aria-label="Billing period"
            className="inline-flex items-center gap-1 rounded-full border border-helm-navy/[0.1] bg-white p-1 shadow-sm"
          >
            {[
              { id: "monthly", label: "Monthly" },
              { id: "annual", label: "Annual (Save 20%)" },
            ].map((opt) => (
              <button
                key={opt.id}
                type="button"
                role="radio"
                aria-checked={billing === opt.id}
                data-testid={`pricing-billing-${opt.id}`}
                onClick={() => setBilling(opt.id)}
                className={`rounded-full px-4 py-2 text-sm font-medium transition-colors ${
                  billing === opt.id
                    ? "bg-helm-navy text-white"
                    : "text-helm-navy/70 hover:text-helm-navy"
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>
        {billing === "annual" && (
          <p className="mx-auto mt-3 max-w-6xl text-center text-[11px] text-helm-navy/60">
            Preview pricing — checkout is monthly today; annual invoicing is coming soon.
          </p>
        )}
      </section>

      <section className="px-6 pb-20 pt-10" aria-label="Plans">
        <div className="mx-auto grid max-w-6xl items-stretch gap-6 sm:grid-cols-2 xl:grid-cols-4">
          {PLANS.map((plan, i) => {
            const renewalDisclosure = paidPlanRenewalDisclosure(plan);
            const displayPrice = billing === "annual" ? ANNUAL_MONTHLY_EQUIVALENT[plan.id] : plan.price;
            const highlighted = plan.highlighted;
            return (
              <motion.article
                key={plan.id}
                variants={fade}
                initial="hidden"
                animate="show"
                custom={i}
                data-testid={`pricing-plan-${plan.id}`}
                className={`relative flex flex-col rounded-2xl p-6 md:p-8 ${
                  highlighted
                    ? "z-10 scale-105 border-2 border-helm-navy bg-white shadow-xl"
                    : "border border-helm-navy/[0.12] bg-white/80 shadow-sm"
                }`}
              >
                {highlighted && (
                  <span className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-helm-gold px-3 py-1 text-xs font-bold uppercase tracking-wide text-helm-ink">
                    Most Popular
                  </span>
                )}
                <h2 className="font-mono text-[10px] uppercase tracking-[0.2em] text-helm-slate">
                  {plan.label}
                </h2>
                <p className="font-mono text-4xl text-helm-navy mt-3 tabular-nums">
                  {displayPrice === 0 ? "$0" : `$${displayPrice}`}
                  {displayPrice > 0 && <span className="text-base text-helm-slate">/mo</span>}
                </p>
                <p className="text-sm text-helm-slate mt-2 min-h-[2.5rem]">{plan.for}</p>
                <p className="text-[11px] font-mono text-helm-slate mt-1">
                  Up to {plan.seats} Trenston users
                  {plan.trialDays > 0 ? ` · ${plan.trialDays}-day free trial` : ""}
                </p>
                <ul className="mt-6 space-y-2.5 flex-1">
                  {plan.includes.map((f) => (
                    <li key={f} className="flex items-start gap-2 text-sm font-medium text-helm-navy">
                      <Check className="w-3.5 h-3.5 text-helm-gold shrink-0 mt-0.5" aria-hidden />
                      {f}
                    </li>
                  ))}
                </ul>
                <div className="mt-8">
                  <button
                    type="button"
                    onClick={enter}
                    data-testid={`pricing-page-cta-${plan.id}`}
                    className={`w-full rounded-md font-medium py-3 transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-helm-gold ${
                      highlighted
                        ? "bg-helm-gold text-helm-ink hover:bg-helm-gold-hover"
                        : "bg-helm-navy text-white hover:bg-helm-ink"
                    }`}
                  >
                    {authed ? "Open cockpit" : plan.id === "free" ? "Get started free" : "Start free trial"}
                  </button>
                  <p
                    className={`mt-3 text-[11px] font-medium leading-relaxed min-h-[3.25rem] ${
                      renewalDisclosure ? "text-helm-navy/70" : "text-transparent select-none"
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
        <div className="mx-auto max-w-2xl">
          <p className="font-mono text-xs uppercase tracking-[0.25em] text-helm-slate">
            Common questions
          </p>
          <div className="mt-6">
            <FaqAccordion items={PRICING_FAQ} />
          </div>
          <div className="pt-12 text-center">
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
