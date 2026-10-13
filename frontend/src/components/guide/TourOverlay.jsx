import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

const PAD = 6;
const GAP = 12;
const CARD_W = 340;
const FIND_TIMEOUT_MS = 1500;

/** Portals go inside the app shell so its theme colours apply (they are scoped to .app-shell). */
export function shellRoot() {
  if (typeof document === "undefined") return null;
  return document.querySelector(".app-shell") || document.body;
}

/** First matching element that is actually on screen (desktop and mobile copies of a control both exist). */
export function findVisible(selectors) {
  if (typeof document === "undefined") return null;
  for (const sel of selectors || []) {
    let nodes = [];
    try {
      nodes = Array.from(document.querySelectorAll(sel));
    } catch {
      nodes = [];
    }
    const el = nodes.find((n) => {
      const r = n.getBoundingClientRect();
      if (r.width < 2 || r.height < 2) return false;
      const style = window.getComputedStyle(n);
      return style.visibility !== "hidden" && style.display !== "none";
    });
    if (el) return el;
  }
  return null;
}

/** Where the explanation card goes: below the target if it fits, otherwise above, clamped to the screen. */
export function placeCard(rect, card, view) {
  const width = Math.min(CARD_W, view.w - 32);
  if (!rect) {
    return { left: Math.round((view.w - width) / 2), top: Math.round(Math.max(16, (view.h - card.h) / 2)), width, docked: false };
  }
  if (view.w < 640) {
    // Phones: dock to the bottom, or the top when the highlight is low on the screen.
    const low = rect.top + rect.height / 2 > view.h / 2;
    return { left: 16, width: view.w - 32, top: low ? 16 : Math.max(16, view.h - card.h - 16), docked: true };
  }
  const below = rect.bottom + PAD + GAP;
  const above = rect.top - PAD - GAP - card.h;
  let top;
  if (below + card.h <= view.h - 12) top = below;
  else if (above >= 12) top = above;
  else top = Math.max(12, Math.min(view.h - card.h - 12, rect.top));
  let left = rect.left + rect.width / 2 - width / 2;
  left = Math.max(16, Math.min(view.w - width - 16, left));
  return { left: Math.round(left), top: Math.round(top), width, docked: false };
}

