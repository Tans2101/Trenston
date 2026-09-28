import { useEffect } from "react";
import PlanCards from "@/components/marketing/PlanCards";
import {
  CtaBand,
  Eyebrow,
  MkAccordion,
  MkButton,
  MkPage,
  PageHero,
  Reveal,
} from "@/components/marketing/mk";
import { useMarketingAuth } from "@/hooks/useMarketingAuth";
import { CATEGORY, PLANS, PRICING_FAQ, TAGLINE } from "@/lib/marketingCopy";

/** Standalone crawlable pricing page — PLANS from marketingCopy.js. */
export default function Pricing() {
  const { authed, enter } = useMarketingAuth();
  useEffect(() => {
    window.scrollTo(0, 0);
  }, []);

  const paid = PLANS.filter((p) => p.price > 0);
  const maxSeats = Math.max(...PLANS.map((p) => p.seats));
  const trialDays = paid[0]?.trialDays;

  const facts = [
    { v: "$0", l: "to start on Free" },
    { v: `${trialDays} days`, l: "free trial on every paid plan" },
    { v: `Up to ${maxSeats}`, l: "Trenston users on Business" },
    { v: "Anytime", l: "cancel from Billing" },
  ];

  return (
    <MkPage authed={authed} onEnter={enter} active="/pricing">
      <PageHero
        eyebrow={CATEGORY}
        lines={["Pricing that", "scales with you."]}
        sub="Start free. Paid plans include a 7-day free trial. Cancel anytime. Plans scale with Trenston users (your team's product logins, separate from total company headcount) and how much AI document processing and Ask Trenston usage you need each month."
      />

      <section className="border-b border-mk-line bg-white px-6">
        <div className="mx-auto grid max-w-7xl grid-cols-2 lg:grid-cols-4">
          {facts.map((f, i) => (
            <Reveal
              key={f.l}
              i={i}
              className={`py-10 pr-6 ${i > 0 ? "lg:border-l lg:border-mk-line lg:pl-8" : ""} ${i % 2 === 1 ? "border-l border-mk-line pl-6" : ""}`}
            >
              <p className="text-3xl font-semibold tracking-[-0.03em] text-mk-black md:text-4xl">{f.v}</p>
              <p className="mt-2 text-sm text-mk-gray">{f.l}</p>
            </Reveal>
          ))}
        </div>
      </section>

      <section className="bg-mk-mist px-6 py-20 md:py-28" aria-label="Plans">
        <div className="mx-auto max-w-7xl">
          <PlanCards authed={authed} onEnter={enter} ctaTestIdPrefix="pricing-page-cta" />
        </div>
      </section>

      <section className="bg-white px-6 py-24 md:py-28">
        <div className="mx-auto grid max-w-7xl gap-12 lg:grid-cols-[0.8fr_1.2fr]">
          <Reveal>
            <Eyebrow>Questions</Eyebrow>
            <h2 className="mt-5 text-4xl font-semibold leading-[1.02] tracking-[-0.035em] md:text-5xl">Common questions.</h2>
            <p className="mt-5 max-w-sm leading-relaxed text-mk-gray">
              Billing runs through Paddle. Anything not covered here, email us.
            </p>
            <MkButton variant="outline-dark" href="mailto:contact@trenston.com" className="mt-8">
              Contact us
            </MkButton>
          </Reveal>
          <Reveal i={1}>
            <MkAccordion items={PRICING_FAQ} idPrefix="pricing-faq" />
          </Reveal>
        </div>
      </section>

      <CtaBand
        title={TAGLINE}
        sub="Start on Free, or try any paid plan free for 7 days."
        authed={authed}
        onEnter={enter}
        secondary={<MkButton variant="outline-light" to="/features">See features</MkButton>}
      />
    </MkPage>
  );
}
