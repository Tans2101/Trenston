import { Reveal } from "@/components/marketing/mk";

/**
 * Large quote card for a named customer: dark card, big quote mark, name | role,
 * company logo + site, LinkedIn. No profile photo by design.
 */
export default function TestimonialCard({ item }) {
  if (!item) return null;
  return (
    <Reveal className="mx-auto max-w-5xl">
      <figure
        data-testid="testimonial-card"
        className="flex flex-col gap-6 rounded-[28px] bg-mk-black px-7 py-10 text-white md:flex-row md:gap-10 md:px-14 md:py-14"
      >
        <span aria-hidden className="select-none -mb-6 h-12 text-[96px] font-semibold leading-[0.7] md:mb-0 md:h-auto text-white/90 md:text-[140px]">
          &ldquo;
        </span>
        <div className="min-w-0 flex-1">
          <blockquote className="text-xl font-medium leading-snug tracking-[-0.015em] md:text-[1.75rem]">
            {item.quote}
          </blockquote>
          <figcaption className="mt-8 flex flex-col gap-4">
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-base">
              <span className="font-semibold">{item.name}</span>
              <span aria-hidden className="h-5 w-px bg-white/40" />
              <span className="text-mk-gray-dark">{item.role}</span>
            </div>
            <div className="flex flex-wrap items-center gap-x-5 gap-y-3 text-sm">
              {item.logo && item.companyUrl ? (
                <a
                  href={item.companyUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  aria-label={`${item.company} (opens in a new tab)`}
                  className="inline-flex items-center rounded-xl bg-white px-4 py-2.5"
                >
                  <img src={item.logo} alt="Slide Practice" width="209" height="32" className="h-8 w-auto" loading="lazy" />
                </a>
              ) : (
                item.companyUrl && (
                  <a href={item.companyUrl} target="_blank" rel="noopener noreferrer" className="font-semibold hover:underline">
                    {item.company}
                  </a>
                )
              )}
              {item.linkedinUrl && (
                <a
                  href={item.linkedinUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  aria-label={`${item.name} on LinkedIn`}
                  className="text-mk-gray-dark underline-offset-4 hover:text-white hover:underline"
                >
                  LinkedIn
                </a>
              )}
            </div>
          </figcaption>
        </div>
      </figure>
    </Reveal>
  );
}
