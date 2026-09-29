import { Link } from "react-router-dom";
import { Check, X, Sparkles, ArrowUpRight } from "lucide-react";
import { motion, useReducedMotion } from "motion/react";
import { GlassCard } from "@/components/kit";
import { ConfidenceBadge } from "@/components/DecisionCard";
import { signalRoute } from "@/lib/signalRoute";

const LIST_MOTION = { duration: 0.22, ease: [0.4, 0, 0.2, 1] };

const CONFIDENCE_LABEL = { high: "High", medium: "Medium", low: "Low" };

function fmtValue(v) {
  if (v === null || v === undefined || v === "") return null;
  const n = Number(v);
  if (!Number.isFinite(n)) return String(v);
  return Math.abs(n) >= 1000 ? Math.round(n).toLocaleString() : String(Math.round(n * 10) / 10);
}

/** Inputs behind a predictive alert, so the founder can check the maths. */
function ForecastDetails({ signal, id }) {
  const f = signal?.forecast;
  if (!f || typeof f !== "object") return null;
  const rows = [
    ["Measured", f.metric],
    ["Period", f.window],
    ["Now", fmtValue(f.current_value)],
    ["Compared with", fmtValue(f.prior_value)],
    ["Minimum reserve", fmtValue(f.reserve)],
    ["Projected date", f.projected_date],
    ["Confidence", f.confidence ? `${CONFIDENCE_LABEL[f.confidence] || f.confidence} (${f.data_points ?? 0} data points)` : null],
  ].filter(([, v]) => v !== null && v !== undefined && v !== "");
  return (
    <details className="mt-3 group" data-testid={`forecast-details-${id}`}>
      <summary className="cursor-pointer list-none text-xs text-helm-muted hover:text-helm-fg">
        How this was worked out
      </summary>
      <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-xs">
        {rows.map(([k, v]) => (
          <div key={k} className="contents">
            <dt className="text-helm-muted">{k}</dt>
            <dd className="text-helm-fg tabular-nums">{v}</dd>
          </div>
        ))}
      </dl>
      {signal.what_would_change ? (
        <p className="mt-2 text-xs text-helm-muted"><span className="text-helm-fg">What would change this: </span>{signal.what_would_change}</p>
      ) : null}
      <p className="mt-2 text-[11px] text-helm-muted">A projection from your recorded data, not a certainty.</p>
    </details>
  );
}

export default function SuggestionCard({
  s,
  canAct,
  busy,
  onAcceptSuggestion,
  onDismissSuggestion,
}) {
  const reduceMotion = useReducedMotion();
  const source = signalRoute(s.signal);
  const isLeave = (s.signal?.type || s.signal?.signal_type) === "pending_leave_request";

  return (
    <motion.div
      layout
      initial={false}
      exit={reduceMotion ? { opacity: 0 } : { opacity: 0, height: 0, marginBottom: 0, overflow: "hidden" }}
      transition={LIST_MOTION}
      className="overflow-hidden"
    >
    <GlassCard className="p-5 fade-up border-helm-status-warning/35" data-testid={`suggestion-${s.id}`} data-deeplink={s.id}>
      <div className="flex flex-col lg:flex-row lg:items-start gap-5">
        <div className="flex-1">
          <div className="flex items-center gap-2 flex-wrap mb-2">
            <span className="text-[10px] font-mono uppercase tracking-wider text-helm-status-warning border border-helm-status-warning/35 rounded px-1.5 py-0.5">
              AI Suggested: verify before acting
            </span>
            <span className="text-[10px] font-mono uppercase tracking-wider text-helm-muted border border-helm-line rounded px-1.5 py-0.5">{s.category}</span>
            <span className="text-[10px] font-mono text-helm-muted">Impact: {s.impact}</span>
          </div>
          <h3 className="text-lg text-helm-fg font-medium tracking-tight">{s.title}</h3>
          {s.description && <p className="text-sm text-helm-muted mt-1">{s.description}</p>}
          <ForecastDetails signal={s.signal} id={s.id} />
          {source?.to && (
            <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1">
              <Link
                to={source.to}
                data-testid={`suggestion-source-${s.id}`}
                className="inline-flex items-center gap-1 text-xs text-helm-gold hover:text-helm-gold-hover font-medium"
              >
                {source.label || "Open source"} <ArrowUpRight className="w-3.5 h-3.5" />
              </Link>
              {isLeave && (
                <span className="text-[11px] text-helm-muted">Accepting logs the decision only. Approve the leave itself in HR.</span>
              )}
            </div>
          )}
          {s.recommendation && (
            <div className="mt-4 rounded-lg border border-helm-line border-l-2 border-l-helm-status-warning/70 bg-helm-card p-3">
              <div className="flex items-center gap-1.5 mb-1.5">
                <Sparkles className="w-3.5 h-3.5 text-helm-status-warning" />
                <span className="text-[11px] font-mono uppercase tracking-wider text-helm-status-warning">Trenston recommendation</span>
                <ConfidenceBadge
                  confidence={s.confidence}
                  confidenceUnavailable={s.confidence_unavailable}
                  ai
                />
              </div>
              <p className="text-sm text-helm-fg leading-relaxed">{s.recommendation}</p>
              {s.confidence != null && !s.confidence_unavailable && (
                <div className="mt-2 h-1 rounded-full bg-helm-fg/5 overflow-hidden">
                  <div className="h-full bg-helm-status-warning/70 rounded-full" style={{ width: `${s.confidence}%` }} />
                </div>
              )}
            </div>
          )}
        </div>
        {canAct && (
          <div className="flex lg:flex-col gap-2 lg:w-40">
            <button
              data-testid={`approve-suggestion-${s.id}`}
              disabled={busy === s.id}
              onClick={() => onAcceptSuggestion(s.id)}
              className="flex-1 inline-flex items-center justify-center gap-1.5 rounded-md bg-helm-gold text-helm-navy text-sm font-medium py-2 hover:bg-helm-gold-hover disabled:opacity-50"
            >
              <Check className="w-4 h-4" /> Accept
            </button>
            <button
              data-testid={`dismiss-suggestion-${s.id}`}
              disabled={busy === s.id}
              onClick={() => onDismissSuggestion(s.id)}
              className="flex-1 inline-flex items-center justify-center gap-1.5 rounded-md border border-helm-line text-helm-muted text-sm py-2 hover:bg-helm-fg/5 hover:text-helm-status-negative disabled:opacity-50"
            >
              <X className="w-4 h-4" /> Dismiss
            </button>
          </div>
        )}
      </div>
    </GlassCard>
    </motion.div>
  );
}
