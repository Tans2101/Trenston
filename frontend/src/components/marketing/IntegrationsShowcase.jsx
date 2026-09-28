import { INTEGRATIONS_SHOWCASE } from "@/lib/marketingCopy";
import { MkLink, Reveal, SectionHeader } from "@/components/marketing/mk";

/**
 * Monochrome monogram tiles, not real vendor logos — trademarked marks
 * (Google, QuickBooks, Xero, SAP, HubSpot, Slack) need written permission we
 * don't have. Kept black-and-white to match the site; see
 * PUBLIC_INTEGRATIONS_ATTRIBUTION in marketingCopy.js.
 */
function IntegrationBadge({ name }) {
  return (
    <div
      aria-hidden
      className="flex h-11 w-11 shrink-0 items-center justify-center bg-mk-black font-mono text-base font-semibold text-white transition-colors duration-300 group-hover:bg-mk-navy"
    >
      {name.trim().charAt(0)}
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
