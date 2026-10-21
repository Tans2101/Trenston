import { useEffect, useState } from "react";
import { Blocks, CheckCircle2, Gauge, LayoutDashboard, ListChecks, MailCheck, MessagesSquare, ShieldCheck, Type, Wrench } from "lucide-react";
import {
  DISPLAY,
  Eyebrow,
  Mark,
  MkAccordion,
  MkButton,
  MkPage,
  PageHero,
  Reveal,
  RuledItem,
  SectionHeader,
} from "@/components/marketing/mk";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import { useMarketingAuth } from "@/hooks/useMarketingAuth";

/*
 * Copy constants below are also read by scripts/staticPageText.mjs (evalConst)
 * so crawlers get the same text. Keep each one a plain array literal ending in "];".
 */

const OUTCOMES = [
  {
    title: "One picture, not five reports",
    body: "Cash, tasks, open decisions and your own numbers sit on one page, so leadership stops collecting them from different people and files.",
  },
  {
    title: "Decisions that stay visible",
    body: "Open decisions and who owns them stay in view between meetings, so they are not lost in chat threads.",
  },
  {
    title: "Your numbers, your words",
    body: "The views use your departments and your KPIs, not a generic template.",
  },
  {
    title: "Only the right people see it",
    body: "Access is limited to approved work emails at your company, with the same roles and permissions as the rest of Trenston.",
  },
];

const HOW_IT_WORKS = [
  {
    title: "Tell us what you need",
    body: "Send the form below. Say which numbers, departments and tools matter to you. We reply within two business days.",
  },
  {
    title: "We scope it with you",
    body: "A short call to agree the views, data sources and who needs access. You get a fixed quote before any work starts.",
  },
  {
    title: "We build it inside Trenston",
    body: "Your dashboard is built from Trenston's standard blocks plus the parts made only for you. Most of it is proven, tested product.",
  },
  {
    title: "Your team signs in",
    body: "People sign in at trenston.com with their approved work emails. They see your custom dashboard next to everything else in Trenston.",
  },
];

const TIERS = [
  {
    name: "Configured",
    standard: "About 70% standard",
    setup: "From $1,500 setup",
    monthly: "From $249 / month",
    body: "Your metrics, your departments and your layout, built from Trenston's existing blocks.",
  },
  {
    name: "Tailored",
    standard: "About 60% standard",
    setup: "From $3,000 setup",
    monthly: "From $399 / month",
    body: "Everything in Configured, plus new views made for your operation and one custom data source.",
  },
  {
    name: "Bespoke",
    standard: "About 50% standard",
    setup: "From $6,000 setup",
    monthly: "From $699 / month",
    body: "New modules, several integrations and your own workflows, quoted per project.",
  },
];

const INCLUDED = [
  "All of Trenston on the Business plan: Briefing, Financials, Decisions, Tasks, departments and Ask Trenston",
  "Your custom dashboard as its own section, visible only to your company",
  "Access by approved work email, with the same roles and permissions as the rest of Trenston",
  "Hosting, updates and support, plus small changes each month",
  "One invoice from Trenston, no card checkout",
];

const FAQ = [
  {
    q: "What do we get out of it?",
    a: "One view of the numbers and open work your leadership team checks, built around your company, so you spend less time asking people for updates. We do not promise specific savings or results. In scoping we agree what the dashboard shows and how each figure is kept up to date.",
  },
  {
    q: "Do we lose normal Trenston?",
    a: "No. Your company gets all of Trenston, and the custom dashboard is an extra section in the sidebar. Everyone signs in the same way.",
  },
  {
    q: "Who can see the custom dashboard?",
    a: "Only people at your company who sign in with an approved, verified work email. You can also limit it to a named list inside your company.",
  },
  {
    q: "What does standard percentage mean?",
    a: "It is how much of your dashboard is built from Trenston's existing, tested blocks. The rest is made for you. More custom work costs more and takes longer.",
  },
  {
    q: "How long does it take?",
    a: "A Configured dashboard is usually ready in one to two weeks after scoping. Tailored and Bespoke work depends on the data sources involved, and we agree a date in the quote.",
  },
  {
    q: "How do we pay?",
    a: "Half of the setup fee before work starts and half on delivery, then a monthly fee. Trenston invoices you directly.",
  },
  {
    q: "Is this for small companies too?",
    a: "Most small teams are well served by standard Trenston, which you can start free today. Custom dashboards suit larger companies with several departments or their own systems.",
  },
];

const SIZES = [
  ["", "Company size"],
  ["1_10", "1 to 10 people"],
  ["11_50", "11 to 50 people"],
  ["51_200", "51 to 200 people"],
  ["201_1000", "201 to 1,000 people"],
  ["1000_plus", "1,000+ people"],
];

