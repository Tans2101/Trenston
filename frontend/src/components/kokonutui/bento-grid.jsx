/**
 * @author: @dorianbaffier / Trenston
 * @description: Bento Grid — Trenston metrics layout (KokonutUI, restyled)
 * @website: https://kokonutui.com
 */

import { motion, useReducedMotion } from "motion/react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Plus } from "lucide-react";
import { Delta } from "@/components/kit";
import { cn } from "@/lib/utils";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

/**
 * Status-dot semantics (single system for every metric card):
 *   healthy   (green) — tracked and OK
 *   attention (amber) — tracked, needs a look
 *   alert     (red)   — tracked, critical / out of range
 *   empty     (gray)  — not tracked / no data yet
 */
const STATUS = {
  healthy: {
    id: "healthy",
    label: "Healthy",
    hint: "Tracked and within range",
    className: "bg-helm-status-positive",
  },
  attention: {
    id: "attention",
    label: "Needs attention",
    hint: "Tracked, but something needs a look",
    className: "bg-helm-status-warning",
  },
  alert: {
    id: "alert",
    label: "Alert",
    hint: "Tracked and critical / out of range",
    className: "bg-helm-status-negative",
  },
  empty: {
    id: "empty",
    label: "Not tracked",
    hint: "No data logged yet",
    className: "bg-helm-muted",
  },
};

/** Fixed Briefing section order — only sections with tiles are rendered. */
const SECTION_ORDER = ["finance", "procurement", "production", "sales", "maintenance"];
const SECTION_LABELS = {
  finance: "Finance",
  procurement: "Procurement",
  production: "Production",
  sales: "Sales",
  maintenance: "Maintenance",
};

function resolveStatus(m) {
  if (m?.missing) return STATUS.empty;
  const tone = m?.tone || "neutral";
  if (tone === "negative" || tone === "alert") return STATUS.alert;
  if (tone === "warning" || tone === "attention") return STATUS.attention;
  if (tone === "positive") return STATUS.healthy;
  // Tracked with a neutral tone — still “has data”, not an empty state
  return STATUS.healthy;
}

/** Parse a display value like "$248K", "17 months", "12.5%" into animatable parts. */
function parseMetricValue(raw) {
  if (raw == null) return { prefix: "", number: null, suffix: "", fallback: "—" };
  const str = String(raw);
  const match = str.match(/^([^\d-]*)(-?\d+(?:\.\d+)?)(.*)$/);
  if (!match) return { prefix: "", number: null, suffix: "", fallback: str };
  return {
    prefix: match[1],
    number: Number(match[2]),
    suffix: match[3],
    fallback: str,
  };
}

function AnimatedMetricValue({ value, missing, className }) {
  const reduceMotion = useReducedMotion();
  const parsed = useMemo(() => parseMetricValue(value), [value]);
  const [display, setDisplay] = useState(() =>
    reduceMotion || parsed.number == null ? parsed.fallback : `${parsed.prefix}0${parsed.suffix}`
  );

  useEffect(() => {
    if (reduceMotion || parsed.number == null) {
      setDisplay(parsed.fallback);
      return undefined;
    }

    const start = 0;
    const end = parsed.number;
    const duration = 900;
    const frameRate = 1000 / 60;
    const totalFrames = Math.max(1, Math.round(duration / frameRate));
    let frame = 0;
    const decimals = String(end).includes(".") ? Math.min(2, (String(end).split(".")[1] || "").length) : 0;

    const id = setInterval(() => {
      frame += 1;
      const progress = Math.min(1, frame / totalFrames);
      const eased = 1 - (1 - progress) ** 3;
      const current = start + (end - start) * eased;
      const formatted = decimals > 0 ? current.toFixed(decimals) : String(Math.round(current));
      setDisplay(`${parsed.prefix}${formatted}${parsed.suffix}`);
      if (frame >= totalFrames) clearInterval(id);
    }, frameRate);

    return () => clearInterval(id);
  }, [parsed, reduceMotion, value]);

  return (
    <span className={cn("tabular-nums tracking-tight", missing ? "text-helm-muted" : "text-helm-fg", className)}>
      {display}
    </span>
  );
}

function StatusDot({ status }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          className={cn("w-1.5 h-1.5 rounded-full shrink-0", status.className)}
          aria-label={status.label}
          data-testid={`metric-status-${status.id}`}
        />
      </TooltipTrigger>
      <TooltipContent
        side="top"
        className="max-w-[14rem] border border-helm-line bg-helm-card text-helm-fg shadow-md"
      >
        <p className="font-medium">{status.label}</p>
        <p className="text-helm-muted mt-0.5 font-sans normal-case tracking-normal">{status.hint}</p>
      </TooltipContent>
    </Tooltip>
  );
}

function StatusLegend() {
  return (
    <div
      className="mb-4 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-[10px] font-mono uppercase tracking-wider text-helm-muted"
      data-testid="briefing-status-legend"
    >
      <span className="tracking-[0.14em]">Status</span>
      {Object.values(STATUS).map((s) => (
        <span key={s.id} className="inline-flex items-center gap-1.5 normal-case tracking-normal font-sans text-xs text-helm-muted">
          <span className={cn("w-1.5 h-1.5 rounded-full", s.className)} aria-hidden />
          {s.label}
        </span>
      ))}
    </div>
  );
}

