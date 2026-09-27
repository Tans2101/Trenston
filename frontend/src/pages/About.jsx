import { useEffect } from "react";
import { Link } from "react-router-dom";
import { motion } from "motion/react";
import {
  ArrowRight,
  Briefcase,
  Building2,
  Calendar,
  Compass,
  Info,
  Linkedin,
  Mail,
  MapPin,
  Radio,
  ShieldCheck,
  Sparkles,
  Target,
  TrendingUp,
  Users,
} from "lucide-react";
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
  { label: "What it is", body: WHAT_TRENSTON_IS, icon: Info },
  { label: "Who it's for", body: AUDIENCE, icon: Users },
  { label: "Founded", body: FOUNDED_DATE, icon: Calendar },
  { label: "Location", body: COMPANY_LOCATION, icon: MapPin },
];

/** WHO_HELM_IS_FOR and VALUES have no icon field in marketingCopy.js (also
 * read by marketingClaimsVerification.test.js) — map by title here instead
 * of changing that shared shape. */
const WHO_ICONS = {
  "Founders and owners running real operations": Users,
  "Owner-operators and traditional businesses": Building2,
  "Leadership teams": Briefcase,
};
const VALUE_ICONS = {
  "Signal over noise": Radio,
  "Quiet control": ShieldCheck,
  "Honest synthesis": Sparkles,
};

function SectionKicker({ icon: Icon, children }) {
  return (
    <div className="flex items-center gap-3 mb-5">
      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-helm-gold/15" aria-hidden>
        <Icon className="h-4 w-4 text-helm-gold" />
      </span>
      <h2 className="font-display text-2xl md:text-3xl font-medium tracking-tight">{children}</h2>
    </div>
  );
}

