import { useEffect } from "react";
import { Clock } from "lucide-react";
import {
  CtaBand,
  Eyebrow,
  MkButton,
  MkPage,
  PageHero,
  Reveal,
  SectionHeader,
} from "@/components/marketing/mk";
import { useMarketingAuth } from "@/hooks/useMarketingAuth";
import {
  PUBLIC_CONTACT_EMAIL,
  PUBLIC_INTEGRATIONS,
  PUBLIC_INTEGRATIONS_ATTRIBUTION,
  PUBLIC_INTEGRATIONS_COMING_SOON,
  PUBLIC_INTEGRATIONS_INTRO,
  TAGLINE,
} from "@/lib/marketingCopy";

/**
 * Brand-adjacent monogram badges, not real vendor logos — trademarked marks
 * need written permission we don't have, so each card gets a colored
 * initial tile instead. Same policy as the in-app Integrations page.
 */
const BRAND_ACCENT = {
  google: "#4285F4",
  quickbooks: "#2CA01C",
  xero: "#13B5EA",
  sap_b1: "#0870D6",
  hubspot: "#FF7A59",
  slack: "#611F69",
};

const NUMBER_WORDS = ["Zero", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten"];

function IntegrationBadge({ id, name }) {
  return (
    <div
      aria-hidden
      className="flex h-14 w-14 shrink-0 items-center justify-center font-mono text-lg font-semibold text-white transition-transform duration-500 group-hover:-rotate-6 group-hover:scale-110"
      style={{ backgroundColor: BRAND_ACCENT[id] || "#0A0A0A" }}
    >
      {name.trim().charAt(0)}
    </div>
  );
}

export default function PublicIntegrations() {
  const { authed, enter } = useMarketingAuth();

  useEffect(() => {
    window.scrollTo(0, 0);
  }, []);

  const requestHref = `mailto:${PUBLIC_CONTACT_EMAIL}?subject=Integration%20request`;
  const count = NUMBER_WORDS[PUBLIC_INTEGRATIONS.length] || String(PUBLIC_INTEGRATIONS.length);

  return (
    <MkPage authed={authed} onEnter={enter} active="/integrations">
      <PageHero eyebrow="Integrations" lines={["Connected", "where it counts."]} sub={PUBLIC_INTEGRATIONS_INTRO}>
        <div className="flex flex-wrap gap-3">
          <MkButton variant="light" onClick={enter}>{authed ? "Open your cockpit" : "Get started free"}</MkButton>
          <MkButton variant="outline-light" href={requestHref}>Request an integration</MkButton>
        </div>
      </PageHero>

      <section className="bg-mk-mist px-6 py-24 md:py-28">
        <div className="mx-auto max-w-7xl">
          <SectionHeader eyebrow="Live today" title={`${count} connections, each with one clear job.`} />
          <div className="mt-14 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {PUBLIC_INTEGRATIONS.map((item, i) => (
              <Reveal
                key={item.id}
                i={i % 3}
                className="mk-card group flex flex-col p-7 md:p-8"
                data-testid={`public-integration-${item.id}`}
              >
                <div className="flex items-start justify-between gap-4">
                  <IntegrationBadge id={item.id} name={item.name} />
                  <span className="inline-flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-mk-gray">
                    <span className="mk-live-dot" aria-hidden />
                    Live
                  </span>
                </div>
                <p className="mt-8 text-xs font-semibold uppercase tracking-[0.16em] text-mk-navy">{item.category}</p>
                <h2 className="mt-2 text-2xl font-semibold tracking-tight text-mk-black">{item.name}</h2>
                <p className="mt-3 flex-1 leading-relaxed text-mk-gray">{item.description}</p>
                <p className="mt-6 border-t border-mk-line pt-5 text-xs font-semibold uppercase tracking-[0.14em] text-mk-black">
                  {item.feeds}
                </p>
                {item.scope ? (
                  <p className="mt-3 border-l-2 border-mk-navy pl-3 text-sm leading-relaxed text-mk-gray">{item.scope}</p>
                ) : null}
              </Reveal>
            ))}
          </div>
          <p className="mx-auto mt-10 max-w-3xl text-center text-xs leading-relaxed text-mk-gray">
            {PUBLIC_INTEGRATIONS_ATTRIBUTION}
          </p>
        </div>
      </section>

      <section className="bg-white px-6 py-24 md:py-28">
        <div className="mx-auto grid max-w-7xl gap-12 lg:grid-cols-[0.8fr_1.2fr]">
          <Reveal>
            <Eyebrow>Coming soon, not shipped</Eyebrow>
            <h2 className="mt-5 text-4xl font-semibold leading-[1.02] tracking-[-0.035em] md:text-5xl">
              Planned connections.
            </h2>
            <p className="mt-5 max-w-md leading-relaxed text-mk-gray">
              These appear in Trenston&apos;s internal catalog as future work. They are not available to connect and
              are not part of today&apos;s product.
            </p>
          </Reveal>
          <div className="space-y-5">
            {PUBLIC_INTEGRATIONS_COMING_SOON.map((item, i) => (
              <Reveal
                key={item.id}
                i={i}
                className="border border-dashed border-mk-gray/40 p-8"
                data-testid={`public-integration-soon-${item.id}`}
              >
                <div className="flex flex-wrap items-center gap-3">
                  <h3 className="text-2xl font-semibold tracking-tight">{item.name}</h3>
                  <span className="inline-flex items-center gap-1.5 border border-mk-line px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-mk-gray">
                    <Clock className="h-3 w-3" aria-hidden />
                    Coming soon
                  </span>
                </div>
                <p className="mt-2 text-xs font-semibold uppercase tracking-[0.16em] text-mk-navy">{item.category}</p>
                <p className="mt-4 leading-relaxed text-mk-gray">{item.description}</p>
              </Reveal>
            ))}
            <Reveal i={1} className="flex flex-col gap-5 bg-mk-navy p-8 text-white sm:flex-row sm:items-center sm:justify-between">
              <div>
                <p className="text-xl font-semibold tracking-tight">Don&apos;t see your stack?</p>
                <p className="mt-1 text-sm text-white/75">Tell us what you run. Requests shape the catalog.</p>
              </div>
              <MkButton variant="light" href={requestHref}>Request an integration</MkButton>
            </Reveal>
          </div>
        </div>
      </section>

      <CtaBand
        title={TAGLINE}
        sub="Connect when it helps. Manual entry stays available everywhere else."
        authed={authed}
        onEnter={enter}
        secondary={<MkButton variant="outline-light" to="/security">How we protect data</MkButton>}
      />
    </MkPage>
  );
}