function cardWidthClass(total) {
  // Size to actual count — avoid a sparse 2-of-4 empty column look.
  if (total <= 1) return "w-full max-w-xs";
  if (total === 2) return "w-full sm:w-[calc(50%-0.375rem)] max-w-sm";
  if (total === 3) return "w-full sm:w-[calc(50%-0.375rem)] lg:w-[calc(33.333%-0.5rem)] max-w-sm";
  return "w-full sm:w-[calc(50%-0.375rem)] lg:w-[calc(25%-0.5625rem)] max-w-sm";
}

function groupMetricsBySection(metrics) {
  const buckets = new Map();
  for (const m of metrics) {
    const key = SECTION_ORDER.includes(m?.section) ? m.section : "finance";
    if (!buckets.has(key)) buckets.set(key, []);
    buckets.get(key).push(m);
  }
  return SECTION_ORDER
    .filter((key) => (buckets.get(key) || []).length > 0)
    .map((key) => ({
      key,
      label: SECTION_LABELS[key] || key,
      metrics: buckets.get(key),
    }));
}

function MetricTile({ m, index, total }) {
  const navigate = useNavigate();
  const clickable = Boolean(m.href && m.missing);
  const status = resolveStatus(m);
  const hasDelta = m.delta != null && m.delta !== 0;
  const surfaceClass = cn(
    "rounded-xl border border-helm-line bg-helm-card p-4 text-left w-full h-full shadow-sm",
    index === 0 && total >= 3 && "md:p-5",
    clickable && "cursor-pointer transition-colors hover:border-helm-gold/40 hover:bg-helm-fg/[0.02] focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-helm-gold",
  );

  const body = (
    <>
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs uppercase tracking-wider text-helm-muted font-mono truncate">{m.label}</span>
        <StatusDot status={status} />
      </div>
      <div className={cn("mt-3 flex items-end justify-between gap-2", index === 0 && total >= 3 && "mt-4")}>
        {clickable ? (
          <span className="flex flex-col items-start gap-2 min-w-0">
            <span className="text-sm text-helm-muted">{m.value || "No data"}</span>
            <span className="inline-flex items-center gap-1 rounded-md border border-dashed border-helm-gold/40 bg-helm-gold/10 px-2 py-1 text-[11px] font-medium text-helm-gold">
              <Plus className="w-3 h-3" aria-hidden />
              Add
            </span>
          </span>
        ) : (
          <AnimatedMetricValue
            value={m.value}
            missing={m.missing}
            className={index === 0 && total >= 3 ? "text-3xl md:text-4xl" : "text-2xl md:text-3xl"}
          />
        )}
        {hasDelta ? <Delta value={m.delta} tone={m.tone} /> : null}
      </div>
    </>
  );

  return clickable ? (
    <button
      type="button"
      className={surfaceClass}
      onClick={() => navigate(m.href)}
      aria-label={`Add ${m.label} data`}
    >
      {body}
    </button>
  ) : (
    <div className={surfaceClass}>{body}</div>
  );
}

/**
 * Trenston briefing metrics bento — driven entirely by `metrics` from the briefing API.
 * Missing metrics with `href` are clickable and navigate to where data can be added.
 * Cards with a `section` field render under uppercase department labels in fixed order.
 */
export default function BentoGrid({ metrics = [], className }) {
  const reduceMotion = useReducedMotion();
  const list = useMemo(
    () => (Array.isArray(metrics) ? metrics : []),
    [metrics],
  );
  const groups = useMemo(() => groupMetricsBySection(list), [list]);
  if (list.length === 0) return null;

  return (
    <TooltipProvider delayDuration={200}>
      <div className={cn("mb-6 space-y-0", className)} data-testid="briefing-metrics-grouped">
        <StatusLegend />
        {groups.map((group, groupIndex) => (
          <section
            key={group.key}
            data-testid={`briefing-metrics-section-${group.key}`}
            className={cn(
              "py-6",
              groupIndex > 0 && "border-t border-helm-fg/20",
            )}
          >
            <h2 className="text-[11px] font-mono uppercase tracking-[0.2em] text-helm-muted mb-3">
              {group.label}
            </h2>
            <motion.div
              className="flex flex-wrap gap-3 md:gap-4"
              initial={reduceMotion ? false : "hidden"}
              animate="visible"
              variants={{
                hidden: { opacity: 0 },
                visible: {
                  opacity: 1,
                  transition: { staggerChildren: reduceMotion ? 0 : 0.08 },
                },
              }}
            >
              {group.metrics.map((m, i) => (
                <motion.div
                  key={`${group.key}-${m.label || i}`}
                  data-testid={`briefing-metric-${group.key}-${i}`}
                  className={cardWidthClass(group.metrics.length)}
                  variants={{
                    hidden: { opacity: 0, y: reduceMotion ? 0 : 12 },
                    visible: {
                      opacity: 1,
                      y: 0,
                      transition: { duration: reduceMotion ? 0 : 0.4, ease: [0.16, 1, 0.3, 1] },
                    },
                  }}
                >
                  <MetricTile m={m} index={i} total={group.metrics.length} />
                </motion.div>
              ))}
            </motion.div>
          </section>
        ))}
      </div>
    </TooltipProvider>
  );
}
