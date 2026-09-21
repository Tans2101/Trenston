import { useEffect } from "react";
import { Link } from "react-router-dom";
import { motion } from "motion/react";
import { ArrowRight } from "lucide-react";
import MarketingNav from "@/components/marketing/MarketingNav";
import MarketingFooter from "@/components/marketing/MarketingFooter";
import FounderCredit from "@/components/marketing/FounderCredit";
import { useMarketingAuth } from "@/hooks/useMarketingAuth";
import {
  ABOUT_DIFFERENTIATOR,
  ABOUT_PROBLEM,
  ABOUT_STORY,
  AUDIENCE,
  CATEGORY,
  COMPANY_LOCATION,
  FOUNDED_DATE,
  FOUNDER_LINKEDIN_URL,
  FOUNDER_NAME,
  FOUNDER_NOTE,
  PUBLIC_CONTACT_EMAIL,
  PUBLIC_CONTACT_MAILTO,
  TAGLINE,
  VALUES,
  VISION,
  WHAT_TRENSTON_IS,
  WHO_HELM_IS_FOR,
  MISSION,
} from "@/lib/marketingCopy";

const ease = [0.16, 1, 0.3, 1];
const fade = {
  hidden: { opacity: 0, y: 20 },
  show: (i = 0) => ({ opacity: 1, y: 0, transition: { duration: 0.7, ease, delay: i * 0.08 } }),
};

const ABOUT_FACTS = [
  { label: "What Trenston is", body: WHAT_TRENSTON_IS },
  { label: "Who it's for", body: AUDIENCE },
  { label: "Problem we solve", body: ABOUT_PROBLEM },
  { label: "Founder", body: FOUNDER_NAME, href: FOUNDER_LINKEDIN_URL },
  { label: "Founded", body: FOUNDED_DATE },
  { label: "Operates from", body: COMPANY_LOCATION },
  { label: "Contact", body: PUBLIC_CONTACT_EMAIL, href: PUBLIC_CONTACT_MAILTO },
];

