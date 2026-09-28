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
  DISPLAY,
  DrawLine,
  Eyebrow,
  MkButton,
  MkPage,
  PageHero,
  Reveal,
  RuledItem,
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
import { cn } from "@/lib/utils";

/** WHO_HELM_IS_FOR and VALUES have no icon field in marketingCopy.js (also
 * read by marketingClaimsVerification.test.js) — map by title here instead
 * of changing that shared shape. */
const WHO_ICONS = {
  "Founders building the company": Users,
  "Owner-operators and traditional businesses": Building2,
  "CEOs and leadership teams": Briefcase,
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

const TOC = [
  { id: "what", label: "What Trenston is" },
  { id: "why", label: "Why we built it" },
  { id: "founder", label: "Who's behind it" },
  { id: "customers", label: "Who it's for" },
  { id: "principles", label: "What we believe" },
];

export default function About() {
  const { authed, enter } = useMarketingAuth();
  useEffect(() => { window.scrollTo(0, 0); }, []);

  const initials = FOUNDER_NAME.split(" ").map((n) => n[0]).join("");

  return (
    <MkPage authed={authed} onEnter={enter} active="/about">
      <PageHero eyebrow="About us" lines={["About", "Trenston."]} sub={MISSION} toc={TOC} />

      {/* What it is + key facts */}
      <section id="what" className="scroll-mt-16 bg-white px-6 py-24 md:py-28" data-testid="about-facts">
        <div className="mx-auto grid max-w-7xl gap-16 lg:grid-cols-[1.3fr_1fr]">
          <Reveal>
            <Eyebrow>What Trenston is</Eyebrow>
            <p className={cn("mt-6 text-2xl leading-[1.4] text-mk-black md:text-[1.85rem]", DISPLAY)}>
              {WHAT_TRENSTON_IS}
            </p>
          </Reveal>
          <dl className="self-end border-t border-mk-black">
            {FACTS.map((f, i) => (
              <Reveal key={f.label} i={i} className="grid grid-cols-[8rem_1fr] gap-4 border-b border-mk-line py-5">
                <dt className="text-xs font-semibold uppercase tracking-[0.14em] text-mk-navy">{f.label}</dt>
                <dd className="leading-snug text-mk-black">{f.value}</dd>
              </Reveal>
            ))}
          </dl>
        </div>
      </section>

      {/* Why we built it — flat black band, pull quote + story */}
      <section id="why" className="scroll-mt-16 bg-mk-black px-6 py-24 text-white md:py-28">
        <div className="mx-auto max-w-7xl">
          <Eyebrow dark>Why we built Trenston</Eyebrow>
          <div className="mt-10 grid gap-14 lg:grid-cols-[1.15fr_1fr]">
            <Reveal>
              <p className={cn("text-3xl leading-[1.25] md:text-[2.5rem]", DISPLAY)}>“{ABOUT_PROBLEM}”</p>
            </Reveal>
            <Reveal i={1}>
              <DrawLine className="bg-white/40" />
              <p className="mt-6 text-xs font-semibold uppercase tracking-[0.16em] text-mk-gray-dark">What we built</p>
              <p className="mt-4 leading-relaxed text-mk-gray-dark">{ABOUT_STORY}</p>
            </Reveal>
          </div>
        </div>
      </section>

      {/* Founder */}
      <section id="founder" className="scroll-mt-16 bg-white px-6 py-24 md:py-28" data-testid="about-founder">
        <div className="mx-auto grid max-w-7xl items-center gap-14 lg:grid-cols-[0.8fr_1.2fr]">
          <Reveal className="mx-auto w-full max-w-sm lg:mx-0">
            {/* No real headshot on file yet — an honest monogram, not a stand-in photo. */}
            <div className="relative flex aspect-[4/5] items-end bg-mk-black p-8" aria-hidden>
              <span className="absolute left-8 top-8 text-xs font-semibold uppercase tracking-[0.16em] text-mk-gray-dark">
                {FOUNDER_ROLE}
              </span>
              <span className="text-[7rem] font-medium leading-none tracking-[-0.05em] text-white">{initials}</span>
            </div>
            <p className="mt-4 flex items-center gap-2 text-sm text-mk-gray">
              <MapPin className="h-4 w-4 text-mk-navy" aria-hidden />
              {COMPANY_LOCATION}
            </p>
          </Reveal>
          <Reveal i={1}>
            <Eyebrow>Who&apos;s behind Trenston</Eyebrow>
            <h2 className={cn("mt-5 text-5xl md:text-6xl", DISPLAY)}>{FOUNDER_NAME}</h2>
            <p className="mt-2 text-sm font-semibold uppercase tracking-[0.14em] text-mk-gray">{FOUNDER_ROLE}</p>
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
        <div className="mx-auto grid max-w-7xl gap-12 md:grid-cols-2">
          <RuledItem icon={Compass} title="Our mission" body={MISSION} />
          <RuledItem icon={TrendingUp} i={1} title="Where we're headed" body={VISION} />
        </div>
      </section>

      {/* Who it's for */}
      <section id="customers" className="scroll-mt-16 bg-white px-6 py-24 md:py-28">
        <div className="mx-auto max-w-7xl">
          <SectionHeader eyebrow="Customers" title="Who Trenston is for." />
          <div className="mt-14 grid gap-12 md:grid-cols-3 md:gap-10">
            {WHO_HELM_IS_FOR.map((item, i) => (
              <RuledItem key={item.title} i={i} icon={WHO_ICONS[item.title] || Building2} title={item.title} body={item.body} />
            ))}
          </div>
        </div>
      </section>

      {/* Values — black band */}
      <section id="principles" className="scroll-mt-16 bg-mk-black px-6 py-24 text-white md:py-28" data-testid="about-values">
        <div className="mx-auto max-w-7xl">
          <SectionHeader dark eyebrow="Principles" title="What we believe." />
          <div className="mt-14 grid gap-12 md:grid-cols-3 md:gap-10">
            {VALUES.map((v, i) => (
              <RuledItem key={v.title} dark i={i} index={i + 1} icon={VALUE_ICONS[v.title] || Sparkles} title={v.title} body={v.body} />
            ))}
          </div>
        </div>
      </section>

      {/* Differentiator */}
      <section className="bg-white px-6 py-24 md:py-28">
        <div className="mx-auto grid max-w-7xl gap-12 lg:grid-cols-[0.8fr_1.2fr]">
          <Reveal>
            <Eyebrow>The difference</Eyebrow>
            <h2 className={cn("mt-4 text-4xl leading-[1.05] md:text-5xl", DISPLAY)}>What makes Trenston different.</h2>
          </Reveal>
          <Reveal i={1}>
            <DrawLine className="bg-mk-black" />
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
