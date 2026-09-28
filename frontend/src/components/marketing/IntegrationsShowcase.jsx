import { INTEGRATIONS_SHOWCASE } from "@/lib/marketingCopy";
import { MkLink, Reveal, SectionHeader } from "@/components/marketing/mk";

/**
 * Brand-adjacent monogram badges, not real vendor logos — trademarked marks
 * (Google, QuickBooks, Xero, SAP, HubSpot, Slack) need written permission
 * we don't have, so each badge is the integration's initial on a
 * brand-colored tile instead. Same policy as the in-app Integrations page.
 * See PUBLIC_INTEGRATIONS_ATTRIBUTION in marketingCopy.js.
 */
const BRAND_ACCENT = {
  Google: "#4285F4",
  QuickBooks: "#2CA01C",
  Xero: "#13B5EA",
  "SAP Business One": "#0870D6",
  HubSpot: "#FF7A59",
  Slack: "#611F69",
};

function IntegrationBadge({ name }) {
  const color = BRAND_ACCENT[name] || "#0A0A0A";
  return (
    <div
      aria-hidden
      className="flex h-12 w-12 shrink-0 items-center justify-center font-mono text-base font-semibold text-white transition-transform duration-500 group-hover:rotate-[-6deg] group-hover:scale-110"
      style={{ backgroundColor: color }}
    >
      {name.trim().charAt(0)}
    </div>
  );
}

export default function IntegrationsShowcase({ compact = false }) {
  return (
    <section
      className={`bg-white px-6 ${compact ? "py-20" : "py-24 md:py-32"}`}
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
        <ul className="mt-14 grid list-none gap-px border border-mk-line bg-mk-line p-0 sm:grid-cols-2 lg:grid-cols-3">
          {INTEGRATIONS_SHOWCASE.map((item, i) => (
            <Reveal
              as="li"
              key={item.name}
              i={i % 3}
              className="group flex items-center gap-5 bg-white p-6 transition-colors duration-300 hover:bg-mk-mist"
            >
              <IntegrationBadge name={item.name} />
              <div>
                <p className="text-lg font-semibold tracking-tight text-mk-black">{item.name}</p>
                <p className="mt-1 text-xs font-semibold uppercase tracking-[0.14em] text-mk-gray">{item.note}</p>
              </div>
            </Reveal>
          ))}
        </ul>
      </div>
    </section>
  );
}