export default function About() {
  const { authed, enter } = useMarketingAuth();
  useEffect(() => { window.scrollTo(0, 0); }, []);

  return (
    <div className="min-h-screen bg-helm-cream text-helm-navy overflow-x-hidden">
      <MarketingNav authed={authed} onEnter={enter} active="/about" />

      <section className="px-6 pt-36 md:pt-48 pb-12">
        <div className="mx-auto max-w-3xl">
          <motion.p variants={fade} initial="hidden" animate="show" custom={0}
            className="font-mono text-xs uppercase tracking-[0.3em] text-helm-slate">{CATEGORY}</motion.p>
          <motion.h1 variants={fade} initial="hidden" animate="show" custom={1}
            className="font-display mt-8 text-5xl md:text-6xl font-medium tracking-[-0.03em] leading-[1.05]">
            About Trenston
          </motion.h1>
        </div>
      </section>

      <section className="px-6 pb-20 border-b border-helm-navy/[0.05]" data-testid="about-facts">
        <div className="mx-auto max-w-3xl">
          <div className="h-px w-10 bg-helm-gold mb-6" aria-hidden />
          <h2 className="font-display text-2xl font-medium tracking-tight text-helm-navy">At a glance</h2>
          <div className="mt-8 border-t border-helm-navy/[0.06]">
            {ABOUT_FACTS.map((row) => (
              <div
                key={row.label}
                className="grid sm:grid-cols-[11rem_1fr] gap-2 sm:gap-8 py-6 border-b border-helm-navy/[0.06]"
              >
                <h3 className="font-mono text-[10px] uppercase tracking-[0.2em] text-helm-slate">{row.label}</h3>
                {row.href ? (
                  <a
                    id={row.label === "Contact" ? "contact" : undefined}
                    href={row.href}
                    {...(row.label === "Founder"
                      ? { target: "_blank", rel: "noopener noreferrer" }
                      : {})}
                    className="text-sm text-helm-navy leading-relaxed hover:text-helm-gold transition-colors"
                  >
                    {row.body}
                  </a>
                ) : (
                  <p className="text-sm text-helm-navy/90 leading-relaxed">{row.body}</p>
                )}
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="px-6 py-20 border-t border-helm-navy/[0.05]">
        <div className="mx-auto max-w-3xl">
          <div className="h-px w-10 bg-helm-gold mb-6" aria-hidden />
          <h2 className="font-display text-3xl font-medium tracking-tight">Why we built Trenston</h2>
          <p className="mt-5 text-helm-slate leading-relaxed">{ABOUT_STORY}</p>
        </div>
      </section>

      <section className="px-6 py-20 border-t border-helm-navy/[0.05]" data-testid="about-founder">
        <div className="mx-auto max-w-3xl">
          <div className="h-px w-10 bg-helm-gold mb-6" aria-hidden />
          <h2 className="font-display text-3xl font-medium tracking-tight">Who&apos;s behind Trenston</h2>
          <p className="mt-5 text-helm-navy/80 leading-relaxed">{FOUNDER_NOTE}</p>
          <FounderCredit
            className="mt-4"
            creditClassName="font-mono text-xs uppercase tracking-[0.2em] text-helm-slate"
            data-testid="founder-credit"
          />
          <p className="mt-2 text-sm text-helm-slate">Based in {COMPANY_LOCATION}.</p>
        </div>
      </section>

      <section className="px-6 py-20 border-t border-helm-navy/[0.05]">
        <div className="mx-auto max-w-3xl space-y-16">
          <div>
            <div className="h-px w-10 bg-helm-gold mb-6" aria-hidden />
            <h2 className="font-display text-3xl font-medium tracking-tight">Our mission</h2>
            <p className="mt-5 text-helm-slate leading-relaxed">{MISSION}</p>
          </div>
          <div>
            <h2 className="font-display text-3xl font-medium tracking-tight">Where we&apos;re headed</h2>
            <p className="mt-5 text-helm-slate leading-relaxed">{VISION}</p>
          </div>
          <div>
            <h2 className="font-display text-3xl font-medium tracking-tight">Who Trenston is for</h2>
            <div className="mt-8 border-t border-helm-navy/[0.06]">
              {WHO_HELM_IS_FOR.map((item) => (
                <div key={item.title} className="grid sm:grid-cols-[11rem_1fr] gap-2 sm:gap-8 py-6 border-b border-helm-navy/[0.06]">
                  <h3 className="font-display text-base text-helm-navy tracking-tight">{item.title}</h3>
                  <p className="text-sm text-helm-slate leading-relaxed">{item.body}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section className="px-6 py-20 border-t border-helm-navy/[0.05]">
        <div className="mx-auto max-w-3xl space-y-16">
          <div>
            <div className="h-px w-10 bg-helm-gold mb-6" aria-hidden />
            <h2 className="font-display text-3xl font-medium tracking-tight mb-8">What we believe</h2>
            <div className="border-t border-helm-navy/[0.06]">
              {VALUES.map((v) => (
                <div key={v.title} className="py-6 border-b border-helm-navy/[0.06]">
                  <h3 className="font-display text-lg text-helm-navy tracking-tight">{v.title}</h3>
                  <p className="mt-2 text-sm text-helm-slate leading-relaxed">{v.body}</p>
                </div>
              ))}
            </div>
          </div>
          <div>
            <h2 className="font-display text-3xl font-medium tracking-tight">What makes Trenston different</h2>
            <p className="mt-5 text-sm text-helm-slate leading-relaxed">{ABOUT_DIFFERENTIATOR}</p>
          </div>
        </div>
      </section>

      <section className="px-6 py-24 border-t border-helm-navy/[0.05]">
        <div className="mx-auto max-w-2xl text-center">
          <div className="mx-auto h-px w-10 bg-helm-gold mb-8" aria-hidden />
          <h2 className="font-display text-4xl font-medium tracking-tight leading-tight">{TAGLINE}</h2>
          <div className="mt-10 flex flex-wrap items-center justify-center gap-3">
            <button type="button" onClick={enter}
              className="group inline-flex items-center gap-2 rounded-md bg-helm-navy text-helm-cream font-medium px-6 py-3 hover:bg-helm-gold transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-helm-gold">
              {authed ? "Open your cockpit" : "Get started"}
              <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-1" />
            </button>
            <Link to="/features"
              className="inline-flex items-center gap-2 rounded-md border border-helm-navy/15 px-6 py-3 text-sm text-helm-navy/80 hover:border-helm-navy/30 transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-helm-gold">
              See all features
            </Link>
          </div>
        </div>
      </section>

      <MarketingFooter />
    </div>
  );
}
