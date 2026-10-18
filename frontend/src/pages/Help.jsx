import { useEffect, useState } from "react";
import { Check, Copy } from "lucide-react";
import {
  CtaBand,
  MkAccordion,
  MkLink,
  MkPage,
  PageHero,
  Reveal,
  RuledItem,
  SectionHeader,
} from "@/components/marketing/mk";
import { useMarketingAuth } from "@/hooks/useMarketingAuth";
import {
  AI_CONNECT_HELP,
  CATEGORY,
  HOW_TO_USE_AUDIENCES,
  HOW_TO_USE_CONCEPTS,
  HOW_TO_USE_FAQ,
  HOW_TO_USE_INTRO,
  HOW_TO_USE_MODULES,
  HOW_TO_USE_STEPS,
} from "@/lib/marketingCopy";

const TOC = [
  { id: "start", label: "Start here" },
  { id: "words", label: "What the words mean" },
  { id: "walkthrough", label: "A first walkthrough" },
  { id: "ai-assistants", label: "Connect an AI assistant" },
  { id: "questions", label: "Common questions" },
  { id: "where", label: "Where to find things" },
];

/** Command or URL on a black band, with a one-click copy. Square, hairline, no rounding. */
function CopyCode({ children }) {
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
    <div className="mt-3 border border-white/25">
      <code className="block overflow-x-auto whitespace-nowrap px-3 py-2.5 font-mono text-xs leading-5 text-white">
        {children}
      </code>
      <button
        type="button"
        onClick={copy}
        className="flex w-full items-center justify-end gap-1.5 border-t border-white/25 px-3 py-1.5 text-xs font-semibold text-white transition-colors hover:bg-white hover:text-mk-black"
      >
        {copied ? <Check className="h-3.5 w-3.5" aria-hidden /> : <Copy className="h-3.5 w-3.5" aria-hidden />}
        {copied ? "Copied" : "Copy"}
      </button>
    </div>
  );
}

function Steps({ steps, testId }) {
  return (
    <ol className="mt-6 space-y-6" data-testid={testId}>
      {steps.map((step, i) => (
        <li key={step.title} className="flex gap-4">
          <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center border border-white/50 font-mono text-[11px] text-white">
            {i + 1}
          </span>
          <div className="min-w-0">
            <p className="font-semibold text-white">{step.title}</p>
            <p className="mt-1 text-sm leading-relaxed text-mk-gray-dark">{step.body}</p>
            {step.code && <CopyCode>{step.code}</CopyCode>}
          </div>
        </li>
      ))}
    </ol>
  );
}

function Checks({ lines }) {
  return (
    <ul className="mt-6 space-y-3">
      {lines.map((line) => (
        <li key={line} className="flex gap-3 text-sm leading-relaxed text-mk-gray-dark">
          <Check className="mt-0.5 h-4 w-4 shrink-0 text-white" aria-hidden />
          <span>{line}</span>
        </li>
      ))}
    </ul>
  );
}

