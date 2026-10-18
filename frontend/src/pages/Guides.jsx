import { useEffect } from "react";
import { ArrowRight } from "lucide-react";
import { Link } from "react-router-dom";
import { CtaBand, MkButton, MkPage, PageHero, Reveal, SectionHeader, Mark } from "@/components/marketing/mk";
import { useMarketingAuth } from "@/hooks/useMarketingAuth";
import { CATEGORY } from "@/lib/marketingCopy";
import content from "@/lib/guidesContent.json";

/** Hub for the founder guides. Copy lives in guidesContent.json (also read by the static prerender). */
export default function Guides() {
  const { authed, enter } = useMarketingAuth();
  useEffect(() => {
    window.scrollTo(0, 0);
  }, []);

  return (
    <MkPage authed={authed} onEnter={enter} active="/guides">
      <PageHero
        eyebrow={CATEGORY}
        lines={["Guides for", <><Mark dark>founders</Mark> and CEOs.</>]}
        sub={content.hub.intro}
      />
      <section className="bg-white px-6 py-20 md:py-28" aria-label="All guides">
        <div className="mx-auto max-w-7xl">
          <SectionHeader eyebrow="All guides" title="Read, then run your company with it." />
          <ul className="mt-12 border-t border-mk-line">
            {content.guides.map((g, i) => (
              <Reveal as="li" key={g.slug} i={i} className="border-b border-mk-line">
                <Link
                  to={`/guides/${g.slug}`}
                  className="group flex flex-col gap-3 py-8 md:flex-row md:items-center md:justify-between"
                >
                  <div className="max-w-3xl">
                    <h2 className="text-2xl font-semibold tracking-tight text-mk-black">{g.title}</h2>
                    <p className="mt-3 leading-relaxed text-mk-gray">{g.description}</p>
                    <p className="mt-3 text-sm text-mk-gray">{g.readMinutes} min read</p>
                  </div>
                  <ArrowRight className="h-6 w-6 shrink-0 text-mk-navy transition-transform group-hover:translate-x-1" aria-hidden />
                </Link>
              </Reveal>
            ))}
          </ul>
        </div>
      </section>
      <CtaBand
        title="Put it into practice."
        sub="Start on Free, then explore the built-in demo company before you set anything up."
        authed={authed}
        onEnter={enter}
        secondary={<MkButton variant="outline-light" to="/features">See features</MkButton>}
      />
    </MkPage>
  );
}
