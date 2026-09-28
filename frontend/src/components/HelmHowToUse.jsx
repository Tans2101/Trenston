import { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { ChevronDown, BookOpen, ArrowRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { GlassCard, SectionLabel } from "@/components/kit";
import {
  HOW_TO_USE_INTRO,
  HOW_TO_USE_AUDIENCES,
  HOW_TO_USE_CONCEPTS,
  HOW_TO_USE_STEPS,
  HOW_TO_USE_FAQ,
  HOW_TO_USE_MODULES,
} from "@/lib/marketingCopy";

/** In-app destinations for each walkthrough step (keyed by step title). */
const STEP_ROUTES = {
  "Open Briefing": { to: "/app", label: "Open Briefing" },
  "Act on one Decision": { to: "/app/decisions", label: "Open Decisions" },
  "Learn My Day and your department lane": { to: "/app/me", label: "Open My Day" },
  "Connect an integration (owners and admins)": { to: "/app/integrations", label: "Open Integrations" },
  "Invite a teammate (owners)": { to: "/app/members", label: "Open Team & Access" },
  "Generate a CEO Pack (owners and report access)": { to: "/app/reports", label: "Open Reports" },
};

function FaqItem({ item, open, onToggle }) {
  return (
    <div className="border-b border-helm-line last:border-b-0">
      <button
        type="button"
        onClick={onToggle}
        className="w-full flex items-start justify-between gap-3 py-4 text-left"
        aria-expanded={open}
      >
        <span className="text-sm text-helm-fg font-medium leading-relaxed">{item.q}</span>
        <ChevronDown
          className={cn(
            "w-4 h-4 text-helm-muted shrink-0 mt-0.5 transition-transform",
            open && "rotate-180",
          )}
        />
      </button>
      {open && (
        <p className="pb-4 text-sm text-helm-muted leading-relaxed pr-6">{item.a}</p>
      )}
    </div>
  );
}

/**
 * Shared how-to guide. On the public /help page paths are plain text; inside
 * the signed-in app (inApp, or any /app route) steps and paths are real links
 * so the guide leads straight to the next action.
 */
export default function TrenstonHowToUse({ className, inApp }) {
  const [openFaq, setOpenFaq] = useState(0);
  const location = useLocation();
  const linked = inApp ?? /^\/app(\/|$)/.test(location.pathname || "");

  return (
    <div className={cn("w-full max-w-3xl mx-auto text-left space-y-12", className)}>
      <div className="flex items-start gap-4">
        <div className="w-12 h-12 rounded-xl bg-helm-gold/12 border border-helm-gold/35 flex items-center justify-center shrink-0">
          <BookOpen className="w-6 h-6 text-helm-gold" />
        </div>
        <div>
          <p className="font-mono text-[10px] uppercase tracking-[0.25em] text-helm-gold">Getting started</p>
          <h2 className="mt-1 text-2xl md:text-3xl font-light tracking-tight text-helm-fg">
            {HOW_TO_USE_INTRO.title}
          </h2>
          <p className="mt-2 text-sm text-helm-muted leading-relaxed max-w-xl">
            {HOW_TO_USE_INTRO.subtitle}
          </p>
        </div>
      </div>

      <p className="text-sm md:text-base text-helm-muted leading-relaxed">
        {HOW_TO_USE_INTRO.lead}
      </p>

      <section>
        <SectionLabel className="mb-4">Who you are in Trenston</SectionLabel>
        <div className="space-y-3">
          {HOW_TO_USE_AUDIENCES.map((item) => (
            <GlassCard key={item.title} className="p-5">
              <h3 className="text-sm font-medium text-helm-fg">{item.title}</h3>
              <p className="mt-2 text-sm text-helm-muted leading-relaxed">{item.body}</p>
            </GlassCard>
          ))}
        </div>
      </section>

      <section>
        <SectionLabel className="mb-2">What the words mean</SectionLabel>
        <p className="text-sm text-helm-muted mb-5 leading-relaxed">
          Trenston uses a few product names that are easy to mix up with everyday English. Read these once, then use the quick reference at the bottom when you only need a reminder of where something lives.
        </p>
        <div className="space-y-4">
          {HOW_TO_USE_CONCEPTS.map((item) => (
            <GlassCard key={item.term} className="p-5">
              <h3 className="text-base font-medium text-helm-fg">{item.term}</h3>
              <p className="mt-2 text-sm text-helm-muted leading-relaxed">{item.explanation}</p>
              <p className="mt-3 text-sm text-helm-fg/80 leading-relaxed">
                <span className="font-mono text-[10px] uppercase tracking-[0.15em] text-helm-gold mr-2">Example</span>
                {item.example}
              </p>
            </GlassCard>
          ))}
        </div>
      </section>

      <section>
        <SectionLabel className="mb-2">A simple first walkthrough</SectionLabel>
        <p className="text-sm text-helm-muted mb-5 leading-relaxed">
          Follow these in order the first time you use Trenston. Later steps are for owners and people with report or integration access; invited teammates can stop after My Day and their department lane.
        </p>
        <ol className="space-y-3">
          {HOW_TO_USE_STEPS.map((step, index) => (
            <li key={step.title}>
              <GlassCard className="p-5">
                <div className="flex items-start gap-3">
                  <span className="font-mono text-xs text-helm-gold shrink-0 mt-0.5">
                    {String(index + 1).padStart(2, "0")}
                  </span>
                  <div>
                    <h3 className="text-sm font-medium text-helm-fg">{step.title}</h3>
                    {step.audience === "owner" && (
                      <p className="mt-1 font-mono text-[10px] uppercase tracking-[0.15em] text-helm-muted">
                        Owners and people with access
                      </p>
                    )}
                    <p className="mt-2 text-sm text-helm-muted leading-relaxed">{step.body}</p>
                    {linked && STEP_ROUTES[step.title] && (
                      <Link
                        to={STEP_ROUTES[step.title].to}
                        data-testid={`how-to-step-link-${index}`}
                        className="mt-3 inline-flex items-center gap-1.5 text-sm text-helm-gold hover:underline underline-offset-2"
                      >
                        {STEP_ROUTES[step.title].label}
                        <ArrowRight className="w-3.5 h-3.5" />
                      </Link>
                    )}
                  </div>
                </div>
              </GlassCard>
            </li>
          ))}
        </ol>
      </section>

      <section>
        <SectionLabel className="mb-4">Common questions</SectionLabel>
        <GlassCard className="px-5">
          {HOW_TO_USE_FAQ.map((item, index) => (
            <FaqItem
              key={item.q}
              item={item}
              open={openFaq === index}
              onToggle={() => setOpenFaq((cur) => (cur === index ? -1 : index))}
            />
          ))}
        </GlassCard>
      </section>

      <section>
        <SectionLabel className="mb-2">Where to find things</SectionLabel>
        <p className="text-sm text-helm-muted mb-4 leading-relaxed">
          {linked
            ? "Quick reference after you know the concepts. Select any card to open that part of Trenston."
            : "Quick reference after you know the concepts. Paths below are what you will see inside the signed-in app; they are not links on this public page."}
        </p>
        <div className="grid sm:grid-cols-2 gap-3">
          {HOW_TO_USE_MODULES.map((m) => {
            const card = (
              <GlassCard
                className={cn("px-4 py-3 h-full", linked && "transition-colors hover:border-helm-gold/35")}
              >
                <p className="text-xs font-medium text-helm-fg">{m.nav}</p>
                <p className={cn("font-mono text-[10px] mt-1", linked ? "text-helm-gold" : "text-helm-muted")}>{m.path}</p>
                <p className="text-[11px] text-helm-muted mt-1.5 leading-relaxed">{m.tip}</p>
              </GlassCard>
            );
            return linked && m.path?.startsWith("/app") ? (
              <Link key={m.nav} to={m.path} className="block" data-testid={`how-to-module-link-${m.nav}`}>
                {card}
              </Link>
            ) : (
              <div key={m.nav}>{card}</div>
            );
          })}
        </div>
        <p className="mt-6 text-xs text-helm-muted">
          Want the full product tour?{" "}
          <Link to="/features" className="text-helm-muted hover:text-helm-fg underline underline-offset-2 transition-colors">
            See all features
          </Link>
        </p>
      </section>
    </div>
  );
}
