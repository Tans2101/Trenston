import { useEffect } from "react";
import { Navigate, useParams } from "react-router-dom";
import { Check, ExternalLink } from "lucide-react";
import {
  CtaBand,
  MkButton,
  MkLink,
  MkPage,
  PageHero,
  Reveal,
  SectionHeader,
  Mark,
} from "@/components/marketing/mk";
import { useMarketingAuth } from "@/hooks/useMarketingAuth";
import { CATEGORY } from "@/lib/marketingCopy";
import content from "@/lib/compareVs.json";

/**
 * One-to-one comparison page. Built to be safe to publish: it only quotes each
 * product's own public wording (with a source link and date), makes no claims
 * about price, performance or missing features, uses plain-text product names,
 * and includes a "when the other tool is the better choice" section. All copy
 * lives in compareVs.json (also read by the static prerender).
 */
export default function CompareVs() {
  const { slug } = useParams();
  const { authed, enter } = useMarketingAuth();
  const page = content.pages.find((p) => p.slug === slug);

  useEffect(() => {
    window.scrollTo(0, 0);
  }, [slug]);

  if (!page) return <Navigate to="/compare" replace />;

  return (
    <MkPage authed={authed} onEnter={enter} active="/compare">
      <PageHero
        eyebrow={CATEGORY}
        lines={["Trenston vs", <><Mark dark>{page.name}</Mark>.</>]}
        sub={page.heroSub}
        toc={[
          { id: "says", label: `What ${page.short} says it is` },
          { id: "side", label: "Side by side" },
          { id: "choose", label: "Which to use" },
        ]}
      />

      <section id="says" className="scroll-mt-16 bg-white px-6 py-20 md:py-28" aria-label={`What ${page.short} says it is`}>
        <div className="mx-auto grid max-w-7xl gap-12 lg:grid-cols-[0.8fr_1.2fr]">
          <SectionHeader
            eyebrow="In their own words"
            title={`What ${page.short} says it is.`}
            intro={`Quoted from the product's own pages, as of ${content.asOf}. Check the source for the current wording.`}
            className="md:items-start lg:self-start"
          />
          <Reveal i={1}>
            <ul className="border-t border-mk-line">
              {page.sources.map((s) => (
                <li key={s.quote} className="border-b border-mk-line py-6">
                  <p className="text-lg leading-snug text-mk-black">&ldquo;{s.quote}&rdquo;</p>
                  <p className="mt-3 text-sm text-mk-gray">
                    {s.tool}.{" "}
                    <a
                      href={s.url}
                      target="_blank"
                      rel="noopener noreferrer nofollow"
                      className="inline-flex items-center gap-1 text-mk-navy underline underline-offset-2"
                    >
                      {s.label}
                      <ExternalLink className="h-3.5 w-3.5" aria-hidden />
                    </a>
                  </p>
                </li>
              ))}
            </ul>
          </Reveal>
        </div>
      </section>

      <section id="side" className="scroll-mt-16 bg-mk-mist px-6 py-20 md:py-28" aria-label="Side by side">
        <div className="mx-auto max-w-7xl">
          <SectionHeader
            eyebrow="Side by side"
            title="Two different jobs."
            intro={content.howToRead}
          />
          <Reveal className="mt-12 overflow-x-auto">
            <table className="w-full min-w-[640px] border-collapse text-left">
              <caption className="sr-only">{page.name} and Trenston described side by side</caption>
              <thead>
                <tr className="border-b border-mk-line text-xs font-semibold uppercase tracking-[0.14em] text-mk-gray">
                  <th scope="col" className="w-1/4 py-4 pr-6"><span className="sr-only">Topic</span></th>
                  <th scope="col" className="w-[37%] py-4 pr-6">{page.name}, as described by its maker</th>
                  <th scope="col" className="py-4 text-mk-navy">Trenston</th>
                </tr>
              </thead>
              <tbody>
                {page.rows.map((r) => (
                  <tr key={r.label} className="border-b border-mk-line align-top">
                    <th scope="row" className="py-5 pr-6 text-base font-semibold text-mk-black">{r.label}</th>
                    <td className="py-5 pr-6 text-[0.9375rem] leading-relaxed text-mk-gray">{r.tool}</td>
                    <td className="py-5 text-[0.9375rem] leading-relaxed text-mk-black">{r.trenston}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Reveal>
          <div className="mt-14 grid gap-10 md:grid-cols-2">
            <Reveal>
              <h3 className="text-xl font-semibold tracking-tight text-mk-black">What Trenston is</h3>
              <ul className="mt-4 border-t border-mk-line">
                {content.trenstonIs.map((t) => (
                  <li key={t} className="flex gap-4 border-b border-mk-line py-4 text-[0.9375rem] leading-relaxed text-mk-black">
                    <Check className="mt-1 h-4 w-4 shrink-0 text-mk-navy" aria-hidden />
                    <span>{t}</span>
                  </li>
                ))}
              </ul>
            </Reveal>
            <Reveal i={1}>
              <h3 className="text-xl font-semibold tracking-tight text-mk-black">What Trenston is not</h3>
              <ul className="mt-4 border-t border-mk-line">
                {content.trenstonIsNot.map((t) => (
                  <li key={t} className="border-b border-mk-line py-4 text-[0.9375rem] leading-relaxed text-mk-black">{t}</li>
                ))}
              </ul>
            </Reveal>
          </div>
        </div>
      </section>

      <section id="choose" className="scroll-mt-16 bg-white px-6 py-20 md:py-28" aria-label="Which to use">
        <div className="mx-auto max-w-7xl">
          <SectionHeader
            eyebrow="Which to use"
            title="Pick the one that fits the job."
            intro={page.together}
          />
          <div className="mt-14 grid gap-12 md:grid-cols-2">
            <Reveal>
              <h3 className="text-xl font-semibold tracking-tight text-mk-black" data-testid="compare-vs-other-better">
                When {page.short} is the better choice
              </h3>
              <ul className="mt-4 border-t border-mk-line">
                {page.useToolWhen.map((t) => (
                  <li key={t} className="flex gap-4 border-b border-mk-line py-4 text-[0.9375rem] leading-relaxed text-mk-black">
                    <Check className="mt-1 h-4 w-4 shrink-0 text-mk-gray" aria-hidden />
                    <span>{t}</span>
                  </li>
                ))}
              </ul>
            </Reveal>
            <Reveal i={1}>
              <h3 className="text-xl font-semibold tracking-tight text-mk-black">When Trenston may fit</h3>
              <ul className="mt-4 border-t border-mk-line">
                {page.useTrenstonWhen.map((t) => (
                  <li key={t} className="flex gap-4 border-b border-mk-line py-4 text-[0.9375rem] leading-relaxed text-mk-black">
                    <Check className="mt-1 h-4 w-4 shrink-0 text-mk-navy" aria-hidden />
                    <span>{t}</span>
                  </li>
                ))}
              </ul>
            </Reveal>
          </div>
          <div className="mt-14 space-y-3 text-xs leading-relaxed text-mk-gray" data-testid="compare-vs-disclaimer">
            <p>As of {content.asOf}.</p>
            <p>{content.trademarks}</p>
            <p>{content.notAdvice}</p>
          </div>
          <nav aria-label="Other comparisons" className="mt-10 flex flex-wrap gap-x-8 gap-y-3 text-sm">
            <MkLink to="/compare" className="text-mk-navy">All comparisons</MkLink>
            {content.pages
              .filter((p) => p.slug !== page.slug)
              .map((p) => (
                <MkLink key={p.slug} to={`/compare/${p.slug}`} className="text-mk-navy">
                  Trenston vs {p.name}
                </MkLink>
              ))}
          </nav>
        </div>
      </section>

      <CtaBand
        title="See it for yourself."
        sub="Start on Free, then explore the built-in demo company before you set anything up."
        authed={authed}
        onEnter={enter}
        secondary={
          <MkButton variant="outline-light" to="/compare">
            How we compare
          </MkButton>
        }
      />
    </MkPage>
  );
}
