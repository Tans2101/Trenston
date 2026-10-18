import { useEffect } from "react";
import { Navigate, useParams } from "react-router-dom";
import { CtaBand, MkButton, MkLink, MkPage, PageHero, Reveal, Mark } from "@/components/marketing/mk";
import { useMarketingAuth } from "@/hooks/useMarketingAuth";
import { CATEGORY } from "@/lib/marketingCopy";
import content from "@/lib/guidesContent.json";

function formatDate(iso) {
  const d = new Date(`${iso}T00:00:00Z`);
  return d.toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric", timeZone: "UTC" });
}

/** One founder guide. Copy lives in guidesContent.json (also read by the static prerender). */
export default function Guide() {
  const { slug } = useParams();
  const { authed, enter } = useMarketingAuth();
  const guide = content.guides.find((g) => g.slug === slug);
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [slug]);
  if (!guide) return <Navigate to="/guides" replace />;
  const others = content.guides.filter((g) => g.slug !== guide.slug);

  return (
    <MkPage authed={authed} onEnter={enter} active="/guides">
      <PageHero eyebrow={CATEGORY} lines={[guide.title.split(" ").slice(0, -2).join(" "), <><Mark dark>{guide.title.split(" ").slice(-2).join(" ")}</Mark>.</>]} sub={guide.intro} />
      <article className="bg-white px-6 py-16 md:py-24">
        <div className="mx-auto max-w-3xl">
          <p className="text-sm text-mk-gray" data-testid="guide-byline">
            By {content.author}, {content.authorRole}. {formatDate(guide.datePublished)}. {guide.readMinutes} min read.
          </p>
          {guide.sections.map((s) => (
            <Reveal key={s.heading} className="mt-12">
              <h2 className="text-2xl font-semibold tracking-tight text-mk-black md:text-3xl">{s.heading}</h2>
              {(s.paragraphs || []).map((p) => (
                <p key={p} className="mt-4 text-lg leading-relaxed text-mk-black">{p}</p>
              ))}
              {s.bullets && (
                <ul className="mt-4 list-disc space-y-3 pl-6 text-lg leading-relaxed text-mk-black">
                  {s.bullets.map((b) => <li key={b}>{b}</li>)}
                </ul>
              )}
            </Reveal>
          ))}
          <Reveal className="mt-16 border-l-4 border-mk-navy bg-mk-mist p-8">
            <h2 className="text-2xl font-semibold tracking-tight text-mk-black">{guide.trenston.heading}</h2>
            {guide.trenston.paragraphs.map((p) => (
              <p key={p} className="mt-4 text-lg leading-relaxed text-mk-black">{p}</p>
            ))}
          </Reveal>
          <nav aria-label="More guides" className="mt-14 flex flex-wrap gap-x-8 gap-y-3 text-sm">
            <MkLink to="/guides" className="text-mk-navy">All guides</MkLink>
            {others.map((g) => <MkLink key={g.slug} to={`/guides/${g.slug}`} className="text-mk-navy">{g.title}</MkLink>)}
          </nav>
        </div>
      </article>
      <CtaBand
        title="See it for yourself."
        sub="Start on Free, then explore the built-in demo company before you set anything up."
        authed={authed}
        onEnter={enter}
        secondary={<MkButton variant="outline-light" to="/features">See features</MkButton>}
      />
    </MkPage>
  );
}
