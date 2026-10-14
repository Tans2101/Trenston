import { INTEGRATIONS_SHOWCASE } from "@/lib/marketingCopy";
import { MkLink, SectionHeader } from "@/components/marketing/mk";
import BrandLogo, { integrationIdFor } from "@/components/BrandLogo";

function MarqueeItem({ item }) {
  return (
    <li className="mk-marquee__item">
      <BrandLogo id={integrationIdFor(item.name)} className="h-8 w-8 shrink-0" />
      <span className="mk-marquee__name">{item.name}</span>
    </li>
  );
}

export default function IntegrationsShowcase({ compact = false }) {
  // Two identical halves; the track slides left by exactly one half, so the loop has no seam.
  const half = [...INTEGRATIONS_SHOWCASE, ...INTEGRATIONS_SHOWCASE];
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
      </div>

      {/* Screen readers get a plain list; the moving strip is decoration. */}
      <ul className="sr-only">
        {INTEGRATIONS_SHOWCASE.map((item) => (
          <li key={item.name}>{item.name}, {item.note}</li>
        ))}
      </ul>
      <div className="mk-marquee mt-14" aria-hidden data-testid="integrations-marquee">
        <div className="mk-marquee__track">
          {[0, 1].map((copy) => (
            <ul key={copy} className="mk-marquee__half">
              {half.map((item, i) => <MarqueeItem key={`${copy}-${i}`} item={item} />)}
            </ul>
          ))}
        </div>
      </div>

      <div className="mx-auto max-w-7xl">
        <p className="mt-8 max-w-2xl text-sm leading-relaxed text-mk-gray" data-testid="integrations-trust">
          Our QuickBooks connection is approved by Intuit as a developer app, and Trenston only reads your accounting data.
        </p>
      </div>
    </section>
  );
}
