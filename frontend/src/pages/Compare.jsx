import { useEffect } from "react";
import { Check, Minus } from "lucide-react";
import {
  CtaBand,
  MkButton,
  MkPage,
  PageHero,
  Reveal,
  RuledItem,
  SectionHeader,
} from "@/components/marketing/mk";
import { useMarketingAuth } from "@/hooks/useMarketingAuth";
import { CATEGORY } from "@/lib/marketingCopy";
import content from "@/lib/compareContent.json";

/**
 * How Trenston compares to types of tools. No competitor is named: the
 * categories are described in general terms and every Trenston statement is
 * backed by shipped behavior. Copy lives in compareContent.json (also read by
 * the static prerender).
 */
export default function Compare() {
  const { authed, enter } = useMarketingAuth();
  useEffect(() => {
    window.scrollTo(0, 0);
  }, []);

  return (
    <MkPage authed={authed} onEnter={enter} active="/compare">
      <PageHero
        eyebrow={CATEGORY}
        lines={["How Trenston", "is different."]}
        sub="Most founders run a company across spreadsheets, dashboards, chat and finance tools. Here is an honest look at where Trenston fits, and where it does not."
        toc={[
          { id: "types", label: "Compared with the tools you use now" },
          { id: "jobs", label: "Job by job" },
          { id: "limits", label: "What Trenston is not" },
          { id: "elsewhere", label: "When another tool is the better choice" },
        ]}
      />

      <section id="types" className="scroll-mt-16 bg-white px-6 py-20 md:py-28" aria-label="Compared with other types of tools">
        <div className="mx-auto max-w-7xl">
          <SectionHeader
            eyebrow="Types of tools"
            title="Compared with the tools you use now."
            intro="Each type of tool is good at something. Here is what that is, where it tends to fall short for running a whole company, and what Trenston does about it."
          />
          <div className="mt-14 grid gap-x-10 gap-y-14 md:grid-cols-2">
            {content.categories.map((c, i) => (
              <RuledItem key={c.id} index={i + 1} title={c.title} i={i}>
                <dl className="mt-4 space-y-4 text-[0.9375rem] leading-relaxed">
                  <div>
                    <dt className="text-xs font-semibold uppercase tracking-[0.14em] text-mk-gray">Good at</dt>
                    <dd className="mt-1 text-mk-black">{c.goodFor}</dd>
                  </div>
                  <div>
                    <dt className="text-xs font-semibold uppercase tracking-[0.14em] text-mk-gray">Where it can fall short</dt>
                    <dd className="mt-1 text-mk-gray">{c.gap}</dd>
                  </div>
                  <div>
                    <dt className="text-xs font-semibold uppercase tracking-[0.14em] text-mk-navy">What Trenston does</dt>
                    <dd className="mt-1 text-mk-black">{c.trenston}</dd>
                  </div>
                </dl>
              </RuledItem>
            ))}
          </div>
        </div>
      </section>

      <section id="jobs" className="scroll-mt-16 bg-mk-mist px-6 py-20 md:py-28" aria-label="Job by job">
        <div className="mx-auto max-w-7xl">
          <SectionHeader
            eyebrow="Job by job"
            title="Seven everyday jobs, side by side."
            intro="The common approach column describes how these jobs are often handled with general-purpose tools. It will not match every team or every tool."
          />
          <Reveal className="mt-12 overflow-x-auto">
            <table className="w-full min-w-[640px] border-collapse text-left">
              <caption className="sr-only">Common approach compared with Trenston for seven everyday jobs</caption>
              <thead>
                <tr className="border-b border-mk-line text-xs font-semibold uppercase tracking-[0.14em] text-mk-gray">
                  <th scope="col" className="w-1/4 py-4 pr-6">The job</th>
                  <th scope="col" className="w-[30%] py-4 pr-6">Common approach</th>
                  <th scope="col" className="py-4 text-mk-navy">With Trenston</th>
                </tr>
              </thead>
              <tbody>
                {content.rows.map((r) => (
                  <tr key={r.job} className="border-b border-mk-line align-top">
                    <th scope="row" className="py-5 pr-6 text-base font-semibold text-mk-black">{r.job}</th>
                    <td className="py-5 pr-6 text-[0.9375rem] leading-relaxed text-mk-gray">{r.common}</td>
                    <td className="py-5 text-[0.9375rem] leading-relaxed text-mk-black">{r.trenston}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Reveal>
        </div>
      </section>

      <section id="limits" className="scroll-mt-16 bg-white px-6 py-20 md:py-28" aria-label="What Trenston is not">
        <div className="mx-auto grid max-w-7xl gap-12 lg:grid-cols-[0.8fr_1.2fr]">
          <SectionHeader
            eyebrow="Straight talk"
            title="What Trenston is not."
            intro="Knowing the limits helps you decide faster. These are the boundaries today."
            className="md:items-start lg:self-start"
          />
          <Reveal i={1}>
            <ul className="border-t border-mk-line">
              {content.notList.map((t) => (
                <li key={t} className="flex gap-4 border-b border-mk-line py-5 text-[0.9375rem] leading-relaxed text-mk-black">
                  <Minus className="mt-1 h-4 w-4 shrink-0 text-mk-gray" aria-hidden />
                  <span>{t}</span>
                </li>
              ))}
            </ul>
          </Reveal>
        </div>
      </section>

      <section id="elsewhere" className="scroll-mt-16 bg-mk-mist px-6 py-20 md:py-28" aria-label="When another tool is the better choice">
        <div className="mx-auto grid max-w-7xl gap-12 lg:grid-cols-[0.8fr_1.2fr]">
          <SectionHeader
            eyebrow="Fit"
            title="When another tool is the better choice."
            intro="Trenston works best on top of the tools you already trust, not instead of all of them."
            className="md:items-start lg:self-start"
          />
          <Reveal i={1}>
            <ul className="border-t border-mk-line">
              {content.betterElsewhere.map((t) => (
                <li key={t} className="flex gap-4 border-b border-mk-line py-5 text-[0.9375rem] leading-relaxed text-mk-black">
                  <Check className="mt-1 h-4 w-4 shrink-0 text-mk-navy" aria-hidden />
                  <span>{t}</span>
                </li>
              ))}
            </ul>
            <p className="mt-8 text-xs leading-relaxed text-mk-gray" data-testid="compare-disclaimer">
              {content.disclaimer}
            </p>
          </Reveal>
        </div>
      </section>

      <CtaBand
        title="See it for yourself."
        sub="Start on Free, then explore the built-in demo company before you set anything up."
        authed={authed}
        onEnter={enter}
        secondary={
          <MkButton variant="outline-light" to="/integrations">
            See what connects
          </MkButton>
        }
      />
    </MkPage>
  );
}
