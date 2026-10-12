import { Reveal } from "@/components/marketing/mk";
import { cn } from "@/lib/utils";

/**
 * A real customer quote, used verbatim with the person's permission.
 * Never edit the words in TESTIMONIALS beyond what the person approved.
 */
export default function Testimonial({ item, dark = false, className }) {
  if (!item) return null;
  return (
    <Reveal className={cn("mx-auto max-w-4xl", className)}>
      <figure data-testid="testimonial">
        <blockquote
          className={cn(
            "text-2xl font-medium leading-snug tracking-[-0.02em] md:text-[2rem]",
            dark ? "text-white" : "text-mk-black",
          )}
        >
          <span aria-hidden>&ldquo;</span>
          {item.quote}
          <span aria-hidden>&rdquo;</span>
        </blockquote>
        <figcaption className={cn("mt-6 text-sm", dark ? "text-mk-gray-dark" : "text-mk-gray")}>
          <span className={cn("font-semibold", dark ? "text-white" : "text-mk-black")}>{item.name}</span>
          {" · "}
          {item.role}
        </figcaption>
      </figure>
    </Reveal>
  );
}
