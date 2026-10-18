import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { ChevronDown, ArrowRight, Bot, Check, Copy, ShieldCheck } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  HOW_TO_USE_INTRO,
  HOW_TO_USE_AUDIENCES,
  HOW_TO_USE_CONCEPTS,
  HOW_TO_USE_STEPS,
  HOW_TO_USE_FAQ,
  HOW_TO_USE_MODULES,
  AI_CONNECT_HELP,
} from "@/lib/marketingCopy";

/** In-app destinations for each walkthrough step (keyed by step title). */
const STEP_ROUTES = {
  "Open Briefing": { to: "/app", label: "Open Briefing" },
  "Bring in your numbers (owners)": { to: "/app/import", label: "Set up from a file" },
  "Act on one Decision": { to: "/app/decisions", label: "Open Decisions" },
  "Learn Home and your department page": { to: "/app", label: "Open Home" },
  "Connect an integration (owners and admins)": { to: "/app/integrations", label: "Open Integrations" },
  "Invite a teammate (owners)": { to: "/app/members", label: "Open Team & Access" },
  "Generate a CEO Pack (owners and report access)": { to: "/app/reports", label: "Open Reports" },
};

/**
 * Colour classes per surface. The public /help page is always solid black (marketing
 * palette), while the signed-in app follows the light/dark cockpit theme
 * (helm tokens). Using helm tokens on the public page put pale text on white
 * for anyone in dark mode, so each surface gets its own set.
 */
const TONES = {
  app: {
    fg: "text-helm-fg",
    body: "text-helm-fg/80",
    muted: "text-helm-muted",
    accent: "text-helm-gold",
    accentHover: "hover:text-helm-gold-hover",
    card: "border-helm-line bg-helm-card",
    cardHover: "hover:border-helm-gold/40",
    line: "border-helm-line",
    divide: "divide-helm-line",
    lineBg: "bg-helm-line",
    ring: "border-helm-gold/45",
    soft: "bg-helm-gold/10",
    code: "border-helm-line bg-helm-bg/60 text-helm-fg",
    navActive: "text-helm-fg border-helm-gold",
    navIdle: "text-helm-muted border-transparent hover:text-helm-fg",
  },
  marketing: {
    fg: "text-white",
    body: "text-white/80",
    muted: "text-mk-gray-dark",
    accent: "text-[#D4B45C]",
    accentHover: "hover:text-[#E3C673]",
    card: "border-white/10 bg-white/[0.04]",
    cardHover: "hover:border-[#D4B45C]/40",
    line: "border-white/10",
    divide: "divide-white/10",
    lineBg: "bg-white/15",
    ring: "border-[#D4B45C]/50",
    soft: "bg-[#D4B45C]/10",
    code: "border-white/10 bg-black/40 text-white",
    navActive: "text-white border-[#D4B45C]",
    navIdle: "text-mk-gray-dark border-transparent hover:text-white",
  },
};

const SECTIONS = [
  { id: "start", label: "Start here" },
  { id: "words", label: "What the words mean" },
  { id: "walkthrough", label: "First walkthrough" },
  { id: "ai-assistants", label: "Connect an AI assistant" },
  { id: "questions", label: "Common questions" },
  { id: "where", label: "Where to find things" },
];
const SECTION_IDS = SECTIONS.map((s) => s.id);

function goTo(event, id) {
  const el = typeof document !== "undefined" ? document.getElementById(id) : null;
  if (!el) return;
  event.preventDefault();
  const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
  el.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
  try {
    window.history.replaceState(null, "", `#${id}`);
  } catch {
    // The jump still worked; only the address bar hash is skipped.
  }
}

function useActiveSection() {
  const [active, setActive] = useState(SECTION_IDS[0]);
  useEffect(() => {
    if (typeof IntersectionObserver === "undefined") return undefined;
    const els = SECTION_IDS.map((id) => document.getElementById(id)).filter(Boolean);
    const seen = new Set();
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => (e.isIntersecting ? seen.add(e.target.id) : seen.delete(e.target.id)));
        const first = SECTION_IDS.find((id) => seen.has(id));
        if (first) setActive(first);
      },
      { rootMargin: "-15% 0px -70% 0px" },
    );
    els.forEach((el) => observer.observe(el));
    return () => observer.disconnect();
  }, []);
  return active;
}