export default function Help() {
  const { authed, enter } = useMarketingAuth();
  useEffect(() => { window.scrollTo(0, 0); }, []);

  return (
    <MkPage authed={authed} onEnter={enter} active="/help">
      <PageHero
        eyebrow={CATEGORY}
        lines={["Help.", "Start here."]}
        sub="New to Trenston? This page explains what the product does, what each part is for, and how owners and invited teammates use it differently."
        toc={TOC}
        size="md"
      />

      {/* Start here: white */}
      <section id="start" className="scroll-mt-16 bg-white px-6 py-16 md:py-20">
        <div className="mx-auto max-w-7xl">
          <SectionHeader eyebrow="Getting started" title={HOW_TO_USE_INTRO.title} intro={HOW_TO_USE_INTRO.lead} />
          <div className="mt-12 grid gap-10 md:grid-cols-2">
            {HOW_TO_USE_AUDIENCES.map((item, i) => (
              <RuledItem key={item.title} i={i} index={i + 1} title={item.title} body={item.body} />
            ))}
          </div>
        </div>
      </section>

      {/* What the words mean: black */}
      <section id="words" className="scroll-mt-16 bg-mk-black px-6 py-16 text-white md:py-20">
        <div className="mx-auto max-w-7xl">
          <SectionHeader
            dark
            eyebrow="Glossary"
            title="What the words mean"
            intro="Trenston uses a few product names that are easy to mix up with everyday English. Read these once, then use the quick reference at the bottom when you only need a reminder of where something lives."
          />
          <div className="mt-12 grid gap-12 md:grid-cols-2 lg:gap-x-16">
            {HOW_TO_USE_CONCEPTS.map((item, i) => (
              <RuledItem dark key={item.term} i={i % 2} index={i + 1} title={item.term} body={item.explanation}>
                <p className="mt-4 border-l border-white/40 pl-4 text-sm leading-relaxed text-white/80">
                  <span className="font-semibold text-white">Example. </span>
                  {item.example}
                </p>
              </RuledItem>
            ))}
          </div>
        </div>
      </section>

      {/* A first walkthrough: white, ruled rows */}
      <section id="walkthrough" className="scroll-mt-16 bg-white px-6 py-16 md:py-20">
        <div className="mx-auto max-w-7xl">
          <SectionHeader
            eyebrow="Your first session"
            title="A simple first walkthrough"
            intro="Follow these in order the first time you use Trenston. Later steps are for owners and people with report or integration access; invited teammates can stop after My Day and their department lane."
          />
          <ol className="mt-12 border-t border-mk-black">
            {HOW_TO_USE_STEPS.map((step, i) => (
              <Reveal as="li" key={step.title} className="grid gap-3 border-b border-mk-line py-7 md:grid-cols-[5rem_1fr_1.5fr] md:gap-8">
                <span className="font-mono text-sm text-mk-gray">{String(i + 1).padStart(2, "0")}</span>
                <div>
                  <h3 className="text-xl font-semibold leading-snug tracking-tight text-mk-black">{step.title}</h3>
                  {step.audience === "owner" && (
                    <p className="mt-2 text-xs font-semibold uppercase tracking-[0.16em] text-mk-navy">
                      Owners and people with access
                    </p>
                  )}
                </div>
                <p className="leading-relaxed text-mk-gray">{step.body}</p>
              </Reveal>
            ))}
          </ol>
        </div>
      </section>

      {/* Connect an AI assistant: black */}
      <section
        id="ai-assistants"
        className="scroll-mt-16 bg-mk-black px-6 py-16 text-white md:py-20"
        data-testid="help-ai-assistants"
      >
        <div className="mx-auto max-w-7xl">
          <SectionHeader
            dark
            eyebrow="For paid plans"
            title="Connect an AI assistant"
            intro={AI_CONNECT_HELP.intro}
          />
          <div className="mt-12 grid gap-12 md:grid-cols-2 lg:gap-10">
            <RuledItem dark i={0} index={1} title="In Claude (recommended)" body="No key needed: you approve it once in Trenston.">
              <Steps steps={AI_CONNECT_HELP.claudeSteps} testId="help-ai-claude-steps" />
            </RuledItem>
            <RuledItem dark i={1} index={2} title="With an API key" body="For Claude Code and your own scripts.">
              <Steps steps={AI_CONNECT_HELP.keySteps} testId="help-ai-key-steps" />
            </RuledItem>
            <RuledItem dark i={2} index={3} title="What read-only means">
              <Checks lines={AI_CONNECT_HELP.readOnly} />
            </RuledItem>
            <RuledItem dark i={3} index={4} title="Keep it safe">
              <Checks lines={AI_CONNECT_HELP.safety} />
              <p className="mt-6 text-sm text-mk-gray-dark">
                In the app: Settings, then API keys.{" "}
                <MkLink to="/security#ai-assistants" className="text-white">How Trenston protects this</MkLink>
              </p>
            </RuledItem>
          </div>
        </div>
      </section>

      {/* Common questions: white */}
      <section id="questions" className="scroll-mt-16 bg-white px-6 py-16 md:py-20">
        <div className="mx-auto max-w-4xl">
          <SectionHeader eyebrow="FAQ" title="Common questions" />
          <div className="mt-10">
            <MkAccordion items={HOW_TO_USE_FAQ} idPrefix="help-faq" />
          </div>
        </div>
      </section>

      {/* Where to find things: mist */}
      <section id="where" className="scroll-mt-16 bg-mk-mist px-6 py-16 md:py-20">
        <div className="mx-auto max-w-7xl">
          <SectionHeader
            eyebrow="Quick reference"
            title="Where to find things"
            intro="A quick reference once you know the concepts. The paths are what you will see inside the signed-in app; they are not links on this public page."
            action={<MkLink to="/features" className="text-mk-navy">See all features</MkLink>}
          />
          <div className="mt-12 grid gap-12 sm:grid-cols-2 lg:grid-cols-3 lg:gap-10">
            {HOW_TO_USE_MODULES.map((m, i) => (
              <RuledItem key={m.nav} i={i % 3} title={m.nav} body={m.tip}>
                <p className="mt-4 font-mono text-xs text-mk-navy">{m.path}</p>
              </RuledItem>
            ))}
          </div>
        </div>
      </section>

      <CtaBand
        title="See it with your own numbers."
        sub="Start free, set up from a spreadsheet you already keep, and read your first Briefing."
        authed={authed}
        onEnter={enter}
      />
    </MkPage>
  );
}