export default function About() {
  const { authed, enter } = useMarketingAuth();
  useEffect(() => { window.scrollTo(0, 0); }, []);

  return (
    <div className="min-h-screen bg-helm-cream text-helm-navy overflow-x-hidden">
      <MarketingNav authed={authed} onEnter={enter} active="/about" />

      <section className="px-6 pt-32 md:pt-40 pb-10">
        <div className="mx-auto max-w-3xl">
          <motion.p variants={fade} initial="hidden" animate="show" custom={0}
            className="font-mono text-xs uppercase tracking-[0.3em] text-helm-gold">{CATEGORY}</motion.p>
          <motion.h1 variants={fade} initial="hidden" animate="show" custom={1}
            className="font-display mt-6 text-5xl md:text-6xl font-medium tracking-[-0.03em] leading-[1.05]">
            About Trenston
          </motion.h1>
        </div>
      </section>

      <section className="px-6 pb-14" data-testid="about-facts">
        <div className="mx-auto max-w-6xl">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {AT_A_GLANCE.map((fact, i) => (
              <motion.div
                key={fact.label}
                variants={fade}
                custom={i}
                initial="hidden"
                whileInView="show"
                viewport={{ once: true, margin: "-40px" }}
                className="rounded-xl border border-helm-navy/[0.1] bg-white p-5 shadow-sm"
              >
                <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-helm-navy/[0.05]" aria-hidden>
                  <fact.icon className="h-4 w-4 text-helm-gold" />
                </span>
                <h3 className="mt-3 text-xs font-semibold uppercase tracking-wider text-helm-slate">{fact.label}</h3>
                <p className="mt-1.5 text-sm text-helm-navy leading-relaxed">{fact.body}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      <section className="px-6 py-14 border-t border-helm-navy/[0.06] bg-white">
        <div className="mx-auto max-w-5xl">
          <SectionKicker icon={Target}>Why we built Trenston</SectionKicker>
          <div className="grid gap-4 md:grid-cols-2">
            <motion.div
              variants={fade}
              initial="hidden"
              whileInView="show"
              viewport={{ once: true, margin: "-40px" }}
              custom={0}
              className="rounded-xl border border-helm-navy/[0.08] bg-helm-cream/60 p-6"
            >
              <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-helm-gold">The gap</p>
              <p className="mt-3 text-sm text-helm-navy/85 leading-relaxed">{ABOUT_PROBLEM}</p>
            </motion.div>
            <motion.div
              variants={fade}
              initial="hidden"
              whileInView="show"
              viewport={{ once: true, margin: "-40px" }}
              custom={1}
              className="rounded-xl border border-helm-navy/[0.08] bg-helm-cream/60 p-6"
            >
              <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-helm-gold">What we built</p>
              <p className="mt-3 text-sm text-helm-navy/85 leading-relaxed">{ABOUT_STORY}</p>
            </motion.div>
          </div>
        </div>
      </section>

      <section className="px-6 py-14 border-t border-helm-navy/[0.06]" data-testid="about-founder">
        <div className="mx-auto max-w-5xl">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8 items-center">
            {/* Left: placeholder avatar frame + location badge. No real headshot
                on file yet, so this is an honest initials placeholder, not a
                stand-in photo. */}
            <div className="md:col-span-1 flex flex-col items-center md:items-start">
              <div
                className="w-32 h-32 rounded-2xl border border-helm-navy/[0.12] bg-gradient-to-br from-helm-gold/20 to-helm-navy/[0.06] flex items-center justify-center"
                aria-hidden
              >
                <span className="font-display text-3xl text-helm-navy/60 tracking-tight">
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
              <SectionKicker icon={Users}>Who&apos;s behind Trenston</SectionKicker>
              <p className="text-helm-navy/85 leading-relaxed">{FOUNDER_NOTE}</p>
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

      <section className="px-6 py-14 border-t border-helm-navy/[0.06] bg-white">
        <div className="mx-auto max-w-5xl">
          <div className="grid gap-4 md:grid-cols-2">
            <motion.div
              variants={fade}
              initial="hidden"
              whileInView="show"
              viewport={{ once: true, margin: "-40px" }}
              custom={0}
              className="rounded-xl border border-helm-navy/[0.08] bg-helm-cream/60 p-6"
            >
              <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-helm-gold/15" aria-hidden>
                <Compass className="h-4 w-4 text-helm-gold" />
              </span>
              <h2 className="font-display mt-4 text-xl font-medium tracking-tight">Our mission</h2>
              <p className="mt-3 text-sm text-helm-navy/85 leading-relaxed">{MISSION}</p>
            </motion.div>
            <motion.div
              variants={fade}
              initial="hidden"
              whileInView="show"
              viewport={{ once: true, margin: "-40px" }}
              custom={1}
              className="rounded-xl border border-helm-navy/[0.08] bg-helm-cream/60 p-6"
            >
              <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-helm-gold/15" aria-hidden>
                <TrendingUp className="h-4 w-4 text-helm-gold" />
              </span>
              <h2 className="font-display mt-4 text-xl font-medium tracking-tight">Where we&apos;re headed</h2>
              <p className="mt-3 text-sm text-helm-navy/85 leading-relaxed">{VISION}</p>
            </motion.div>
          </div>

          <div className="mt-10">
            <SectionKicker icon={Users}>Who Trenston is for</SectionKicker>
            <div className="grid gap-4 sm:grid-cols-3">
              {WHO_HELM_IS_FOR.map((item, i) => {
                const Icon = WHO_ICONS[item.title] || Building2;
                return (
                  <motion.div
                    key={item.title}
                    variants={fade}
                    custom={i}
                    initial="hidden"
                    whileInView="show"
                    viewport={{ once: true, margin: "-40px" }}
                    className="rounded-xl border border-helm-navy/[0.1] bg-white p-5 shadow-sm"
                  >
                    <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-helm-navy/[0.05]" aria-hidden>
                      <Icon className="h-4 w-4 text-helm-gold" />
                    </span>
                    <h3 className="font-display mt-3 text-base text-helm-navy tracking-tight">{item.title}</h3>
                    <p className="mt-1.5 text-sm text-helm-navy/85 leading-relaxed">{item.body}</p>
                  </motion.div>
                );
              })}
            </div>
          </div>
        </div>
      </section>

      <section className="px-6 py-14 border-t border-helm-navy/[0.06]" data-testid="about-values">
        <div className="mx-auto max-w-6xl">
          <SectionKicker icon={Sparkles}>What we believe</SectionKicker>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {VALUES.map((v, i) => {
              const Icon = VALUE_ICONS[v.title] || Sparkles;
              return (
                <motion.div
                  key={v.title}
                  variants={fade}
                  custom={i}
                  initial="hidden"
                  whileInView="show"
                  viewport={{ once: true, margin: "-40px" }}
                  className="rounded-xl border border-helm-navy/[0.1] bg-white p-6 shadow-sm"
                >
                  <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-helm-gold/15" aria-hidden>
                    <Icon className="h-4 w-4 text-helm-gold" />
                  </span>
                  <h3 className="font-display mt-4 text-lg text-helm-navy tracking-tight">{v.title}</h3>
                  <p className="mt-2 text-sm text-helm-navy/85 leading-relaxed">{v.body}</p>
                </motion.div>
              );
            })}
          </div>
          <div className="mt-6 rounded-xl border border-helm-navy/[0.08] bg-white p-6 shadow-sm">
            <div className="flex items-start gap-3">
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-helm-navy/[0.05]" aria-hidden>
                <Target className="h-4 w-4 text-helm-gold" />
              </span>
              <div>
                <h2 className="font-display text-lg font-medium tracking-tight">What makes Trenston different</h2>
                <p className="mt-2 text-sm text-helm-navy/85 leading-relaxed">{ABOUT_DIFFERENTIATOR}</p>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="px-6 py-20 border-t border-helm-navy/[0.06] bg-white">
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
