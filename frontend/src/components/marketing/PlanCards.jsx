import { Check } from "lucide-react";
import { PLANS, paidPlanRenewalDisclosure } from "@/lib/marketingCopy";
import { MkButton, Reveal } from "@/components/marketing/mk";
import { cn } from "@/lib/utils";

/**
 * Four plan cards from PLANS (single source of truth). The highlighted plan
 * renders on solid navy; the rest are flat white cards.
 * Rows are fixed-height where copy varies so every CTA lines up.
 */
export default function PlanCards({ authed, onEnter, ctaTestIdPrefix = "pricing-cta", renewalTestIdPrefix }) {
  return (
    <div className="grid items-stretch gap-5 sm:grid-cols-2 xl:grid-cols-4">
      {PLANS.map((plan, i) => {
        const hi = plan.highlighted;
        const disclosure = paidPlanRenewalDisclosure(plan);
        return (
          <Reveal key={plan.id} i={i} className="flex">
            <article
              data-testid={`pricing-plan-${plan.id}`}
              className={cn(
                "relative flex w-full flex-col p-7 md:p-8",
                hi ? "bg-mk-navy text-white" : "mk-card",
              )}
            >
              <div className="flex items-center justify-between gap-3">
                <h3 className={cn("text-xs font-semibold uppercase tracking-[0.18em]", hi ? "text-white/75" : "text-mk-navy")}>
                  {plan.label}
                </h3>
                {hi && (
                  <span className="bg-white px-2.5 py-1 text-[10px] font-bold uppercase tracking-[0.14em] text-mk-black">
                    Most popular
                  </span>
                )}
              </div>
              <p className="mt-6 flex items-baseline gap-1 tabular-nums">
                <span className="text-5xl font-medium tracking-[-0.03em]">${plan.price}</span>
                {plan.price > 0 && <span className={cn("text-base", hi ? "text-white/70" : "text-mk-gray")}>/mo</span>}
              </p>
              <p className={cn("mt-3 min-h-[2.75rem] text-sm leading-snug", hi ? "text-white/85" : "text-mk-gray")}>{plan.for}</p>
              <p className={cn("min-h-[2.5rem] font-mono text-[11px] leading-relaxed", hi ? "text-white/70" : "text-mk-gray")}>
                Up to {plan.seats} Trenston users
                {plan.trialDays > 0 ? ` · ${plan.trialDays}-day free trial` : ""}
              </p>
              <div className={cn("my-6 h-px", hi ? "bg-white/20" : "bg-mk-line")} aria-hidden />
              <ul className="flex-1 space-y-3">
                {plan.includes.map((f) => (
                  <li key={f} className={cn("flex items-start gap-2.5 text-sm font-medium", hi ? "text-white" : "text-mk-black")}>
                    <Check className={cn("mt-0.5 h-4 w-4 shrink-0", hi ? "text-white" : "text-mk-navy")} aria-hidden />
                    {f}
                  </li>
                ))}
              </ul>
              <div className="mt-8">
                <MkButton
                  variant={hi ? "light" : "outline-dark"}
                  onClick={onEnter}
                  className="w-full"
                  data-testid={`${ctaTestIdPrefix}-${plan.id}`}
                >
                  {authed ? "Open cockpit" : plan.id === "free" ? "Get started free" : "Start free trial"}
                </MkButton>
                <p
                  data-testid={disclosure && renewalTestIdPrefix ? `${renewalTestIdPrefix}-${plan.id}` : undefined}
                  className={cn(
                    "mt-3 min-h-[3.25rem] text-[11px] font-medium leading-relaxed",
                    disclosure ? (hi ? "text-white/75" : "text-mk-gray") : "select-none text-transparent",
                  )}
                  aria-hidden={!disclosure}
                >
                  {disclosure || " "}
                </p>
              </div>
            </article>
          </Reveal>
        );
      })}
    </div>
  );
}
