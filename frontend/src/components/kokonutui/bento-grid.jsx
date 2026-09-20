/**
 * @author: @dorianbaffier / Trenston
 * @description: Bento Grid — Trenston metrics layout (KokonutUI, restyled)
 * @website: https://kokonutui.com
 */

import { motion, useReducedMotion } from "motion/react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Delta } from "@/components/kit";
import { cn } from "@/lib/utils";

const toneDot = {
  positive: "bg-helm-status-positive",
  negative: "bg-helm-status-negative",
  neutral: "bg-helm-muted",
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

function cellClass(index, total) {
  // Equal tiles — keep finance KPIs side-by-side at one height.
  return "col-span-1";
}

function gridClass(total) {
  if (total === 1) return "grid-cols-1 max-w-xs";
  if (total === 2) return "grid-cols-2 max-w-xl";
  if (total === 3) return "grid-cols-1 sm:grid-cols-3";
  return "grid-cols-2 lg:grid-cols-4";
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
  const surfaceClass = cn(
    "rounded-xl border border-helm-line bg-helm-card p-4 text-left w-full h-full",
    index === 0 && total >= 3 && "md:p-5",
    clickable && "cursor-pointer transition-colors hover:border-helm-gold/40 hover:bg-helm-fg/[0.02] focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-helm-gold",
  );
  const body = (
    <>
      <div className="flex items-center justify-between">
        <span className="text-xs uppercase tracking-wider text-helm-muted font-mono">{m.label}</span>
        <span className={cn("w-1.5 h-1.5 rounded-full", toneDot[m.tone] || toneDot.neutral)} />
      </div>
      <div className={cn("mt-3 flex items-end justify-between gap-2", index === 0 && total >= 3 && "mt-4")}>
        <AnimatedMetricValue
          value={m.value}
          missing={m.missing}
          className={cn(
            index === 0 && total >= 3 ? "text-3xl md:text-4xl" : "text-2xl md:text-3xl",
            clickable && "underline decoration-helm-muted/40 underline-offset-4",
          )}
        />
        <Delta value={m.delta} tone={m.tone} />
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
    <div className={cn("mb-6 space-y-6", className)} data-testid="briefing-metrics-grouped">
      {groups.map((group) => (
        <section key={group.key} data-testid={`briefing-metrics-section-${group.key}`}>
          <h2 className="text-[11px] font-mono uppercase tracking-[0.2em] text-helm-muted mb-3">
            {group.label}
          </h2>
          <motion.div
            className={cn("grid gap-3 md:gap-4", gridClass(group.metrics.length))}
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
                className={cellClass(i, group.metrics.length)}
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
  );
}
