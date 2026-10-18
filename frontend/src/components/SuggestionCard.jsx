import { Link } from "react-router-dom";
import { Check, X, Sparkles, ArrowUpRight } from "lucide-react";
import { motion, useReducedMotion } from "motion/react";
import { MetaLine } from "@/components/DecisionCard";
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

  const meta = [
    s.category && s.category !== "General" ? s.category : null,
    s.impact ? `${s.impact} impact` : null,
    s.confidence != null && s.confidence !== "" && !s.confidence_unavailable ? `${s.confidence}% AI estimate` : null,
  ];

  return (
    <motion.div
      layout
      initial={false}
      exit={reduceMotion ? { opacity: 0 } : { opacity: 0, height: 0, overflow: "hidden" }}
      transition={LIST_MOTION}
      className="dec-row border-b border-helm-line"
      data-testid={`suggestion-${s.id}`}
      data-deeplink={s.id}
    >
      <div className="flex items-start gap-3 px-1 py-4 sm:px-3">
        <Sparkles className="mt-[3px] h-3.5 w-3.5 shrink-0 dec-spark" aria-hidden />
        <div className="flex min-w-0 flex-1 flex-col gap-3 sm:flex-row sm:items-start">
        <div className="min-w-0 flex-1">
          <h3 className="text-[15px] font-medium leading-snug tracking-tight text-helm-fg">{s.title}</h3>
          <MetaLine parts={meta} />
          {s.description && <p className="mt-1.5 text-[13px] leading-relaxed text-helm-muted">{s.description}</p>}
          {s.recommendation && (
            <p className="mt-1.5 text-[13px] leading-relaxed text-helm-fg/85">
              <span className="text-helm-muted">Trenston suggests: </span>
              {s.recommendation}
            </p>
          )}
          <ForecastDetails signal={s.signal} id={s.id} />
          {source?.to && (
            <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1">
              <Link
                to={source.to}
                data-testid={`suggestion-source-${s.id}`}
                className="inline-flex items-center gap-1 text-[13px] font-medium text-helm-fg hover:underline underline-offset-4"
              >
                {source.label || "Open source"} <ArrowUpRight className="h-3.5 w-3.5" />
              </Link>
              {isLeave && (
                <span className="text-[11px] text-helm-muted">Accepting logs the decision only. Approve the leave itself in HR.</span>
              )}
            </div>
          )}
          <p className="mt-2 text-[11px] text-helm-muted">Drafted by Trenston from your data. Check it before you accept.</p>
        </div>
        {canAct && (
          <div className="flex shrink-0 items-center gap-1">
            <button
              type="button"
              data-testid={`approve-suggestion-${s.id}`}
              disabled={busy === s.id}
              onClick={() => onAcceptSuggestion(s.id)}
              className="app-btn-secondary inline-flex h-8 items-center gap-1.5 px-3 text-[13px] font-medium disabled:opacity-50"
            >
              <Check className="h-3.5 w-3.5" /> Accept
            </button>
            <button
              type="button"
              data-testid={`dismiss-suggestion-${s.id}`}
              disabled={busy === s.id}
              onClick={() => onDismissSuggestion(s.id)}
              aria-label={`Dismiss ${s.title}`}
              title="Dismiss"
              className="inline-flex h-8 w-8 items-center justify-center text-helm-muted hover:bg-helm-fg/5 hover:text-helm-fg disabled:opacity-50"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        )}
        </div>
      </div>
    </motion.div>
  );
}
