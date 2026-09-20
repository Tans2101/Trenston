import { Linkedin } from "lucide-react";
import { FOUNDER_CREDIT, FOUNDER_LINKEDIN_URL, FOUNDER_NAME } from "@/lib/marketingCopy";
import { cn } from "@/lib/utils";

/**
 * Founder name/role plus a LinkedIn icon link (same restrained lucide treatment
 * as the Instagram icon in MarketingFooter).
 */
export default function FounderCredit({ className, creditClassName, "data-testid": testId }) {
  return (
    <span className={cn("inline-flex items-center gap-2", className)} data-testid={testId}>
      <span className={creditClassName}>{FOUNDER_CREDIT}</span>
      <a
        href={FOUNDER_LINKEDIN_URL}
        target="_blank"
        rel="noopener noreferrer"
        aria-label={`${FOUNDER_NAME} on LinkedIn`}
        title={`${FOUNDER_NAME} on LinkedIn`}
        className="inline-flex shrink-0 text-helm-slate hover:text-helm-navy transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-helm-gold"
        data-testid="founder-linkedin"
      >
        <Linkedin className="h-4 w-4" aria-hidden />
      </a>
    </span>
  );
}