const BUDGETS = [
  ["not_sure", "Not sure yet"],
  ["under_2k", "Under $2,000"],
  ["2k_5k", "$2,000 to $5,000"],
  ["5k_10k", "$5,000 to $10,000"],
  ["10k_plus", "$10,000+"],
];

const STEP_ICONS = [MessagesSquare, Wrench, Blocks, MailCheck];
const OUTCOME_ICONS = [Gauge, ListChecks, Type, ShieldCheck];

const field = "w-full border border-mk-line bg-white px-4 py-3 text-[0.9375rem] text-mk-black placeholder:text-mk-gray focus:border-mk-black focus:outline-none";
const fieldLabel = "mb-2 block text-sm font-medium text-mk-black";

function InquiryForm() {
  const [form, setForm] = useState({
    name: "", email: "", company: "", role: "", company_size: "", tools: "", needs: "", budget_range: "not_sure", website: "",
  });
  const [state, setState] = useState("idle");
  const [error, setError] = useState("");
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    setState("sending");
    setError("");
    try {
      await api.post("/custom-dashboards/inquiry", form);
      setState("sent");
    } catch (err) {
      const detail = err?.response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Could not send. Email contact@trenston.com instead.");
      setState("idle");
    }
  };

  if (state === "sent") {
    return (
      <div className="border border-mk-black p-8" data-testid="custom-inquiry-sent" role="status">
        <CheckCircle2 className="h-7 w-7 text-mk-navy" aria-hidden />
        <h3 className="mt-4 text-2xl font-semibold tracking-tight">Thanks, we have it.</h3>
        <p className="mt-3 text-mk-gray">
          We will reply to {form.email} within two business days to set up a short scoping call.
        </p>
      </div>
    );
  }

  return (
    <form onSubmit={submit} className="grid gap-5 sm:grid-cols-2" data-testid="custom-inquiry-form" noValidate={false}>
      <div>
        <label className={fieldLabel} htmlFor="ci-name">Your name</label>
        <input id="ci-name" className={field} required maxLength={120} value={form.name} onChange={set("name")} autoComplete="name" />
      </div>
      <div>
        <label className={fieldLabel} htmlFor="ci-email">Work email</label>
        <input id="ci-email" className={field} type="email" required value={form.email} onChange={set("email")} autoComplete="email" />
      </div>
      <div>
        <label className={fieldLabel} htmlFor="ci-company">Company</label>
        <input id="ci-company" className={field} required maxLength={160} value={form.company} onChange={set("company")} autoComplete="organization" />
      </div>
      <div>
        <label className={fieldLabel} htmlFor="ci-role">Your role</label>
        <input id="ci-role" className={field} maxLength={120} value={form.role} onChange={set("role")} placeholder="CEO, COO, Head of Finance" />
      </div>
      <div>
        <label className={fieldLabel} htmlFor="ci-size">Company size</label>
        <select id="ci-size" className={field} value={form.company_size} onChange={set("company_size")}>
          {SIZES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
      </div>
      <div>
        <label className={fieldLabel} htmlFor="ci-budget">Budget range</label>
        <select id="ci-budget" className={field} value={form.budget_range} onChange={set("budget_range")}>
          {BUDGETS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
      </div>
      <div className="sm:col-span-2">
        <label className={fieldLabel} htmlFor="ci-tools">Tools you use today</label>
        <input id="ci-tools" className={field} maxLength={1000} value={form.tools} onChange={set("tools")} placeholder="QuickBooks, SAP, Excel, HubSpot" />
      </div>
      <div className="sm:col-span-2">
        <label className={fieldLabel} htmlFor="ci-needs">What do you want to see?</label>
        <textarea
          id="ci-needs" className={cn(field, "min-h-[140px]")} required maxLength={4000}
          value={form.needs} onChange={set("needs")}
          placeholder="The numbers you check every day, the departments involved, and what you want to stop chasing people for."
        />
      </div>
      {/* Hidden from people; bots fill it in. */}
      <div aria-hidden="true" className="absolute -left-[9999px] h-0 w-0 overflow-hidden">
        <label htmlFor="ci-website">Website</label>
        <input id="ci-website" tabIndex={-1} autoComplete="off" value={form.website} onChange={set("website")} />
      </div>
      {error ? <p className="text-sm text-red-700 sm:col-span-2" role="alert">{error}</p> : null}
      <div className="flex flex-wrap items-center gap-4 sm:col-span-2">
        <button type="submit" className="mk-btn mk-btn-dark" disabled={state === "sending"} data-testid="custom-inquiry-submit">
          <span>{state === "sending" ? "Sending" : "Request a custom dashboard"}</span>
        </button>
        <p className="text-sm text-mk-gray">Prices are confirmed after a scoping call. A budget range just helps us plan.</p>
      </div>
    </form>
  );
}

export default function CustomDashboards() {
  const { authed, enter } = useMarketingAuth();
  useEffect(() => {
    window.scrollTo(0, 0);
  }, []);

  return (
    <MkPage authed={authed} onEnter={enter} active="/custom">
      <PageHero
        eyebrow="Custom dashboards"
        lines={["Know where your company", <>stands, <Mark dark>without asking.</Mark></>]}
        sub="A dashboard built around your numbers, departments and systems, inside Trenston. Your leadership team sees one picture instead of chasing updates, and only approved people at your company can open it."
        size="md"
      >
        <div className="flex flex-wrap gap-3">
          <MkButton variant="light" href="#request">Request a custom dashboard</MkButton>
          <MkButton variant="outline-light" to="/pricing" arrow={false}>See standard plans</MkButton>
        </div>
      </PageHero>

      <section className="mx-auto max-w-7xl px-6 py-20 md:py-24">
        <SectionHeader eyebrow="What changes" title="Less chasing. More of your company in one place." />
        <div className="mt-14 grid gap-x-10 gap-y-12 sm:grid-cols-2 lg:grid-cols-4">
          {OUTCOMES.map((s, i) => (
            <RuledItem key={s.title} icon={OUTCOME_ICONS[i]} index={i + 1} title={s.title} body={s.body} i={i} />
          ))}
        </div>
      </section>

      <section className="border-t border-mk-line mx-auto max-w-7xl px-6 py-20 md:py-24">
        <SectionHeader eyebrow="How it works" title="From first message to your team signing in." />
        <div className="mt-14 grid gap-x-10 gap-y-12 sm:grid-cols-2 lg:grid-cols-4">
          {HOW_IT_WORKS.map((s, i) => (
            <RuledItem key={s.title} icon={STEP_ICONS[i]} index={i + 1} title={s.title} body={s.body} i={i} />
          ))}
        </div>
      </section>

      <section className="border-t border-mk-line bg-white">
        <div className="mx-auto max-w-7xl px-6 py-20 md:py-24">
          <SectionHeader
            eyebrow="Pricing"
            title="Three levels of custom."
            intro="Every custom dashboard is part standard Trenston and part made for you. The more that is made for you, the more it costs."
          />
          <div className="mt-12 grid gap-6 lg:grid-cols-3">
            {TIERS.map((t, i) => (
              <Reveal key={t.name} i={i} className="flex flex-col border border-mk-black p-8" data-testid={`custom-tier-${t.name.toLowerCase()}`}>
                <Eyebrow>{t.standard}</Eyebrow>
                <h3 className={cn("mt-4 text-3xl", DISPLAY)}>{t.name}</h3>
                <p className="mt-4 text-mk-gray">{t.body}</p>
                <div className="mt-auto pt-8">
                  <p className="text-lg font-semibold">{t.setup}</p>
                  <p className="text-mk-gray">{t.monthly}</p>
                </div>
              </Reveal>
            ))}
          </div>
          <Reveal className="mt-12 grid gap-8 lg:grid-cols-[1fr_1.4fr]">
            <div className="flex items-start gap-3">
              <LayoutDashboard className="mt-1 h-6 w-6 shrink-0 text-mk-navy" aria-hidden />
              <h3 className="text-2xl font-semibold tracking-tight">Every level includes</h3>
            </div>
            <ul className="border-t border-mk-black">
              {INCLUDED.map((line) => (
                <li key={line} className="flex gap-3 border-b border-mk-line py-4 text-[0.9375rem]">
                  <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-mk-navy" aria-hidden />
                  {line}
                </li>
              ))}
            </ul>
          </Reveal>
        </div>
      </section>

      <section id="request" className="border-t border-mk-line bg-mk-mist scroll-mt-24">
        <div className="mx-auto grid max-w-7xl gap-12 px-6 py-20 md:py-24 lg:grid-cols-[1fr_1.6fr]">
          <Reveal>
            <Eyebrow>Request</Eyebrow>
            <h2 className={cn("mt-4 text-4xl leading-[1.05] md:text-[3.25rem]", DISPLAY)}>Tell us what you want to see.</h2>
            <p className="mt-6 text-lg leading-relaxed text-mk-gray">
              There is no checkout for custom work. Send the form, we talk it through with you, and you get a fixed quote.
            </p>
            <p className="mt-6 text-mk-gray">
              Prefer email? <a className="mk-link" href="mailto:contact@trenston.com">contact@trenston.com</a>
            </p>
          </Reveal>
          <Reveal i={1}>
            <InquiryForm />
          </Reveal>
        </div>
      </section>

      <section className="mx-auto max-w-4xl px-6 py-20 md:py-24">
        <SectionHeader eyebrow="Questions" title="Custom dashboards, answered." />
        <div className="mt-10">
          <MkAccordion items={FAQ} idPrefix="custom-faq" />
        </div>
      </section>
    </MkPage>
  );
}