function SectionHeading({ tone, eyebrow, title, children }) {
  return (
    <header className="mb-4 md:mb-5">
      {eyebrow && (
        <p className={cn("mb-2 font-mono text-[11px] uppercase tracking-[0.2em]", tone.accent)}>{eyebrow}</p>
      )}
      <h2 className={cn("font-display text-2xl md:text-[1.75rem] font-semibold tracking-tight leading-tight", tone.fg)}>
        {title}
      </h2>
      {children && <p className={cn("mt-2 max-w-2xl text-base leading-6", tone.muted)}>{children}</p>}
    </header>
  );
}

function Card({ tone, className, children, ...props }) {
  return (
    <div className={cn("rounded-xl border", tone.card, className)} {...props}>
      {children}
    </div>
  );
}

function CodeBlock({ tone, children }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(children);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      // Clipboard can be blocked; the text is still selectable.
    }
  };
  return (
    <div className={cn("mt-3 rounded-lg border", tone.code)}>
      <code className="block overflow-x-auto whitespace-nowrap px-3 py-2.5 font-mono text-xs leading-5">{children}</code>
      <div className={cn("flex justify-end border-t px-2 py-1", tone.line)}>
        <button
          type="button"
          onClick={copy}
          className={cn(
            "inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs font-medium transition-colors",
            tone.accent,
            tone.accentHover,
          )}
        >
          {copied ? <Check className="h-3.5 w-3.5" aria-hidden /> : <Copy className="h-3.5 w-3.5" aria-hidden />}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
    </div>
  );
}

function FaqItem({ tone, item, open, onToggle }) {
  return (
    <div className={cn("border-b last:border-b-0", tone.line)}>
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-start justify-between gap-4 py-4 text-left"
        aria-expanded={open}
      >
        <span className={cn("text-base font-medium leading-6", tone.fg)}>{item.q}</span>
        <ChevronDown
          className={cn("mt-1.5 h-4 w-4 shrink-0 transition-transform", tone.muted, open && "rotate-180")}
          aria-hidden
        />
      </button>
      {open && <p className={cn("pb-5 pr-8 text-base leading-6", tone.body)}>{item.a}</p>}
    </div>
  );
}

function StepList({ tone, steps, testId }) {
  return (
    <ol className="space-y-5" data-testid={testId}>
      {steps.map((step, index) => (
        <li key={step.title} className="flex gap-3">
          <span
            className={cn(
              "mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border font-mono text-[11px]",
              tone.ring,
              tone.accent,
            )}
          >
            {index + 1}
          </span>
          <div className="min-w-0">
            <p className={cn("text-base font-medium leading-6", tone.fg)}>{step.title}</p>
            <p className={cn("mt-1 text-sm leading-6", tone.body)}>{step.body}</p>
            {step.code && <CodeBlock tone={tone}>{step.code}</CodeBlock>}
          </div>
        </li>
      ))}
    </ol>
  );
}

function CheckList({ tone, lines }) {
  return (
    <ul className="space-y-2.5">
      {lines.map((line) => (
        <li key={line} className={cn("flex gap-3 text-base leading-6", tone.body)}>
          <Check className={cn("mt-1.5 h-4 w-4 shrink-0", tone.accent)} aria-hidden />
          <span>{line}</span>
        </li>
      ))}
    </ul>
  );
}

