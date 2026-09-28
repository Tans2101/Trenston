import { useEffect } from "react";
import {
  Briefcase,
  Building2,
  Compass,
  Linkedin,
  Mail,
  MapPin,
  Radio,
  ShieldCheck,
  Sparkles,
  TrendingUp,
  Users,
} from "lucide-react";
import {
  CtaBand,
  DarkBackdrop,
  DrawLine,
  Eyebrow,
  MkButton,
  MkPage,
  PageHero,
  Reveal,
  SectionHeader,
} from "@/components/marketing/mk";
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
  MISSION,
  PUBLIC_CONTACT_EMAIL,
  PUBLIC_CONTACT_MAILTO,
  TAGLINE,
  VALUES,
  VISION,
  WHAT_TRENSTON_IS,
  WHO_HELM_IS_FOR,
} from "@/lib/marketingCopy";

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

const FACTS = [
  { label: "Founded", value: FOUNDED_DATE },
  { label: "Headquarters", value: COMPANY_LOCATION },
  { label: "Category", value: CATEGORY },
  { label: "Built for", value: AUDIENCE },
];

export default function About() {
  const { authed, enter } = useMarketingAuth();
  useEffect(() => { window.scrollTo(0, 0); }, []);

  const initials = FOUNDER_NAME.split(" ").map((n) => n[0]).join("");

  return (
    <MkPage authed={authed} onEnter={enter} active="/about">
      <PageHero eyebrow="About us" lines={["About", "Trenston."]} sub={MISSION} />

      {/* What it is + key facts */}
      <section className="bg-white px-6 py-24 md:py-28" data-testid="about-facts">
        <div className="mx-auto grid max-w-7xl gap-16 lg:grid-cols-[1.3fr_1fr]">
          <Reveal>
            <Eyebrow>What Trenston is</Eyebrow>
            <p className="mt-8 text-2xl font-medium leading-[1.4] tracking-[-0.015em] text-mk-black md:text-[1.9rem]">
              {WHAT_TRENSTON_IS}
            </p>
          </Reveal>
          <dl className="self-end">
            {FACTS.map((f, i) => (
              <Reveal key={f.label} i={i} className="border-t border-mk-line py-5 last:border-b">
                <dt className="text-xs font-semibold uppercase tracking-[0.16em] text-mk-navy">{f.label}</dt>
                <dd className="mt-2 text-lg leading-snug text-mk-black">{f.value}</dd>
              </Reveal>
            ))}
          </dl>
        </div>
      </section>

      {/* Why we built it — black band, pull quote + story */}
      <section className="relative overflow-hidden bg-mk-black px-6 py-24 text-white md:py-32">
        <DarkBackdrop />
        <div className="relative mx-auto max-w-7xl">
          <Eyebrow dark>Why we built Trenston</Eyebrow>
          <div className="mt-10 grid gap-14 lg:grid-cols-[1.15fr_1fr]">
            <Reveal>
              <p className="text-3xl font-semibold leading-[1.2] tracking-[-0.025em] md:text-[2.6rem]">
                <span className="text-mk-sky">“</span>
                {ABOUT_PROBLEM}
                <span className="text-mk-sky">”</span>
              </p>
            </Reveal>
            <Reveal i={1}>
              <DrawLine className="bg-white/30" />
              <p className="mt-6 text-xs font-semibold uppercase tracking-[0.16em] text-mk-gray-dark">What we built</p>
              <p className="mt-4 leading-relaxed text-mk-gray-dark">{ABOUT_STORY}</p>
            </Reveal>
          </div>
        </div>
      </section>

      {/* Founder */}
      <section className="bg-white px-6 py-24 md:py-28" data-testid="about-founder">
        <div className="mx-auto grid max-w-7xl items-center gap-14 lg:grid-cols-[0.8fr_1.2fr]">
          <Reveal className="relative mx-auto w-full max-w-sm lg:mx-0">
            {/* No real headshot on file yet — an honest monogram, not a stand-in photo. */}
            <div className="group relative aspect-[4/5] overflow-hidden bg-mk-black" aria-hidden>
              <div className="mk-grid absolute inset-0 opacity-70" />
              <div className="absolute -bottom-1/4 -right-1/4 h-3/4 w-3/4 rounded-full bg-mk-navy blur-2xl transition-transform duration-700 group-hover:scale-125" />
              <span className="absolute inset-0 flex items-center justify-center text-[7rem] font-semibold tracking-[-0.06em] text-white">
                {initials}
              </span>
            </div>
            <span className="absolute -bottom-4 left-6 inline-flex items-center gap-2 bg-mk-navy px-4 py-2.5 text-sm text-white">
              <MapPin className="h-4 w-4" aria-hidden />
              {COMPANY_LOCATION}
            </span>
          </Reveal>
          <Reveal i={1}>
            <Eyebrow>Who&apos;s behind Trenston</Eyebrow>
            <h2 className="mt-6 text-5xl font-semibold tracking-[-0.04em] md:text-6xl">{FOUNDER_NAME}</h2>
            <p className="mt-2 text-sm font-semibold uppercase tracking-[0.16em] text-mk-gray">{FOUNDER_ROLE}</p>
            <p className="mt-8 max-w-xl text-xl leading-relaxed text-mk-black">{FOUNDER_NOTE}</p>
            <div className="mt-10 flex flex-wrap gap-3">
              <a
                href={FOUNDER_LINKEDIN_URL}
                target="_blank"
                rel="noopener noreferrer"
                data-testid="founder-linkedin"
                className="mk-btn mk-btn-dark"
              >
                <Linkedin className="h-4 w-4" aria-hidden />
                <span>LinkedIn</span>
              </a>
              <a id="contact" href={PUBLIC_CONTACT_MAILTO} data-testid="founder-contact" className="mk-btn mk-btn-outline-dark">
                <Mail className="h-4 w-4" aria-hidden />
                <span>{PUBLIC_CONTACT_EMAIL}</span>
              </a>
            </div>
          </Reveal>
        </div>
      </section>

      {/* Mission & vision */}
      <section className="bg-mk-mist px-6 py-24 md:py-28">
        <div className="mx-auto grid max-w-7xl gap-5 md:grid-cols-2">
          {[
            { icon: Compass, label: "Our mission", body: MISSION },
            { icon: TrendingUp, label: "Where we're headed", body: VISION },
          ].map(({ icon: Icon, label, body }, i) => (
            <Reveal key={label} i={i} className="mk-card group p-8 md:p-10">
              <span className="mk-icon-tile">
                <Icon className="h-5 w-5" aria-hidden />
              </span>
              <h2 className="mt-8 text-3xl font-semibold tracking-[-0.03em]">{label}</h2>
              <p className="mt-4 leading-relaxed text-mk-gray">{body}</p>
            </Reveal>
          ))}
        </div>
      </section>

      {/* Who it's for */}
      <section className="bg-white px-6 py-24 md:py-28">
        <div className="mx-auto max-w-7xl">
          <SectionHeader eyebrow="Customers" title="Who Trenston is for." />
          <div className="mt-14 grid gap-5 md:grid-cols-3">
            {WHO_HELM_IS_FOR.map((item, i) => {
              const Icon = WHO_ICONS[item.title] || Building2;
              return (
                <Reveal key={item.title} i={i} className="mk-card group p-8">
                  <span className="mk-icon-tile">
                    <Icon className="h-5 w-5" aria-hidden />
                  </span>
                  <h3 className="mt-8 text-xl font-semibold leading-snug tracking-tight">{item.title}</h3>
                  <p className="mt-3 leading-relaxed text-mk-gray">{item.body}</p>
                </Reveal>
              );
            })}
          </div>
        </div>
      </section>

      {/* Values — black band */}
      <section className="bg-mk-black px-6 py-24 text-white md:py-32" data-testid="about-values">
        <div className="mx-auto max-w-7xl">
          <SectionHeader dark eyebrow="Principles" title="What we believe." />
          <div className="mt-14 grid gap-5 md:grid-cols-3">
            {VALUES.map((v, i) => {
              const Icon = VALUE_ICONS[v.title] || Sparkles;
              return (
                <Reveal key={v.title} i={i} className="mk-card mk-card-dark group flex flex-col p-8">
                  <div className="flex items-start justify-between">
                    <span className="mk-icon-tile">
                      <Icon className="h-5 w-5" aria-hidden />
                    </span>
                    <span className="font-mono text-sm text-mk-gray-dark">0{i + 1}</span>
                  </div>
                  <h3 className="mt-10 text-2xl font-semibold tracking-tight">{v.title}</h3>
                  <p className="mt-3 leading-relaxed text-mk-gray-dark">{v.body}</p>
                </Reveal>
              );
            })}
          </div>
        </div>
      </section>

      {/* Differentiator */}
      <section className="bg-white px-6 py-24 md:py-28">
        <div className="mx-auto grid max-w-7xl gap-12 lg:grid-cols-[0.8fr_1.2fr]">
          <Reveal>
            <Eyebrow>The difference</Eyebrow>
            <h2 className="mt-5 text-4xl font-semibold leading-[1.02] tracking-[-0.035em] md:text-5xl">
              What makes Trenston different.
            </h2>
          </Reveal>
          <Reveal i={1}>
            <DrawLine className="bg-mk-navy" />
            <p className="mt-8 text-xl leading-relaxed text-mk-black">{ABOUT_DIFFERENTIATOR}</p>
          </Reveal>
        </div>
      </section>

      <CtaBand
        title={TAGLINE}
        sub="See the cockpit for yourself. Free to start, 7-day free trials on paid plans."
        authed={authed}
        onEnter={enter}
        secondary={<MkButton variant="outline-light" to="/features">See all features</MkButton>}
      />
    </MkPage>
  );
}
