import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Check, Compass, X } from "lucide-react";
import { api } from "@/lib/api";
import { useFetch } from "@/hooks/useFetch";
import { cn } from "@/lib/utils";
import { GUIDES_CHANGED_EVENT, useGuides } from "@/components/guide/GuideProvider";

/**
 * "Get started" list. Each step opens the right page and lights up the exact
 * button to press, so new people learn by doing instead of reading.
 */
export function GetStartedView({ checklist, onShow, onHide, busy }) {
  const steps = checklist.steps || [];
  const done = steps.filter((s) => s.done).length;
  const next = steps.find((s) => !s.done);
  const pct = steps.length ? Math.round((done / steps.length) * 100) : 0;
  return (
    <section className="mb-6 rounded-xl border border-helm-line bg-helm-card p-5 shadow-sm" data-testid="onboarding-checklist">
      <div className="flex items-center gap-3">
        <p className="text-[11px] font-mono uppercase tracking-wider text-helm-muted">Get started</p>
        <span className="ml-auto text-xs tabular-nums text-helm-muted">{done} of {steps.length} done</span>
        <button
          type="button"
          data-testid="dismiss-setup-checklist"
          onClick={onHide}
          disabled={busy}
          className="p-0.5 text-helm-muted transition-colors hover:text-helm-fg disabled:opacity-50"
          aria-label="Hide the Get started list"
          title="Hide"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
      <div className="mt-3 h-1 overflow-hidden rounded-full bg-helm-line" aria-hidden>
        <div className="h-full rounded-full bg-helm-gold transition-all" style={{ width: `${pct}%` }} />
      </div>
      <ul className="mt-4 divide-y divide-helm-line border-y border-helm-line">
        {steps.map((s) => {
          const isNext = next && s.id === next.id;
          return (
            <li key={s.id} className="flex items-center gap-3 py-3" data-testid={`setup-${s.id}`}>
              <span
                className={cn(
                  "flex h-5 w-5 shrink-0 items-center justify-center rounded-full border",
                  s.done ? "border-helm-gold bg-helm-gold text-helm-navy" : "border-helm-line",
                )}
                aria-hidden
              >
                {s.done ? <Check className="h-3 w-3" strokeWidth={3} /> : null}
              </span>
              <div className="min-w-0 flex-1">
                <p className={cn("text-sm", s.done ? "text-helm-muted line-through decoration-helm-muted/50" : "text-helm-fg")}>
                  {s.label}
                </p>
                {!s.done && s.hint ? <p className="mt-0.5 text-xs text-helm-muted">{s.hint}</p> : null}
              </div>
              {!s.done && (
                <button
                  type="button"
                  onClick={() => onShow(s)}
                  data-testid={`setup-show-${s.id}`}
                  className={cn(
                    "inline-flex shrink-0 items-center gap-1.5 rounded-md px-3 py-1.5 text-sm transition-colors",
                    isNext
                      ? "bg-helm-gold font-medium text-helm-navy hover:bg-helm-gold-hover"
                      : "border border-helm-line text-helm-fg hover:bg-helm-fg/[0.04]",
                  )}
                >
                  <Compass className="h-3.5 w-3.5" /> Show me
                </button>
              )}
            </li>
          );
        })}
      </ul>
      <p className="mt-3 text-xs text-helm-muted">
        Each step takes a minute or two. Press Show me and Trenston points at exactly what to click.
      </p>
    </section>
  );
}

export default function GetStarted() {
  const { data, reload, setData } = useFetch("/onboarding/checklist");
  const { startTour, setChecklistShowing } = useGuides();
  const [busy, setBusy] = useState(false);
  const showing = Boolean(data && Array.isArray(data.steps) && !data.complete && !data.dismissed);

  // While this list is up, it is the way in, so the page's own welcome card stays out of the way.
  useEffect(() => {
    setChecklistShowing(showing);
    return () => setChecklistShowing(false);
  }, [showing, setChecklistShowing]);

  useEffect(() => {
    const onChange = () => reload();
    window.addEventListener(GUIDES_CHANGED_EVENT, onChange);
    return () => window.removeEventListener(GUIDES_CHANGED_EVENT, onChange);
  }, [reload]);

  if (!showing) return null;

  const hide = async () => {
    if (busy) return;
    setBusy(true);
    try {
      await api.post("/onboarding/checklist/dismiss");
      setData((prev) => (prev ? { ...prev, dismissed: true } : prev));
      toast.success("Hidden. Press ? at the top of any page whenever you need help.");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not hide the list");
    } finally {
      setBusy(false);
    }
  };

  return (
    <GetStartedView
      checklist={data}
      busy={busy}
      onHide={hide}
      onShow={(s) => startTour(s.tour, { route: s.route })}
    />
  );
}
