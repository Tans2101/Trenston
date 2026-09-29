import { INTEGRATIONS_SHOWCASE } from "@/lib/marketingCopy";
import { MkLink, Reveal, SectionHeader } from "@/components/marketing/mk";
import BrandLogo, { integrationIdFor } from "@/components/BrandLogo";

/**
 * Vendor logos, monochrome to match the site, shown in the vendor's colour on
 * hover. See PUBLIC_INTEGRATIONS_ATTRIBUTION for the trademark notice.
 */
function IntegrationBadge({ name }) {
  const id = integrationIdFor(name);
  return (
    <div
      aria-hidden
      className="relative flex h-11 w-11 shrink-0 items-center justify-center border border-mk-line bg-white text-mk-black"
    >
      <BrandLogo
        id={id}
        variant="mono"
        className="h-6 w-6 transition-opacity duration-300 group-hover:opacity-0"
      />
      <BrandLogo
        id={id}
        className="absolute h-6 w-6 opacity-0 transition-opacity duration-300 group-hover:opacity-100"
      />
    </div>
  );
}

export default function IntegrationsShowcase({ compact = false }) {
  return (
    <section
      className={`bg-white px-6 ${compact ? "py-20" : "py-24 md:py-28"}`}
      data-testid="integrations-showcase"
      aria-label="Works with"
    >
      <div className="mx-auto max-w-7xl">
        <SectionHeader
          eyebrow="Works with"
          title="Tools your team already uses."
          intro="Connect what you run today. Nothing requires an integration. Manual entry stays available."
          action={<MkLink to="/integrations" className="text-mk-navy">See what each integration does</MkLink>}
        />
        <ul className="mt-14 grid list-none border-t border-mk-black p-0 sm:grid-cols-2 lg:grid-cols-3">
          {INTEGRATIONS_SHOWCASE.map((item, i) => (
            <Reveal
              as="li"
              key={item.name}
              i={i % 3}
              className="group flex items-center gap-5 border-b border-mk-line py-6 sm:pr-8"
            >
              <IntegrationBadge name={item.name} />
              <div>
                <p className="text-lg font-semibold tracking-tight text-mk-black">
                  <span className="mk-title-line">{item.name}</span>
                </p>
                <p className="mt-1 text-xs font-semibold uppercase tracking-[0.14em] text-mk-gray">{item.note}</p>
              </div>
            </Reveal>
          ))}
        </ul>
      </div>
    </section>
  );
}
