import { useEffect } from "react";
import { Link } from "react-router-dom";
import { motion } from "motion/react";
import { ArrowRight, Linkedin, Mail, MapPin } from "lucide-react";
import MarketingNav from "@/components/marketing/MarketingNav";
import MarketingFooter from "@/components/marketing/MarketingFooter";
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
  FOUNDER_ROLE,
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

/** The 4 key facts shown as cards. "Problem we solve" leads the story
 * section below instead, and "Founder" / "Contact" live in the founder
 * spotlight section — nothing here is dropped, just relocated. */
const AT_A_GLANCE = [
  { label: "What it is", body: WHAT_TRENSTON_IS },
  { label: "Who it's for", body: AUDIENCE },
  { label: "Founded", body: FOUNDED_DATE },
  { label: "Location", body: COMPANY_LOCATION },
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
        <div className="mx-auto max-w-6xl">
          <div className="h-px w-10 bg-helm-gold mb-6" aria-hidden />
          <h2 className="font-display text-2xl font-medium tracking-tight text-helm-navy">At a glance</h2>
          <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {AT_A_GLANCE.map((fact, i) => (
              <motion.div
                key={fact.label}
                variants={fade}
                custom={i}
                initial="hidden"
                whileInView="show"
                viewport={{ once: true, margin: "-40px" }}
                className="rounded-xl border border-helm-navy/[0.1] bg-white p-6 shadow-sm"
              >
                <h3 className="text-xs font-semibold uppercase tracking-wider text-helm-slate">{fact.label}</h3>
                <p className="mt-3 text-sm text-helm-navy leading-relaxed">{fact.body}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      <section className="px-6 py-20 border-t border-helm-navy/[0.05]">
        <div className="mx-auto max-w-3xl">
          <div className="h-px w-10 bg-helm-gold mb-6" aria-hidden />
          <h2 className="font-display text-3xl font-medium tracking-tight">Why we built Trenston</h2>
          <p className="mt-5 text-helm-navy/85 leading-relaxed">{ABOUT_PROBLEM}</p>
          <p className="mt-4 text-helm-navy/85 leading-relaxed">{ABOUT_STORY}</p>
        </div>
      </section>

      <section className="px-6 py-20 border-t border-helm-navy/[0.05]" data-testid="about-founder">
        <div className="mx-auto max-w-5xl">
          <div className="h-px w-10 bg-helm-gold mb-10" aria-hidden />
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8 items-center">
            {/* Left: placeholder avatar frame + location badge. No real headshot
                on file yet, so this is an honest initials placeholder, not a
                stand-in photo. */}
            <div className="md:col-span-1 flex flex-col items-center md:items-start">
              <div
                className="w-32 h-32 rounded-2xl border border-helm-navy/[0.12] bg-helm-navy/[0.04] flex items-center justify-center"
                aria-hidden
              >
                <span className="font-display text-3xl text-helm-navy/50 tracking-tight">
                  {FOUNDER_NAME.split(" ").map((n) => n[0]).join("")}
                </span>
              </div>
              <span className="mt-3 inline-flex items-center gap-1.5 rounded-full border border-helm-navy/[0.1] bg-white px-3 py-1.5 text-xs text-helm-navy/80 shadow-sm">
                <MapPin className="w-3 h-3 text-helm-gold" aria-hidden />
                {COMPANY_LOCATION}
              </span>
            </div>

            {/* Right: bio, name, title, LinkedIn + contact badges */}
            <div className="md:col-span-2">
              <h2 className="font-display text-3xl font-medium tracking-tight">Who&apos;s behind Trenston</h2>
              <p className="mt-5 text-helm-navy/85 leading-relaxed">{FOUNDER_NOTE}</p>
              <div className="mt-5 flex flex-wrap items-center gap-3">
                <div>
                  <p className="font-display text-lg text-helm-navy tracking-tight">{FOUNDER_NAME}</p>
                  <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-helm-slate">{FOUNDER_ROLE}</p>
                </div>
                <a
                  href={FOUNDER_LINKEDIN_URL}
                  target="_blank"
                  rel="noopener noreferrer"
                  data-testid="founder-linkedin"
                  className="inline-flex items-center gap-1.5 rounded-full border border-helm-navy/[0.1] bg-white px-3 py-1.5 text-xs text-helm-navy hover:border-helm-gold/40 hover:text-helm-gold transition-colors shadow-sm"
                >
                  <Linkedin className="w-3.5 h-3.5" aria-hidden />
                  LinkedIn
                </a>
                <a
                  id="contact"
                  href={PUBLIC_CONTACT_MAILTO}
                  data-testid="founder-contact"
                  className="inline-flex items-center gap-1.5 rounded-full border border-helm-navy/[0.1] bg-white px-3 py-1.5 text-xs text-helm-navy hover:border-helm-gold/40 hover:text-helm-gold transition-colors shadow-sm"
                >
                  <Mail className="w-3.5 h-3.5" aria-hidden />
                  {PUBLIC_CONTACT_EMAIL}
                </a>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="px-6 py-20 border-t border-helm-navy/[0.05]">
        <div className="mx-auto max-w-3xl space-y-16">
          <div>
            <div className="h-px w-10 bg-helm-gold mb-6" aria-hidden />
            <h2 className="font-display text-3xl font-medium tracking-tight">Our mission</h2>
            <p className="mt-5 text-helm-navy/85 leading-relaxed">{MISSION}</p>
          </div>
          <div>
            <h2 className="font-display text-3xl font-medium tracking-tight">Where we&apos;re headed</h2>
            <p className="mt-5 text-helm-navy/85 leading-relaxed">{VISION}</p>
          </div>
          <div>
            <h2 className="font-display text-3xl font-medium tracking-tight">Who Trenston is for</h2>
            <div className="mt-8 border-t border-helm-navy/[0.06]">
              {WHO_HELM_IS_FOR.map((item) => (
                <div key={item.title} className="grid sm:grid-cols-[11rem_1fr] gap-2 sm:gap-8 py-6 border-b border-helm-navy/[0.06]">
                  <h3 className="font-display text-base text-helm-navy tracking-tight">{item.title}</h3>
                  <p className="text-sm text-helm-navy/85 leading-relaxed">{item.body}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section className="px-6 py-20 border-t border-helm-navy/[0.05]" data-testid="about-values">
        <div className="mx-auto max-w-6xl space-y-16">
          <div>
            <div className="h-px w-10 bg-helm-gold mb-6" aria-hidden />
            <h2 className="font-display text-3xl font-medium tracking-tight mb-8">What we believe</h2>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {VALUES.map((v, i) => (
                <motion.div
                  key={v.title}
                  variants={fade}
                  custom={i}
                  initial="hidden"
                  whileInView="show"
                  viewport={{ once: true, margin: "-40px" }}
                  className="rounded-xl border border-helm-navy/[0.1] bg-white p-6 shadow-sm"
                >
                  <h3 className="font-display text-lg text-helm-navy tracking-tight">{v.title}</h3>
                  <p className="mt-2 text-sm text-helm-navy/85 leading-relaxed">{v.body}</p>
                </motion.div>
              ))}
            </div>
          </div>
          <div className="max-w-3xl">
            <h2 className="font-display text-3xl font-medium tracking-tight">What makes Trenston different</h2>
            <p className="mt-5 text-sm text-helm-navy/85 leading-relaxed">{ABOUT_DIFFERENTIATOR}</p>
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