function AiConnectSection({ tone, linked }) {
  return (
    <section id="ai-assistants" className="scroll-mt-28" data-testid="help-ai-assistants">
      <SectionHeading tone={tone} eyebrow="For Growth and Business" title="Connect an AI assistant">
        {AI_CONNECT_HELP.intro}
      </SectionHeading>
      <Card tone={tone} className="mb-4 p-5">
        <p className={cn("mb-4 flex items-center gap-2 text-base font-semibold", tone.fg)}>
          <ShieldCheck className={cn("h-5 w-5", tone.accent)} aria-hidden /> What read-only means
        </p>
        <CheckList tone={tone} lines={AI_CONNECT_HELP.readOnly} />
      </Card>
      <div className="grid gap-4 md:grid-cols-2">
        <Card tone={tone} className="p-5">
          <p className={cn("mb-1 flex items-center gap-2 text-base font-semibold", tone.fg)}>
            <Bot className={cn("h-5 w-5", tone.accent)} aria-hidden /> In Claude (recommended)
          </p>
          <p className={cn("mb-5 text-sm", tone.muted)}>No key needed: you approve it once in Trenston.</p>
          <StepList tone={tone} steps={AI_CONNECT_HELP.claudeSteps} testId="help-ai-claude-steps" />
        </Card>
        <Card tone={tone} className="p-5">
          <p className={cn("mb-1 text-base font-semibold", tone.fg)}>With an API key</p>
          <p className={cn("mb-5 text-sm", tone.muted)}>For Claude Code and your own scripts.</p>
          <StepList tone={tone} steps={AI_CONNECT_HELP.keySteps} testId="help-ai-key-steps" />
        </Card>
      </div>
      <Card tone={tone} className="mt-4 p-5">
        <p className={cn("mb-4 text-base font-semibold", tone.fg)}>Keep it safe</p>
        <CheckList tone={tone} lines={AI_CONNECT_HELP.safety} />
        <p className={cn("mt-5 text-sm", tone.muted)}>
          {linked ? (
            <Link to="/app/settings#api-keys" className={cn("font-medium underline underline-offset-2", tone.accent, tone.accentHover)}>
              Open API keys in Settings
            </Link>
          ) : (
            <>
              In the app: Settings, then API keys.{" "}
              <Link to="/security#ai-assistants" className={cn("font-medium underline underline-offset-2", tone.accent, tone.accentHover)}>
                How Trenston protects this
              </Link>
            </>
          )}
        </p>
      </Card>
    </section>
  );
}

function ContentsNav({ tone, active }) {
  return (
    <nav aria-label="On this page" className="hidden lg:block">
      <div className="sticky top-28">
        <p className={cn("mb-3 font-mono text-[11px] uppercase tracking-[0.2em]", tone.muted)}>On this page</p>
        <ul className="space-y-1">
          {SECTIONS.map((s) => (
            <li key={s.id}>
              <a
                href={`#${s.id}`}
                onClick={(e) => goTo(e, s.id)}
                aria-current={active === s.id ? "true" : undefined}
                className={cn(
                  "block border-l-2 py-1.5 pl-4 text-sm leading-5 transition-colors",
                  active === s.id ? tone.navActive : tone.navIdle,
                )}
              >
                {s.label}
              </a>
            </li>
          ))}
        </ul>
      </div>
    </nav>
  );
}

