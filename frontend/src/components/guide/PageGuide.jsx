import { useEffect, useRef } from "react";
import { Link, useLocation } from "react-router-dom";
import { CircleHelp, Compass, Keyboard, LifeBuoy, RotateCcw, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { guideForPath } from "@/lib/pageGuides";
import { TIPS_OFF, useGuides } from "@/components/guide/GuideProvider";

/**
 * First-visit card at the top of a page: what the page is for, and a way to be
 * shown around. Shows once per person per page.
 */
export function PageIntro() {
  const { pathname } = useLocation();
  const { isSeen, markSeen, startTour, activeTour, checklistShowing } = useGuides();
  const guide = guideForPath(pathname);
  if (!guide || activeTour || isSeen(guide.id) || isSeen(TIPS_OFF)) return null;
  // The Get started list already offers this tour as its first step.
  if (checklistShowing && (guide.id === "briefing" || guide.id === "myday")) return null;
  const hasTour = guide.steps.length > 0;

  return (
    <div
      className="mb-6 flex flex-col gap-3 rounded-xl border border-helm-gold/30 bg-helm-gold/[0.07] p-4 sm:flex-row sm:items-center"
      data-testid="page-intro"
      role="note"
    >
      <Compass className="hidden h-5 w-5 shrink-0 text-helm-gold sm:block" aria-hidden />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-helm-fg">New to {guide.name}?</p>
        <p className="mt-0.5 text-sm text-helm-muted leading-relaxed">{guide.purpose}</p>
      </div>
      <div className="flex shrink-0 flex-wrap items-center gap-2">
        {hasTour && (
          <button
            type="button"
            onClick={() => startTour(guide.id)}
            data-testid="page-intro-tour"
            className="rounded-md bg-helm-gold px-3.5 py-2 text-sm font-medium text-helm-navy hover:bg-helm-gold-hover"
          >
            Show me around
          </button>
        )}
        <button
          type="button"
          onClick={() => markSeen(guide.id)}
          data-testid="page-intro-dismiss"
          className="rounded-md border border-helm-line px-3.5 py-2 text-sm text-helm-fg hover:bg-helm-fg/[0.04]"
        >
          Got it
        </button>
        <button
          type="button"
          onClick={() => markSeen(TIPS_OFF)}
          data-testid="page-intro-off"
          className="px-1 text-xs text-helm-muted underline-offset-2 hover:text-helm-fg hover:underline"
        >
          Stop showing these
        </button>
      </div>
    </div>
  );
}

/** The "?" button in the top bar. */
export function PageHelpButton({ mobile = false }) {
  const { setHelpOpen } = useGuides();
  return (
    <button
      type="button"
      data-testid={mobile ? "page-help-btn-mobile" : "page-help-btn"}
      aria-label="Help with this page"
      title="Help with this page"
      onClick={() => setHelpOpen(true)}
      className={cn(
        mobile
          ? "p-2 text-helm-fg"
          : "inline-flex h-9 w-9 items-center justify-center rounded-full border border-helm-line text-helm-muted transition-colors hover:bg-helm-fg/[0.04] hover:text-helm-fg",
      )}
    >
      <CircleHelp className={mobile ? "h-5 w-5" : "h-4 w-4"} />
    </button>
  );
}

const PANEL_BTN = "flex w-full items-center gap-3 rounded-lg border border-helm-line px-3 py-2.5 text-left text-sm text-helm-fg transition-colors hover:border-helm-gold/40 hover:bg-helm-gold/[0.06]";

/** Side panel (bottom sheet on phones) explaining the current page. */
export function PageHelpPanel() {
  const { pathname } = useLocation();
  const { helpOpen, setHelpOpen, startTour, resetAll } = useGuides();
  const panelRef = useRef(null);
  const guide = guideForPath(pathname);

  useEffect(() => {
    if (!helpOpen) return undefined;
    panelRef.current?.focus();
    const onKey = (e) => { if (e.key === "Escape") setHelpOpen(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [helpOpen, setHelpOpen]);

  useEffect(() => { setHelpOpen(false); }, [pathname, setHelpOpen]);

  if (!helpOpen) return null;
  const isMac = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform || "");

  return (
    <div className="fixed inset-0 z-[150]" data-testid="page-help-panel">
      <div className="absolute inset-0 bg-helm-ink/50" onClick={() => setHelpOpen(false)} aria-hidden />
      <aside
        ref={panelRef}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-label="Help with this page"
        className="absolute inset-x-0 bottom-0 max-h-[85vh] overflow-y-auto rounded-t-2xl border border-helm-line bg-helm-card p-5 shadow-2xl outline-none sm:inset-y-0 sm:left-auto sm:right-0 sm:max-h-none sm:w-[380px] sm:rounded-none sm:rounded-l-2xl"
      >
        <div className="flex items-start gap-3">
          <div className="min-w-0 flex-1">
            <p className="text-[11px] font-mono uppercase tracking-wider text-helm-muted">How this page works</p>
            <h2 className="mt-1 text-lg font-medium text-helm-fg">{guide?.name || "Trenston"}</h2>
          </div>
          <button
            type="button"
            onClick={() => setHelpOpen(false)}
            className="rounded p-1 text-helm-muted hover:text-helm-fg"
            aria-label="Close help"
            data-testid="page-help-close"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <p className="mt-3 text-sm leading-relaxed text-helm-fg">
          {guide?.purpose || "Trenston keeps your money, decisions, work and team in one place. Pick a page on the left to start."}
        </p>

        {guide?.tips?.length > 0 && (
          <ul className="mt-4 space-y-2" data-testid="page-help-tips">
            {guide.tips.map((t) => (
              <li key={t} className="flex gap-2 text-sm leading-relaxed text-helm-muted">
                <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-helm-gold" aria-hidden />
                <span>{t}</span>
              </li>
            ))}
          </ul>
        )}

        <div className="mt-6 space-y-2">
          {guide?.steps?.length > 0 && (
            <button type="button" className={PANEL_BTN} onClick={() => startTour(guide.id)} data-testid="page-help-tour">
              <Compass className="h-4 w-4 shrink-0 text-helm-gold" />
              <span className="flex-1">
                Show me around this page
                <span className="block text-xs text-helm-muted">{guide.steps.length} short steps</span>
              </span>
            </button>
          )}
          <button type="button" className={PANEL_BTN} onClick={() => startTour("quickadd")} data-testid="page-help-quickadd">
            <Keyboard className="h-4 w-4 shrink-0 text-helm-gold" />
            <span className="flex-1">
              Add things fast with {isMac ? "Cmd+K" : "Ctrl+K"}
              <span className="block text-xs text-helm-muted">Tasks, decisions and notes from any page</span>
            </span>
          </button>
          <Link to="/app/help" className={PANEL_BTN} onClick={() => setHelpOpen(false)} data-testid="page-help-full">
            <LifeBuoy className="h-4 w-4 shrink-0 text-helm-gold" />
            <span className="flex-1">
              Full guide and questions
              <span className="block text-xs text-helm-muted">Every page explained, step by step</span>
            </span>
          </Link>
        </div>

        <div className="mt-6 border-t border-helm-line pt-4 text-sm text-helm-muted">
          <p>
            Still stuck?{" "}
            <a href="mailto:contact@trenston.com?subject=Help%20with%20Trenston" className="text-helm-gold hover:underline">
              Email us
            </a>{" "}
            and a real person replies.
          </p>
          <button
            type="button"
            onClick={resetAll}
            data-testid="page-help-reset"
            className="mt-3 inline-flex items-center gap-1.5 text-xs text-helm-muted hover:text-helm-fg"
          >
            <RotateCcw className="h-3.5 w-3.5" /> Show the welcome tips on every page again
          </button>
        </div>
      </aside>
    </div>
  );
}
