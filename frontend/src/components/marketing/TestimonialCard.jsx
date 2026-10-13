import { Reveal } from "@/components/marketing/mk";
import { cn } from "@/lib/utils";

/**
 * Compact quote card: dark card, name | role, optional company logo + site and
 * LinkedIn. No profile photo by design. Used for every testimonial so they match.
 */
export default function TestimonialCard({ item, className }) {
  if (!item) return null;
  return (
    <Reveal className={cn("h-full", className)}>
      <figure
        data-testid="testimonial-card"
        className="flex h-full flex-col rounded-3xl bg-mk-black p-7 text-white md:p-8"
      >
        <span aria-hidden className="select-none text-5xl font-semibold leading-none text-white/80">
          &ldquo;
        </span>
        <blockquote className="mt-2 flex-1 text-base font-medium leading-relaxed tracking-[-0.005em] md:text-[1.05rem]">
          {item.quote}
        </blockquote>
        <figcaption className="mt-6 flex flex-col gap-3 border-t border-white/15 pt-5">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
            <span className="font-semibold">{item.name}</span>
            <span aria-hidden className="h-4 w-px bg-white/40" />
            <span className="text-mk-gray-dark">{item.role}</span>
          </div>
          {(item.logo || item.linkedinUrl) && (
            <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-sm">
              {item.logo && item.companyUrl && (
                <a
                  href={item.companyUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  aria-label={`${item.company} (opens in a new tab)`}
                  className="inline-flex items-center"
                >
                  <img src={item.logo} alt="Slide Practice" width="140" height="21" className="h-[21px] w-auto" loading="lazy" />
                </a>
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
          )}
        </figcaption>
      </figure>
    </Reveal>
  );
}
