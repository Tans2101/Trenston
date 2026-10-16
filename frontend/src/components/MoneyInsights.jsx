import { useCallback, useEffect, useState } from "react";
import { Sparkles } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { GlassCard, SectionLabel } from "@/components/kit";

const SECTIONS = [
  { key: "making_money", title: "What's making money", testId: "insight-making-money" },
  { key: "losing_money", title: "What's losing money", testId: "insight-losing-money" },
  { key: "why_it_matters", title: "Why this matters", testId: "insight-why-it-matters" },
];

const MAINTENANCE_FALLBACK = "AI summaries are under maintenance. Please try again later.";

/** The server sends {reason: "maintenance", message} when the AI is unavailable. */
export function insightErrorState(err) {
  const detail = err?.response?.data?.detail;
  if (err?.response?.status === 503 || detail?.reason === "maintenance") {
    return { kind: "maintenance", message: detail?.message || MAINTENANCE_FALLBACK };
  }
  if (typeof detail === "string" && detail) return { kind: "error", message: detail };
  return { kind: "error", message: "Could not write the summary. Please try again." };
}

/**
 * Three separate cards on Financials: what makes money, what loses money, why it
 * matters. The numbers come from the ledger; the AI only words them. Refreshing
 * with unchanged data costs nothing (the server returns the saved summary).
 */
export default function MoneyInsights({ canGenerate = true }) {
  const [insight, setInsight] = useState(null);
  const [allowed, setAllowed] = useState(true);
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState(null);

  useEffect(() => {
    let cancelled = false;
    api.get("/financials/insights")
      .then(({ data }) => {
        if (cancelled) return;
        setInsight(data.insight || null);
        setAllowed(data.allowed !== false);
      })
      .catch(() => {})
      .finally(() => { if (!cancelled) setLoaded(true); });
    return () => { cancelled = true; };
  }, []);

  const generate = useCallback(async () => {
    setBusy(true);
    setProblem(null);
    try {
      const { data } = await api.post("/financials/insights", {}, { timeout: 45000 });
      setInsight(data.insight);
      if (data.insight?.cached) toast.success("Already up to date. Nothing has changed since the last summary.");
    } catch (err) {
      const state = insightErrorState(err);
      setProblem(state);
      if (state.kind === "error") toast.error(state.message);
    } finally {
      setBusy(false);
    }
  }, []);

  const canWrite = allowed && canGenerate;
  // People who can't write a summary still see one that was already written.
  if (!loaded || (!canWrite && !insight)) return null;

  const sections = insight?.sections;
  const periodLabel = insight ? `${insight.period_label}${insight.month_so_far ? " so far" : ""}` : "";

  return (
    <section className="mb-10 fade-up" aria-labelledby="fin-insights-heading" data-testid="money-insights">
      <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
        <SectionLabel><span id="fin-insights-heading">Money summary</span></SectionLabel>
        <div className="flex items-center gap-3">
          {insight && (
            <p className="text-xs text-helm-muted" data-testid="insight-meta">
              AI summary of {periodLabel}. Check the figures in the tables below.
            </p>
          )}
          {canWrite && (
          <button
            type="button"
            onClick={generate}
            disabled={busy}
            data-testid="insight-generate"
            className="inline-flex items-center gap-1.5 rounded-md border border-helm-line px-3 py-1.5 text-xs text-helm-fg transition-colors hover:border-helm-gold/60 disabled:opacity-60"
          >
            <Sparkles className="h-3.5 w-3.5 text-helm-gold" aria-hidden />
            {busy ? "Writing" : insight ? "Refresh" : "Write summary"}
          </button>
          )}
        </div>
      </div>

      {problem?.kind === "maintenance" && (
        <GlassCard className="mb-4 border-helm-status-warning/35 p-5" data-testid="insight-maintenance" role="status">
          <p className="text-sm text-helm-fg">{problem.message}</p>
        </GlassCard>
      )}

      {sections ? (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          {SECTIONS.map((s) => (
            <GlassCard key={s.key} className="p-5" data-testid={s.testId}>
              <SectionLabel>{s.title}</SectionLabel>
              <p className="mt-3 text-base leading-relaxed text-helm-fg">{sections[s.key]}</p>
            </GlassCard>
          ))}
        </div>
      ) : (
        !problem && (
          <GlassCard className="p-5" data-testid="insight-empty">
            <p className="text-sm text-helm-muted">
              Get a short read on what is earning, what is costing you, and what it means for your cash.
              Press Write summary to create it from your latest month.
            </p>
          </GlassCard>
        )
      )}
    </section>
  );
}