export default function TourOverlay({ guide, stepIndex, onNext, onBack, onClose, onTry }) {
  const step = guide.steps[stepIndex];
  const total = guide.steps.length;
  const [rect, setRect] = useState(null);
  const [searching, setSearching] = useState(true);
  const [cardH, setCardH] = useState(180);
  const [view, setView] = useState(() => ({ w: window.innerWidth, h: window.innerHeight }));
  const elRef = useRef(null);
  const cardRef = useRef(null);

  const measure = useCallback(() => {
    setView({ w: window.innerWidth, h: window.innerHeight });
    const el = elRef.current;
    if (!el || !el.isConnected) {
      setRect(null);
      return;
    }
    const r = el.getBoundingClientRect();
    setRect({ top: r.top, left: r.left, width: r.width, height: r.height, bottom: r.bottom, right: r.right });
  }, []);

  // Find this step's element (pages load lazily, so keep looking briefly).
  useEffect(() => {
    let cancelled = false;
    elRef.current = null;
    setRect(null);
    setSearching(true);
    const started = Date.now();
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
    const look = () => {
      if (cancelled) return;
      const el = findVisible(step.targets);
      if (el) {
        elRef.current = el;
        el.scrollIntoView?.({ block: "center", inline: "nearest", behavior: reduce ? "auto" : "smooth" });
        window.setTimeout(() => {
          if (cancelled) return;
          measure();
          setSearching(false);
        }, reduce ? 30 : 380);
        return;
      }
      if (Date.now() - started > FIND_TIMEOUT_MS || !(step.targets || []).length) {
        setSearching(false);
        return;
      }
      window.setTimeout(look, 120);
    };
    look();
    return () => { cancelled = true; };
  }, [step, measure]);

  useEffect(() => {
    const onMove = () => window.requestAnimationFrame(measure);
    window.addEventListener("resize", onMove);
    window.addEventListener("scroll", onMove, true);
    return () => {
      window.removeEventListener("resize", onMove);
      window.removeEventListener("scroll", onMove, true);
    };
  }, [measure]);

  useLayoutEffect(() => {
    if (cardRef.current) setCardH(cardRef.current.offsetHeight || 180);
  }, [stepIndex, searching, view.w]);

  useEffect(() => {
    if (!searching) cardRef.current?.focus({ preventScroll: true });
  }, [searching, stepIndex]);

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "Escape") { e.preventDefault(); onClose(); }
      else if (e.key === "ArrowRight") { e.preventDefault(); onNext(); }
      else if (e.key === "ArrowLeft" && stepIndex > 0) { e.preventDefault(); onBack(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, onNext, onBack, stepIndex]);

  if (searching) {
    return createPortal(<div className="fixed inset-0 z-[200]" aria-hidden />, shellRoot());
  }

  const pos = placeCard(rect, { h: cardH }, view);
  const last = stepIndex === total - 1;
  const titleId = `tour-title-${guide.id}`;

  return createPortal(
    <div className="fixed inset-0 z-[200]" data-testid="tour-overlay">
      {/* Click-catcher: the page is paused while the tour is open. */}
      <div className={cn("absolute inset-0", !rect && "bg-black/55")} onClick={() => {}} aria-hidden />
      {rect && (
        <div
          aria-hidden
          data-testid="tour-highlight"
          className="pointer-events-none absolute rounded-lg ring-[3px] ring-helm-gold transition-all duration-200"
          style={{
            top: rect.top - PAD,
            left: rect.left - PAD,
            width: rect.width + PAD * 2,
            height: rect.height + PAD * 2,
            boxShadow: "0 0 0 9999px rgba(0,0,0,0.62)",
          }}
        />
      )}
      <div
        ref={cardRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        data-testid="tour-card"
        className="absolute rounded-xl border border-helm-line bg-helm-card p-4 shadow-2xl outline-none"
        style={{ top: pos.top, left: pos.left, width: pos.width }}
      >
        <div className="flex items-start gap-3">
          <p className="text-[11px] font-mono uppercase tracking-wider text-helm-muted">
            {guide.name} · {stepIndex + 1} of {total}
          </p>
          <button
            type="button"
            onClick={onClose}
            className="ml-auto -mr-1 -mt-1 rounded p-1 text-helm-muted hover:text-helm-fg"
            aria-label="Close the tour"
            data-testid="tour-close"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <h2 id={titleId} className="mt-1.5 text-base font-medium text-helm-fg">{step.title}</h2>
        <p className="mt-1 text-sm leading-relaxed text-helm-muted">{step.body}</p>
        <div className="mt-4 flex items-center gap-2">
          <div className="flex gap-1" aria-hidden>
            {guide.steps.map((s, i) => (
              <span key={s.title} className={cn("h-1.5 w-1.5 rounded-full", i === stepIndex ? "bg-helm-gold" : "bg-helm-line")} />
            ))}
          </div>
          <div className="ml-auto flex items-center gap-2">
            {stepIndex > 0 && (
              <button
                type="button"
                onClick={onBack}
                className="rounded-md px-3 py-1.5 text-sm text-helm-muted hover:text-helm-fg"
                data-testid="tour-back"
              >
                Back
              </button>
            )}
            {step.tryIt && (
              <button
                type="button"
                onClick={() => onTry(step.tryIt)}
                className="rounded-md border border-helm-line px-3 py-1.5 text-sm text-helm-fg hover:bg-helm-fg/[0.04]"
                data-testid="tour-try"
              >
                Try it now
              </button>
            )}
            <button
              type="button"
              onClick={onNext}
              className="rounded-md bg-helm-gold px-3.5 py-1.5 text-sm font-medium text-helm-navy hover:bg-helm-gold-hover"
              data-testid="tour-next"
            >
              {last ? "Done" : "Next"}
            </button>
          </div>
        </div>
      </div>
    </div>,
    shellRoot(),
  );
}