function JumpChips({ tone }) {
  return (
    <nav aria-label="Jump to a section" className="-mx-1 mb-10 lg:hidden">
      <ul className="flex gap-2 overflow-x-auto px-1 pb-2">
        {SECTIONS.map((s) => (
          <li key={s.id} className="shrink-0">
            <a
              href={`#${s.id}`}
              onClick={(e) => goTo(e, s.id)}
              className={cn("block rounded-full border px-3.5 py-2 text-sm font-medium", tone.card, tone.fg)}
            >
              {s.label}
            </a>
          </li>
        ))}
      </ul>
    </nav>
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
  const tone = TONES[linked ? "app" : "marketing"];
  const active = useActiveSection();

  return (
    <div className={cn("w-full text-left lg:grid lg:grid-cols-[13rem_minmax(0,1fr)] lg:gap-14", className)}>
      <ContentsNav tone={tone} active={active} />

      <div className="min-w-0 max-w-3xl">
        <JumpChips tone={tone} />

        <div className="space-y-12">
          <section id="start" className="scroll-mt-28">
            <SectionHeading tone={tone} eyebrow="Getting started" title={HOW_TO_USE_INTRO.title} />
            <p className={cn("text-base leading-6 md:text-lg", tone.body)}>{HOW_TO_USE_INTRO.lead}</p>
            <p className={cn("mb-3 mt-6 text-sm font-medium", tone.muted)}>Which one are you?</p>
            <div className="grid gap-4 md:grid-cols-2">
              {HOW_TO_USE_AUDIENCES.map((item) => (
                <Card key={item.title} tone={tone} className="p-5">
                  <h3 className={cn("text-lg font-semibold leading-snug", tone.fg)}>{item.title}</h3>
                  <p className={cn("mt-3 text-base leading-6", tone.body)}>{item.body}</p>
                </Card>
              ))}
            </div>
          </section>

          <section id="words" className="scroll-mt-28">
            <SectionHeading tone={tone} title="What the words mean">
              Trenston uses a few product names that are easy to mix up with everyday English. Read these once, then use
              the quick reference at the bottom when you only need a reminder of where something lives.
            </SectionHeading>
            <dl className={cn("divide-y border-y", tone.divide, tone.line)}>
              {HOW_TO_USE_CONCEPTS.map((item) => (
                <div key={item.term} className="py-5">
                  <dt className={cn("text-xl font-semibold tracking-tight", tone.fg)}>{item.term}</dt>
                  <dd className={cn("mt-2 text-base leading-6", tone.body)}>{item.explanation}</dd>
                  <dd className={cn("mt-4 border-l-2 pl-4 text-base leading-6", tone.ring, tone.muted)}>
                    <span className={cn("mr-2 font-mono text-[11px] font-medium uppercase tracking-[0.15em]", tone.accent)}>
                      Example
                    </span>
                    {item.example}
                  </dd>
                </div>
              ))}
            </dl>
          </section>

          <section id="walkthrough" className="scroll-mt-28">
            <SectionHeading tone={tone} title="A simple first walkthrough">
              Follow these in order the first time you use Trenston. Later steps are for owners and people with report or
              integration access; invited teammates can stop after My Day and their department lane.
            </SectionHeading>
            <ol>
              {HOW_TO_USE_STEPS.map((step, index) => {
                const route = linked ? STEP_ROUTES[step.title] : null;
                const last = index === HOW_TO_USE_STEPS.length - 1;
                return (
                  <li key={step.title} className={cn("relative pl-14", !last && "pb-7")}>
                    <span
                      className={cn(
                        "absolute left-0 top-0 flex h-9 w-9 items-center justify-center rounded-full border text-sm font-semibold",
                        tone.ring,
                        tone.soft,
                        tone.accent,
                      )}
                    >
                      {index + 1}
                    </span>
                    {!last && <span className={cn("absolute left-[17px] top-11 bottom-1 w-px", tone.lineBg)} aria-hidden />}
                    <h3 className={cn("pt-1 text-lg font-semibold leading-snug", tone.fg)}>{step.title}</h3>
                    {step.audience === "owner" && (
                      <p className={cn("mt-2 inline-block rounded-full px-2.5 py-1 text-xs font-medium", tone.soft, tone.accent)}>
                        Owners and people with access
                      </p>
                    )}
                    <p className={cn("mt-2 text-base leading-6", tone.body)}>{step.body}</p>
                    {route && (
                      <Link
                        to={route.to}
                        data-testid={`how-to-step-link-${index}`}
                        className={cn(
                          "mt-3 inline-flex items-center gap-1.5 text-base font-medium underline-offset-4 hover:underline",
                          tone.accent,
                        )}
                      >
                        {route.label}
                        <ArrowRight className="h-4 w-4" aria-hidden />
                      </Link>
                    )}
                  </li>
                );
              })}
            </ol>
          </section>

          <AiConnectSection tone={tone} linked={linked} />

          <section id="questions" className="scroll-mt-28">
            <SectionHeading tone={tone} title="Common questions" />
            <div className={cn("border-y", tone.line)}>
              {HOW_TO_USE_FAQ.map((item, index) => (
                <FaqItem
                  key={item.q}
                  tone={tone}
                  item={item}
                  open={openFaq === index}
                  onToggle={() => setOpenFaq((cur) => (cur === index ? -1 : index))}
                />
              ))}
            </div>
          </section>

          <section id="where" className="scroll-mt-28">
            <SectionHeading tone={tone} title="Where to find things">
              {linked
                ? "A quick reference once you know the concepts. Select any card to open that part of Trenston."
                : "A quick reference once you know the concepts. The paths are what you will see inside the signed-in app; they are not links on this public page."}
            </SectionHeading>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              {HOW_TO_USE_MODULES.map((m) => {
                const card = (
                  <Card tone={tone} className={cn("h-full p-4", linked && cn("transition-colors", tone.cardHover))}>
                    <p className={cn("text-base font-semibold", tone.fg)}>{m.nav}</p>
                    <p className={cn("mt-1 font-mono text-xs", linked ? tone.accent : tone.muted)}>{m.path}</p>
                    <p className={cn("mt-2 text-sm leading-6", tone.body)}>{m.tip}</p>
                  </Card>
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
            <p className={cn("mt-6 text-base", tone.muted)}>
              Want the full product tour?{" "}
              <Link to="/features" className={cn("font-medium underline underline-offset-4", tone.accent, tone.accentHover)}>
                See all features
              </Link>
            </p>
          </section>
        </div>
      </div>
    </div>
  );
}
